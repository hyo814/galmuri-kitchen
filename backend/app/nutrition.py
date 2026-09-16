"""레시피 1인분 영양 계산과 식품 고르기 저장(스펙 21절 구현 세부, 4b-2 Task 3), 영양 채우기(Task 4). 윗부분은 DB 없이 테스트하는 순수 함수."""

import math
import time
from collections import defaultdict
from types import SimpleNamespace

from flask import Blueprint, abort, current_app, g, jsonify, request
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import TooManyRequests

from . import ai, foods, scan
from .amounts import TRACE_WORDS, parse_amount
from .auth import get_owned_or_404, login_required
from .foods import NUTRIENTS, OFF, missing_count, name_parts, nutrition_mode
from .matching import normalize
from .models import AiCall, FoodMatch, FoodNutrient, FoodSearch, Recipe, UnitWeightEstimate, db, utcnow
from .recipe_parse import ingredient_key
from .recipes import ALWAYS_HAVE
from .validation import commit_or_duplicate, text

bp = Blueprint("nutrition", __name__, url_prefix="/api")

SPOON_GRAMS = {"큰술": 15, "숟가락": 15, "스푼": 15, "tbs": 15, "tbsp": 15,
               "작은술": 5, "티스푼": 5, "tsp": 5, "컵": 200, "꼬집": 0.5}  # 22절 계량 기준(결정 5). 영문 키는 소문자, t·ts는 fixed_grams가 가른다
COUNTED = ("ok", "estimated")
MISSING = ("unmatched", "needs_weight", "no_estimate", "unknown_amount", "pending")
MAX_MATCHES = 2000
MAX_UNITS = 20  # 재료 하나에 고친 단위 무게 수(unit_grams JSON이 끝없이 커지지 않게)
IN_CHUNK, LIKE_CHUNK = 500, 50
WEIGHT_ERROR = "무게는 0.1~5000g 사이로 입력해주세요."
SAVE_RACE = "방금 저장했어요. 다시 불러와주세요."
FILL_SECONDS = 8
MAX_FILL_RECIPES = 31
NUTRITION_DAILY_LIMIT = 20
DEMO_NUTRITION_DAILY_LIMIT = 2  # 체험 계정 한 명(Ruling 11). 체험 전체는 DEMO_NUTRITION_GLOBAL_DAILY
NUTRITION_BURST = 10
MAX_WEIGHT_GUESSES, MAX_FOOD_GUESSES = 60, 30
LIMITS = {"grams": (0.1, 5000), "kcal": (0, 900), "carbs_g": (0, 100), "protein_g": (0, 100), "fat_g": (0, 100), "sugars_g": (0, 100), "sodium_mg": (0, 40000)}


def match_key(name):
    """재료 이름 → 기억·자동 맞추기 키. '돼지고기 앞다리살(국산)' → '돼지고기앞다리살'."""
    return normalize(ingredient_key(name))[:60]


def fixed_grams(unit):
    """g·ml(1ml=1g, ponytail: 기름·꿀은 10~40% 차이)·숟가락 단위 한 단위 g. 셀 수 있는 단위면 None.
    Ruling 10: t·ts는 원래 글자로 가른다(T·Ts·TS 큰술 15, t·ts 작은술 5). tbs·tbsp는 대소문자 무관 15, tsp는 대소문자 무관 5."""
    lower = unit.lower()
    if lower in ("g", "ml"):
        return 1.0
    if lower in ("t", "ts"):
        return 15 if unit[0] == "T" else 5
    return SPOON_GRAMS.get(lower)


def auto_match(key, rows):
    """결정 10(개정 2). rows는 key in name_parts(이름)인 FoodNutrient(source != 'ai') 후보. 고른 행 또는 None.
    ① 원재료성 후보가 있으면 (조각에 '생것' 없음, 조각 수, 이름 길이, 빠진 영양소 수, 이름) 순 첫 행 ② 없으면 normalize(이름) == key인 행이 딱 하나일 때 그것.
    고른 행은 저장하지 않는다(요청마다 다시 고른다) — 사용자가 고른 식품만 food_matches에 남는다."""
    raw = [r for r in rows if r.group_name == "원재료성"]
    if raw:
        def order(r):
            parts = name_parts(r.name)
            return "생것" not in parts, len(parts), len(r.name), missing_count(r), r.name
        return min(raw, key=order)
    exact = [r for r in rows if normalize(r.name) == key]
    return exact[0] if len(exact) == 1 else None


def search_terms(key_text):
    """[전체 이름] + 여러 낱말이면 [가장 긴 낱말(같으면 앞)] (결정 11). key_text는 ingredient_key(이름)."""
    words = key_text.split()
    return [key_text, max(words, key=len)] if len(words) > 1 else [key_text]


def daily_limit(user):
    return DEMO_NUTRITION_DAILY_LIMIT if user.provider == "demo" else NUTRITION_DAILY_LIMIT


def estimate_mode(user):
    """AI 추정 모드. ai.scan_mode를 따르되, 키가 있는데 ① 체험 계정이 sample(체험 전체 AI 예산을 다 씀)이거나
    ② 오늘 체험 전체 영양 추정이 DEMO_NUTRITION_GLOBAL_DAILY에 닿았거나 ③ 이 사용자의 오늘 영양 추정이 하루 한도에 닿았거나
    ④ 일반 사용자인데 로그인 사용자 전체 AI 예산을 다 썼거나 오늘 로그인 사용자 전체 영양 추정이 USER_NUTRITION_GLOBAL_DAILY에 닿았으면 off —
    예시 값을 공유 캐시에 넣지 않고, 줄을 끝없이 계산 중으로 두지 않는다(무게 알려주기·고르기로 고칠 수 있게). 60초 연속 한도는 곧 풀려 세지 않는다."""
    mode = ai.scan_mode(user)
    if not current_app.config["ANTHROPIC_API_KEY"]:
        return mode
    demo = user.provider == "demo"
    if (demo and mode == "sample") or (not demo and ai.user_ai_budget_spent()):  # 로그인 사용자 전체 AI 예산을 다 쓰면 오류 대신 AI 추정 없이 계산
        return "off"
    # ponytail: 세고 부르기라 동시에 온 요청 몇 개만큼 넘을 수 있다(demo_ai_budget_spent와 같은 여유)
    start, end = foods._day_bounds(scan.seoul_today())
    used = AiCall.query.filter(AiCall.demo.is_(demo), AiCall.kind.in_(scan.NUTRITION_KINDS), AiCall.created_at >= start, AiCall.created_at < end).count()
    if used >= current_app.config["DEMO_NUTRITION_GLOBAL_DAILY" if demo else "USER_NUTRITION_GLOBAL_DAILY"]:
        return "off"
    return "off" if scan.calls_today(user.id, scan.NUTRITION_KINDS) >= daily_limit(user) else mode


def _longest_word(words):
    """가장 긴 낱말(같으면 앞)의 자리."""
    return max(range(len(words)), key=lambda i: len(words[i]))


def _in_limits(value, field):
    lo, hi = LIMITS[field]
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and lo <= value <= hi


def clean_guess(raw, weight_pairs, food_names):
    """모델 출력은 믿지 않는다. weights는 요청한 (match_key(name), unit)만·유한수·LIMITS 안, 처음 나온 것만.
    foods는 요청한 match_key만, 일곱 칸이 모두 LIMITS 안이고 탄단지 합 100g 이하·당류 ≤ 탄수화물일 때만(이름은 요청한 원래 이름). → ({(key, unit): grams}, {key: {name, 영양소…}})"""
    raw = raw if isinstance(raw, dict) else {}
    wanted_weights = {(match_key(n), u) for n, u in weight_pairs}
    wanted_foods = {}
    for name in food_names:
        wanted_foods.setdefault(match_key(name), name)
    weights, foods_out = {}, {}
    for row in raw.get("weights") if isinstance(raw.get("weights"), list) else []:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str) or not isinstance(row.get("unit"), str):
            continue
        pair = (match_key(row["name"]), row["unit"])
        if pair in wanted_weights and pair not in weights and _in_limits(row.get("grams"), "grams"):
            weights[pair] = float(row["grams"])
    for row in raw.get("foods") if isinstance(raw.get("foods"), list) else []:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str):
            continue
        key = match_key(row["name"])
        if key in wanted_foods and key not in foods_out and all(_in_limits(row.get(n), n) for n in NUTRIENTS):
            if row["carbs_g"] + row["protein_g"] + row["fat_g"] <= 100 and row["sugars_g"] <= row["carbs_g"]:
                foods_out[key] = {"name": wanted_foods[key], **{n: float(row[n]) for n in NUTRIENTS}}
    return weights, foods_out


def store_guess(weights, foods_by_key, source):
    """UnitWeightEstimate(source)·FoodNutrient(food_code 'ai:<키>', name 원래 이름 100자, name_key 키, group_name '추정', source 'ai')를 넣는다.
    이미 있는 행은 두고, 동시 요청이 먼저 넣어 IntegrityError가 나면 rollback하고 남은 행만 한 번 더 넣는다."""
    for _ in range(2):
        keys = {key for key, _ in weights}
        have_weights = {(w.name_key, w.unit) for w in UnitWeightEstimate.query.filter(UnitWeightEstimate.name_key.in_(keys))} if keys else set()
        codes = [f"ai:{key}" for key in foods_by_key]
        have_codes = {code for (code,) in db.session.query(FoodNutrient.food_code).filter(FoodNutrient.food_code.in_(codes))} if codes else set()
        now = utcnow()
        db.session.add_all(UnitWeightEstimate(name_key=key, unit=unit, grams=grams, source=source, created_at=now)
                           for (key, unit), grams in weights.items() if (key, unit) not in have_weights)
        db.session.add_all(FoodNutrient(food_code=f"ai:{key}", name=food["name"][:100], name_key=key, group_name="추정", source="ai", fetched_at=now,
                                        **{n: food[n] for n in NUTRIENTS})
                           for key, food in foods_by_key.items() if f"ai:{key}" not in have_codes)
        try:
            db.session.commit()
            return
        except IntegrityError:
            db.session.rollback()


def _round1(value):
    """0 이상 값 소수 첫째 자리 반올림(.5는 올림, 화면 Math.round와 같게)."""
    return math.floor(value * 10 + 0.5) / 10


def _round0(value):
    return math.floor(value + 0.5)


NO_KEY = {"key": "", "state": "unsearched", "food": None, "unit_grams": {}}  # 재료 키가 빈 이름('+'·'(고명)'): 찾지 않는다


def ingredient_row(item, resolved, can_estimate, servings):
    """재료 한 줄 계산. resolved = {"key", "state": matched|auto|estimate|estimate_missing|unmatched|unsearched,
    "food": {food_code, name, group, kcal, carbs_g, protein_g, fat_g, sugars_g, sodium_mg} | None,
    "unit_grams": {단위: (g, "user"|"ai"|"sample")}}. 상태 순서는 스펙 21절 구현 세부 표."""
    state, food = resolved["state"], resolved["food"]
    amount = item.get("amount") or ""
    parsed = parse_amount(amount)
    quantity, unit = parsed if parsed else (None, None)
    per_unit = fixed_grams(unit) if unit else None
    countable = parsed is not None and per_unit is None
    weight, weight_source = resolved["unit_grams"].get(unit, (None, None)) if countable else (None, None)
    grams = values = None
    reason = None

    if normalize(item["name"]) in ALWAYS_HAVE or normalize(amount) in TRACE_WORDS:
        status, grams, values = "trace", 0.0, dict.fromkeys(NUTRIENTS, 0.0)
    elif parsed is None or not resolved["key"]:
        status = "unknown_amount"  # 양을 못 읽었거나 이름으로 식품을 찾을 수 없다(빼고 약)
    elif state == "unsearched":
        status, reason = "pending", "search"
    elif state == "unmatched":
        status = "unmatched"
    elif state == "estimate_missing":
        status, reason = ("pending", "food") if can_estimate else ("no_estimate", None)
    elif per_unit is None and weight is None:
        status, reason = ("pending", "weight") if can_estimate else ("needs_weight", None)
    else:
        grams = quantity * (per_unit if per_unit is not None else weight)
        values = {n: None if food[n] is None else food[n] * grams / 100 for n in NUTRIENTS}  # None = 식품에 값이 없다
        status = "estimated" if state == "estimate" or weight_source in ("ai", "sample") else "ok"

    shows_food = state in ("matched", "auto") and food is not None
    return {
        "name": item["name"], "amount": amount, "key": resolved["key"], "status": status, "pending_reason": reason,
        "countable": countable, "quantity": quantity, "unit": unit,
        "grams": _round1(grams) if grams is not None else None,
        "unit_grams": _round1(weight) if weight is not None else None, "unit_grams_source": weight_source,
        "food": {"food_code": food["food_code"], "name": food["name"], "group": food["group"], "kcal": _round0(food["kcal"])} if shows_food else None,
        "estimate_food": state in ("estimate", "estimate_missing"),
        "values": values,
        "kcal_per_serving": _round0(values["kcal"] / servings) if values is not None else None,
    }


def recipe_nutrition(ingredients, servings, resolved_by_key, can_estimate):
    """레시피 1인분(결정 14, 개정 2). 식품에 값이 없는 영양소는 아는 값만 더하고, incomplete에 {영양소: [빠진 재료 이름(재료 순서, 한 번씩)]}을 적는다.
    per_serving은 COUNTED 줄이 있거나 모든 줄이 trace일 때만(아니면 None). 빈 키는 NO_KEY로 계산한다(resolved_by_key에 넣지 않는다)."""
    servings = max(servings or 0, 1)
    keys = [match_key(item["name"]) for item in ingredients]
    rows = [ingredient_row(item, resolved_by_key[key] if key else NO_KEY, can_estimate, servings) for item, key in zip(ingredients, keys)]
    statuses = [row["status"] for row in rows]
    counted_count, trace_count = sum(s in COUNTED for s in statuses), statuses.count("trace")
    per_serving, incomplete = None, {}
    if counted_count or (rows and trace_count == len(rows)):
        counted = [row for row in rows if row["values"] is not None]
        totals = {n: sum(row["values"][n] or 0 for row in counted) / servings for n in NUTRIENTS}
        per_serving = {n: _round0(v) if n in ("kcal", "sodium_mg") else _round1(v) for n, v in totals.items()}
        for row in counted:
            for n, value in row["values"].items():
                if value is None and row["name"] not in incomplete.setdefault(n, []):
                    incomplete[n].append(row["name"])
    return {
        "servings": servings,
        "per_serving": per_serving,
        "approx": any(s not in ("ok", "trace") for s in statuses),
        "estimated_count": statuses.count("estimated"),
        "missing_count": sum(s in MISSING for s in statuses),
        "pending": "pending" in statuses,
        "usable": counted_count * 2 >= len(statuses) - trace_count,
        "incomplete": incomplete,
        "ingredients": [{k: v for k, v in row.items() if k != "values"} for row in rows],
    }


def _chunks(values, size):
    values = sorted(values)
    return [values[i:i + size] for i in range(0, len(values), size)]


def _food_json(row):
    return {"food_code": row.food_code, "name": row.name, "group": row.group_name, **{n: getattr(row, n) for n in NUTRIENTS}}


class NutritionContext:
    """요청마다 한 번. 재료 키가 K개면 쿼리는 FoodMatch·FoodSearch·UnitWeightEstimate 각 ceil(K/500), 코드 ceil(2K/500), 후보 ceil(K/50)번."""

    def __init__(self, user, recipes):
        keys, self.fallbacks = set(), {}
        for item in (i for recipe in recipes for i in recipe.ingredients):
            key = match_key(item["name"])
            words = [normalize(w) for w in ingredient_key(item["name"]).split()]
            words = [w for w in words if w]
            if key and len(words) > 1:  # 여러 낱말: 전체 이름 후보가 없을 때 가장 긴 낱말 후보를 나머지 낱말로 거른다
                at = _longest_word(words)
                self.fallbacks.setdefault(key, (words[at], words[:at] + words[at + 1:]))
            keys.add(key)
        keys.discard("")
        self.user = user
        self.can_estimate = estimate_mode(user) != "off"
        # 오늘 식품 DB 찾기 한도를 다 썼으면 안 찾아본 재료를 계산 중 대신 unmatched(고르기)로 둔다 — 채우기가 찾지 못해 끝없이 계산 중이 된다
        self.can_search = None
        self.matches, self.searched, self.foods = {}, set(), {}
        self.weights, self.candidates = defaultdict(dict), defaultdict(list)
        for chunk in _chunks(keys, IN_CHUNK):
            for m in FoodMatch.query.filter(FoodMatch.user_id == user.id, FoodMatch.ingredient_key.in_(chunk)):
                self.matches[m.ingredient_key] = m
            self.searched.update(k for (k,) in db.session.query(FoodSearch.query_key).filter(FoodSearch.query_key.in_(chunk)))
            for w in UnitWeightEstimate.query.filter(UnitWeightEstimate.name_key.in_(chunk)):
                self.weights[w.name_key][w.unit] = (w.grams, w.source)
        codes = {m.food_code for m in self.matches.values() if m.food_code} | {f"ai:{k}" for k in keys}
        for chunk in _chunks(codes, IN_CHUNK):
            self.foods.update((f.food_code, f) for f in FoodNutrient.query.filter(FoodNutrient.food_code.in_(chunk)))
        # 기억이 있는 재료는 resolve가 후보를 보지 않는다 — 그 키와 여러 낱말 대체 키는 찾지 않는다
        free = keys - self.matches.keys()
        like_keys = (free | {fb for key, (fb, _) in self.fallbacks.items() if key in free}) - ALWAYS_HAVE
        # ponytail: 한 묶음(50개 OR LIKE '%키%')마다 food_nutrients 전체를 훑는다(O(행 수), warm --limit이 행 수를 묶는다).
        # 키는 normalize로 소문자·DB 이름은 한국어라 ILIKE(lower 비교, 6배 느림) 대신 LIKE — 영문 대문자가 섞인 이름은 후보에서 빠진다.
        # 느려지면 이름 조각 표 food_name_parts(part 색인)를 만들어 조각 = 키로 찾는다
        found = {}  # 한 행이 여러 묶음의 LIKE에 걸릴 수 있다('대파'는 '%대파%'·'%파%') — 코드로 한 번만
        for chunk in _chunks(like_keys, LIKE_CHUNK):
            patterns = [FoodNutrient.name.like("%" + k.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%", escape="\\")
                        for k in chunk]
            found.update((row.food_code, row) for row in FoodNutrient.query.filter(FoodNutrient.source != "ai", or_(*patterns)))
        for row in found.values():
            for part in set(name_parts(row.name)) & like_keys:
                self.candidates[part].append(row)

    def resolve(self, key):
        """결정 10·9(개정 1). 사용자 기억 → 자동 맞추기 → 찾아봤으면 AI 추정 → 아직 안 찾아봄."""
        match = self.matches.get(key)
        unit_grams = dict(self.weights.get(key, {}))
        food = None
        if match is not None:
            unit_grams.update((unit, (grams, "user")) for unit, grams in (match.unit_grams or {}).items())
            if match.food_code is None:
                food = self.foods.get(f"ai:{key}")
                state = "estimate" if food else "estimate_missing"
            else:
                food = self.foods.get(match.food_code)
                state = "matched" if food else "unmatched"
        elif (food := auto_match(key, self.candidates.get(key, [])) or self._fallback_match(key)) is not None:
            state = "auto"
        elif key in self.searched:
            food = self.foods.get(f"ai:{key}")
            state = "estimate" if food else "estimate_missing"
        else:
            if self.can_search is None:  # 안 찾아본 재료가 있을 때만 센다
                self.can_search = foods.fetch_allowed(self.user)
            state = "unsearched" if self.can_search else "unmatched"
        return {"key": key, "state": state, "food": _food_json(food) if food else None, "unit_grams": unit_grams}

    def _fallback_match(self, key):
        """전체 이름 후보가 하나도 없는 여러 낱말 재료만. '돼지고기 앞다리살' → '돼지고기' 후보 중 나머지 낱말마다
        앞이 같은 이름 조각(앞다리살·앞다리)이 있는 행으로 자동 맞추기. 없으면 None(지금처럼 추정 쪽)."""
        if self.candidates.get(key) or key not in self.fallbacks:
            return None
        fb, others = self.fallbacks[key]
        rows = [r for r in self.candidates.get(fb, [])
                if all(any(w.startswith(p) or p.startswith(w) for p in name_parts(r.name)) for w in others)]
        return auto_match(fb, rows)

    def recipe(self, recipe):
        resolved = {key: self.resolve(key) for key in {match_key(i["name"]) for i in recipe.ingredients} - {""}}
        return recipe_nutrition(recipe.ingredients, recipe.servings, resolved, self.can_estimate)


def _require_nutrition():
    if nutrition_mode(g.user) == "off":
        abort(503, OFF)


@bp.get("/recipes/<int:recipe_id>/nutrition")
@login_required
def recipe_nutrition_view(recipe_id):
    _require_nutrition()
    recipe = get_owned_or_404(Recipe, recipe_id)
    res = jsonify(NutritionContext(g.user, [recipe]).recipe(recipe))
    res.headers["Cache-Control"] = "no-store"  # 건강 정보
    return res


@bp.put("/food-matches")
@login_required
def put_food_match():
    _require_nutrition()
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "잘못된 요청이에요.")
    key = match_key(text(data.get("name"), "재료 이름은", 50))
    if not key:
        abort(400, "잘못된 요청이에요.")
    if "food_code" not in data:  # null은 추정으로 두기, 빠진 것은 잘못된 요청
        abort(400, "잘못된 요청이에요.")
    food_code = data["food_code"]
    if food_code is not None and (not isinstance(food_code, str) or foods.food_by_code(food_code) is None):
        abort(400, "식품을 다시 골라주세요.")
    unit = data.get("unit")
    grams = None
    if unit is not None:
        if not isinstance(unit, str) or not 1 <= len(unit.strip()) <= 10 or fixed_grams(unit.strip()) is not None:
            abort(400, "잘못된 요청이에요.")
        unit = unit.strip()
        grams = data.get("unit_grams")
        if grams is not None:
            if isinstance(grams, bool) or not isinstance(grams, (int, float)) or not math.isfinite(grams) or not 0.1 <= grams <= 5000:
                abort(400, WEIGHT_ERROR)
            grams = _round1(float(grams))

    match = FoodMatch.query.filter_by(user_id=g.user.id, ingredient_key=key).first()
    if match is None:
        if FoodMatch.query.filter_by(user_id=g.user.id).count() >= MAX_MATCHES:
            abort(400, f"식품은 {MAX_MATCHES}개까지 기억할 수 있어요.")
        match = FoodMatch(user_id=g.user.id, ingredient_key=key, unit_grams={})
        db.session.add(match)
    match.food_code = food_code
    if unit is not None:
        unit_grams = dict(match.unit_grams or {})  # 새 dict를 넣어야 JSON 칸 변경이 저장된다
        if grams is None:
            unit_grams.pop(unit, None)
        else:
            if unit not in unit_grams and len(unit_grams) >= MAX_UNITS:
                abort(400, "잘못된 요청이에요.")
            unit_grams[unit] = grams
        match.unit_grams = unit_grams
    commit_or_duplicate(SAVE_RACE)
    return "", 204


def _fill_recipe_ids(data):
    """1~31개의 서로 다른 bool 아닌 양의 정수(DB int 범위 안). 아니면 None."""
    ids = data.get("recipe_ids") if isinstance(data, dict) else None
    if not isinstance(ids, list) or not 1 <= len(ids) <= MAX_FILL_RECIPES or not all(type(i) is int and 0 < i < 2**31 for i in ids):
        return None
    return ids if len(set(ids)) == len(ids) else None


def _rows(user, recipes):
    context = NutritionContext(user, recipes)
    return [row for recipe in recipes for row in context.recipe(recipe)["ingredients"]]


@bp.post("/nutrition/fill")
@login_required
def fill_nutrition():
    """영양 채우기(스펙 21절, 결정 8·11·12·13). 계산 GET은 캐시만 읽고, 외부 요청·AI는 여기서만 한다."""
    _require_nutrition()
    ids = _fill_recipe_ids(request.get_json(silent=True))
    if ids is None:
        abort(400, "잘못된 요청이에요.")
    user = g.user
    # 찾기가 커밋할 때마다 객체가 만료돼 다시 읽지 않도록 쓸 값만 꺼내 둔다
    by_id = {r.id: SimpleNamespace(id=r.id, servings=r.servings, ingredients=r.ingredients)
             for r in Recipe.query.filter(Recipe.user_id == user.id, Recipe.id.in_(ids))}
    recipes = [by_id[i] for i in ids if i in by_id]

    # 1) 식품 DB 찾기: 아직 안 찾아본 재료 키마다 한 번, 한도·실패·시간 예산이면 조용히 멈춘다(결정 11·12)
    deadline = time.monotonic() + FILL_SECONDS
    rows = _rows(user, recipes)
    names = {}
    for row in rows:
        if row["pending_reason"] == "search":
            names.setdefault(row["key"], row["name"])
    for name in names.values():
        if time.monotonic() >= deadline:
            break
        first, *rest = search_terms(ingredient_key(name))
        if not foods.search_and_cache(first, user):
            break
        searched = FoodSearch.query.filter_by(query_key=foods.query_key(first)).first()
        if rest and searched is not None and searched.total == 0:
            if time.monotonic() >= deadline or not foods.search_and_cache(rest[0], user):
                break
    out_of_time = bool(names) and time.monotonic() >= deadline  # 찾기에 예산을 다 썼으면 AI는 다음 채우기에서(캐시에서 바로 AI로 간다)

    # 2) AI 추정: 단위 무게(키·단위로 중복 제거 60개)와 식품 영양(키로 중복 제거 30개)을 한 번에(결정 8)
    rows = [] if out_of_time else _rows(user, recipes)
    weights, food_names = {}, {}
    for row in rows:
        name = ingredient_key(row["name"])  # 괄호 속 설명('두부(3kg)')·줄바꿈은 모델에 보내지 않는다(공유 캐시에 남으므로)
        reason = row["pending_reason"]
        if reason == "food" and len(food_names) < MAX_FOOD_GUESSES:
            food_names.setdefault(row["key"], name)
        # 식품 추정을 기다리는 셀 수 있는 재료는 무게도 함께 묻는다(아니면 무게를 다음 채우기에서야 물어 계산 중으로 남는다)
        needs_weight = reason == "weight" or (reason == "food" and row["countable"] and row["unit_grams"] is None)
        if needs_weight and len(weights) < MAX_WEIGHT_GUESSES:
            weights.setdefault((row["key"], row["unit"]), (name, row["unit"]))
    if weights or food_names:
        weight_pairs, food_list = list(weights.values()), list(food_names.values())
        mode = estimate_mode(user)
        if mode == "sample":  # 키 없는 개발 모드 예시, 기록 없음
            store_guess(*clean_guess(ai.sample_nutrition_guess(weight_pairs, food_list), weight_pairs, food_list), "sample")
        elif mode == "on":
            _estimate(user, weight_pairs, food_list)

    # 3) 아직 계산 중인 레시피(요청 순서)
    context = NutritionContext(user, recipes)
    return jsonify(pending_recipe_ids=[r.id for r in recipes if context.recipe(r)["pending"]])


def _estimate(user, weight_pairs, food_list):
    """한도(하루 20번·체험 2번·60초 10번)나 AI 실패면 오류 없이 넘어간다(줄은 계산 중으로 남는다. 하루 한도는 estimate_mode가 먼저 off로 본다)."""
    try:
        scan.check_ai_limits(user.id, scan.NUTRITION_KINDS, daily_limit(user), "영양 추정은", burst=NUTRITION_BURST)
    except TooManyRequests:
        db.session.rollback()  # PostgreSQL 잠금을 푼다
        return
    call = scan.start_ai_call(user.id, "nutrition")
    try:
        raw, usage = ai.estimate_nutrition(weight_pairs, food_list)
    except ai.AiError:
        return
    scan.finish_ai_call(call, usage)
    store_guess(*clean_guess(raw, weight_pairs, food_list), "ai")
