import io
import os
from datetime import date

import pytest
from sqlalchemy import text as sql

from app import cooklog, storage
from app.cooklog import new_photo_key
from app.models import CookLog, CookLogItem, FoodLog, IngredientRemoval, Recipe, db
from tests.test_cooklog_save import cook, kimchi_setup, quantities
from tests.test_meals import add_recipe
from tests.test_shopping_notes import JPEG, PNG, as_user, photo_path

BAD = "잘못된 요청이에요."
FUTURE = "아직 오지 않은 날은 남길 수 없어요."
PHOTO_FULL = "사진 저장 공간이 가득 찼어요. 오래된 일기 사진을 지워주세요."


@pytest.fixture(autouse=True)
def today(monkeypatch):
    for target in ("app.food_logs.seoul_today", "app.ingredients.seoul_today", "app.meals.seoul_today"):
        monkeypatch.setattr(target, lambda: date(2026, 9, 15))


def diary(app, user_id, title, cooked_on, **cols):
    """CookLog(+ cols["items"]로 CookLogItem)을 저장 API 없이 앱 컨텍스트에서 직접 넣는다."""
    items = cols.pop("items", [])
    with app.app_context():
        log = CookLog(user_id=user_id, title=title, cooked_on=cooked_on, servings=cols.pop("servings", 2), **cols)
        for item in items:
            log.items.append(CookLogItem(**item))
        db.session.add(log)
        db.session.commit()
        return log.id


def make_recipe(app, user_id, **cols):
    with app.app_context():
        recipe = Recipe(user_id=user_id, title=cols.pop("title", "레시피"), servings=cols.pop("servings", 2), **cols)
        db.session.add(recipe)
        db.session.commit()
        return recipe.id


def make_food_log(app, user_id, eaten_on, **cols):
    with app.app_context():
        food = FoodLog(
            user_id=user_id, eaten_on=eaten_on, meal=cols.pop("meal", "dinner"),
            source=cols.pop("source", "cook_log"), place=cols.pop("place", "home"), **cols,
        )
        db.session.add(food)
        db.session.commit()
        return food.id


def test_list_order_and_cursor(client, login, app):
    user = login()
    diary(app, user.id, "9/10", date(2026, 9, 10))
    diary(app, user.id, "9/15a", date(2026, 9, 15))
    diary(app, user.id, "9/15b", date(2026, 9, 15))
    diary(app, user.id, "9/12", date(2026, 9, 12))
    other = login("other")
    diary(app, other.id, "남의 일기", date(2026, 9, 20))
    as_user(client, user)

    res = client.get("/api/cook-logs?limit=2")
    assert res.status_code == 200
    assert res.headers["Cache-Control"] == "no-store"
    body = res.get_json()
    assert [i["title"] for i in body["items"]] == ["9/15b", "9/15a"]
    assert body["next_cursor"] is not None
    assert set(body["items"][0].keys()) == {
        "id", "recipe_id", "title", "cooked_on", "servings", "rating", "memo", "photo_url",
        "eat_out_price", "eat_out_source", "ingredient_cost", "saved", "excluded_count", "created_at",
    }

    body2 = client.get(f"/api/cook-logs?limit=2&cursor={body['next_cursor']}").get_json()
    assert [i["title"] for i in body2["items"]] == ["9/12", "9/10"]
    assert body2["next_cursor"] is None

    res = client.get("/api/cook-logs?cursor=abc")
    assert (res.status_code, res.get_json()["error"]) == (400, BAD)

    assert len(client.get("/api/cook-logs?limit=0").get_json()["items"]) == 1

    # limit=1로 끝까지 넘기며 전체 순서를 맞춘다 — 같은 날짜(9/15) 경계에서 큰 id → 작은 id로 정확히 이어지는지가 핵심(I2a).
    titles, cursor = [], None
    for _ in range(10):
        query = f"?limit=1&cursor={cursor}" if cursor else "?limit=1"
        page = client.get(f"/api/cook-logs{query}").get_json()
        assert len(page["items"]) == 1
        titles.append(page["items"][0]["title"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert titles == ["9/15b", "9/15a", "9/12", "9/10"]
    assert cursor is None


def test_list_limit_clamps_to_50(client, login, app):
    user = login()
    for i in range(60):
        diary(app, user.id, f"i{i}", date(2026, 9, 1))
    assert len(client.get("/api/cook-logs?limit=99").get_json()["items"]) == 50


def test_detail_shape(client, login, app):
    user = login()
    log_id = diary(
        app, user.id, "김치찌개", date(2026, 9, 10),
        items=[{"name": f"재료{i}", "used": 1.0, "unit": "개", "cost": 100} for i in range(5)],
    )
    res = client.get(f"/api/cook-logs/{log_id}")
    assert res.status_code == 200
    assert res.headers["Cache-Control"] == "no-store"
    body = res.get_json()
    assert len(body["items"]) == 5
    assert "undo_until" in body and "food_log_id" in body

    login("other")
    assert client.get(f"/api/cook-logs/{log_id}").status_code == 404
    as_user(client, user)
    assert client.get(f"/api/cook-logs/{2**31}").status_code == 404


def test_patch_recomputes_saved_and_updates_recipe(client, login, app):
    user = login()
    recipe_id = make_recipe(app, user.id, title="김치찌개", eat_out_price=9000, eat_out_source="user")
    food_id = make_food_log(app, user.id, date(2026, 9, 15))
    log_id = diary(
        app, user.id, "김치찌개", date(2026, 9, 15),
        recipe_id=recipe_id, food_log_id=food_id, servings=2, rating=4,
        eat_out_price=9000, eat_out_source="user", ingredient_cost=7180, saved=10820, excluded_count=1,
        items=[
            {"name": "김치", "used": 0.3, "unit": "kg", "cost": 3870},
            {"name": "두부", "used": 1, "unit": "모", "cost": 2480},
            {"name": "대파", "used": 1, "unit": "대", "cost": 830},
            {"name": "고춧가루", "excluded": "seasoning"},
            {"name": "돼지고기", "amount_text": "200g", "excluded": "no_price"},
        ],
    )

    body = client.patch(f"/api/cook-logs/{log_id}", json={"eat_out_price": 12000}).get_json()
    assert (body["saved"], body["ingredient_cost"]) == (16820, 7180)
    got = client.get(f"/api/recipes/{recipe_id}").get_json()
    assert (got["eat_out_price"], got["eat_out_source"]) == (12000, "user")

    body = client.patch(f"/api/cook-logs/{log_id}", json={"eat_out_price": None}).get_json()
    assert (body["saved"], body["ingredient_cost"]) == (None, 7180)
    got = client.get(f"/api/recipes/{recipe_id}").get_json()
    assert (got["eat_out_price"], got["eat_out_source"]) == (12000, "user")

    body = client.patch(
        f"/api/cook-logs/{log_id}", json={"rating": None, "memo": "  ", "cooked_on": "2026-09-14"}
    ).get_json()
    assert (body["rating"], body["memo"], body["cooked_on"]) == (None, None, "2026-09-14")
    with app.app_context():
        assert db.session.get(FoodLog, food_id).eaten_on == date(2026, 9, 15)

    for bad in ({"servings": 3}, {"usages": []}, []):
        res = client.patch(f"/api/cook-logs/{log_id}", json=bad)
        assert (res.status_code, res.get_json()["error"]) == (400, BAD)

    res = client.patch(f"/api/cook-logs/{log_id}", json={"cooked_on": "2026-09-16"})
    assert (res.status_code, res.get_json()["error"]) == (400, FUTURE)


def test_delete_keeps_stock_and_food_log(client, login, app):
    """실제 저장 경로(kimchi_setup + cook)로 두부 차감·먹은 기록·사진을 만든 뒤 지운다(I2b) —
    diary()로 흉내내지 않고 진짜 저장이 남긴 재고·IngredientRemoval·FoodLog 개수가 지우기 전후로 그대로인지 본다."""
    login()
    recipe, ids, usages = kimchi_setup(client)
    res = cook(client, recipe["id"], usages, image=JPEG, eat_out_price=9000, food_log=True, meal="dinner")
    assert res.status_code == 201, res.get_json()
    log = res.get_json()["log"]
    log_id, food_id = log["id"], log["food_log_id"]
    file_path = photo_path(app, log["photo_url"])
    assert os.path.exists(file_path)

    before_stock = quantities(client)
    with app.app_context():
        removal_count = IngredientRemoval.query.count()
        food_log_count = FoodLog.query.count()
    assert removal_count > 0  # 두부가 이미 차감으로 지워져 다 먹었어요 기록이 있다

    res = client.delete(f"/api/cook-logs/{log_id}")
    assert res.status_code == 204

    assert quantities(client) == before_stock  # 재고는 지우기 전후로 그대로(결정 17)
    with app.app_context():
        assert IngredientRemoval.query.count() == removal_count
        assert FoodLog.query.count() == food_log_count
        food = db.session.get(FoodLog, food_id)
        assert food is not None and food.source == "cook_log"
    assert not os.path.exists(file_path)
    assert client.post(f"/api/cook-logs/{log_id}/undo").status_code == 404


def test_photo_replace_and_remove(client, login, app, monkeypatch):
    login()
    recipe = add_recipe(client, "김치찌개", [{"name": "김치", "amount": "300g"}])
    log = cook(client, recipe["id"], []).get_json()["log"]
    log_id = log["id"]
    assert log["photo_url"] is None

    def put_photo(data, name="a.jpg"):
        return client.put(f"/api/cook-logs/{log_id}/photo", data={"image": (io.BytesIO(data), name)}, content_type="multipart/form-data")

    res = put_photo(JPEG)
    assert res.status_code == 200, res.get_json()
    url = res.get_json()["photo_url"]
    assert url.endswith(".jpg")
    path1 = photo_path(app, url)
    assert os.path.exists(path1)

    res = put_photo(PNG, "a.png")
    assert res.status_code == 200
    url2 = res.get_json()["photo_url"]
    assert url2 != url and url2.endswith(".png")
    assert not os.path.exists(path1)
    assert os.path.exists(photo_path(app, url2))

    assert client.delete(f"/api/cook-logs/{log_id}/photo").status_code == 204
    assert not os.path.exists(photo_path(app, url2))
    assert client.get(f"/api/cook-logs/{log_id}").get_json()["photo_url"] is None
    assert client.delete(f"/api/cook-logs/{log_id}/photo").status_code == 204  # 다시 지워도 204

    app.config["DEV_MODE"] = False
    assert put_photo(JPEG).status_code == 503
    app.config["DEV_MODE"] = True

    assert put_photo(b"hello").status_code == 415

    res = put_photo(JPEG)  # 사진 없는 상태로 되돌려 놓고 정상 업로드
    assert res.status_code == 200
    current_url = res.get_json()["photo_url"]
    current_path = photo_path(app, current_url)
    assert os.path.exists(current_path)

    other_log = cook(client, recipe["id"], []).get_json()["log"]
    other_id = other_log["id"]

    monkeypatch.setattr("app.cooklog.MAX_USER_PHOTO_BYTES", len(JPEG) - 1)  # 자기 사진을 빼도 새 사진(PNG)이 한도를 넘게
    res = put_photo(PNG, "d.png")
    assert (res.status_code, res.get_json()["error"]) == (400, PHOTO_FULL)
    assert client.get(f"/api/cook-logs/{log_id}").get_json()["photo_url"] == current_url  # 실패한 바꾸기는 옛 사진 그대로(minor)
    assert os.path.exists(current_path)

    monkeypatch.setattr("app.cooklog.MAX_USER_PHOTO_BYTES", len(JPEG))
    res = put_photo(JPEG)  # 자기 사진(len(JPEG))은 합계에서 빼므로 0 + len(JPEG) <= 한도
    assert res.status_code == 200, res.get_json()

    res = client.put(f"/api/cook-logs/{other_id}/photo", data={"image": (io.BytesIO(JPEG), "c.jpg")}, content_type="multipart/form-data")
    assert (res.status_code, res.get_json()["error"]) == (400, PHOTO_FULL)


def test_ownership_across_mutations_404_and_unchanged(client, login, app):
    """PATCH·DELETE·PUT 사진·DELETE 사진 네 곳 모두 남의 것이면 404이고, 일기·사진 파일은 그대로여야 한다(I2c)."""
    user = login()
    with app.app_context():
        key = new_photo_key(user.id, "jpg")
        storage.put(key, JPEG, "image/jpeg")
    log_id = diary(app, user.id, "김치찌개", date(2026, 9, 15), rating=3, memo="원래 메모", photo_key=key, photo_size=len(JPEG))
    file_path = photo_path(app, f"/api/photos/{key}")

    login("other")
    assert client.patch(f"/api/cook-logs/{log_id}", json={"rating": 5}).status_code == 404
    assert client.delete(f"/api/cook-logs/{log_id}").status_code == 404
    res = client.put(f"/api/cook-logs/{log_id}/photo", data={"image": (io.BytesIO(PNG), "x.png")}, content_type="multipart/form-data")
    assert res.status_code == 404
    assert client.delete(f"/api/cook-logs/{log_id}/photo").status_code == 404

    with app.app_context():
        row = db.session.get(CookLog, log_id)
        assert (row.rating, row.memo, row.photo_key) == (3, "원래 메모", key)
    assert os.path.exists(file_path)


def test_photo_put_race_no_orphan_file(client, login, app, monkeypatch):
    """PUT 도중 "다른 PUT"이 먼저 커밋해 버린 상황을 결정적으로 재현한다(I1): lock_user를 부르는 순간
    사진 키를 직접 바꿔치기한다. 이미 읽어 둔 cook_log 파이썬 객체는 커밋해도 그대로 캐시에 남기려고
    (SQLAlchemy 기본 expire_on_commit이 새로 고치면 우연히 버그가 가려진다 — 진짜 별도 커넥션은 StaticPool
    SQLite가 같은 커넥션을 공유해 트랜잭션이 겹쳐 못 쓴다) 이 한 번의 커밋만 expire_on_commit을 끈다.
    잠근 뒤 다시 읽지 않으면(옛 버그) old를 잠금 전 값(None)으로 착각해 이 커밋이 만든 파일을 고아로 남긴다."""
    user = login()
    recipe = add_recipe(client, "김치찌개", [{"name": "김치", "amount": "300g"}])
    log_id = cook(client, recipe["id"], []).get_json()["log"]["id"]

    other_key = new_photo_key(user.id, "png")
    real_lock_user = cooklog.lock_user  # 패치 전에 잡아 둔다 — 안에서 app.cooklog.lock_user를 다시 부르면 무한 재귀

    def racing_lock_user(user_id):
        real_lock_user(user_id)  # 실제 잠금 그대로(SQLite는 no-op)
        storage.put(other_key, PNG, "image/png")
        db.session.execute(
            sql("UPDATE cook_logs SET photo_key = :key, photo_size = :size WHERE id = :id"),
            {"key": other_key, "size": len(PNG), "id": log_id},
        )
        session = db.session()  # db.session.expire_on_commit = ... 는 scoped_session 프록시에 앉아 효과가 없다
        session.expire_on_commit = False
        try:
            session.commit()
        finally:
            session.expire_on_commit = True

    monkeypatch.setattr("app.cooklog.lock_user", racing_lock_user)

    res = client.put(f"/api/cook-logs/{log_id}/photo", data={"image": (io.BytesIO(JPEG), "outer.jpg")}, content_type="multipart/form-data")
    assert res.status_code == 200, res.get_json()
    outer_url = res.get_json()["photo_url"]

    assert client.get(f"/api/cook-logs/{log_id}").get_json()["photo_url"] == outer_url  # 늦게 커밋한(바깥) 요청이 최종 상태

    root = os.path.join(app.config["UPLOAD_DIR"], "cooklog")
    files_on_disk = {name for _, _, names in os.walk(root) for name in names}
    assert files_on_disk == {os.path.basename(outer_url)}  # 동시 PUT이 만든 사진이 고아로 남지 않았다


def test_recipe_detail_cooked(client, login, app):
    user = login()
    recipe = add_recipe(client, "김치찌개", [{"name": "김치", "amount": "300g"}])
    res = client.get(f"/api/recipes/{recipe['id']}")
    assert res.get_json()["cooked"] is None
    assert res.headers["Cache-Control"] == "no-store"  # 이제 일기 유래 정보(cooked)를 담는다(minor)

    diary(app, user.id, "김치찌개", date(2026, 9, 10), recipe_id=recipe["id"], rating=3)
    diary(app, user.id, "김치찌개", date(2026, 9, 15), recipe_id=recipe["id"], rating=4)
    diary(app, user.id, "김치찌개", date(2026, 9, 15), recipe_id=recipe["id"], rating=None)

    other = login("other")
    diary(app, other.id, "남의 요리", date(2026, 9, 20), recipe_id=recipe["id"], rating=5)
    as_user(client, user)

    got = client.get(f"/api/recipes/{recipe['id']}").get_json()
    assert got["cooked"] == {"count": 3, "last_on": "2026-09-15", "last_rating": None}

    listed = client.get("/api/recipes").get_json()["items"]
    assert listed and all("cooked" not in item for item in listed)
    created = client.post("/api/recipes", json={
        "title": "새 레시피", "servings": 2, "ingredients": [{"name": "재료", "amount": ""}], "steps": [],
    }).get_json()
    assert "cooked" not in created


def test_auth(client, raw_client):
    assert client.get("/api/cook-logs").status_code == 401
    assert client.get("/api/cook-logs/1").status_code == 401
    assert client.patch("/api/cook-logs/1", json={}).status_code == 401
    assert client.delete("/api/cook-logs/1").status_code == 401
    assert client.put("/api/cook-logs/1/photo").status_code == 401
    assert client.delete("/api/cook-logs/1/photo").status_code == 401
    assert raw_client.patch("/api/cook-logs/1").status_code == 400
    assert raw_client.delete("/api/cook-logs/1").status_code == 400
