import threading
import time
from urllib.parse import urlparse

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from .auth import get_owned_or_404, login_required
from .ingredients import seasoning_names, seoul_today, status_of, user_rules
from .matching import match_prepared, prepare
from .models import Ingredient, PublicRecipe, Recipe, db
from .recipe_parse import ingredient_key
from .validation import decode_cursor, encode_cursor, integer, iso_datetime, text

bp = Blueprint("recipes", __name__, url_prefix="/api")

MAX_RECIPES_PER_USER = 1000
MAX_INGREDIENTS = 50
MAX_STEPS = 30
ALWAYS_HAVE = {"물"}  # 물은 재고에 넣지 않으니 늘 있는 것으로 본다
SOURCES = ("mine", "ai", "youtube", "instagram", "blog", "text", "photo")  # 화면이 만들 수 있는 출처. public은 저장 API만 쓴다
URL_ERROR = "링크는 http:// 또는 https://로 시작하는 주소로 입력해주세요."
RECIPE_LIST_PAGE_SIZE = 30
RECOMMENDATION_PAGE_SIZE = 20
CHOICES_CANDIDATE_LIMIT = 200  # ponytail: 최근 200개 안에서만 고른다 — 넘으면 검색어로 찾게 안내하거나 추천 순위 캐시를 쓴다
CHOICES_MAX = 50
QUERY_MAX = 50  # 칸 채우기 내 레시피·식약처 레시피 제목 검색어


def inventory_rows(user_id):
    """[(Ingredient 행, 빨리 먹어야 하는지)] — 빨리 먹어야 할 재료(urgent·danger)가 앞, 그 안은 id 순. 추천(inventory)과 요리했어요 초안이 같이 쓴다."""
    today, rules, seasonings = seoul_today(), user_rules(user_id), seasoning_names(user_id)
    items = Ingredient.query.options(joinedload(Ingredient.location)).filter_by(user_id=user_id).order_by(Ingredient.id).all()
    rows = [(i, status_of(i, today, rules, seasonings) in ("urgent", "danger")) for i in items]
    return sorted(rows, key=lambda row: not row[1])


def inventory(user_id):
    """[(재고 이름, 빨리 먹어야 하는지)] — inventory_rows 순서 그대로. 요청마다 한 번 만든다."""
    return [(item.name, urgent) for item, urgent in inventory_rows(user_id)]


def stock_for_recipe(user_id):
    """(inventory()와 같은 [(이름, 빨리 먹어야 하는지)], {이름: (수량, 단위)}) — 레시피 상세·저장류 라우트가
    inventory_rows를 한 번만 읽어 매칭(annotate)과 남은 양 표시(29절)에 같이 쓴다.
    annotate·_match_key_fast는 같은 이름 중 맨 앞 행(urgent 먼저, 그 안은 id순)을 골라 매칭하므로 남은 양도 그 기준:
    뒤이은 같은 이름 행은 단위가 같으면 수량을 더하고(수량 없는 행은 빼고 합산), 단위가 다르면 더하지 않고 첫 행 값 그대로 둔다."""
    rows = inventory_rows(user_id)
    amounts = {}
    for item, _ in rows:
        if item.name not in amounts:
            amounts[item.name] = (item.quantity, item.unit)
        else:
            quantity, unit = amounts[item.name]
            if unit == item.unit:
                values = [v for v in (quantity, item.quantity) if v is not None]
                amounts[item.name] = (sum(values) if values else None, unit)
    return [(item.name, urgent) for item, urgent in rows], amounts


def annotate(ingredients, keys, stock, amounts=None):
    """M7: 추천과 같은 준비된 재고 + 빠른 매칭(_prepared_stock/_match_key_fast)을 써서
    상세 화면 하나 열 때마다 정규식을 다시 돌리지 않게 한다(재고가 커도 빠르게).
    amounts(stock_for_recipe의 두 번째 값)가 있으면 매칭된 줄에 stock_quantity·stock_unit을 붙인다(29절, 레시피 상세만)."""
    prepared_stock = _prepared_stock(stock)
    rows = []
    for item, key in zip(ingredients, keys):
        matched, have = _match_key_fast(prepare(key), prepared_stock)
        row = {"name": item["name"], "amount": item["amount"], "have": have, "matched_name": matched}
        if amounts and matched in amounts:
            row["stock_quantity"], row["stock_unit"] = amounts[matched]
        else:
            row["stock_quantity"], row["stock_unit"] = None, None
        rows.append(row)
    return rows


def recipe_json(recipe, stock, amounts=None):
    return {
        "kind": "mine",
        "id": recipe.id,
        "title": recipe.title,
        "servings": recipe.servings,
        "category": None,
        "ingredients": annotate(recipe.ingredients, [ingredient_key(i["name"]) for i in recipe.ingredients], stock, amounts),
        "steps": recipe.steps,
        "source": recipe.source,
        "source_url": recipe.source_url,
        "public_recipe_id": recipe.public_recipe_id,
        "image_url": recipe.image_url,
        "eat_out_price": recipe.eat_out_price,
        "eat_out_source": recipe.eat_out_source,
    }


def public_json(recipe, stock, amounts=None):
    return {
        "kind": "public",
        "id": recipe.id,
        "title": recipe.title,
        "servings": recipe.servings,
        "category": recipe.category,
        "method": recipe.method,
        "kcal": recipe.kcal,
        "ingredients": annotate(recipe.ingredients, recipe.ingredient_keys, stock, amounts),
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
        "updated_at": iso_datetime(recipe.updated_at),
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


def _image_url(value, source):
    """AI 레시피에 붙인 비슷한 공공 레시피 사진만 받는다: 공공 레시피에 실제로 있는 주소와 똑같을 때만.
    주소 모양을 따지지 않으므로 역슬래시·사용자 정보 같은 호스트 속이기가 통하지 않는다. 유튜브 썸네일 같은 외부 사진은 저장하지 않는다(스펙 25절)."""
    if value is None:
        return None
    if (
        source != "ai"
        or not isinstance(value, str)
        or not 0 < len(value) <= 500
        or "\x00" in value  # PostgreSQL은 NUL 문자열 비교에서 오류를 낸다
        or db.session.query(PublicRecipe.id).filter_by(image_url=value).first() is None
    ):
        abort(400, "잘못된 요청이에요.")
    return value


def parse_recipe(data):
    """생성·수정(PUT) 공통. source·image_url은 만들 때만 받는다(create_recipe). source_url은 보냈을 때만 바꾼다."""
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


def check_recipe_cap(adding=1):
    """adding개를 더 저장하면 상한을 넘는지(AI 식단 초안 넣기는 새 요리 여러 개를 한 번에 만든다)."""
    if Recipe.query.filter_by(user_id=g.user.id).count() + adding > MAX_RECIPES_PER_USER:
        abort(400, f"레시피는 {MAX_RECIPES_PER_USER}개까지 저장할 수 있어요.")


def _public_or_404(recipe_id):
    recipe = db.session.get(PublicRecipe, recipe_id) if recipe_id <= 2**31 - 1 else None
    if recipe is None:
        abort(404, "찾을 수 없어요.")
    return recipe


def _prepared_stock(stock):
    """재고 이름을 한 번씩만 normalize·tokenize해서 [(이름, prepare(이름))]로 둔다.
    ponytail: 추천은 재료 키(최대 12개 × 레시피 최대 1,100개) × 재고를 비교한다 — 매 비교마다 정규식을 새로 돌리면
    (재고 2,000개 기준) 실측 18초까지 걸렸다. 재고·키 양쪽을 한 번만 준비해 두면 비교 자체는 가벼운 문자열 연산만 남는다."""
    return [(name, prepare(name)) for name, _ in stock]


def _match_key_fast(key_prepared, prepared_stock):
    """재료 키(미리 준비함)에 매칭되는 첫 재고 이름(없으면 None)과 있음 여부. annotate·추천이 함께 쓴다."""
    for name, name_prepared in prepared_stock:
        if match_prepared(key_prepared, name_prepared):
            return name, True
    return None, key_prepared[0] in ALWAYS_HAVE


def stock_context(user_id):
    """(준비된 재고, 빨리 먹어야 할 재고 이름 집합). 요청마다 한 번 만들어 여러 레시피 요약에 같이 쓴다."""
    stock = inventory(user_id)
    return _prepared_stock(stock), {name for name, urgent in stock if urgent}


def match_summary(ingredients, prepared_stock, urgent):
    """레시피 재료 중 재고에 있는 수·전체 수·마저 쓰는 빨리 먹어야 할 재료 이름(식단 칸·칸 채우기 목록, 스펙 20절)."""
    results = [_match_key_fast(prepare(ingredient_key(i["name"])), prepared_stock) for i in ingredients]
    return {
        "have_count": sum(1 for _, has in results if has),
        "total_count": len(results),
        "urgent_names": list(dict.fromkeys(name for name, _ in results if name and name in urgent)),
    }


def _card(kind, recipe_id, title, image_url, servings, keys, names, prepared_stock, urgent, matches, keep_unmatched=False):
    """겹치는 재료가 하나도 없으면(물만 겹쳐도) None. 검색(keep_unmatched)은 겹치지 않아도 카드를 만든다."""
    results = []
    for key in keys:
        if key not in matches:
            matches[key] = _match_key_fast(prepare(key), prepared_stock)
        results.append(matches[key])
    matched = [name for name, _ in results if name]
    if not matched and not keep_unmatched:
        return None
    have = sum(1 for _, has in results if has)
    urgent_names = list(dict.fromkeys(name for name in matched if name in urgent))
    rate = round(have / len(keys), 2) if keys else 0  # 검색은 재료가 0개인 공공 레시피(빈 RCP_PARTS_DTLS)도 넣는다
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


def _rank(cards):
    return sorted((c for c in cards if c), key=lambda c: (-c["score"], c["title"], c["id"]))


# --- 추천 순위 캐시 (fix round 1: 재고가 클수록 매 요청 계산 비용이 커지는 문제 해결) ---
# ponytail: 프로세스별 캐시다(gunicorn 워커마다 따로 가진다. 이 규모에선 충분하고, 여러 인스턴스로 늘면 Redis로 옮긴다).
_RANK_CACHE = {}  # user_id -> {"signature", "created", "mine": [...]|None, "public": ([...], sample)|None}
_RANK_CACHE_TTL = 120  # seconds (time.monotonic)
_RANK_CACHE_MAX_USERS = 50
_RANK_CACHE_LOCK = threading.Lock()  # gthread 워커의 여러 스레드가 같은 dict를 바꾸므로 교체·삭제를 잠근다


def _rank_cache_signature(user_id, stock):
    """서명이 같으면(오늘 날짜·재고·내 레시피·공공 레시피가 그대로면) 다시 계산하지 않는다."""
    mine_count, mine_max_id, mine_max_updated = (
        db.session.query(func.count(Recipe.id), func.max(Recipe.id), func.max(Recipe.updated_at)).filter_by(user_id=user_id).one()
    )
    public_count, public_max_id, public_max_updated = db.session.query(
        func.count(PublicRecipe.id), func.max(PublicRecipe.id), func.max(PublicRecipe.updated_at)
    ).one()
    return (
        seoul_today().isoformat(),
        tuple(sorted(stock)),
        mine_count,
        mine_max_id,
        iso_datetime(mine_max_updated) if mine_max_updated else None,
        public_count,
        public_max_id,
        iso_datetime(public_max_updated) if public_max_updated else None,
    )


def _rank_cache_entry(user_id, signature):
    now = time.monotonic()
    with _RANK_CACHE_LOCK:
        entry = _RANK_CACHE.get(user_id)
        if entry is None or entry["signature"] != signature or now - entry["created"] > _RANK_CACHE_TTL:
            # I3: 새로 넣기 전에 이미 TTL이 지난 다른 사용자 항목도 같이 치운다(안 쓰는 계정이 메모리를 오래 잡지 않게).
            for uid in [uid for uid, e in _RANK_CACHE.items() if now - e["created"] > _RANK_CACHE_TTL]:
                del _RANK_CACHE[uid]
            entry = {"signature": signature, "created": now, "mine": None, "public": None}
            _RANK_CACHE[user_id] = entry
            while len(_RANK_CACHE) > _RANK_CACHE_MAX_USERS:
                oldest_id = min(_RANK_CACHE, key=lambda uid: _RANK_CACHE[uid]["created"])
                del _RANK_CACHE[oldest_id]
        return entry


def _ranked_mine(user_id, prepared_stock, urgent):
    matches = {}
    return _rank(
        _card(
            "mine",
            r.id,
            r.title,
            r.image_url,
            r.servings,
            [ingredient_key(i["name"]) for i in r.ingredients],
            [i["name"] for i in r.ingredients],
            prepared_stock,
            urgent,
            matches,
        )
        for r in Recipe.query.filter_by(user_id=user_id)
    )


def _ranked_public(prepared_stock, urgent, q=""):
    """q가 있으면 제목(공백·대소문자 무시)에 q가 들어간 레시피만, 재고와 겹치지 않아도 넣는다(검색)."""
    matches = {}
    query = db.session.query(
        PublicRecipe.id,
        PublicRecipe.title,
        PublicRecipe.image_url,
        PublicRecipe.servings,
        PublicRecipe.ingredient_keys,
        PublicRecipe.ingredients,
        PublicRecipe.is_sample,
    )
    if q:
        query = query.filter(func.replace(func.lower(PublicRecipe.title), " ", "").contains("".join(q.lower().split()), autoescape=True))
    rows = query.all()
    ranked = _rank(
        _card(
            "public", r.id, r.title, r.image_url, r.servings, r.ingredient_keys, [i["name"] for i in r.ingredients], prepared_stock, urgent, matches,
            keep_unmatched=bool(q),
        )
        for r in rows
    )
    sample = bool(rows) and all(r.is_sample for r in rows)
    return ranked, sample


@bp.get("/recommendations")
@login_required
def recommendations():
    """보유 재료 일치율 순 추천(스펙 4·25절). 재고와 겹치는 재료가 하나도 없는 레시피는 뺀다.
    section=all(기본)은 내 레시피 상위 10개 + 공공 레시피 한 페이지, section=public은 공공 레시피만(내 레시피는 계산하지 않는다).
    section=public에 q가 있으면 식약처 레시피 제목 검색 결과다(재고와 안 겹쳐도 넣고, 거른 행만 계산하므로 캐시하지 않는다)."""
    section = request.args.get("section", "all")
    q = request.args.get("q", "").strip()[:QUERY_MAX]
    if section not in ("all", "public") or (q and section != "public"):
        abort(400, "잘못된 요청이에요.")
    offset = max(request.args.get("offset", 0, type=int) or 0, 0)
    limit = min(max(request.args.get("limit", RECOMMENDATION_PAGE_SIZE, type=int), 1), 50)

    stock = inventory(g.user.id)
    urgent = {name for name, is_urgent in stock if is_urgent}
    if q:
        public_ranked, sample = _ranked_public(_prepared_stock(stock), urgent, q)
    else:
        signature = _rank_cache_signature(g.user.id, stock)
        entry = _rank_cache_entry(g.user.id, signature)
        if (section == "all" and entry["mine"] is None) or entry["public"] is None:
            prepared_stock = _prepared_stock(stock)
            if section == "all" and entry["mine"] is None:
                entry["mine"] = _ranked_mine(g.user.id, prepared_stock, urgent)
            if entry["public"] is None:
                entry["public"] = _ranked_public(prepared_stock, urgent)
        public_ranked, sample = entry["public"]

    public_total = len(public_ranked)
    public_page = public_ranked[offset : offset + limit]
    next_offset = offset + limit if offset + limit < public_total else None
    # M11: public_total은 재고와 겹치는 것만 센다 — 카탈로그가 아예 비었는지(vs 그냥 안 겹치는지) 구분하려면
    # 전체 개수가 따로 필요하다. 가벼운 COUNT라 캐시 없이 매번 구해도 된다.
    public_count = db.session.query(func.count(PublicRecipe.id)).scalar()
    body = {
        "public": public_page,
        "public_total": public_total,
        "public_count": public_count,
        "next_offset": next_offset,
        "sample": sample,
        "inventory_count": len(stock),
    }
    if section == "all":
        body["mine"] = entry["mine"][:10]
        body["mine_total"] = len(entry["mine"])
    return jsonify(**body)


@bp.get("/recipes/choices")
@login_required
def recipe_choices():
    """식단 칸 채우기 시트의 `내 레시피` 목록(20절): 최근 200개 후보를 재고 일치 점수 순으로. q가 있으면 제목 필터.
    줄마다 cooked(요리 일기 쓰기 시트의 `요리 2번 · 마지막 9월 14일`, 29절 추가 2026-09-16)."""
    from .cooklog import cooked_counts  # cooklog가 recipes를 import하므로 여기서만(순환 import 방지)
    q = request.args.get("q", "").strip()[:QUERY_MAX]
    query = Recipe.query.filter_by(user_id=g.user.id)
    if q:
        query = query.filter(Recipe.title.contains(q, autoescape=True))
    candidates = query.order_by(Recipe.updated_at.desc(), Recipe.id.desc()).limit(CHOICES_CANDIDATE_LIMIT).all()

    prepared_stock, urgent = stock_context(g.user.id)
    summaries = [(r, match_summary(r.ingredients, prepared_stock, urgent)) for r in candidates]

    def score(summary):
        # 재료가 0개인 레시피(공공 레시피 저장·동기화가 빈 RCP_PARTS_DTLS를 그대로 둘 수 있다)도 0/0으로 죽지 않게.
        rate = summary["have_count"] / summary["total_count"] if summary["total_count"] else 0
        return rate + 0.1 * len(summary["urgent_names"])

    ranked = sorted(summaries, key=lambda pair: -score(pair[1]))[:CHOICES_MAX]
    cooked = cooked_counts([r.id for r, _ in ranked], g.user.id)
    return jsonify(items=[{"id": r.id, "title": r.title, "servings": r.servings, **summary, "cooked": cooked.get(r.id)} for r, summary in ranked])


@bp.get("/recipes")
@login_required
def list_recipes():
    """updated_at·id 내림차순 커서 페이지(스펙 25절). limit(1~50, 기본 30) + next_cursor."""
    limit = min(max(request.args.get("limit", RECIPE_LIST_PAGE_SIZE, type=int), 1), 50)
    query = Recipe.query.filter_by(user_id=g.user.id)
    cursor = request.args.get("cursor")
    if cursor:
        cursor_updated_at, cursor_id = decode_cursor(cursor)
        query = query.filter(
            or_(Recipe.updated_at < cursor_updated_at, and_(Recipe.updated_at == cursor_updated_at, Recipe.id < cursor_id))
        )
    recipes = query.order_by(Recipe.updated_at.desc(), Recipe.id.desc()).limit(limit + 1).all()
    has_more = len(recipes) > limit
    recipes = recipes[:limit]
    next_cursor = encode_cursor(recipes[-1].updated_at, recipes[-1].id) if has_more else None
    return jsonify(items=[list_json(r) for r in recipes], next_cursor=next_cursor)


@bp.post("/recipes")
@login_required
def create_recipe():
    data = request.get_json(silent=True)
    fields = parse_recipe(data)
    source = data.get("source", "mine")
    if source not in SOURCES:
        abort(400, "잘못된 요청이에요.")
    fields.update(source=source, image_url=_image_url(data.get("image_url"), source))
    check_recipe_cap()
    recipe = Recipe(user_id=g.user.id, **fields)
    db.session.add(recipe)
    db.session.commit()
    stock, amounts = stock_for_recipe(g.user.id)
    return jsonify(recipe_json(recipe, stock, amounts)), 201


@bp.get("/recipes/<int:recipe_id>")
@login_required
def get_recipe(recipe_id):
    from .cooklog import recipe_cooked  # cooklog가 recipes를 import하므로 여기서만(순환 import 방지)

    recipe = get_owned_or_404(Recipe, recipe_id)
    stock, amounts = stock_for_recipe(g.user.id)
    res = jsonify({**recipe_json(recipe, stock, amounts), "cooked": recipe_cooked(recipe.id, g.user.id)})
    res.headers["Cache-Control"] = "no-store"  # cooked가 일기(식습관·지출) 정보를 담는다(리뷰 minor)
    return res


@bp.put("/recipes/<int:recipe_id>")
@login_required
def update_recipe(recipe_id):
    recipe = get_owned_or_404(Recipe, recipe_id)
    for key, value in parse_recipe(request.get_json(silent=True)).items():
        setattr(recipe, key, value)
    db.session.commit()
    stock, amounts = stock_for_recipe(g.user.id)
    return jsonify(recipe_json(recipe, stock, amounts))


@bp.delete("/recipes/<int:recipe_id>")
@login_required
def delete_recipe(recipe_id):
    db.session.delete(get_owned_or_404(Recipe, recipe_id))
    db.session.commit()
    return "", 204


@bp.get("/public-recipes/<int:recipe_id>")
@login_required
def get_public_recipe(recipe_id):
    stock, amounts = stock_for_recipe(g.user.id)
    return jsonify(public_json(_public_or_404(recipe_id), stock, amounts))


@bp.post("/public-recipes/<int:recipe_id>/save")
@login_required
def save_public_recipe(recipe_id):
    """공공 레시피를 내 레시피로 복사한다. 이미 저장했으면 그 레시피를 200으로 돌려준다."""
    public = _public_or_404(recipe_id)
    stock, amounts = stock_for_recipe(g.user.id)  # 아래 두 갈래·재시도 분기가 모두 같은 값을 쓴다
    existing = Recipe.query.filter_by(user_id=g.user.id, public_recipe_id=public.id).first()
    if existing:
        return jsonify(recipe_json(existing, stock, amounts))
    check_recipe_cap()
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
        return jsonify(recipe_json(winner, stock, amounts))
    return jsonify(recipe_json(recipe, stock, amounts)), 201
