"""AI 레시피 제안(스펙 7절)과 AI 사용량. AI 호출 한도·기록 흐름은 scan.py의 함수를 같이 쓴다."""

from flask import Blueprint, abort, current_app, g, jsonify

from . import ai, scan
from .auth import login_required
from .matching import normalize, tokens
from .models import PublicRecipe, db
from .recipe_parse import MAX_AMOUNT, MAX_NAME, MAX_STEP, ingredient_key
from .recipes import MAX_INGREDIENTS, MAX_STEPS, annotate, inventory

bp = Blueprint("recipe_ai", __name__, url_prefix="/api")

MAX_TITLE = 60
MAX_SUGGESTIONS = 3
FAIL = "레시피를 만들지 못했어요. 잠시 후 다시 시도해주세요."


def _int_in(value, low, high):
    return value if isinstance(value, int) and not isinstance(value, bool) and low <= value <= high else None


def clean_draft(raw):
    """AI(또는 예시) 레시피 한 개를 저장 폼에 넣을 수 있게 정리한다. 모델 출력은 믿지 않는다. 쓸 수 없으면 None."""
    if not isinstance(raw, dict) or not isinstance(raw.get("title"), str):
        return None
    title = raw["title"].strip()[:MAX_TITLE].strip()
    ingredients, seen = [], set()
    for row in raw.get("ingredients") if isinstance(raw.get("ingredients"), list) else []:
        name = row.get("name") if isinstance(row, dict) else None
        name = name.strip()[:MAX_NAME].strip() if isinstance(name, str) else ""
        if not name or normalize(name) in seen:
            continue
        seen.add(normalize(name))
        amount = row.get("amount")
        ingredients.append({"name": name, "amount": amount.strip()[:MAX_AMOUNT].strip() if isinstance(amount, str) else ""})
        if len(ingredients) == MAX_INGREDIENTS:
            break
    if not title or not ingredients:
        return None
    steps = [s.strip()[:MAX_STEP] for s in raw.get("steps") if isinstance(s, str) and s.strip()] if isinstance(raw.get("steps"), list) else []
    draft = {
        "title": title,
        "servings": _int_in(raw.get("servings"), 1, 20) or 2,
        "ingredients": ingredients,
        "steps": steps[:MAX_STEPS],
    }
    if "minutes" in raw:
        draft["minutes"] = _int_in(raw["minutes"], 1, 300)
    return draft


def public_image_candidates():
    """사진이 있는 공공 레시피 [(id, 정규화 이름, 2자 이상 토큰, 사진 주소)]. 요청마다 한 번만 만든다(약 1,100건)."""
    rows = (
        db.session.query(PublicRecipe.id, PublicRecipe.title, PublicRecipe.image_url)
        .filter(PublicRecipe.image_url.isnot(None), PublicRecipe.image_url != "")
        .order_by(PublicRecipe.id)
    )
    return [(r.id, normalize(r.title), {t for t in tokens(r.title) if len(t) >= 2}, r.image_url) for r in rows]


def similar_public_image(title, candidates):
    """이름이 가장 비슷한 공공 레시피 사진. 같음 → 포함(짧은 쪽 3자 이상, 길이 차 작은 것) → 토큰 Jaccard 0.5 이상(높은 것).
    같은 점수면 id가 작은 것(candidates는 id 순).
    ponytail: 규칙 기반. 엉뚱한 사진이 자주 붙으면 임계값을 올리거나 사진 없이 둔다."""
    norm = normalize(title)
    words = {t for t in tokens(title) if len(t) >= 2}
    if not norm:
        return None
    best = None
    for _, other, other_words, image_url in candidates:
        if other == norm:
            return image_url  # 가장 좋은 점수, id 순이라 처음 것이 이긴다
        if min(len(norm), len(other)) >= 3 and (norm in other or other in norm):
            score = (1, abs(len(norm) - len(other)))
        else:
            union = words | other_words
            jaccard = len(words & other_words) / len(union) if union else 0
            if jaccard < 0.5:
                continue
            score = (2, -jaccard)
        if best is None or score < best[0]:
            best = (score, image_url)
    return best[1] if best else None


@bp.post("/recommendations/ai")
@login_required
def ai_recipes():
    """지금 재고로 레시피 3개를 만든다(저장하지 않는다). 저장은 화면이 POST /api/recipes(source ai)로 한다."""
    stock = inventory(g.user.id)
    if not stock:
        abort(400, "재고에 재료를 먼저 추가해주세요.")
    mode = ai.scan_mode()
    if mode == "off":
        abort(503, "AI 레시피를 지금은 쓸 수 없어요.")
    if mode == "sample":
        raw = {"recipes": ai.SAMPLE_SUGGESTIONS}
    else:
        scan.check_ai_limits(g.user.id, scan.RECIPE_KINDS, current_app.config["AI_DAILY_RECIPE_LIMIT"], "AI 레시피는")
        call = scan.start_ai_call(g.user.id, "recipe")
        try:
            raw, usage = ai.suggest_recipes([f"{name} (빨리)" if urgent else name for name, urgent in stock])
        except ai.AiError:
            abort(502, FAIL)
        scan.finish_ai_call(call, usage)

    rows = raw.get("recipes") if isinstance(raw, dict) and isinstance(raw.get("recipes"), list) else []
    drafts = [d for d in map(clean_draft, rows) if d][:MAX_SUGGESTIONS]
    if not drafts:
        abort(502, FAIL)

    urgent = {name for name, is_urgent in stock if is_urgent}
    candidates = public_image_candidates()
    recipes = []
    for draft in drafts:
        ingredients = annotate(draft["ingredients"], [ingredient_key(i["name"]) for i in draft["ingredients"]], stock)
        urgent_names = list(dict.fromkeys(i["matched_name"] for i in ingredients if i["matched_name"] in urgent))
        recipes.append(
            {
                **draft,
                "minutes": draft.get("minutes"),
                "ingredients": ingredients,
                "urgent_names": urgent_names,
                "image_url": similar_public_image(draft["title"], candidates),
            }
        )
    used = {name for recipe in recipes for name in recipe["urgent_names"]}
    urgent_first = list(dict.fromkeys(name for name, _ in stock if name in used))  # 재고 임박 순
    return jsonify(recipes=recipes, urgent_first=urgent_first, sample=mode == "sample")


@bp.get("/ai-usage")
@login_required
def ai_usage():
    """오늘(서울 날짜) 쓴 횟수와 한도. 화면의 `오늘 N번 남음`은 recipe.limit - recipe.used."""
    config = current_app.config
    return jsonify(
        scan={"used": scan.calls_today(g.user.id, scan.SCAN_KINDS), "limit": config["AI_DAILY_SCAN_LIMIT"]},
        recipe={"used": scan.calls_today(g.user.id, scan.RECIPE_KINDS), "limit": config["AI_DAILY_RECIPE_LIMIT"]},
    )
