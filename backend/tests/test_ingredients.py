from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.ingredients import OLD_DAYS_BY_KIND, ingredient_status, matching_rule, seoul_today
from app.locations import INVALID_LOCATION, KINDS
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
