"""식약처 식품영양성분 DB(공공데이터포털 15127578) 요청과 공유 캐시(스펙 21절). 외부 요청은 outbound.fetch_fixed로만."""

import json
import math
import re
from collections import Counter
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

import click
from flask import Blueprint, abort, current_app, g, jsonify, request
from sqlalchemy import case, func
from sqlalchemy.exc import IntegrityError

from . import outbound
from .auth import login_required
from .ingredients import SEOUL, seoul_today
from .matching import normalize
from .models import AiCall, FoodNutrient, FoodSearch, PublicRecipe, db, utcnow

bp = Blueprint("foods", __name__, url_prefix="/api", cli_group=None)  # 명령은 `flask warm-food-nutrients`

ENDPOINT = "https://apis.data.go.kr/1471000/FoodNtrCpntDbInfo02/getFoodNtrCpntDbInq02"
ROWS_PER_PAGE = 100
MAX_PAGES = 3  # 1쪽 + 마지막 쪽 + (마지막 쪽이 짧으면) 그 앞쪽. Step 0b 실측: 원재료성 행이 결과 뒤쪽에 몰려 있다(스펙 21절 구현 세부)
FETCH_SECONDS = 5
REFRESH_AFTER = timedelta(days=30)
USER_DAILY_FETCHES, DEMO_DAILY_FETCHES, GLOBAL_DAILY_FETCHES = 300, 50, 8000
FETCH_BURST, FETCH_BURST_SECONDS = 20, 60  # 사용자마다 60초에 20번(식품 고르기 검색을 빨리 고쳐 쓸 때)
JAMO_ONLY = re.compile(r"[ㄱ-ㅣ]+")  # 한글 조합 중인 자모(ㄱ-ㅎ, ㅏ-ㅣ)뿐
FETCH_KIND = "food_fetch"  # ai_calls 기록(AI 호출 아님, 모델·토큰 없음). AI 한도·사용량에는 세지 않는다
MAX_QUERY = 30
SEARCH_LIMIT = 20
GROUP_ORDER = {"원재료성": 0, "가공식품": 1, "음식": 2}
OFF = "영양 계산을 지금은 쓸 수 없어요."
SAMPLE_FILE = Path(__file__).parent / "data" / "sample_foods.json"
# 실측(nutrition-api-research.md, Task 2 Step 0 재확인): AMT_NUM1 에너지·3 단백질·4 지방·6 탄수화물·7 당류·13 나트륨, 100g당.
# 코드 필드는 FOOD_CD로 실측 확인됨(Step 0). "두부"·"대파" 1쪽(100행) 표본에는 "음식"·"가공식품"만 있고 "원재료성"이 없었지만,
# Step 0b에서 결과 뒤쪽(마지막 쪽)에 원재료성 행(DB_GRP_CM "R1")이 몰려 있음을 확인했다(스펙 21절 구현 세부, _search_api 참고).
FIELDS = {"code": "FOOD_CD", "name": "FOOD_NM_KR", "group": "DB_GRP_NM", "basis": "SERVING_SIZE",
          "kcal": "AMT_NUM1", "protein_g": "AMT_NUM3", "fat_g": "AMT_NUM4", "carbs_g": "AMT_NUM6", "sugars_g": "AMT_NUM7", "sodium_mg": "AMT_NUM13"}
FIELDS["serving"] = "Z10500"  # 식품중량 '400g'. Task 1 Step 0 실측(결정 24) 확인: 값 모양은 '270.000g'처럼 소수도 온다
NUTRIENTS = ("kcal", "carbs_g", "protein_g", "fat_g", "sugars_g", "sodium_mg")
DISH_GROUP = "음식"
PACKAGED_GROUP = "가공식품"
MAX_SERVING_G = 5000


def nutrition_mode(user):
    """on: 키 있음 / sample: 키 없음 + 개발 모드(예시 식품) / off: 키 없음 + 운영(영양 칸 숨김). 체험 계정도 키가 있으면 on(하루 50번)."""
    if current_app.config["FOOD_NUTRITION_API_KEY"]:
        return "on"
    return "sample" if current_app.config["DEV_MODE"] else "off"


def food_name_key(name):
    """'돼지고기, 앞다리, 생것' → '돼지고기', '김치찌개_돼지고기' → '김치찌개'. 쉼표·밑줄 앞 첫 부분을 normalize, 60자."""
    return normalize(re.split(r"[,_]", name, maxsplit=1)[0])[:60]


def query_key(text):
    return normalize(text)[:60]


def name_parts(name):
    """DB 원문 이름을 '_'·','로 모두 나눠 각 조각을 normalize한 목록(빈 조각은 뺀다). Task 3 이름 부분 매칭용
    (`food_name_key`·`name_key` 칸은 그대로 첫 조각만 쓴다). matching.normalize는 괄호와 그 안 내용을 통째로 지우므로
    한 조각 안의 부연 설명은 사라진다: '파_대파_생것' → ['파', '대파', '생것'], '돼지고기_삼겹살(삼겹살)_생것' → ['돼지고기', '삼겹살', '생것']
    ('삼겹살(삼겹살)' → normalize가 '(삼겹살)'을 지워 '삼겹살'만 남는다)."""
    return [part for part in (normalize(piece) for piece in re.split(r"[,_]", name)) if part]


def _number(value):
    """0 이상 유한수만. bool·숫자 아님·음수·무한대는 None."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def serving_grams(value):
    """'400g'·'400 g'·'1,000g'·'250ml'(1ml=1g, 4b-2 결정 5)·400 → float. bool·못 읽음·1~5000 밖이면 None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        match = re.fullmatch(r"([\d,]+(?:\.\d+)?)\s*(g|ml)", value.strip().lower())
        if not match:
            return None
        number = float(match.group(1).replace(",", ""))
    else:
        return None
    return number if math.isfinite(number) and 1 <= number <= MAX_SERVING_G else None


def food_by_code(code):
    """먹은 기록이 쓰는 식품 한 행(source != 'ai'). 문자열이 아니거나 없으면 None."""
    if not isinstance(code, str) or not 1 <= len(code) <= 80:
        return None
    return FoodNutrient.query.filter(FoodNutrient.food_code == code, FoodNutrient.source != "ai").first()


def row_fields(item):
    """API 한 행 → FoodNutrient 칸 dict, 못 쓰면 None. 코드 1~80자·이름 1~100자·기준량 '100g'/'100ml'(공백·대소문자 무시)·kcal 숫자 필수.
    나머지 영양소는 숫자가 아니면 None('-'·''). 값은 0 이상 유한수만. group은 20자까지(없으면 '')."""
    code = item.get(FIELDS["code"])
    if not isinstance(code, str) or not 1 <= len(code) <= 80:
        return None
    name = item.get(FIELDS["name"])
    name = name.strip() if isinstance(name, str) else ""
    if not 1 <= len(name) <= 100:
        return None
    basis = item.get(FIELDS["basis"])
    basis = re.sub(r"\s+", "", basis).lower() if isinstance(basis, str) else ""
    if basis not in ("100g", "100ml"):
        return None
    kcal = _number(item.get(FIELDS["kcal"]))
    if kcal is None:
        return None
    group = item.get(FIELDS["group"])
    group = group.strip()[:20] if isinstance(group, str) else ""
    fields = {"food_code": code, "name": name, "name_key": food_name_key(name), "group_name": group, "kcal": kcal}
    for nutrient in NUTRIENTS[1:]:
        fields[nutrient] = _number(item.get(FIELDS[nutrient]))
    fields["serving_g"] = serving_grams(item.get(FIELDS["serving"]))
    return fields


def _total_count(value):
    """totalCount가 숫자 문자열이면 int, 아니면(불리언 포함) 0."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def fetch_page(key, name, page):
    """(행 dict 목록, totalCount). serviceKey는 Decoding 키를 인코딩하지 않고 주소에 그대로 붙인다(조사 문서: 다시 인코딩하면 403).
    header.resultCode가 '00'이 아니면 FetchError('ResultCode'). body.items는 목록 또는 {'item': 한 행 또는 목록}.
    응답 모양이 기대와 다르면(header·body가 dict가 아니거나 없음 등) ValueError."""
    body, _ = outbound.fetch_fixed(f"{ENDPOINT}?serviceKey={key}",
                                    params={"FOOD_NM_KR": name, "type": "json", "numOfRows": ROWS_PER_PAGE, "pageNo": page},
                                    seconds=FETCH_SECONDS)
    try:
        data = json.loads(body)
        header = data["header"]
        if header.get("resultCode") != "00":
            raise outbound.FetchError("ResultCode")
        result_body = data["body"]
        items = result_body.get("items")
        total = result_body.get("totalCount")
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        raise ValueError(type(e).__name__) from None
    if isinstance(items, dict):
        value = items.get("item")
        items = value if isinstance(value, list) else ([value] if value is not None else [])
    return (items if isinstance(items, list) else []), _total_count(total)


def _aware(value):
    """SQLite는 시간대 없이 돌려준다. app.videos의 같은 관례: 없으면 UTC로 본다."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _day_bounds(day):
    start = datetime.combine(day, time.min, tzinfo=SEOUL).astimezone(timezone.utc)
    return start, start + timedelta(days=1)


def _fetches_between(start, end, user_id=None):
    query = AiCall.query.filter(AiCall.kind == FETCH_KIND, AiCall.created_at >= start, AiCall.created_at < end)
    if user_id is not None:
        query = query.filter(AiCall.user_id == user_id)
    return query.count()


def fetch_allowed(user):
    """오늘(서울) food_fetch 기록이 사용자 한도(체험 50·그 외 300, user None이면 CLI라 사용자 한도 없음)·전체 8,000 미만인지."""
    # ponytail: 세고 부르기라 동시에 온 요청 몇 개만큼 한도를 넘을 수 있다(coupang.py GLOBAL_HOURLY의 여유와 같은 종류의 문제).
    start, end = _day_bounds(seoul_today())
    if _fetches_between(start, end) >= GLOBAL_DAILY_FETCHES:
        return False
    if user is None:
        return True
    limit = DEMO_DAILY_FETCHES if user.provider == "demo" else USER_DAILY_FETCHES
    return _fetches_between(start, end, user.id) < limit


def _burst_allowed(user):
    """지난 60초 이 사용자의 food_fetch가 FETCH_BURST 미만인지(CLI는 사용자 없음이라 세지 않는다). fetch_allowed와 따로 두어
    영양 계산(NutritionContext)이 잠깐의 연속 한도로 안 찾아본 재료를 고르기로 바꾸지 않게 한다."""
    now = utcnow()
    return user is None or _fetches_between(now - timedelta(seconds=FETCH_BURST_SECONDS), now, user.id) < FETCH_BURST


def _upsert_food(fields, source, now):
    row = FoodNutrient.query.filter_by(food_code=fields["food_code"]).first()
    if row is None:
        db.session.add(FoodNutrient(**fields, source=source, fetched_at=now))
    else:
        for key, value in fields.items():
            setattr(row, key, value)
        row.fetched_at = now


def _upsert_search(key, total, now):
    row = FoodSearch.query.filter_by(query_key=key).first()
    if row is None:
        db.session.add(FoodSearch(query_key=key, total=total, searched_at=now))
    else:
        row.total, row.searched_at = total, now


def _search_sample(key):
    """SAMPLE_FILE에서 name_key가 같거나 이름에 검색어(key)가 든 행만 넣고 기록한다(외부 요청·ai_calls 없음)."""
    try:
        rows = json.loads(SAMPLE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    matched = [
        row for row in rows
        if isinstance(row, dict) and isinstance(row.get("name"), str) and (food_name_key(row["name"]) == key or key in normalize(row["name"]))
    ]
    now = utcnow()
    try:
        for row in matched:
            fields = {
                "food_code": row["food_code"], "name": row["name"][:100], "name_key": food_name_key(row["name"]),
                "group_name": (row.get("group") or "")[:20], "kcal": float(row["kcal"]),
            }
            for nutrient in NUTRIENTS[1:]:
                value = row.get(nutrient)
                fields[nutrient] = float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
            fields["serving_g"] = serving_grams(row.get("serving_g"))
            _upsert_food(fields, "sample", now)
        _upsert_search(key, len(matched), now)
        db.session.commit()
    except IntegrityError:  # 동시에 같은 행을 다른 요청이 먼저 넣었다(.first()의 autoflush 중일 수도 있다)
        db.session.rollback()
    return True


def _search_api(key, user):
    """on 모드는 쪽마다 fetch_allowed 확인 → AiCall(kind=food_fetch, model=None, demo) 커밋 → fetch_page(key를 검색어로).
    Step 0b 실측(결정 11): 원재료성 행은 필터가 없어 결과 뒤쪽에 몰려 있다(예: 돼지고기는 마지막 쪽 전체, 대파는 마지막 쪽 끝 1행).
    그래서 1쪽은 항상 받고, total이 ROWS_PER_PAGE보다 크면 마지막 쪽(ceil(total/ROWS_PER_PAGE))도 받는다. 마지막 쪽 번호가
    3 이상이고 그 쪽이 짧으면(50개 미만) 원재료성 구간이 그 앞쪽까지 걸쳐 있을 수 있어 그 앞쪽도 받는다(최대 MAX_PAGES쪽).
    뒤쪽 쪽이 한도·실패로 막히면 이미 받은 행은 그대로 캐시에 넣되 food_searches는 남기지 않아(다음에 다시 찾도록) False."""
    api_key = current_app.config["FOOD_NUTRITION_API_KEY"]
    demo = user is not None and user.provider == "demo"
    fetched = [0]

    def fetch(page):
        if fetched[0] >= MAX_PAGES or not fetch_allowed(user) or not _burst_allowed(user):
            return None
        fetched[0] += 1
        db.session.add(AiCall(user_id=user.id if user else None, kind=FETCH_KIND, model=None, demo=demo, created_at=utcnow()))
        db.session.commit()
        try:
            return fetch_page(api_key, key, page)
        except (outbound.FetchError, ValueError) as e:
            current_app.logger.warning("food fetch failed: %s", type(e).__name__)  # 이유 이름만(주소·키 없음)
            return None

    def store(collected, total=None):
        """collected를 upsert하고, total을 주면(성공) food_searches도 upsert한다. 동시에 같은 행이 들어가 겹치면
        (.first()의 autoflush 중일 수도 있다) 롤백한다(다른 요청이 먼저 넣었다는 뜻이라 다시 시도할 필요 없다)."""
        now = utcnow()
        try:
            for item in collected:
                fields = row_fields(item)
                if fields is not None:
                    _upsert_food(fields, "api", now)
            if total is not None:
                _upsert_search(key, total, now)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()

    result = fetch(1)
    if result is None:
        return False
    items, total = result
    collected = [item for item in items if isinstance(item, dict)]

    if total > ROWS_PER_PAGE:
        last_page = math.ceil(total / ROWS_PER_PAGE)
        result = fetch(last_page)
        if result is None:
            store(collected)  # 1쪽은 살리고, 검색 기록은 남기지 않아 다음에 다시 찾는다
            return False
        last_items = [item for item in result[0] if isinstance(item, dict)]
        collected.extend(last_items)
        if last_page >= 3 and len(last_items) < 50:
            result = fetch(last_page - 1)
            if result is None:
                store(collected)
                return False
            collected.extend(item for item in result[0] if isinstance(item, dict))

    store(collected, total)
    return True


def search_and_cache(name, user):
    """이름 하나를 찾아 food_nutrients에 넣는다. API 검색어·food_searches 키·search_items의 LIKE 키를 모두
    query_key(name)으로 통일한다(공백·괄호 정리, 계란→달걀 같은 동의어가 세 곳 다 같은 이름으로 적용된다).
    이미 찾아봤고 30일 안이면 부르지 않는다. 찾았거나 이미 있으면 True, 자모뿐인 이름('ㄷ')·한도(하루·60초 20번)·실패로 못 찾았으면 False
    (찾아본 기록을 남기지 않아 다음에 다시 찾는다)."""
    key = query_key(name)
    if not key or JAMO_ONLY.fullmatch(key):
        return False
    existing = FoodSearch.query.filter_by(query_key=key).first()
    if existing is not None and _aware(existing.searched_at) >= utcnow() - REFRESH_AFTER:
        return True
    if nutrition_mode(user) == "sample":
        return _search_sample(key)
    return _search_api(key, user)


def search_items(q):
    """캐시에서 이름에 query_key(q)가 든 행(source != 'ai') 200개까지(원재료성이 먼저 오도록 SQL에서 정렬해 200개 안에서
    밀려나지 않게 함) → 파이썬에서 다시 정렬 (query_key(q)가 name_parts(이름)에 없음, GROUP_ORDER(없으면 3), 이름 길이, 이름)
    → 앞 20개 [{food_code, name, group, kcal}] (kcal은 정수 반올림). LIKE도 search_and_cache와 같은 정규화한 키로 찾는다
    (계란으로 찾아도 "달걀…" 캐시 행을 본다)."""
    key = query_key(q)
    escaped = key.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    raw_first = case((FoodNutrient.group_name == "원재료성", 0), else_=1)
    rows = (
        FoodNutrient.query.filter(FoodNutrient.source != "ai", func.lower(FoodNutrient.name).like(f"%{escaped}%", escape="\\"))  # 한 키만 찾는 곳이라 영문 대문자 이름(CGV…)도 찾게 lower
        .order_by(raw_first)
        .limit(200)
        .all()
    )
    rows.sort(key=lambda row: (key not in name_parts(row.name), GROUP_ORDER.get(row.group_name, 3), len(row.name), row.name))
    return [{"food_code": r.food_code, "name": r.name, "group": r.group_name, "kcal": round(r.kcal)} for r in rows[:SEARCH_LIMIT]]


def dish_items(q):
    """search_items와 같은 key = query_key(q)로 캐시에서 사 먹은 음식 후보를 찾는다: 음식(DISH_GROUP)과 가공식품 행(source != 'ai').
    이름은 소문자·공백을 뺀 값에 LIKE(`돼지고기덮밥`으로 `돼지고기 덮밥`도). 식약처 음식 이름은 `덮밥_돼지고기(제육)` 모양이라
    `제육덮밥`은 편의점 제품 같은 가공식품에만 있는 경우가 많아 가공식품도 뒤에 보여준다(2026-09-15 실측).
    음식 먼저 200개까지 → (key가 name_parts(이름)에 없음, 음식 먼저, 이름 길이, 이름) → 앞 SEARCH_LIMIT개.
    [{food_code, name, group, serving_g, kcal, carbs_g, protein_g, fat_g, sugars_g, sodium_mg}] — 100g당 원값(화면이 양으로 곱한다)."""
    key = query_key(q)
    escaped = key.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    rows = (
        FoodNutrient.query.filter(
            FoodNutrient.source != "ai", FoodNutrient.group_name.in_((DISH_GROUP, PACKAGED_GROUP)),
            func.replace(func.lower(FoodNutrient.name), " ", "").like(f"%{escaped}%", escape="\\"),  # 키 하나만 찾는 곳
        )
        .order_by(case((FoodNutrient.group_name == DISH_GROUP, 0), else_=1))
        .limit(200)
        .all()
    )
    rows.sort(key=lambda row: (key not in name_parts(row.name), row.group_name != DISH_GROUP, len(row.name), row.name))
    return [
        {
            "food_code": r.food_code, "name": r.name, "group": r.group_name, "serving_g": r.serving_g, "kcal": r.kcal,
            "carbs_g": r.carbs_g, "protein_g": r.protein_g, "fat_g": r.fat_g, "sugars_g": r.sugars_g, "sodium_mg": r.sodium_mg,
        }
        for r in rows[:SEARCH_LIMIT]
    ]


@bp.get("/foods/search")
@login_required
def search_foods():
    mode = nutrition_mode(g.user)
    if mode == "off":
        abort(503, OFF)
    q = (request.args.get("q") or "").strip()[:MAX_QUERY]
    if not query_key(q):  # 정규화하면 빈 문자열(공백·괄호뿐인 입력 포함)
        abort(400, "찾을 식품 이름을 입력해주세요.")
    # 한 글자는 캐시만 찾는다(입력 중 '돼'마다 부르지 않게). 채우기는 search_and_cache로 '파'·'무' 같은 한 글자 재료도 찾는다
    searched = len(query_key(q)) >= 2 and search_and_cache(q, g.user)
    items = search_items(q)
    return jsonify(items=items, searched=searched)


@bp.get("/foods/dishes")
@login_required
def search_dishes():
    mode = nutrition_mode(g.user)
    if mode == "off":
        abort(503, OFF)
    q = (request.args.get("q") or "").strip()[:MAX_QUERY]
    if not query_key(q):  # 정규화하면 빈 문자열(공백·괄호뿐인 입력 포함)
        abort(400, "찾을 음식 이름을 입력해주세요.")
    searched = search_and_cache(q, g.user)
    items = dish_items(q)
    return jsonify(items=items, searched=searched)


@bp.cli.command("warm-food-nutrients")
@click.option("--limit", default=300, type=click.IntRange(1, 2000))
def warm_food_nutrients(limit):
    """PublicRecipe.ingredient_keys를 모두 세어 많은 순 N개를 search_and_cache(name, None)으로 찾아본다."""
    if not current_app.config["FOOD_NUTRITION_API_KEY"]:
        raise click.ClickException("FOOD_NUTRITION_API_KEY가 없어요.")
    counter = Counter()
    for (keys,) in db.session.query(PublicRecipe.ingredient_keys):
        counter.update(key for key in (keys or []) if key)
    names = [name for name, _ in counter.most_common(limit)]
    done = 0
    for name in names:
        if not search_and_cache(name, None):
            break
        done += 1
    if done == len(names):
        click.echo(f"식품 이름 {done}개를 찾아봤어요.")
    elif not fetch_allowed(None):
        click.echo(f"식품 이름 {done}개를 찾아봤어요. 한도 때문에 {len(names) - done}개는 다음에 찾아요.")
    else:
        click.echo(f"식품 이름 {done}개를 찾아봤어요. 요청이 실패해 {len(names) - done}개는 다음에 찾아요.")
