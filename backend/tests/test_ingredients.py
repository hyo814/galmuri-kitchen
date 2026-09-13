from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError

import app.ingredients as ingredients_module
from app.ingredients import BULK_MAX, OLD_DAYS_BY_KIND, ingredient_status, matching_rule, seoul_today
from app.locations import INVALID_LOCATION, KINDS, choose_location, user_locations
from app.models import Ingredient, StorageLocation, User, db

TODAY = date(2026, 9, 13)


@pytest.mark.parametrize(
    "purchased, expires, expected",
    [
        (TODAY, TODAY + timedelta(days=3), "urgent"),
        (TODAY, TODAY + timedelta(days=4), "ok"),
        (TODAY, TODAY - timedelta(days=1), "urgent"),
        (TODAY - timedelta(days=30), TODAY + timedelta(days=10), "ok"),
        (TODAY - timedelta(days=7), None, "old"),
        (TODAY - timedelta(days=6), None, "ok"),
    ],
)
def test_ingredient_status(purchased, expires, expected):
    assert ingredient_status(purchased, expires, TODAY) == expected


@pytest.mark.parametrize(
    "kind, days, expected",
    [
        ("fridge", 6, "ok"),
        ("fridge", 7, "old"),
        ("freezer", 59, "ok"),
        ("freezer", 60, "old"),
        ("room", 400, "ok"),
    ],
)
def test_old_threshold_depends_on_location_kind(kind, days, expected):
    assert ingredient_status(TODAY - timedelta(days=days), None, TODAY, kind) == expected


@pytest.mark.parametrize(
    "days, expires_in, expected",
    [
        (24, None, "ok"),
        (25, None, "old"),
        (30, None, "danger"),
        (30, 10, "ok"),  # 입력한 소비기한이 품목 규칙보다 우선 (사용자 결정)
        (5, 1, "urgent"),  # 유통기한 임박이 품목 규칙보다 심각
    ],
)
def test_item_rule_status(days, expires_in, expected):
    expires = None if expires_in is None else TODAY + timedelta(days=expires_in)
    assert ingredient_status(TODAY - timedelta(days=days), expires, TODAY, "fridge", (25, 30)) == expected


def test_item_rule_replaces_location_kind_rule():
    assert ingredient_status(TODAY - timedelta(days=10), None, TODAY, "fridge", (25, 30)) == "ok"
    assert ingredient_status(TODAY - timedelta(days=31), None, TODAY, "room", (25, 30)) == "danger"


@pytest.mark.parametrize(
    "days, expected",
    [(30, "ok"), (60, "old")],
)
def test_freezer_ignores_item_rule(days, expected):
    # 냉동 위치는 품목 규칙을 무시하고 위치 종류 기준(60일)만 쓴다 (사용자 결정)
    assert ingredient_status(TODAY - timedelta(days=days), None, TODAY, "freezer", (25, 30)) == expected


def test_old_days_cover_all_location_kinds():
    assert set(OLD_DAYS_BY_KIND) == set(KINDS)


def test_matching_rule_picks_shortest_danger():
    rules = [
        SimpleNamespace(keyword="빵", warn_days=21, danger_days=24, id=1),
        SimpleNamespace(keyword="소시지", warn_days=41, danger_days=44, id=2),
    ]
    assert matching_rule("소시지빵", rules) == (21, 24)
    assert matching_rule("우유", rules) is None


def test_egg_rule_applied_and_sorted_first(client, login):
    login()
    today = seoul_today()
    create(client, name="우유", expires_on=today.isoformat())
    res = create(client, name="유정란 계란 10구", purchased_on=(today - timedelta(days=31)).isoformat())
    assert res.get_json()["status"] == "danger"
    assert client.get("/api/ingredients").get_json()[0]["name"] == "유정란 계란 10구"


def test_location_defaults_and_fields(client, login):
    login()
    freezer = client.get("/api/locations").get_json()[1]
    res = create(client, name="만두", purchased_on=(seoul_today() - timedelta(days=30)).isoformat(), location_id=freezer["id"])
    body = res.get_json()
    assert (body["location_name"], body["location_kind"], body["status"]) == ("냉동실", "freezer", "ok")

    body = create(client, name="우유").get_json()
    assert (body["location_name"], body["location_kind"]) == ("냉장실", "fridge")

    moved = client.patch(f"/api/ingredients/{body['id']}", json={"location_id": freezer["id"]}).get_json()
    assert (moved["location_id"], moved["location_name"]) == (freezer["id"], "냉동실")


def test_freezer_item_ignores_item_rule_via_api(client, login):
    login()
    freezer = client.get("/api/locations").get_json()[1]
    res = create(
        client,
        name="냉동 식빵",
        purchased_on=(seoul_today() - timedelta(days=25)).isoformat(),
        location_id=freezer["id"],
    )
    assert res.get_json()["status"] == "ok"


def test_expiry_date_wins_over_item_rule_via_api(client, login):
    login()
    res = create(
        client,
        name="계란",
        purchased_on=(seoul_today() - timedelta(days=31)).isoformat(),
        expires_on=(seoul_today() + timedelta(days=14)).isoformat(),
    )
    assert res.get_json()["status"] == "ok"


def create(client, **fields):
    body = {"name": "우유", "quantity": 1, "unit": "개", "purchased_on": seoul_today().isoformat(), **fields}
    return client.post("/api/ingredients", json=body)


def test_requires_login(client):
    assert client.get("/api/ingredients").status_code == 401


def test_create_and_list_sorted_by_urgency(client, login):
    login()
    today = seoul_today()
    create(client, name="계란")
    create(client, name="애호박", purchased_on=(today - timedelta(days=30)).isoformat())
    res = create(client, name="우유", expires_on=today.isoformat())
    assert res.status_code == 201
    assert res.get_json()["status"] == "urgent"

    items = client.get("/api/ingredients").get_json()
    assert [(i["name"], i["status"]) for i in items] == [("우유", "urgent"), ("애호박", "old"), ("계란", "ok")]
    assert items[0]["days_left"] == 0
    assert items[1]["days_since_purchase"] == 30
    assert items[2]["days_left"] is None


@pytest.mark.parametrize(
    "fields",
    [
        {"name": ""},
        {"name": "가" * 51},
        {"quantity": 0},
        {"quantity": "많이"},
        {"purchased_on": "2026-13-01"},
        {"purchased_on": None},
        {"expires_on": "내일"},
        {"name": 123},
        {"quantity": True},
        {"location_id": "1"},
        {"location_id": 2**70},
        {"unit": {"a": 1}},
        {"unit": "가" * 11},
    ],
)
def test_create_validation(client, login, fields):
    login()
    res = create(client, **fields)
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_update_partial_and_clear_expiry(client, login):
    login()
    item = create(client, expires_on="2030-01-01").get_json()
    res = client.patch(f"/api/ingredients/{item['id']}", json={"quantity": 2.5, "expires_on": None})
    assert res.status_code == 200
    body = res.get_json()
    assert (body["name"], body["quantity"], body["expires_on"]) == ("우유", 2.5, None)


def test_delete(client, login):
    login()
    item = create(client).get_json()
    assert client.delete(f"/api/ingredients/{item['id']}").status_code == 204
    assert client.get("/api/ingredients").get_json() == []


def test_other_users_ingredient_is_hidden(client, login):
    login("owner")
    item = create(client).get_json()
    login("intruder")
    assert client.get("/api/ingredients").get_json() == []
    assert client.patch(f"/api/ingredients/{item['id']}", json={"name": "x"}).status_code == 404
    assert client.delete(f"/api/ingredients/{item['id']}").status_code == 404


def test_patch_ingredient_to_other_users_location_rejected(client, login):
    login("owner")
    owner_location_id = client.get("/api/locations").get_json()[0]["id"]
    login("intruder")
    item = create(client).get_json()
    res = client.patch(f"/api/ingredients/{item['id']}", json={"location_id": owner_location_id})
    assert res.status_code == 400
    assert res.get_json()["error"] == INVALID_LOCATION


def test_deleting_user_cascades_ingredients(app):
    with app.app_context():
        user = User(provider="test", provider_id="cascade", nickname="x")
        db.session.add(user)
        db.session.commit()
        location = StorageLocation(user_id=user.id, name="냉장실", kind="fridge")
        db.session.add(location)
        db.session.commit()
        db.session.add(Ingredient(user_id=user.id, location_id=location.id, name="계란", purchased_on=date(2026, 1, 1)))
        db.session.commit()

        db.session.delete(user)
        db.session.commit()

        assert Ingredient.query.filter_by(user_id=user.id).count() == 0
        assert StorageLocation.query.filter_by(user_id=user.id).count() == 0


def test_seasoning_staple_skips_fridge_old_badge(client, login):
    login()
    old = (seoul_today() - timedelta(days=30)).isoformat()
    client.post("/api/staples", json={"name": "고추장", "category": "조미료"})
    client.post("/api/staples", json={"name": "굴소스", "category": "소스"})
    client.post("/api/staples", json={"name": "애호박", "category": "야채"})
    statuses = {name: create(client, name=name, purchased_on=old).get_json()["status"] for name in ["고추장", "굴소스", "애호박"]}
    assert statuses == {"고추장": "ok", "굴소스": "ok", "애호박": "old"}
    listed = {i["name"]: i["status"] for i in client.get("/api/ingredients").get_json()}
    assert listed == statuses


def test_seasoning_skip_does_not_catch_dishes_named_after_a_seasoning(client, login):
    login()
    old = (seoul_today() - timedelta(days=30)).isoformat()
    for name in ["고추장", "간장", "된장", "굴소스", "마요네즈"]:
        client.post("/api/staples", json={"name": name, "category": "조미료"})
    ok_names = ["청정원 순창 고추장 500g", "진간장 (500ml)", "초고추장", "굴소스"]
    old_names = ["고추장 불고기 500g", "간장 닭갈비", "된장 삼겹살", "굴소스 볶음밥", "참치마요네즈 샐러드"]
    statuses = {
        name: create(client, name=name, purchased_on=old).get_json()["status"] for name in ok_names + old_names
    }
    assert statuses == {**{n: "ok" for n in ok_names}, **{n: "old" for n in old_names}}


def bulk(client, *items):
    return client.post("/api/ingredients/bulk", json={"items": list(items)})


def test_bulk_requires_login(client):
    assert bulk(client, {"name": "대파"}).status_code == 401


def test_bulk_creates_items_in_given_or_default_locations(client, login):
    login()
    kinds = {l["kind"]: l["id"] for l in client.get("/api/locations").get_json()}
    today = seoul_today().isoformat()
    res = bulk(
        client,
        {"name": "대파", "quantity": 1, "unit": "단", "purchased_on": today},
        {"name": "냉동만두", "quantity": 1, "unit": "봉", "purchased_on": today, "location_id": kinds["freezer"]},
        {"name": "햇반", "quantity": 6, "unit": "개", "purchased_on": today, "expires_on": "2027-01-01", "location_id": kinds["room"]},
    )
    assert res.status_code == 201
    assert [(i["name"], i["quantity"], i["unit"], i["location_name"]) for i in res.get_json()] == [
        ("대파", 1, "단", "냉장실"),
        ("냉동만두", 1, "봉", "냉동실"),
        ("햇반", 6, "개", "실온"),
    ]
    assert {i["name"] for i in client.get("/api/ingredients").get_json()} == {"대파", "냉동만두", "햇반"}


def test_bulk_default_location_is_first_fridge_then_first_location(client, login):
    login()
    fridge = client.get("/api/locations").get_json()[0]
    today = seoul_today().isoformat()
    client.patch(f"/api/locations/{fridge['id']}", json={"kind": "room"})
    kimchi = client.post("/api/locations", json={"name": "김치냉장고", "kind": "fridge"}).get_json()
    assert bulk(client, {"name": "김치", "purchased_on": today}).get_json()[0]["location_name"] == "김치냉장고"
    client.patch(f"/api/locations/{kimchi['id']}", json={"kind": "freezer"})
    assert bulk(client, {"name": "쌀", "purchased_on": today}).get_json()[0]["location_name"] == "냉장실"


def test_bulk_rejects_other_users_location_and_creates_nothing(client, login):
    login("owner")
    owner_location_id = client.get("/api/locations").get_json()[0]["id"]
    login("intruder")
    today = seoul_today().isoformat()
    res = bulk(client, {"name": "대파", "purchased_on": today}, {"name": "우유", "purchased_on": today, "location_id": owner_location_id})
    assert res.status_code == 400
    assert res.get_json() == {"error": f"2번째 재료: {INVALID_LOCATION}", "errors": [{"index": 1, "error": INVALID_LOCATION}]}
    assert client.get("/api/ingredients").get_json() == []


def test_bulk_invalid_items_create_nothing_and_list_errors(client, login):
    login()
    today = seoul_today().isoformat()
    res = bulk(
        client,
        {"name": "대파", "purchased_on": today},
        {"name": "", "purchased_on": today},
        "우유",
        {"name": "두부", "quantity": 0, "purchased_on": today},
        {"name": "계란", "purchased_on": today, "location_id": True},
    )
    assert res.status_code == 400
    assert res.get_json() == {
        "error": "2번째 재료: 이름은 1~50자로 입력해주세요.",
        "errors": [
            {"index": 1, "error": "이름은 1~50자로 입력해주세요."},
            {"index": 2, "error": "잘못된 요청이에요."},
            {"index": 3, "error": "수량은 0보다 커야 해요."},
            {"index": 4, "error": INVALID_LOCATION},
        ],
    }
    assert client.get("/api/ingredients").get_json() == []


@pytest.mark.parametrize(
    "body",
    [None, {}, {"items": []}, {"items": "대파"}, {"items": [{"name": "대파", "purchased_on": "2026-09-13"}] * 51}],
)
def test_bulk_body_validation(client, login, body):
    login()
    res = client.post("/api/ingredients/bulk", json=body)
    assert (res.status_code, res.get_json()) == (400, {"error": "재료를 1~50개 보내주세요."})
    assert client.get("/api/ingredients").get_json() == []


def test_bulk_requires_fetch_header(raw_client):
    res = raw_client.post("/api/ingredients/bulk", json={"items": [{"name": "대파"}]})
    assert (res.status_code, res.get_json()) == (400, {"error": "잘못된 요청이에요."})


# --- Fix round 1 (G1-G5) ---


def test_bulk_avoids_n_plus_one_after_commit(client, login, app):
    # G1: to_json 결과를 flush 직후(만료 전)에 만들어 커밋 이후 N+1 조회가 없어야 한다.
    login()
    today = seoul_today().isoformat()
    items = [{"name": f"재료{i}", "purchased_on": today} for i in range(10)]
    with app.app_context():
        engine = db.engine
    statements = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.strip().upper())

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        res = bulk(client, *items)
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)

    assert res.status_code == 201
    seen_insert = False
    ingredient_selects_after_insert = 0
    for stmt in statements:
        if stmt.startswith("INSERT INTO INGREDIENTS"):
            seen_insert = True
        elif stmt.startswith("SELECT") and seen_insert and "INGREDIENTS" in stmt:
            ingredient_selects_after_insert += 1  # 만료된 속성 재조회(=N+1)가 있으면 여기 잡힌다
    assert ingredient_selects_after_insert == 0


def test_bulk_respects_per_user_ingredient_cap(client, login, monkeypatch):
    # G2: 사용자당 재료 2000개 상한(테스트는 값을 낮춰 확인) - 일괄 추가는 초과분이 있으면 전부 취소.
    monkeypatch.setattr(ingredients_module, "MAX_INGREDIENTS_PER_USER", 3)
    login()
    today = seoul_today().isoformat()
    bulk(client, {"name": "a", "purchased_on": today}, {"name": "b", "purchased_on": today})
    res = bulk(client, {"name": "c", "purchased_on": today}, {"name": "d", "purchased_on": today})
    assert res.status_code == 400
    assert res.get_json() == {"error": "재료는 3개까지 저장할 수 있어요. 다 쓴 재료를 정리해주세요."}
    assert len(client.get("/api/ingredients").get_json()) == 2


def test_create_respects_per_user_ingredient_cap(client, login, monkeypatch):
    # G2: 단건 생성도 상한에 걸리면 400.
    monkeypatch.setattr(ingredients_module, "MAX_INGREDIENTS_PER_USER", 3)
    login()
    today = seoul_today().isoformat()
    for _ in range(3):
        assert create(client, purchased_on=today).status_code == 201
    res = create(client, purchased_on=today)
    assert res.status_code == 400
    assert res.get_json() == {"error": "재료는 3개까지 저장할 수 있어요. 다 쓴 재료를 정리해주세요."}
    assert len(client.get("/api/ingredients").get_json()) == 3


def test_bulk_commit_failure_returns_friendly_error(client, login, monkeypatch):
    # G3: 커밋 실패(예: 검증 이후 위치가 바뀜)는 한국어 JSON 400으로 안내하고 아무것도 만들지 않는다.
    login()
    today = seoul_today().isoformat()

    def raise_integrity_error():
        raise IntegrityError("insert", {}, Exception("conflict"))

    monkeypatch.setattr(db.session, "commit", raise_integrity_error)
    res = bulk(client, {"name": "무", "purchased_on": today})
    assert res.status_code == 400
    assert res.get_json() == {"error": "선택한 보관 위치가 방금 바뀌었어요. 다시 시도해주세요."}
    monkeypatch.undo()
    assert client.get("/api/ingredients").get_json() == []


def test_bulk_rejects_non_int_location_id(client, login):
    # G4: choose_location도 owned_location처럼 bool/비-int location_id를 거부한다.
    login()
    fridge_id = client.get("/api/locations").get_json()[0]["id"]
    today = seoul_today().isoformat()
    res = bulk(
        client,
        {"name": "대파", "purchased_on": today, "location_id": float(fridge_id)},
        {"name": "우유", "purchased_on": today, "location_id": str(fridge_id)},
    )
    assert res.status_code == 400
    assert res.get_json()["errors"] == [
        {"index": 0, "error": INVALID_LOCATION},
        {"index": 1, "error": INVALID_LOCATION},
    ]
    assert client.get("/api/ingredients").get_json() == []


def test_bulk_exactly_max_items_creates_all(client, login):
    # G5: 정확히 상한(50)개면 전부 생성된다.
    login()
    today = seoul_today().isoformat()
    items = [{"name": f"재료{i}", "purchased_on": today} for i in range(BULK_MAX)]
    res = bulk(client, *items)
    assert res.status_code == 201
    assert len(res.get_json()) == BULK_MAX
    assert len(client.get("/api/ingredients").get_json()) == BULK_MAX


def test_bulk_response_matches_list_response_for_same_item(client, login):
    # G5: 일괄 추가 응답 항목은 같은 재료의 목록 API 응답과 같아야 한다.
    login()
    today = seoul_today().isoformat()
    created_item = bulk(client, {"name": "무", "quantity": 2, "unit": "개", "purchased_on": today}).get_json()[0]
    listed = {i["id"]: i for i in client.get("/api/ingredients").get_json()}
    assert created_item == listed[created_item["id"]]


def test_choose_location_prefers_first_fridge_when_multiple_exist(app):
    # G5: choose_location은 넘겨받은 목록의 순서를 그대로 쓴다(정렬은 user_locations의 책임).
    with app.app_context():
        user = User(provider="test", provider_id="tie", nickname="tie")
        db.session.add(user)
        db.session.commit()
        first = StorageLocation(user_id=user.id, name="A", kind="fridge", sort_order=0)
        second = StorageLocation(user_id=user.id, name="B", kind="fridge", sort_order=1)
        db.session.add_all([second, first])
        db.session.commit()
        assert choose_location(user_locations(user.id), None) is first


def test_bulk_49_valid_then_trailing_invalid_creates_nothing(client, login):
    # G5: 마지막 항목만 틀려도 전부 취소되고 오류는 index 49 하나뿐이다.
    login()
    today = seoul_today().isoformat()
    items = [{"name": f"재료{i}", "purchased_on": today} for i in range(49)] + [{"name": "", "purchased_on": today}]
    res = bulk(client, *items)
    assert res.status_code == 400
    assert res.get_json()["errors"] == [{"index": 49, "error": "이름은 1~50자로 입력해주세요."}]
    assert client.get("/api/ingredients").get_json() == []


# --- 3단계 T1: 미래 구입일 거부, 날짜 형식 ---

FUTURE_PURCHASE = "구입일은 오늘보다 뒤일 수 없어요."


def test_future_purchased_on_rejected_on_create_bulk_and_patch(client, login):
    login()
    today = seoul_today()
    tomorrow = (today + timedelta(days=1)).isoformat()
    res = create(client, purchased_on=tomorrow)
    assert (res.status_code, res.get_json()) == (400, {"error": FUTURE_PURCHASE})
    res = bulk(client, {"name": "대파", "purchased_on": today.isoformat()}, {"name": "우유", "purchased_on": tomorrow})
    assert res.get_json() == {"error": f"2번째 재료: {FUTURE_PURCHASE}", "errors": [{"index": 1, "error": FUTURE_PURCHASE}]}
    item = create(client, purchased_on=today.isoformat()).get_json()
    res = client.patch(f"/api/ingredients/{item['id']}", json={"purchased_on": tomorrow})
    assert (res.status_code, res.get_json()) == (400, {"error": FUTURE_PURCHASE})
    assert [i["purchased_on"] for i in client.get("/api/ingredients").get_json()] == [today.isoformat()]


@pytest.mark.parametrize("value", ["20260101", "2026-9-1", "2026-09-01T00:00", " 2026-09-01"])
def test_dates_must_be_yyyy_mm_dd(client, login, value):
    login()
    res = create(client, purchased_on=value)
    assert (res.status_code, res.get_json()) == (400, {"error": "구입일은 YYYY-MM-DD 형식으로 입력해주세요."})
    res = create(client, expires_on=value)
    assert (res.status_code, res.get_json()) == (400, {"error": "유통기한은 YYYY-MM-DD 형식으로 입력해주세요."})
