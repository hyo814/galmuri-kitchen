from datetime import datetime, timedelta, timezone

import pytest

from app import ingredients as ingredients_module
from app import shopping
from app.ingredients import seoul_today
from app.models import Ingredient, ShoppingItem, StorageLocation, User, db

INVALID_LOCATION = "보관 위치를 다시 선택해주세요."
CAP_ERROR = "장보기 목록은 300개까지 담을 수 있어요. 필요 없는 항목을 빼주세요."


def add(client, **body):
    return client.post("/api/shopping/items", json={"name": "두부", **body})


def snapshot(client):
    res = client.get("/api/shopping")
    assert res.status_code == 200
    assert res.headers["Cache-Control"] == "no-store"
    return res.get_json()


def iso(when):
    return when.isoformat()


def test_requires_login_and_csrf(client, raw_client, login):
    assert client.get("/api/shopping").status_code == 401
    login()
    res = raw_client.post("/api/shopping/items", json={"name": "두부"})
    assert res.status_code == 400
    assert res.get_json() == {"error": "잘못된 요청이에요."}


def test_snapshot_splits_items_and_recent_stocked_and_purges_old(client, login, app):
    user = login()
    first = add(client, name="두부").get_json()
    second = add(client, name="대파").get_json()
    now = datetime.now(timezone.utc)
    with app.app_context():
        recent = ShoppingItem(user_id=user.id, name="우유", stocked_at=now - timedelta(days=3))
        older = ShoppingItem(user_id=user.id, name="계란", stocked_at=now - timedelta(days=1))
        old = ShoppingItem(user_id=user.id, name="양파", stocked_at=now - timedelta(days=8))
        db.session.add_all([recent, older, old])
        db.session.commit()
        old_id = old.id
    login("other")
    add(client, name="남의 두부")
    with client.session_transaction() as s:
        s["user_id"], s["pid"] = user.id, user.provider_id

    body = snapshot(client)
    assert [i["id"] for i in body["items"]] == [first["id"], second["id"]]
    assert [i["name"] for i in body["stocked"]] == ["계란", "우유"]
    assert body["notes"] == []
    assert body["today"] == seoul_today().isoformat()
    with app.app_context():
        assert db.session.get(ShoppingItem, old_id) is None


def test_create_defaults(client, login):
    login()
    res = add(client)
    assert res.status_code == 201
    item = res.get_json()
    assert {k: item[k] for k in ("name", "quantity", "unit", "planned_on", "location_id", "location_name", "source", "source_label", "done_at", "done_changed_at", "stocked_at", "client_id")} == {
        "name": "두부",
        "quantity": 1,
        "unit": "개",
        "planned_on": None,
        "location_id": None,
        "location_name": None,
        "source": "manual",
        "source_label": None,
        "done_at": None,
        "done_changed_at": None,
        "stocked_at": None,
        "client_id": None,
    }

    fridge = client.get("/api/locations").get_json()[0]
    res = client.post(
        "/api/shopping/items",
        json={"name": " 두부 ", "quantity": 2, "unit": "모", "planned_on": "2026-09-14", "location_id": fridge["id"], "source": "recipe", "source_label": "두부조림", "client_id": "a1-B2"},
    )
    item = res.get_json()
    assert (item["name"], item["quantity"], item["unit"], item["planned_on"], item["location_name"], item["source"], item["source_label"], item["client_id"]) == (
        "두부",
        2,
        "모",
        "2026-09-14",
        "냉장실",
        "recipe",
        "두부조림",
        "a1-B2",
    )


@pytest.mark.parametrize(
    "body, error",
    [
        ({"name": ""}, "이름은 1~50자로 입력해주세요."),
        ({"name": "가" * 51}, "이름은 1~50자로 입력해주세요."),
        ({"quantity": 0}, "수량은 0보다 커야 해요."),
        ({"quantity": True}, "수량은 0보다 커야 해요."),
        ({"quantity": "1"}, "수량은 0보다 커야 해요."),
        ({"quantity": 10**400}, "수량은 0보다 커야 해요."),
        ({"location_id": 2147483647}, INVALID_LOCATION),
        ({"unit": "가" * 11}, "단위는 1~10자로 입력해주세요."),
        ({"source": "ai"}, "잘못된 요청이에요."),
        ({"source_label": "가" * 61}, "출처 이름은 1~60자로 입력해주세요."),
        ({"planned_on": "2026/09/14"}, "날짜 형식이 올바르지 않아요."),
        ({"client_id": "a" * 37}, "잘못된 요청이에요."),
        ({"client_id": "a b"}, "잘못된 요청이에요."),
        ({"client_id": ""}, "잘못된 요청이에요."),
    ],
)
def test_create_validation(client, login, body, error):
    login()
    res = add(client, **body)
    assert res.status_code == 400
    assert res.get_json() == {"error": error}


@pytest.mark.parametrize("raw", ['{"name": "두부", "quantity": NaN}', '{"name": "두부", "quantity": 1e999}'])
def test_create_rejects_raw_nan_and_infinite_quantity(client, login, raw):
    login()
    res = client.post("/api/shopping/items", data=raw, content_type="application/json")
    assert res.status_code == 400
    assert res.get_json() == {"error": "수량은 0보다 커야 해요."}


def test_create_boundaries_and_blank_defaults(client, login):
    login()
    item = add(client, name="가" * 50, unit="", source_label="   ").get_json()
    assert (len(item["name"]), item["unit"], item["source_label"]) == (50, "개", None)


def test_create_rejects_other_users_location(client, login):
    login("owner")
    location_id = client.get("/api/locations").get_json()[0]["id"]
    login("intruder")
    res = add(client, location_id=location_id)
    assert res.status_code == 400
    assert res.get_json() == {"error": INVALID_LOCATION}
    res = client.post("/api/shopping/items/bulk", json={"source": "recipe", "items": [{"name": "우유"}, {"name": "두부", "location_id": location_id}]})
    assert res.status_code == 400
    assert res.get_json() == {"error": f"2번째 재료: {INVALID_LOCATION}", "errors": [{"index": 1, "error": INVALID_LOCATION}]}
    item = add(client).get_json()
    res = client.patch(f"/api/shopping/items/{item['id']}", json={"location_id": location_id})
    assert res.status_code == 400
    assert res.get_json() == {"error": INVALID_LOCATION}


def test_offline_add_keeps_item_when_location_is_gone(client, login):
    login("owner")
    others = client.get("/api/locations").get_json()[0]["id"]
    login()
    room = client.get("/api/locations").get_json()[-1]["id"]
    assert client.delete(f"/api/locations/{room}").status_code == 204

    assert add(client, location_id=room).status_code == 400  # 온라인(client_id 없음)은 그대로 400
    for client_id, location_id in (("off-1", room), ("off-2", others)):
        res = add(client, location_id=location_id, client_id=client_id)
        assert res.status_code == 201
        assert res.get_json()["location_id"] is None


def test_bulk_location_deleted_after_loading_is_400(client, login, app, monkeypatch):
    login()
    real = shopping.user_locations

    def with_deleted(user_id):
        return [*real(user_id), StorageLocation(id=2147483000, user_id=user_id, name="없어진 곳", kind="room")]

    monkeypatch.setattr(shopping, "user_locations", with_deleted)
    res = client.post("/api/shopping/items/bulk", json={"source": "recipe", "items": [{"name": "우유", "location_id": 2147483000}]})
    assert res.status_code == 400
    assert res.get_json() == {"error": "선택한 보관 위치가 방금 바뀌었어요. 다시 시도해주세요."}
    assert snapshot(client)["items"] == []


def test_create_same_client_id_returns_existing_200(client, login, app):
    login()
    first = add(client, client_id="c-1")
    again = add(client, client_id="c-1")
    assert (first.status_code, again.status_code) == (201, 200)
    assert again.get_json()["id"] == first.get_json()["id"]
    assert len(snapshot(client)["items"]) == 1

    login("other")
    other = add(client, client_id="c-1")
    assert other.status_code == 201
    assert other.get_json()["id"] != first.get_json()["id"]


def test_cap_300_excludes_stocked(client, login, app):
    user = login()
    now = datetime.now(timezone.utc)
    with app.app_context():
        db.session.add(ShoppingItem(user_id=user.id, name="기기에서 담은 것", client_id="c-300"))
        db.session.add_all([ShoppingItem(user_id=user.id, name=f"항목{i}") for i in range(298)])
        db.session.add_all([ShoppingItem(user_id=user.id, name=f"산 것{i}", stocked_at=now) for i in range(5)])
        db.session.commit()
    assert add(client, name="마지막").status_code == 201
    res = add(client, name="하나 더")
    assert res.status_code == 400
    assert res.get_json() == {"error": CAP_ERROR}
    assert add(client, client_id="c-300").status_code == 200  # 가득 차도 다시 보낸 추가는 그 항목

    res = client.post("/api/shopping/items/bulk", json={"source": "recipe", "items": [{"name": "고등어"}, {"name": "무"}]})
    assert res.status_code == 400
    assert res.get_json() == {"error": CAP_ERROR}
    with app.app_context():
        assert ShoppingItem.query.filter_by(user_id=user.id).count() == 305


def test_bulk_skips_listed_duplicates_and_in_request_duplicates(client, login, app):
    user = login()
    scallion = add(client, name="대파").get_json()
    client.patch(f"/api/shopping/items/{scallion['id']}", json={"done": True, "changed_at": iso(datetime.now(timezone.utc))})
    with app.app_context():
        db.session.add(ShoppingItem(user_id=user.id, name="두부", stocked_at=datetime.now(timezone.utc)))
        db.session.commit()

    res = client.post(
        "/api/shopping/items/bulk",
        json={
            "source": "recipe",
            "source_label": "두부조림",
            "items": [{"name": "대파 (국산)"}, {"name": "두부", "quantity": 2, "unit": "모"}, {"name": "양파"}, {"name": " 양파 "}],
        },
    )
    assert res.status_code == 201
    body = res.get_json()
    assert [(i["name"], i["quantity"], i["unit"], i["source"], i["source_label"]) for i in body["created"]] == [
        ("두부", 2, "모", "recipe", "두부조림"),
        ("양파", 1, "개", "recipe", "두부조림"),
    ]
    assert body["skipped"] == ["대파 (국산)", "양파"]
    assert [i["name"] for i in snapshot(client)["items"]] == ["대파", "두부", "양파"]


def test_bulk_skips_only_same_normalized_name(client, login):
    login()
    for name in ("국간장", "대파", "계란"):
        add(client, name=name)
    res = client.post(
        "/api/shopping/items/bulk",
        json={"source": "recipe", "items": [{"name": "간장"}, {"name": "대파"}, {"name": "대파 1단"}, {"name": "달걀"}]},
    )
    assert res.status_code == 201
    body = res.get_json()
    # 국간장이 있어도 간장은 담는다(부분 매칭 아님). 대파 1단은 이름이 달라 담고, 달걀은 계란과 같은 재료라 건너뛴다
    assert ([i["name"] for i in body["created"]], body["skipped"]) == (["간장", "대파 1단"], ["대파", "달걀"])
    # 영수증 match는 그대로 부분 매칭이다
    matched = client.post("/api/shopping/items/match", json={"names": ["간장"]}).get_json()["items"]
    assert [i["name"] for i in matched] == ["국간장", "간장"]


def test_bulk_all_or_nothing_with_index_errors(client, login, app):
    user = login()
    res = client.post(
        "/api/shopping/items/bulk",
        json={"source": "memo", "items": [{"name": "우유"}, {"name": ""}, {"name": "계란", "quantity": 0}]},
    )
    assert res.status_code == 400
    assert res.get_json() == {
        "error": "2번째 재료: 이름은 1~50자로 입력해주세요.",
        "errors": [{"index": 1, "error": "이름은 1~50자로 입력해주세요."}, {"index": 2, "error": "수량은 0보다 커야 해요."}],
    }
    with app.app_context():
        assert ShoppingItem.query.filter_by(user_id=user.id).count() == 0


@pytest.mark.parametrize(
    "body, error",
    [
        ({"source": "recipe", "items": []}, "살 것을 1~50개 보내주세요."),
        ({"source": "recipe", "items": [{"name": f"재료{i}"} for i in range(51)]}, "살 것을 1~50개 보내주세요."),
        ({"source": "recipe", "items": "우유"}, "살 것을 1~50개 보내주세요."),
        ({"source": "ai", "items": [{"name": "우유"}]}, "잘못된 요청이에요."),
        ([], "잘못된 요청이에요."),
    ],
)
def test_bulk_rejects_bad_shape(client, login, body, error):
    login()
    res = client.post("/api/shopping/items/bulk", json=body)
    assert res.status_code == 400
    assert res.get_json() == {"error": error}


def test_bulk_accepts_exactly_50(client, login):
    login()
    res = client.post("/api/shopping/items/bulk", json={"source": "memo", "items": [{"name": f"재료{i:02d}번"} for i in range(50)]})
    assert res.status_code == 201
    assert (len(res.get_json()["created"]), res.get_json()["skipped"]) == (50, [])


def test_check_last_change_wins(client, login):
    login()
    item = add(client).get_json()
    url = f"/api/shopping/items/{item['id']}"
    now = datetime.now(timezone.utc).replace(microsecond=0)
    t1, t2, t3 = now - timedelta(minutes=3), now - timedelta(minutes=2), now - timedelta(minutes=1)

    res = client.patch(url, json={"done": True, "changed_at": iso(t2)})
    assert res.status_code == 200
    assert datetime.fromisoformat(res.get_json()["done_at"]) == t2

    res = client.patch(url, json={"done": False, "changed_at": iso(t1)})
    assert res.status_code == 200
    assert datetime.fromisoformat(res.get_json()["done_at"]) == t2  # 늦게 도착한 옛 해제는 무시

    seoul = timezone(timedelta(hours=9))
    res = client.patch(url, json={"done": False, "changed_at": t3.astimezone(seoul).isoformat()})
    body = res.get_json()
    assert body["done_at"] is None
    assert datetime.fromisoformat(body["done_changed_at"]) == t3

    future = datetime.now(timezone.utc) + timedelta(hours=1)
    body = client.patch(url, json={"done": True, "changed_at": iso(future)}).get_json()
    done_at = datetime.fromisoformat(body["done_at"])
    assert abs(done_at - datetime.now(timezone.utc)) < timedelta(seconds=5)
    assert datetime.fromisoformat(body["done_changed_at"]) == done_at


def test_check_tie_z_suffix_and_far_past(client, login):
    login()
    item = add(client).get_json()
    url = f"/api/shopping/items/{item['id']}"
    stamp = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=1)
    z = stamp.strftime("%Y-%m-%dT%H:%M:%SZ")

    body = client.patch(url, json={"done": True, "changed_at": z}).get_json()
    assert datetime.fromisoformat(body["done_at"]) == stamp
    body = client.patch(url, json={"done": False, "changed_at": iso(stamp)}).get_json()
    assert body["done_at"] is None  # 같은 시각이면 나중에 도착한 것

    res = client.patch(url, json={"done": True, "changed_at": "1970-01-01T00:00:00Z"})
    assert res.status_code == 200
    assert (res.get_json()["done_at"], datetime.fromisoformat(res.get_json()["done_changed_at"])) == (None, stamp)

    fresh = add(client, name="새 항목").get_json()
    res = client.patch(f"/api/shopping/items/{fresh['id']}", json={"done": True, "changed_at": "1970-01-01T00:00:00Z"})
    assert (res.status_code, res.get_json()["done_at"], res.get_json()["done_changed_at"]) == (200, None, None)


@pytest.mark.parametrize(
    "body",
    [
        {"done": True},
        {"changed_at": "2026-09-14T00:00:00+00:00"},
        {"done": "yes", "changed_at": "2026-09-14T00:00:00+00:00"},
        {"done": True, "changed_at": "어제"},
        {"done": True, "changed_at": "2026-09-14T00:00:00"},
        {"done": True, "changed_at": 3},
        {"done": True, "changed_at": "2026-09-14T00:00:00+00:00", "name": "대파"},
    ],
)
def test_patch_mixed_or_bad_check_shapes_400(client, login, body):
    login()
    item = add(client).get_json()
    res = client.patch(f"/api/shopping/items/{item['id']}", json=body)
    assert res.status_code == 400
    assert res.get_json() == {"error": "잘못된 요청이에요."}


def test_patch_edit_and_clear_nullable_fields(client, login):
    login()
    fridge = client.get("/api/locations").get_json()[0]["id"]
    item = add(client, planned_on="2026-09-14", location_id=fridge, source="recipe", source_label="두부조림").get_json()
    url = f"/api/shopping/items/{item['id']}"

    res = client.patch(url, json={"name": "순두부", "quantity": 0.5, "unit": "봉"})
    body = res.get_json()
    assert res.status_code == 200
    assert (body["name"], body["quantity"], body["unit"], body["planned_on"], body["location_id"], body["source_label"]) == (
        "순두부",
        0.5,
        "봉",
        "2026-09-14",
        fridge,
        "두부조림",
    )

    body = client.patch(url, json={"planned_on": None, "location_id": None}).get_json()
    assert (body["planned_on"], body["location_id"], body["location_name"]) == (None, None, None)
    assert client.patch(url, json={"quantity": -1}).status_code == 400


def test_delete_and_other_users_item_404(client, login):
    login("owner")
    item = add(client).get_json()
    url = f"/api/shopping/items/{item['id']}"
    login("intruder")
    assert client.patch(url, json={"name": "x"}).status_code == 404
    assert client.patch(url, json={"done": True, "changed_at": iso(datetime.now(timezone.utc))}).status_code == 404
    assert client.delete(url).status_code == 404
    assert client.patch("/api/shopping/items/2147483648", json={"name": "x"}).status_code == 404

    login("owner2")
    mine = add(client).get_json()
    assert client.delete(f"/api/shopping/items/{mine['id']}").status_code == 204
    assert client.delete(f"/api/shopping/items/{mine['id']}").status_code == 404
    assert snapshot(client)["items"] == []


def test_patch_stocked_item_404(client, login, app):
    user = login()
    with app.app_context():
        stocked = ShoppingItem(user_id=user.id, name="우유", stocked_at=datetime.now(timezone.utc))
        db.session.add(stocked)
        db.session.commit()
        url = f"/api/shopping/items/{stocked.id}"
    assert client.patch(url, json={"name": "두유"}).status_code == 404
    assert client.patch(url, json={"done": True, "changed_at": iso(datetime.now(timezone.utc))}).status_code == 404


def test_user_delete_cascades(client, login, app):
    user = login()
    item_id = add(client).get_json()["id"]
    with app.app_context():
        db.session.delete(db.session.get(User, user.id))
        db.session.commit()
        assert db.session.get(ShoppingItem, item_id) is None


# --- 재고에 넣기 (Task 2) ---

LIST_CHANGED = "목록이 방금 바뀌었어요. 다시 불러와주세요."


def checked(client, name, **body):
    item = add(client, name=name, **body).get_json()
    res = client.patch(f"/api/shopping/items/{item['id']}", json={"done": True, "changed_at": iso(datetime.now(timezone.utc))})
    return res.get_json()


def locations_by_name(client):
    return {l["name"]: l["id"] for l in client.get("/api/locations").get_json()}


def stock_row(item, **overrides):
    return {"id": item["id"], "name": item["name"], "quantity": item["quantity"], "unit": item["unit"], "location_id": item.get("location_id"), **overrides}


def stock(client, *rows, purchased_on=None):
    return client.post("/api/shopping/items/stock", json={"purchased_on": purchased_on or seoul_today().isoformat(), "items": list(rows)})


def test_stock_draft_only_checked_unstocked_with_location_reason(client, login, app):
    user = login()
    locs = locations_by_name(client)
    today = seoul_today()
    with app.app_context():
        older = datetime.now(timezone.utc) - timedelta(days=5)
        db.session.add_all(
            [
                Ingredient(user_id=user.id, name="우유", location_id=locs["실온"], purchased_on=today, created_at=older),
                Ingredient(user_id=user.id, name="우유 (1L)", location_id=locs["냉동실"], purchased_on=today),
                Ingredient(user_id=user.id, name="대파 (국산)", location_id=locs["실온"], purchased_on=today),
                ShoppingItem(user_id=user.id, name="계란", done_at=datetime.now(timezone.utc), stocked_at=datetime.now(timezone.utc)),
            ]
        )
        db.session.commit()
    with_location = checked(client, "배추", location_id=locs["냉동실"])
    same_name = checked(client, "우유", quantity=2, unit="L")
    scallion = checked(client, "대파")
    fallback = checked(client, "두부")
    add(client, name="양파")  # 체크 안 함
    login("other")
    checked(client, "남의 우유")
    with client.session_transaction() as s:
        s["user_id"], s["pid"] = user.id, user.provider_id

    res = client.get("/api/shopping/stock-draft")
    assert res.status_code == 200
    assert res.headers["Cache-Control"] == "no-store"
    assert res.get_json() == {
        "purchased_on": today.isoformat(),
        "items": [
            {"id": with_location["id"], "name": "배추", "quantity": 1, "unit": "개", "household": False, "location_id": locs["냉동실"], "location_reason": "item"},
            {"id": same_name["id"], "name": "우유", "quantity": 2, "unit": "L", "household": False, "location_id": locs["냉동실"], "location_reason": "same_name"},
            {"id": scallion["id"], "name": "대파", "quantity": 1, "unit": "개", "household": False, "location_id": locs["실온"], "location_reason": "same_name"},
            {"id": fallback["id"], "name": "두부", "quantity": 1, "unit": "개", "household": False, "location_id": locs["냉장실"], "location_reason": "default"},
        ],
    }


def test_stock_creates_ingredients_and_marks_items_stocked_atomically(client, login, app):
    user = login()
    locs = locations_by_name(client)
    scallion = checked(client, "대파", unit="단")
    milk = checked(client, "우유")
    onion = add(client, name="양파").get_json()
    yesterday = (seoul_today() - timedelta(days=1)).isoformat()

    res = stock(client, stock_row(scallion, location_id=locs["냉장실"]), stock_row(milk, name="서울우유", quantity=2, unit="L", location_id=None, expires_on="2026-09-20", price=3000), purchased_on=yesterday)
    assert res.status_code == 201
    assert res.get_json() == {"created": 2}

    ingredients = client.get("/api/ingredients").get_json()
    assert sorted((i["name"], i["quantity"], i["unit"], i["purchased_on"], i["location_name"], i["expires_on"], i["price"]) for i in ingredients) == [
        ("대파", 1, "단", yesterday, "냉장실", None, None),
        ("서울우유", 2, "L", yesterday, "냉장실", None, None),
    ]
    body = snapshot(client)
    assert [i["id"] for i in body["items"]] == [onion["id"]]
    assert {i["id"] for i in body["stocked"]} == {scallion["id"], milk["id"]}
    assert all(i["stocked_at"] for i in body["stocked"])
    assert client.get("/api/shopping/stock-draft").get_json()["items"] == []
    retry = stock(client, stock_row(scallion), stock_row(milk), purchased_on=yesterday)  # 응답을 못 받은 기기가 다시 보냄
    assert (retry.status_code, retry.get_json()) == (200, {"created": 0})
    partial = stock(client, stock_row(milk), stock_row(checked(client, "두부")))
    assert (partial.status_code, partial.get_json()) == (400, {"error": LIST_CHANGED})
    with app.app_context():
        assert Ingredient.query.filter_by(user_id=user.id).count() == 2


def test_stock_accepts_more_than_50_rows(client, login, app):
    user = login()
    with app.app_context():
        done = datetime.now(timezone.utc)
        db.session.add_all([ShoppingItem(user_id=user.id, name=f"재료{i:02d}번", done_at=done) for i in range(60)])
        db.session.commit()
    draft = client.get("/api/shopping/stock-draft").get_json()["items"]
    res = stock(client, *[stock_row(item) for item in draft])
    assert (res.status_code, res.get_json()) == (201, {"created": 60})
    assert len(client.get("/api/ingredients").get_json()) == 60


def test_stock_rejects_unchecked_already_stocked_or_missing_without_creating(client, login, app):
    user = login()
    good = checked(client, "대파")
    unchecked = add(client, name="양파").get_json()
    with app.app_context():
        done = datetime.now(timezone.utc)
        stocked = ShoppingItem(user_id=user.id, name="우유", done_at=done, stocked_at=done)
        db.session.add(stocked)
        db.session.commit()
        stocked_json = {"id": stocked.id, "name": "우유", "quantity": 1, "unit": "개"}
    for bad in (stock_row(unchecked), stocked_json, {**stock_row(good), "id": 2147483647}):
        res = stock(client, stock_row(good), bad)
        assert res.status_code == 400
        assert res.get_json() == {"error": LIST_CHANGED}
    with app.app_context():
        assert Ingredient.query.filter_by(user_id=user.id).count() == 0
        assert db.session.get(ShoppingItem, good["id"]).stocked_at is None


def test_stock_other_users_item_400(client, login, app):
    login("owner")
    theirs = checked(client, "대파")
    login("intruder")
    res = stock(client, stock_row(theirs))
    assert res.status_code == 400
    assert res.get_json() == {"error": LIST_CHANGED}
    with app.app_context():
        assert db.session.get(ShoppingItem, theirs["id"]).stocked_at is None
        assert Ingredient.query.count() == 0


def test_stock_index_errors_all_or_nothing(client, login, app):
    user = login()
    first, second, third = checked(client, "대파"), checked(client, "우유"), checked(client, "두부")
    res = stock(client, stock_row(first, quantity=10**400), stock_row(second, name=""), stock_row(third, quantity=0))
    assert res.status_code == 400
    assert res.get_json() == {
        "error": "1번째 재료: 수량은 0보다 커야 해요.",
        "errors": [
            {"index": 0, "error": "수량은 0보다 커야 해요."},
            {"index": 1, "error": "이름은 1~50자로 입력해주세요."},
            {"index": 2, "error": "수량은 0보다 커야 해요."},
        ],
    }
    with app.app_context():
        assert Ingredient.query.filter_by(user_id=user.id).count() == 0
        assert ShoppingItem.query.filter(ShoppingItem.user_id == user.id, ShoppingItem.stocked_at.is_not(None)).count() == 0


@pytest.mark.parametrize(
    "body, error",
    [
        ({"purchased_on": "2026/09/14", "items": "ROW"}, "날짜 형식이 올바르지 않아요."),
        ({"purchased_on": "FUTURE", "items": "ROW"}, "산 날은 오늘보다 뒤일 수 없어요."),
        ({"purchased_on": "TODAY", "items": []}, "재료를 1~300개 보내주세요."),
        ({"purchased_on": "TODAY", "items": [{"id": i + 1, "name": "우유"} for i in range(301)]}, "재료를 1~300개 보내주세요."),
        ({"purchased_on": "TODAY", "items": "우유"}, "재료를 1~300개 보내주세요."),
        ({"purchased_on": "TODAY", "items": ["우유"]}, "잘못된 요청이에요."),
        ({"purchased_on": "TODAY", "items": [{"id": "1", "name": "우유"}]}, "잘못된 요청이에요."),
        ({"purchased_on": "TODAY", "items": [{"id": True, "name": "우유"}]}, "잘못된 요청이에요."),
        ({"purchased_on": "TODAY", "items": "DUPLICATE"}, "잘못된 요청이에요."),
        ([], "잘못된 요청이에요."),
    ],
)
def test_stock_rejects_bad_shape(client, login, body, error):
    login()
    item = checked(client, "우유")
    if isinstance(body, dict):
        today = seoul_today()
        body = {**body, "purchased_on": {"TODAY": today.isoformat(), "FUTURE": (today + timedelta(days=1)).isoformat()}.get(body["purchased_on"], body["purchased_on"])}
        if body["items"] == "ROW":
            body["items"] = [stock_row(item)]
        elif body["items"] == "DUPLICATE":
            body["items"] = [stock_row(item), stock_row(item)]
    res = client.post("/api/shopping/items/stock", json=body)
    assert res.status_code == 400
    assert res.get_json() == {"error": error}


def test_stock_respects_2000_cap(client, login, app, monkeypatch):
    monkeypatch.setattr(ingredients_module, "MAX_INGREDIENTS_PER_USER", 3)
    user = login()
    fridge = locations_by_name(client)["냉장실"]
    with app.app_context():
        db.session.add_all([Ingredient(user_id=user.id, name=f"재료{i}", location_id=fridge, purchased_on=seoul_today()) for i in range(2)])
        db.session.commit()
    first, second = checked(client, "대파"), checked(client, "우유")
    res = stock(client, stock_row(first), stock_row(second))
    assert res.status_code == 400
    assert res.get_json() == {"error": "재료는 3개까지 저장할 수 있어요. 다 쓴 재료를 정리해주세요."}
    with app.app_context():
        assert Ingredient.query.filter_by(user_id=user.id).count() == 2
    assert stock(client, stock_row(first)).status_code == 201


def test_stock_location_deleted_after_loading_is_400(client, login, app, monkeypatch):
    login()
    item = checked(client, "우유")
    real = shopping.user_locations

    def with_deleted(user_id):
        return [*real(user_id), StorageLocation(id=2147483000, user_id=user_id, name="없어진 곳", kind="room")]

    monkeypatch.setattr(shopping, "user_locations", with_deleted)
    res = stock(client, stock_row(item, location_id=2147483000))
    assert res.status_code == 400
    assert res.get_json() == {"error": "선택한 보관 위치가 방금 바뀌었어요. 다시 시도해주세요."}
    assert client.get("/api/ingredients").get_json() == []
    assert snapshot(client)["stocked"] == []


def test_stock_trims_oldest_stocked_over_limit(client, login, app, monkeypatch):
    monkeypatch.setattr(shopping, "MAX_STOCKED_ITEMS", 3)
    user = login()
    now = datetime.now(timezone.utc)
    with app.app_context():
        old = [ShoppingItem(user_id=user.id, name=f"산 것{i}", stocked_at=now - timedelta(days=3, hours=i)) for i in range(3)]
        db.session.add_all(old)
        db.session.commit()
        keep_id = old[0].id
    first, second = checked(client, "대파"), checked(client, "우유")
    assert stock(client, stock_row(first), stock_row(second)).status_code == 201
    assert [i["id"] for i in snapshot(client)["stocked"]][:2] == sorted([first["id"], second["id"]], reverse=True)
    assert [i["id"] for i in snapshot(client)["stocked"]][2:] == [keep_id]

    third = add(client, name="두부").get_json()
    assert client.post("/api/shopping/items/mark-stocked", json={"ids": [third["id"]]}).status_code == 204
    assert [i["id"] for i in snapshot(client)["stocked"]] == [third["id"], *sorted([first["id"], second["id"]], reverse=True)]


def test_mark_stocked_trims_past_300(client, login, app):
    user = login()
    now = datetime.now(timezone.utc)
    with app.app_context():
        db.session.add_all([ShoppingItem(user_id=user.id, name=f"산 것{i}", stocked_at=now - timedelta(minutes=i)) for i in range(300)])
        db.session.commit()
        oldest = {i.id for i in ShoppingItem.query.filter(ShoppingItem.name.in_(["산 것298", "산 것299"])).all()}
    ids = [add(client, name=name).get_json()["id"] for name in ("우유", "두부")]
    assert client.post("/api/shopping/items/mark-stocked", json={"ids": ids}).status_code == 204
    stocked = {i["id"] for i in snapshot(client)["stocked"]}
    assert len(stocked) == 300
    assert set(ids) <= stocked and not oldest & stocked


def test_household_defaults_from_name_and_can_be_overridden(client, login):
    login()
    assert add(client, name="주방세제").get_json()["household"] is True
    assert add(client, name="두부").get_json()["household"] is False
    assert add(client, name="수세미오이", household=False).get_json()["household"] is False
    item = add(client, name="대나무 바구니", household=True).get_json()
    assert item["household"] is True
    assert add(client, name="휴지", household="yes").get_json() == {"error": "잘못된 요청이에요."}

    url = f"/api/shopping/items/{item['id']}"
    assert client.patch(url, json={"household": False}).get_json()["household"] is False
    assert client.patch(url, json={"name": "휴지"}).get_json()["household"] is False  # 고치기는 보낸 때만 바꾼다
    assert client.patch(url, json={"household": 1}).status_code == 400
    assert client.patch(url, json={"household": True, "done": True, "changed_at": iso(datetime.now(timezone.utc))}).status_code == 400

    res = client.post("/api/shopping/items/bulk", json={"source": "memo", "items": [{"name": "치약"}, {"name": "양파"}, {"name": "행주", "household": False}]})
    assert [(i["name"], i["household"]) for i in res.get_json()["created"]] == [("치약", True), ("양파", False), ("행주", False)]
    assert {i["name"]: i["household"] for i in snapshot(client)["items"]}["치약"] is True


def test_stock_skip_rows_only_mark_stocked(client, login, app):
    user = login()
    locs = locations_by_name(client)
    tofu = checked(client, "두부")
    sponge = checked(client, "수세미")
    tissue = checked(client, "휴지")
    draft = client.get("/api/shopping/stock-draft").get_json()["items"]
    assert [(i["name"], i["household"]) for i in draft] == [("두부", False), ("수세미", True), ("휴지", True)]

    assert stock(client, stock_row(tofu), {"id": sponge["id"], "skip": "yes"}).status_code == 400
    res = stock(client, stock_row(tofu, location_id=locs["냉장실"]), {"id": sponge["id"], "skip": True}, {"id": tissue["id"], "skip": True})
    assert (res.status_code, res.get_json()) == (201, {"created": 1})
    assert [i["name"] for i in client.get("/api/ingredients").get_json()] == ["두부"]
    assert {i["id"] for i in snapshot(client)["stocked"]} == {tofu["id"], sponge["id"], tissue["id"]}

    bad = checked(client, "우유")
    soap = checked(client, "비누")
    res = stock(client, {"id": soap["id"], "skip": True}, stock_row(bad, quantity=0))
    assert res.get_json()["errors"] == [{"index": 1, "error": "수량은 0보다 커야 해요."}]  # 틀리면 산 것으로도 안 옮긴다
    with app.app_context():
        assert db.session.get(ShoppingItem, soap["id"]).stocked_at is None
        assert Ingredient.query.filter_by(user_id=user.id).count() == 1
        Ingredient.query.filter_by(user_id=user.id).delete()
        StorageLocation.query.filter_by(user_id=user.id).delete()
        db.session.commit()
    assert stock(client, {"id": soap["id"], "skip": True}).status_code == 201  # 산 것으로만 옮기면 보관 위치가 없어도 된다
    with app.app_context():
        assert db.session.get(ShoppingItem, soap["id"]).stocked_at is not None
        assert Ingredient.query.filter_by(user_id=user.id).count() == 0


def test_stock_without_any_location(client, login, app):
    user = login()
    item = checked(client, "우유")
    with app.app_context():
        StorageLocation.query.filter_by(user_id=user.id).delete()
        db.session.commit()
    draft = client.get("/api/shopping/stock-draft").get_json()["items"]
    assert [(i["id"], i["location_id"], i["location_reason"]) for i in draft] == [(item["id"], None, "none")]
    res = stock(client, stock_row(item, location_id=None))
    assert (res.status_code, res.get_json()) == (400, {"error": "보관 위치를 먼저 만들어주세요."})
    with app.app_context():
        assert db.session.get(ShoppingItem, item["id"]).stocked_at is None


def test_match_returns_listed_items_only(client, login, app):
    user = login()
    milk = add(client, name="우유").get_json()
    onion = checked(client, "양파")
    add(client, name="간장게장")
    with app.app_context():
        db.session.add(ShoppingItem(user_id=user.id, name="대파", stocked_at=datetime.now(timezone.utc)))
        db.session.commit()
    login("other")
    add(client, name="양파")
    with client.session_transaction() as s:
        s["user_id"], s["pid"] = user.id, user.provider_id

    res = client.post("/api/shopping/items/match", json={"names": ["서울우유 1L", "양파(국산)", "대파 1단", "간장", ""]})
    assert res.status_code == 200
    assert res.get_json() == {"items": [{"id": milk["id"], "name": "우유"}, {"id": onion["id"], "name": "양파"}]}


@pytest.mark.parametrize("body", [{}, {"names": []}, {"names": "우유"}, {"names": [1]}, {"names": ["가" * 51]}, {"names": ["우유"] * 51}, []])
def test_match_rejects_bad_shape(client, login, body):
    login()
    res = client.post("/api/shopping/items/match", json=body)
    assert res.status_code == 400
    assert res.get_json() == {"error": "잘못된 요청이에요."}


def test_mark_stocked_ignores_missing_and_others(client, login, app):
    user = login()
    milk = add(client, name="우유").get_json()
    onion = checked(client, "양파")
    tofu = add(client, name="두부").get_json()
    earlier = datetime.now(timezone.utc) - timedelta(days=2)
    with app.app_context():
        already = ShoppingItem(user_id=user.id, name="대파", stocked_at=earlier)
        db.session.add(already)
        db.session.commit()
        already_id = already.id
    login("other")
    theirs = add(client, name="남의 우유").get_json()
    with client.session_transaction() as s:
        s["user_id"], s["pid"] = user.id, user.provider_id

    res = client.post("/api/shopping/items/mark-stocked", json={"ids": [milk["id"], onion["id"], already_id, theirs["id"], 2147483647]})
    assert res.status_code == 204
    body = snapshot(client)
    assert [i["id"] for i in body["items"]] == [tofu["id"]]
    assert {i["id"] for i in body["stocked"]} == {milk["id"], onion["id"], already_id}
    with app.app_context():
        assert Ingredient.query.filter_by(user_id=user.id).count() == 0  # 재고는 스캔으로 이미 넣었다
        assert shopping._utc(db.session.get(ShoppingItem, already_id).stocked_at) == earlier  # 이미 산 것은 그대로
        assert db.session.get(ShoppingItem, theirs["id"]).stocked_at is None


@pytest.mark.parametrize("body", [{}, {"ids": []}, {"ids": [1] * 301}, {"ids": ["1"]}, {"ids": [True]}, {"ids": [0]}, {"ids": [2**31]}, []])
def test_mark_stocked_rejects_bad_shape(client, login, body):
    login()
    res = client.post("/api/shopping/items/mark-stocked", json=body)
    assert res.status_code == 400
    assert res.get_json() == {"error": "잘못된 요청이에요."}


def test_stock_endpoints_require_login(client):
    assert client.get("/api/shopping/stock-draft").status_code == 401
    for path in ("stock", "match", "mark-stocked"):
        assert client.post(f"/api/shopping/items/{path}", json={}).status_code == 401
