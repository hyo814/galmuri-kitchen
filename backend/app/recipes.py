from datetime import timezone
from urllib.parse import urlparse

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from .auth import get_owned_or_404, login_required
from .ingredients import seasoning_names, seoul_today, status_of, user_rules
from .matching import names_match, normalize
from .models import Ingredient, PublicRecipe, Recipe, db
from .recipe_parse import ingredient_key
from .validation import integer, text

bp = Blueprint("recipes", __name__, url_prefix="/api")

MAX_RECIPES_PER_USER = 1000
MAX_INGREDIENTS = 50
MAX_STEPS = 30
ALWAYS_HAVE = {"물"}  # 물은 재고에 넣지 않으니 늘 있는 것으로 본다
URL_ERROR = "링크는 http:// 또는 https://로 시작하는 주소로 입력해주세요."


def inventory(user_id):
    """[(재고 이름, 빨리 먹어야 하는지)] — 빨리 먹어야 할 재료(urgent·danger)가 앞. 요청마다 한 번 만든다."""
    today, rules, seasonings = seoul_today(), user_rules(user_id), seasoning_names(user_id)
    items = Ingredient.query.options(joinedload(Ingredient.location)).filter_by(user_id=user_id).order_by(Ingredient.id).all()
    stock = [(i.name, status_of(i, today, rules, seasonings) in ("urgent", "danger")) for i in items]
    return sorted(stock, key=lambda row: not row[1])


def match_key(key, stock):
    """재료 키에 매칭되는 첫 재고 이름(없으면 None)과 있음 여부."""
    matched = next((name for name, _ in stock if names_match(name, key)), None)
    return matched, matched is not None or normalize(key) in ALWAYS_HAVE


def annotate(ingredients, keys, stock):
    rows = []
    for item, key in zip(ingredients, keys):
        matched, have = match_key(key, stock)
        rows.append({"name": item["name"], "amount": item["amount"], "have": have, "matched_name": matched})
    return rows


def _iso(value):
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()  # SQLite는 tz 없이 돌려준다


def recipe_json(recipe, stock):
    return {
        "kind": "mine",
        "id": recipe.id,
        "title": recipe.title,
        "servings": recipe.servings,
        "category": None,
        "ingredients": annotate(recipe.ingredients, [ingredient_key(i["name"]) for i in recipe.ingredients], stock),
        "steps": recipe.steps,
        "source": recipe.source,
        "source_url": recipe.source_url,
        "public_recipe_id": recipe.public_recipe_id,
        "image_url": recipe.image_url,
    }


def public_json(recipe, stock):
    return {
        "kind": "public",
        "id": recipe.id,
        "title": recipe.title,
        "servings": recipe.servings,
        "category": recipe.category,
        "method": recipe.method,
        "kcal": recipe.kcal,
        "ingredients": annotate(recipe.ingredients, recipe.ingredient_keys, stock),
        "steps": recipe.steps,
        "image_url": recipe.image_url,
        "is_sample": recipe.is_sample,
    }


def list_json(recipe):
    return {
        "id": recipe.id,
        "title": recipe.title,
        "servings": recipe.servings,
        "source": recipe.source,
        "image_url": recipe.image_url,
        "ingredient_count": len(recipe.ingredients),
        "updated_at": _iso(recipe.updated_at),
    }


def _ingredients(value):
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_INGREDIENTS:
        abort(400, f"재료를 1~{MAX_INGREDIENTS}개 입력해주세요.")
    rows = []
    for index, item in enumerate(value, 1):
        if not isinstance(item, dict):
            abort(400, "잘못된 요청이에요.")
        name, amount = item.get("name"), item.get("amount")
        amount = "" if amount is None else amount
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 50:
            abort(400, f"{index}번째 재료 이름은 1~50자로 입력해주세요.")
        if not isinstance(amount, str) or len(amount.strip()) > 30:
            abort(400, f"{index}번째 재료 양은 30자까지 입력해주세요.")
        rows.append({"name": name.strip(), "amount": amount.strip()})
    return rows


MAX_RAW_STEPS = 100  # 다듬기 전 원본 길이 상한(비어 있어 걸러지는 것까지 포함). 정식 상한은 MAX_STEPS


def _steps(value):
    if not isinstance(value, list) or len(value) > MAX_RAW_STEPS or not all(isinstance(step, str) for step in value):
        abort(400, "만드는 법을 다시 확인해주세요.")
    steps = [step.strip() for step in value if step.strip()]
    if len(steps) > MAX_STEPS:
        abort(400, f"만드는 법은 {MAX_STEPS}단계까지 입력할 수 있어요.")
    for index, step in enumerate(steps, 1):
        if len(step) > 500:
            abort(400, f"{index}번째 단계는 500자까지 입력해주세요.")
    return steps


def _source_url(value):
    if value in (None, ""):
        return None
    if not isinstance(value, str) or len(value.strip()) > 500:
        abort(400, URL_ERROR)
    parsed = urlparse(value.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        abort(400, URL_ERROR)
    return value.strip()


def parse_recipe(data):
    """생성·수정(PUT) 공통. source는 서버가 정하므로 받지 않는다. source_url은 보냈을 때만 바꾼다."""
    if not isinstance(data, dict):
        abort(400, "잘못된 요청이에요.")
    fields = {
        "title": text(data.get("title"), "제목은", 60),
        "servings": integer(data.get("servings", 2), "인분은", 1, 20),
        "ingredients": _ingredients(data.get("ingredients")),
        "steps": _steps(data.get("steps", [])),
    }
    if "source_url" in data:
        fields["source_url"] = _source_url(data["source_url"])
    return fields


def _check_recipe_cap():
    if Recipe.query.filter_by(user_id=g.user.id).count() >= MAX_RECIPES_PER_USER:
        abort(400, f"레시피는 {MAX_RECIPES_PER_USER}개까지 저장할 수 있어요.")


def _public_or_404(recipe_id):
    recipe = db.session.get(PublicRecipe, recipe_id) if recipe_id <= 2**31 - 1 else None
    if recipe is None:
        abort(404, "찾을 수 없어요.")
    return recipe


@bp.get("/recommendations")
@login_required
def recommendations():
    """보유 재료 일치율 순 추천(스펙 4절). 재고와 겹치는 재료가 하나도 없는 레시피는 뺀다."""
    limit = min(max(request.args.get("limit", 20, type=int), 1), 50)
    stock = inventory(g.user.id)
    urgent = {name for name, is_urgent in stock if is_urgent}
    # ponytail: 서로 다른 재료 키마다 재고 전체와 names_match로 비교한다 — 최악 O(레시피 × 재료 × 재고), 키가 겹치면 캐시로 줄어든다.
    # 공공 레시피 1,100건 × 재고 60개에서 1.5초 안(테스트). 느려지면 재고 이름 단어로 역색인을 만들어 후보만 비교한다.
    matches = {}

    def card(kind, recipe_id, title, image_url, servings, keys, names):
        results = []
        for key in keys:
            if key not in matches:
                matches[key] = match_key(key, stock)
            results.append(matches[key])
        matched = [name for name, _ in results if name]
        if not matched:
            return None
        have = sum(1 for _, has in results if has)
        urgent_names = list(dict.fromkeys(name for name in matched if name in urgent))
        rate = round(have / len(keys), 2)
        return {
            "kind": kind,
            "id": recipe_id,
            "title": title,
            "image_url": image_url,
            "servings": servings,
            "match_rate": rate,
            "have_count": have,
            "total_count": len(keys),
            "missing": [name for name, (_, has) in zip(names, results) if not has][:5],
            "urgent_used": len(urgent_names),
            "urgent_names": urgent_names,
            "score": round(rate + 0.1 * len(urgent_names), 2),
        }

    def ranked(cards):
        return sorted((c for c in cards if c), key=lambda c: (-c["score"], c["title"], c["id"]))[:limit]

    mine = ranked(
        card("mine", r.id, r.title, r.image_url, r.servings, [ingredient_key(i["name"]) for i in r.ingredients], [i["name"] for i in r.ingredients])
        for r in Recipe.query.filter_by(user_id=g.user.id)
    )
    rows = db.session.query(
        PublicRecipe.id, PublicRecipe.title, PublicRecipe.image_url, PublicRecipe.servings, PublicRecipe.ingredient_keys, PublicRecipe.is_sample
    ).all()
    public = ranked(card("public", r.id, r.title, r.image_url, r.servings, r.ingredient_keys, r.ingredient_keys) for r in rows)
    return jsonify(mine=mine, public=public, sample=bool(rows) and all(r.is_sample for r in rows), inventory_count=len(stock))


@bp.get("/recipes")
@login_required
def list_recipes():
    recipes = Recipe.query.filter_by(user_id=g.user.id).order_by(Recipe.id.desc()).all()
    return jsonify([list_json(r) for r in recipes])


@bp.post("/recipes")
@login_required
def create_recipe():
    fields = parse_recipe(request.get_json(silent=True))
    _check_recipe_cap()
    recipe = Recipe(user_id=g.user.id, source="mine", **fields)
    db.session.add(recipe)
    db.session.commit()
    return jsonify(recipe_json(recipe, inventory(g.user.id))), 201


@bp.get("/recipes/<int:recipe_id>")
@login_required
def get_recipe(recipe_id):
    return jsonify(recipe_json(get_owned_or_404(Recipe, recipe_id), inventory(g.user.id)))


@bp.put("/recipes/<int:recipe_id>")
@login_required
def update_recipe(recipe_id):
    recipe = get_owned_or_404(Recipe, recipe_id)
    for key, value in parse_recipe(request.get_json(silent=True)).items():
        setattr(recipe, key, value)
    db.session.commit()
    return jsonify(recipe_json(recipe, inventory(g.user.id)))


@bp.delete("/recipes/<int:recipe_id>")
@login_required
def delete_recipe(recipe_id):
    db.session.delete(get_owned_or_404(Recipe, recipe_id))
    db.session.commit()
    return "", 204


@bp.get("/public-recipes/<int:recipe_id>")
@login_required
def get_public_recipe(recipe_id):
    return jsonify(public_json(_public_or_404(recipe_id), inventory(g.user.id)))


@bp.post("/public-recipes/<int:recipe_id>/save")
@login_required
def save_public_recipe(recipe_id):
    """공공 레시피를 내 레시피로 복사한다. 이미 저장했으면 그 레시피를 200으로 돌려준다."""
    public = _public_or_404(recipe_id)
    existing = Recipe.query.filter_by(user_id=g.user.id, public_recipe_id=public.id).first()
    if existing:
        return jsonify(recipe_json(existing, inventory(g.user.id)))
    _check_recipe_cap()
    recipe = Recipe(
        user_id=g.user.id,
        title=public.title[:60].strip(),
        servings=public.servings,
        ingredients=public.ingredients,  # 파서가 이미 50개·이름 50자·양 30자로 잘랐다
        steps=public.steps[:MAX_STEPS],
        source="public",
        public_recipe_id=public.id,
        image_url=public.image_url,
    )
    db.session.add(recipe)
    try:
        db.session.commit()
    except IntegrityError:
        # 동시에 두 번 눌러 UNIQUE(user_id, public_recipe_id)에 걸린 경우: 진 쪽도 저장된 레시피를 그대로 돌려준다(멱등).
        db.session.rollback()
        winner = Recipe.query.filter_by(user_id=g.user.id, public_recipe_id=public.id).first()
        if winner is None:
            abort(400, "이미 저장한 레시피예요.")
        return jsonify(recipe_json(winner, inventory(g.user.id)))
    return jsonify(recipe_json(recipe, inventory(g.user.id))), 201
