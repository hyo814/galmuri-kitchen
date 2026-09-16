"""AI 레시피 제안(스펙 7절), 링크·글·사진으로 레시피 가져오기(스펙 17절), AI 사용량. AI 호출 한도·기록 흐름은 scan.py의 함수를 같이 쓴다."""

import re

from flask import Blueprint, abort, current_app, g, jsonify, request

from . import ai, outbound, scan
from .auth import ai_daily_limit, get_owned_or_404, login_required
from .matching import normalize, tokens
from .models import AiCall, PublicRecipe, Recipe, db
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
        key = normalize(name) or name  # "(국산)"처럼 괄호뿐인 이름은 정규화하면 비어 버린다
        if not name or key in seen:
            continue
        seen.add(key)
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
    mode = ai.scan_mode(g.user)
    if mode == "off":
        abort(503, "AI 레시피를 지금은 쓸 수 없어요.")
    if mode == "sample":
        raw, call = {"recipes": ai.SAMPLE_SUGGESTIONS}, None
    else:
        scan.check_ai_limits(g.user.id, scan.RECIPE_KINDS, ai_daily_limit(g.user, "AI_DAILY_RECIPE_LIMIT"), "AI 레시피는")
        call = scan.start_ai_call(g.user.id, "recipe")
        try:
            raw, usage = ai.suggest_recipes([f"{name} (빨리)" if urgent else name for name, urgent in stock])
        except ai.AiError:
            scan.miss_ai_call(call)
            abort(502, FAIL)
        scan.finish_ai_call(call, usage)

    rows = raw.get("recipes") if isinstance(raw, dict) and isinstance(raw.get("recipes"), list) else []
    drafts = [d for d in map(clean_draft, rows) if d][:MAX_SUGGESTIONS]
    if not drafts:
        if call:
            scan.miss_ai_call(call)
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


MIN_IMPORT_TEXT = 10
FETCH_BURST_LIMIT = 5  # 링크 가져오기 외부 요청: 60초에 5번
FETCH_DAILY_LIMIT = 50  # 하루(서울 날짜) 50번. AI 한도에 걸리지 않는 실패 요청으로 외부 요청을 남용하지 못하게 한다
NEED_TEXT = {
    "youtube": "유튜브 링크에서는 레시피를 읽지 못했어요. 영상 설명을 복사한 뒤 아래에 붙여 넣어주세요.",
    "instagram": "인스타그램 링크에서는 레시피를 읽지 못했어요. 게시물 설명을 길게 눌러 복사한 뒤 아래에 붙여 넣어주세요.",
    "blog": "이 링크에서는 레시피를 읽지 못했어요. 글을 복사한 뒤 아래에 붙여 넣어주세요.",
    "text": "레시피를 찾지 못했어요. 재료와 만드는 법이 담긴 글을 붙여 넣어주세요.",
}
# 영상 설명·캡션에 레시피 표시(RECIPE_SIGNAL)가 없어 AI를 부르지 않았을 때. 표시 규칙이 놓친 레시피(양배추 1/4통)일 수도 있어 복사도 안내한다
NO_RECIPE = {
    "youtube": "영상 설명에서 레시피를 찾지 못했어요. 설명에 있으면 복사해 붙여 넣고, 영상에만 있으면 보면서 재료와 만드는 법을 아래에 적어주세요.",
    "instagram": "게시물 설명에서 레시피를 찾지 못했어요. 설명에 있으면 길게 눌러 복사해 붙여 넣고, 영상에만 있으면 보면서 재료와 만드는 법을 아래에 적어주세요.",
}


def need_text(source, messages=NEED_TEXT):
    """링크를 못 읽었거나 레시피가 없을 때. 화면은 글 붙여넣기로 바꿔 이 문구를 보여준다."""
    return jsonify(error=messages[source], need_text=True), 422


# 블로그 본문 글에 이 표시가 하나도 없으면 레시피가 사진에만 있는 글로 보고 본문 사진을 함께 읽는다.
# 유튜브 설명·인스타그램 캡션에 없으면 AI를 부르지 않고 글 붙여넣기로 보낸다(NO_RECIPE).
# 숫자와 단위는 같은 줄에서만 본다(꼬리말 "02218\n개인정보"), 단위 뒤에 영문이 붙으면(5GB·5ton) 양이 아니다.
# 2026-09-16 숟가락·숟갈과 숫자 뒤 공기·T·t·ts·tbsp·tsp를 더했다(간장 3T·2숟가락만 적은 영상 설명도 AI가 읽게).
# ponytail: 낱말·단위 규칙이라 "컵케이크"·"1 T-shirt"·"샤오미 13T"(드문 모델 이름)처럼 표시가 섞인 글은 글만 보낸다(영상 설명이면 AI를 부른다).
# 놓치는 글이 많으면 표시 개수 기준으로 바꾸거나 사진 후보가 있을 때 늘 함께 보낸다(비용↑).
RECIPE_SIGNAL = re.compile(
    r"재료|큰술|작은술|스푼|숟가락|숟갈|컵|꼬집|\d[ \t]*(?:g|ml|개|모|대|쪽|공기|tbsp|tsp|ts|t)(?![a-z])", re.I
)

MAX_IMPORT_PHOTOS = 5
PHOTO_NOT_FOUND = "사진에서 레시피를 찾지 못했어요. 글자가 잘 보이게 다시 찍거나 글 붙여넣기를 써주세요."


def import_photos():
    """요리책·캡처·손글씨 레시피 사진 1~5장(multipart `image`)을 AI로 정리한 초안. 사진은 저장하지 않는다.
    업로드 검증(개수·빈 파일·형식)에서 걸린 요청은 세지 않는다. 한도는 AI 레시피와 같은 묶음(recipe_photo)."""
    files = request.files.getlist("image")  # 합쳐서 10MB 초과는 여기서 413
    if len(files) > MAX_IMPORT_PHOTOS:
        abort(400, "사진은 5장까지 올려주세요.")
    images = []
    for file in files:
        data = file.read()
        if not data:
            abort(400, "사진을 올려주세요.")
        media_type = scan.sniff_image_type(data)  # 선언된 Content-Type이 아니라 파일 시그니처를 믿는다
        if media_type is None:
            abort(415, "사진 파일(JPG·PNG·WEBP)만 올릴 수 있어요.")
        images.append((data, media_type))
    if not images:
        abort(400, "사진을 올려주세요.")

    mode = ai.scan_mode(g.user)
    if mode == "off":
        abort(503, "레시피 가져오기를 지금은 쓸 수 없어요.")
    if mode == "sample":
        return jsonify(**clean_draft(ai.SAMPLE_IMPORT), source="photo", source_url=None, source_card=None, sample=True)

    scan.check_ai_limits(g.user.id, scan.RECIPE_KINDS, ai_daily_limit(g.user, "AI_DAILY_RECIPE_LIMIT"), "AI 레시피는")
    call = scan.start_ai_call(g.user.id, "recipe_photo")
    try:
        raw, usage = ai.extract_recipe_from_images(images)
    except ai.AiError:
        scan.miss_ai_call(call)
        abort(502, "레시피를 정리하지 못했어요. 잠시 후 다시 시도해주세요.")
    scan.finish_ai_call(call, usage)
    draft = clean_draft(raw.get("recipe")) if isinstance(raw, dict) and raw.get("found") is True else None
    if draft is None:
        scan.miss_ai_call(call)
        # 글 붙여넣기로 바꾸지 않고 사진 단계에 경고로 보여준다(need_text는 링크·글과 같은 모양으로 둔다)
        return jsonify(error=PHOTO_NOT_FOUND, need_text=True), 422
    return jsonify(**draft, source="photo", source_url=None, source_card=None, sample=False)


@bp.post("/recipes/import")
@login_required
def import_recipe():
    """링크(유튜브 설명란·인스타그램 캡션·블로그 글)나 붙여 넣은 글을 AI로 정리한 초안. 저장하지 않는다(화면이 POST /api/recipes).
    multipart/form-data면 사진으로 가져오기(import_photos)."""
    if request.mimetype == "multipart/form-data":
        return import_photos()
    data = request.get_json(silent=True)
    data = data if isinstance(data, dict) else {}
    url, text = data.get("url"), data.get("text")
    no_url = url is None or (isinstance(url, str) and not url.strip())
    if no_url == (text is None or (isinstance(text, str) and not text.strip())):
        abort(400, "링크나 글을 입력해주세요.")
    source_card = None
    if no_url:
        if not isinstance(text, str) or not MIN_IMPORT_TEXT <= len(text.strip()) <= ai.MAX_IMPORT_TEXT:
            abort(400, "글은 10~10,000자로 붙여 넣어주세요.")
        source, source_url, link = "text", None, None
    else:
        link = outbound.parse_link(url)
        if link is None:
            abort(400, "링크를 다시 확인해주세요. https로 시작하는 주소를 붙여 넣어주세요.")
        kind, value = link
        source, source_url = {
            "youtube": ("youtube", f"https://www.youtube.com/watch?v={value}"),
            "instagram": ("instagram", f"https://www.instagram.com/p/{value}/"),
            "web": ("blog", value),
        }[kind]

    mode = ai.scan_mode(g.user)
    if mode == "off":
        abort(503, "레시피 가져오기를 지금은 쓸 수 없어요.")
    if mode == "sample":
        card = ai.SAMPLE_SOURCE_CARD if link else None
        return jsonify(**clean_draft(ai.SAMPLE_IMPORT), source=source, source_url=source_url, source_card=card, sample=True)

    user_id, limit = g.user.id, ai_daily_limit(g.user, "AI_DAILY_RECIPE_LIMIT")
    youtube_key = current_app.config["YOUTUBE_API_KEY"]
    # 한도에 걸린 요청은 외부 요청도 기록도 하지 않는다. 외부 요청은 따로 기록하고 따로 센다(link_fetch, AI 한도·사용량에는 안 셈).
    # 외부 요청을 기다리는 동안 DB 잠금·연결을 잡지 않게 커밋해 두고, AI를 부르기 직전에 다시 잠그고 세어 같은 트랜잭션에서 기록한다.
    scan.check_ai_limits(user_id, scan.RECIPE_KINDS, limit, "AI 레시피는")
    if link is not None and not (kind == "youtube" and not youtube_key):
        scan.check_ai_limits(user_id, scan.FETCH_KINDS, FETCH_DAILY_LIMIT, "링크 가져오기는", burst=FETCH_BURST_LIMIT)
        db.session.add(AiCall(user_id=user_id, kind="link_fetch", model=None, created_at=scan.utcnow()))
    db.session.commit()

    images = []
    if link is None:
        body = text.strip()
    else:
        # 외부 요청 실패는 AI 한도에 세지 않는다. 사설 주소 같은 이유는 구분해 알려주지 않는다.
        try:
            if kind == "youtube":
                if not youtube_key:  # 자막은 가져오지 않는다(스펙 17절)
                    return need_text(source)
                video = outbound.video_snippet(value, youtube_key)
                if video is None:
                    abort(404, "영상을 찾을 수 없어요. 링크를 다시 확인해주세요.")
                # 쇼츠처럼 레시피가 영상에만 있으면 AI를 불러도 못 찾는다. 제목의 양(계란 2개로…)은 레시피가 아니라 보지 않는다.
                # ponytail: 표시 규칙에 없는 표기로만 적힌 설명 레시피(양배추 1/4통·계란 두 알)도 여기서 글 붙여넣기로 간다.
                # 잦으면 RECIPE_SIGNAL을 늘린다(블로그 본문 사진 보내기 기준도 함께 바뀐다).
                if not RECIPE_SIGNAL.search(video["description"]):
                    return need_text(source, NO_RECIPE)
                body = f"{video['title']}\n\n{video['description']}"
                source_card = {"title": video["title"], "author": video["channel_title"], "thumbnail_url": video["thumbnail_url"]}
            elif kind == "instagram":
                post = outbound.instagram_post(value)
                if post is None:
                    return need_text(source)
                # 릴스처럼 레시피가 영상에만 있거나 미리보기 캡션이 잘렸다.
                # ponytail: 미리보기가 한국어(좋아요 1,234개)로 오면 그 수가 표시로 잡혀 거르지 못하고 예전처럼 AI를 부른다.
                # 서버(싱가포르)는 영어 미리보기를 받는다고 보고 두었다 — 잦으면 좋아요·댓글 수를 떼고 본다.
                if not RECIPE_SIGNAL.search(post["caption"]):
                    return need_text(source, NO_RECIPE)
                body = post["caption"]
                source_card = {"title": post["title"], "author": None, "thumbnail_url": post["thumbnail_url"]}
            else:
                page = outbound.web_page(value)
                body = f"{page['title']}\n\n{page['text']}"
                source_url = page["url"] if len(page["url"]) <= outbound.MAX_LINK else value  # 저장 폼은 500자까지 받는다
                source_card = {"title": page["title"], "author": page["site_name"], "thumbnail_url": None}
                if page["images"] and not RECIPE_SIGNAL.search(page["text"]):  # 사진 요청 실패는 건너뛰고 기록을 더하지 않는다
                    images = outbound.page_images(page["images"])
        except outbound.FetchError as e:
            current_app.logger.warning("import fetch failed: %s", e)  # 예외·이유 이름만(주소·키 없음)
            return need_text(source)
        if len(body.strip()) < MIN_IMPORT_TEXT and not images:
            return need_text(source)

    scan.check_ai_limits(user_id, scan.RECIPE_KINDS, limit, "AI 레시피는")
    call = scan.start_ai_call(user_id, "link")
    try:
        raw, usage = ai.extract_recipe(body, images)
    except ai.AiError:
        scan.miss_ai_call(call)
        abort(502, "레시피를 정리하지 못했어요. 잠시 후 다시 시도해주세요.")
    scan.finish_ai_call(call, usage)
    draft = clean_draft(raw.get("recipe")) if isinstance(raw, dict) and raw.get("found") is True else None
    if draft is None:
        scan.miss_ai_call(call)
        return need_text(source)
    return jsonify(**draft, source=source, source_url=source_url, source_card=source_card, sample=False)


EAT_OUT_MIN, EAT_OUT_MAX = 1_000, 100_000
EAT_OUT_FAIL = "사 먹는 가격을 추정하지 못했어요. 직접 입력해주세요."
EAT_OUT_OFF = "사 먹는 가격을 지금은 추정할 수 없어요."


@bp.post("/recipes/<int:recipe_id>/eat-out-estimate")
@login_required
def estimate_eat_out_price(recipe_id):
    """29절 결정 11. 레시피에 값이 있으면 AI 없이 그 값. 없을 때만 한 번 추정해 레시피에 저장한다."""
    recipe = get_owned_or_404(Recipe, recipe_id)
    if recipe.eat_out_price is not None:
        return jsonify(eat_out_price=recipe.eat_out_price, eat_out_source=recipe.eat_out_source)

    mode = ai.scan_mode(g.user)
    if mode == "off":
        abort(503, EAT_OUT_OFF)
    if mode == "sample":
        price, source = ai.SAMPLE_EAT_OUT_PRICE, "sample"  # 예시 모드는 기록을 남기지 않는다
    else:
        scan.check_ai_limits(g.user.id, scan.RECIPE_KINDS, ai_daily_limit(g.user, "AI_DAILY_RECIPE_LIMIT"), "AI 레시피는")
        call = scan.start_ai_call(g.user.id, "eat_out")
        try:
            raw, usage = ai.estimate_eat_out(recipe.title, [ingredient_key(i["name"]) for i in recipe.ingredients])
        except ai.AiError:
            scan.miss_ai_call(call)
            abort(502, EAT_OUT_FAIL)
        scan.finish_ai_call(call, usage)
        price = raw.get("price") if isinstance(raw, dict) else None
        if isinstance(price, bool) or not isinstance(price, int) or not (EAT_OUT_MIN <= price <= EAT_OUT_MAX):
            scan.miss_ai_call(call)
            abort(502, EAT_OUT_FAIL)
        source = "ai"

    # eat_out_price가 그사이 채워졌으면(사용자 입력·경합) 덮지 않는다. updated_at을 그대로 넣어 onupdate가 돌지 않게 한다
    # (내 레시피 목록 순서가 추정 때문에 바뀌지 않게, Task 4·5도 폼 값으로 레시피를 바꿀 때 같은 방법을 쓴다).
    Recipe.query.filter(Recipe.id == recipe_id, Recipe.eat_out_price.is_(None)).update(
        {Recipe.eat_out_price: price, Recipe.eat_out_source: source, Recipe.updated_at: Recipe.updated_at},
        synchronize_session=False,
    )
    db.session.commit()
    db.session.refresh(recipe)
    return jsonify(eat_out_price=recipe.eat_out_price, eat_out_source=recipe.eat_out_source)


@bp.get("/ai-usage")
@login_required
def ai_usage():
    """오늘(서울 날짜) 쓴 횟수(세지 않은 헛호출 _miss는 빼고)와 한도. 화면의 `오늘 N번 남음`은 recipe.limit - recipe.used."""
    return jsonify(
        scan={"used": scan.calls_today(g.user.id, scan.SCAN_KINDS), "limit": ai_daily_limit(g.user, "AI_DAILY_SCAN_LIMIT")},
        recipe={"used": scan.calls_today(g.user.id, scan.RECIPE_KINDS), "limit": ai_daily_limit(g.user, "AI_DAILY_RECIPE_LIMIT")},
    )
