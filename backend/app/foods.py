"""식약처 식품영양성분 DB(공공데이터포털 15127578) 요청과 공유 캐시(스펙 21절). 외부 요청은 outbound.fetch_fixed로만."""

import json
import math
import re
from collections import Counter
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

import click
from flask import Blueprint, abort, current_app, g, jsonify, request
from sqlalchemy.exc import IntegrityError

from . import outbound
from .auth import login_required
from .ingredients import SEOUL, seoul_today
from .matching import normalize
from .models import AiCall, FoodNutrient, FoodSearch, PublicRecipe, db, utcnow

bp = Blueprint("foods", __name__, url_prefix="/api", cli_group=None)  # 명령은 `flask warm-food-nutrients`

ENDPOINT = "https://apis.data.go.kr/1471000/FoodNtrCpntDbInfo02/getFoodNtrCpntDbInq02"
ROWS_PER_PAGE = 100
MAX_PAGES = 2
FETCH_SECONDS = 5
REFRESH_AFTER = timedelta(days=30)
USER_DAILY_FETCHES, DEMO_DAILY_FETCHES, GLOBAL_DAILY_FETCHES = 300, 50, 8000
FETCH_KIND = "food_fetch"  # ai_calls 기록(AI 호출 아님, 모델·토큰 없음). AI 한도·사용량에는 세지 않는다
MAX_QUERY = 30
SEARCH_LIMIT = 20
GROUP_ORDER = {"원재료성": 0, "가공식품": 1, "음식": 2}
OFF = "영양 계산을 지금은 쓸 수 없어요."
SAMPLE_FILE = Path(__file__).parent / "data" / "sample_foods.json"
# 실측(nutrition-api-research.md, Task 2 Step 0 재확인): AMT_NUM1 에너지·3 단백질·4 지방·6 탄수화물·7 당류·13 나트륨, 100g당.
# 코드 필드는 FOOD_CD로 실측 확인됨(Step 0). DB_GRP_NM은 "두부"·"대파" 각 100행 표본에서 "음식"·"가공식품"만 관측되고
# "원재료성" 행은 관측되지 않았다(스펙 21절 구현 세부에 기록).
FIELDS = {"code": "FOOD_CD", "name": "FOOD_NM_KR", "group": "DB_GRP_NM", "basis": "SERVING_SIZE",
          "kcal": "AMT_NUM1", "protein_g": "AMT_NUM3", "fat_g": "AMT_NUM4", "carbs_g": "AMT_NUM6", "sugars_g": "AMT_NUM7", "sodium_mg": "AMT_NUM13"}
NUTRIENTS = ("kcal", "carbs_g", "protein_g", "fat_g", "sugars_g", "sodium_mg")


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


def _number(value):
    """0 이상 유한수만. bool·숫자 아님·음수·무한대는 None."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


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
    return fields


def fetch_page(key, name, page):
    """(행 dict 목록, totalCount). serviceKey는 Decoding 키를 인코딩하지 않고 주소에 그대로 붙인다(조사 문서: 다시 인코딩하면 403).
    header.resultCode가 '00'이 아니면 FetchError('ResultCode'). body.items는 목록 또는 {'item': …}."""
    body, _ = outbound.fetch_fixed(f"{ENDPOINT}?serviceKey={key}",
                                    params={"FOOD_NM_KR": name, "type": "json", "numOfRows": ROWS_PER_PAGE, "pageNo": page},
                                    seconds=FETCH_SECONDS)
    try:
        data = json.loads(body)
        header, result_body = data["header"], data["body"]
        items = result_body.get("items")
        total = result_body.get("totalCount")
    except (ValueError, KeyError, TypeError) as e:
        raise ValueError(type(e).__name__) from None
    if header.get("resultCode") != "00":
        raise outbound.FetchError("ResultCode")
    if isinstance(items, dict):
        items = [items["item"]] if "item" in items else []
    return (items if isinstance(items, list) else []), (total if isinstance(total, int) else 0)


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
    start, end = _day_bounds(seoul_today())
    if _fetches_between(start, end) >= GLOBAL_DAILY_FETCHES:
        return False
    if user is None:
        return True
    limit = DEMO_DAILY_FETCHES if user.provider == "demo" else USER_DAILY_FETCHES
    return _fetches_between(start, end, user.id) < limit


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


def _has_exact(items, key):
    return any(isinstance(item, dict) and normalize(item.get(FIELDS["name"]) or "") == key for item in items)


def _search_sample(key, name):
    """SAMPLE_FILE에서 name_key가 같거나 이름에 검색어가 든 행만 넣고 기록한다(외부 요청·ai_calls 없음)."""
    try:
        rows = json.loads(SAMPLE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    matched = [
        row for row in rows
        if isinstance(row, dict) and isinstance(row.get("name"), str) and (food_name_key(row["name"]) == key or key in normalize(row["name"]))
    ]
    now = utcnow()
    for row in matched:
        fields = {
            "food_code": row["food_code"], "name": row["name"][:100], "name_key": food_name_key(row["name"]),
            "group_name": (row.get("group") or "")[:20], "kcal": float(row["kcal"]),
        }
        for nutrient in NUTRIENTS[1:]:
            value = row.get(nutrient)
            fields[nutrient] = float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
        _upsert_food(fields, "sample", now)
    _upsert_search(key, len(matched), now)
    db.session.commit()
    return True


def _search_api(key, name, user):
    """on 모드는 쪽마다 fetch_allowed 확인 → AiCall(kind=food_fetch, model=None, demo) 커밋 → fetch_page.
    1쪽 total이 ROWS_PER_PAGE보다 크고 normalize(행 이름) == query_key(name)인 행이 없으면 2쪽(MAX_PAGES까지)."""
    api_key = current_app.config["FOOD_NUTRITION_API_KEY"]
    demo = user is not None and user.provider == "demo"
    collected, total = [], 0
    for page in range(1, MAX_PAGES + 1):
        if page > 1 and not (total > ROWS_PER_PAGE and not _has_exact(collected, key)):
            break
        if not fetch_allowed(user):
            return False
        db.session.add(AiCall(user_id=user.id if user else None, kind=FETCH_KIND, model=None, demo=demo, created_at=utcnow()))
        db.session.commit()
        try:
            items, total = fetch_page(api_key, name, page)
        except (outbound.FetchError, ValueError) as e:
            current_app.logger.warning("food fetch failed: %s", type(e).__name__)  # 이유 이름만(주소·키 없음)
            return False
        collected.extend(item for item in items if isinstance(item, dict))

    now = utcnow()
    for item in collected:
        fields = row_fields(item)
        if fields is not None:
            _upsert_food(fields, "api", now)
    _upsert_search(key, total, now)
    try:
        db.session.commit()
    except IntegrityError:  # 동시에 같은 행을 다른 요청이 먼저 넣었다
        db.session.rollback()
    return True


def search_and_cache(name, user):
    """이름 하나를 찾아 food_nutrients에 넣는다. 이미 찾아봤고 30일 안이면 부르지 않는다. 찾았거나 이미 있으면 True,
    한도·실패로 못 찾았으면 False(찾아본 기록을 남기지 않아 다음에 다시 찾는다)."""
    key = query_key(name)
    if not key:
        return False
    existing = FoodSearch.query.filter_by(query_key=key).first()
    if existing is not None and _aware(existing.searched_at) >= utcnow() - REFRESH_AFTER:
        return True
    if nutrition_mode(user) == "sample":
        return _search_sample(key, name)
    return _search_api(key, name, user)


def search_items(q):
    """캐시에서 이름에 q가 든 행(source != 'ai') 200개까지 → 정렬 (normalize(이름) != query_key(q), GROUP_ORDER(없으면 3), 이름 길이, 이름)
    → 앞 20개 [{food_code, name, group, kcal}] (kcal은 정수 반올림)."""
    key = query_key(q)
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    rows = (
        FoodNutrient.query.filter(FoodNutrient.source != "ai", FoodNutrient.name.ilike(f"%{escaped}%", escape="\\")).limit(200).all()
    )
    rows.sort(key=lambda row: (normalize(row.name) != key, GROUP_ORDER.get(row.group_name, 3), len(row.name), row.name))
    return [{"food_code": r.food_code, "name": r.name, "group": r.group_name, "kcal": round(r.kcal)} for r in rows[:SEARCH_LIMIT]]


@bp.get("/foods/search")
@login_required
def search_foods():
    mode = nutrition_mode(g.user)
    if mode == "off":
        abort(503, OFF)
    q = (request.args.get("q") or "").strip()
    if not q:
        abort(400, "찾을 식품 이름을 입력해주세요.")
    q = q[:MAX_QUERY]
    searched = search_and_cache(q, g.user)
    items = search_items(q)
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
    if done < len(names):
        click.echo(f"식품 이름 {done}개를 찾아봤어요. 한도 때문에 {len(names) - done}개는 다음에 찾아요.")
    else:
        click.echo(f"식품 이름 {done}개를 찾아봤어요.")
