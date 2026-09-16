"""레시피 없이 쓴 요리 일기(스펙 29절 추가 2026-09-16, 시안 docs/design/diary-write)."""

import io
import json
import os
from datetime import date

import pytest

from app.models import AiCall, CookLog, FoodLog, IngredientRemoval, db
from tests.test_cooklog_save import cook, error, quantities, stock
from tests.test_export import read_zip
from tests.test_meals import add_recipe
from tests.test_shopping_notes import JPEG, PNG, as_user, photo_path

BAD = "잘못된 요청이에요."
TITLE_ERROR = "요리 이름은 1~60자로 입력해주세요."
COST_ERROR = "재료비는 0~1,000,000원 사이 숫자로 입력해주세요."
EAT_OUT_ERROR = "사 먹으면 얼마는 0~1,000,000원 사이 숫자로 입력해주세요."
PHOTO_FULL = "사진 저장 공간이 가득 찼어요. 오래된 일기 사진을 지워주세요."


@pytest.fixture(autouse=True)
def today(monkeypatch):
    for target in ("app.food_logs.seoul_today", "app.ingredients.seoul_today", "app.meals.seoul_today"):
        monkeypatch.setattr(target, lambda: date(2026, 9, 15))


def write(client, image=None, **data):
    body = {"manual": True, "title": "제육덮밥", "servings": 2, "cooked_on": "2026-09-15", "food_log": False, **data}
    form = {"data": json.dumps(body), **({"image": (io.BytesIO(image), "a.jpg")} if image else {})}
    return client.post("/api/cook-logs", data=form, content_type="multipart/form-data")


def counts(app):
    with app.app_context():
        return CookLog.query.count(), FoodLog.query.count()


def test_manual_diary_keeps_stock_and_computes_saved(client, login, app):
    login()
    stock(client, "돼지고기", 600, "g", 9800)
    before = quantities(client)
    res = write(client, eat_out_price=9000, ingredient_cost=6500, rating=5, memo="양념을 조금 줄였더니 딱 좋았어요")
    assert res.status_code == 201, res.get_json()
    body = res.get_json()
    assert body["deducted_names"] == []
    log = body["log"]
    assert (log["manual"], log["recipe_id"], log["title"], log["servings"], log["items"]) == (True, None, "제육덮밥", 2, [])
    assert (log["eat_out_price"], log["eat_out_source"], log["ingredient_cost"], log["saved"], log["excluded_count"]) == (
        9000, "user", 6500, 11500, 0,
    )
    assert (log["rating"], log["memo"], log["food_log_id"], log["photo_url"]) == (5, "양념을 조금 줄였더니 딱 좋았어요", None, None)
    assert quantities(client) == before  # 재고는 그대로
    with app.app_context():
        assert IngredientRemoval.query.count() == 0
        assert CookLog.query.one().manual is True


@pytest.mark.parametrize(
    "fields, cost, saved",
    [
        ({"eat_out_price": 9000}, None, None),  # 재료비를 비웠다 — 계산 못 함
        ({"ingredient_cost": 6500}, 6500, None),  # 사 먹으면 얼마를 비웠다
        ({"eat_out_price": None, "ingredient_cost": None}, None, None),
        ({}, None, None),
        ({"eat_out_price": 9000, "ingredient_cost": 0}, 0, 18000),  # 0원도 적은 값
        ({"eat_out_price": 3000, "ingredient_cost": 9000}, 9000, -3000),  # 더 들었으면 음수 그대로(결정 15)
    ],
)
def test_manual_saved_rules(client, login, app, fields, cost, saved):
    login()
    log = write(client, **fields).get_json()["log"]
    assert (log["ingredient_cost"], log["saved"], log["excluded_count"]) == (cost, saved, 0)
    with app.app_context():
        assert CookLog.query.one().ingredient_cost == (cost or 0)  # 칸은 비울 수 없어 모르면 0으로 둔다


def test_manual_food_log_and_meal(client, login, app, monkeypatch):
    login()
    res = write(client, title="  제육덮밥  ", food_log=True, meal="dinner")
    assert res.status_code == 201, res.get_json()
    log = res.get_json()["log"]
    assert log["title"] == "제육덮밥"
    food = client.get("/api/food-logs?date=2026-09-15").get_json()["logs"][0]
    assert (food["id"], food["source"], food["place"], food["title"], food["recipe_id"], food["servings"], food["meal"], food["nutrition"]) == (
        log["food_log_id"], "cook_log", "home", "제육덮밥", None, 1.0, "dinner", None,
    )
    assert error(write(client, food_log=True)) == (400, "끼니를 골라주세요.")
    monkeypatch.setattr("app.food_logs.MAX_PER_DAY", 1)
    assert error(write(client, food_log=True, meal="lunch")) == (400, "하루에 1개까지 남길 수 있어요.")
    assert counts(app) == (1, 1)  # 먹은 기록에 걸리면 일기도 남기지 않는다


MANUAL_VALIDATION = [
    ({"title": None}, TITLE_ERROR),
    ({"title": "   "}, TITLE_ERROR),
    ({"title": "가" * 61}, TITLE_ERROR),
    ({"title": 3}, TITLE_ERROR),
    ({"title": "제육\x00덮밥"}, BAD),  # PostgreSQL이 받지 않는 글자 → 500 대신 400
    ({"servings": 0}, "인분은 1~20 사이 정수로 입력해주세요."),
    ({"servings": 21}, "인분은 1~20 사이 정수로 입력해주세요."),
    ({"cooked_on": "2026-09-16"}, "아직 오지 않은 날은 남길 수 없어요."),
    ({"cooked_on": None}, "날짜를 골라주세요."),
    ({"rating": 0}, "별점은 1~5 사이 정수로 입력해주세요."),
    ({"memo": "가" * 501}, "메모는 500자까지 입력해주세요."),
    ({"eat_out_price": -1}, EAT_OUT_ERROR),
    ({"ingredient_cost": -1}, COST_ERROR),
    ({"ingredient_cost": 1_000_001}, COST_ERROR),
    ({"ingredient_cost": True}, COST_ERROR),
    ({"ingredient_cost": "6500"}, COST_ERROR),
    ({"ingredient_cost": 6500.5}, COST_ERROR),
    ({"manual": "yes"}, BAD),
    ({"recipe_id": 1}, BAD),  # 레시피 칸·쓴 재료·식단 칸은 받지 않는다
    ({"usages": []}, BAD),
    ({"meal_slot_id": 1}, BAD),
    ({"food_log": "yes"}, BAD),
]


@pytest.mark.parametrize("override, message", MANUAL_VALIDATION)
def test_manual_validation(client, login, app, override, message):
    login()
    assert error(write(client, **override)) == (400, message)
    assert counts(app) == (0, 0)


def test_recipe_payload_rejects_manual_fields(client, login, app):
    login()
    recipe = add_recipe(client, "김치찌개", [{"name": "김치", "amount": "300g"}])
    assert error(cook(client, recipe["id"], [], ingredient_cost=100)) == (400, BAD)  # 레시피 일기의 재료비는 쓴 재료로 계산한다
    assert error(cook(client, recipe["id"], [], title="딴 이름")) == (400, BAD)
    res = cook(client, recipe["id"], [], manual=False)
    assert res.status_code == 201, res.get_json()
    assert res.get_json()["log"]["manual"] is False
    assert counts(app) == (1, 0)


def test_manual_photo_and_limits(client, login, app, monkeypatch):
    user = login()
    res = write(client, image=JPEG)
    assert res.status_code == 201, res.get_json()
    url = res.get_json()["log"]["photo_url"]
    assert url.startswith(f"/api/photos/cooklog/{user.id}/")
    assert client.get(url).status_code == 200

    app.config["DEV_MODE"] = False  # 운영에서 R2가 없으면
    assert error(write(client, image=JPEG)) == (503, "사진을 지금은 올릴 수 없어요.")
    app.config["DEV_MODE"] = True
    assert write(client, image=b"hello").status_code == 415
    monkeypatch.setattr("app.cooklog.MAX_USER_PHOTO_BYTES", len(JPEG))  # 이미 한 장이 있다
    assert error(write(client, image=JPEG)) == (400, PHOTO_FULL)
    monkeypatch.setattr("app.cooklog.MAX_COOK_LOGS", 1)
    assert error(write(client)) == (400, "요리 일기는 1개까지 남길 수 있어요.")
    assert counts(app) == (1, 0)

    log_id = res.get_json()["log"]["id"]
    monkeypatch.setattr("app.cooklog.MAX_USER_PHOTO_BYTES", 10**6)
    replaced = client.put(f"/api/cook-logs/{log_id}/photo", data={"image": (io.BytesIO(PNG), "b.png")}, content_type="multipart/form-data")
    assert replaced.status_code == 200, replaced.get_json()
    assert replaced.get_json()["manual"] is True
    assert not os.path.exists(photo_path(app, url))
    assert client.delete(f"/api/cook-logs/{log_id}/photo").status_code == 204
    assert client.get(f"/api/cook-logs/{log_id}").get_json()["photo_url"] is None


def test_manual_undo_deletes_diary_food_log_and_photo(client, login, app):
    login()
    log = write(client, image=JPEG, food_log=True, meal="lunch").get_json()["log"]
    path = photo_path(app, log["photo_url"])
    assert os.path.exists(path)
    res = client.post(f"/api/cook-logs/{log['id']}/undo")
    assert (res.status_code, res.get_json()) == (200, {"restored": [], "skipped": []})
    assert counts(app) == (0, 0)
    assert not os.path.exists(path)
    assert client.post(f"/api/cook-logs/{log['id']}/undo").status_code == 404


def test_manual_patch_cost_recomputes_saved(client, login, app):
    login()
    log = write(client, eat_out_price=9000).get_json()["log"]

    def patch(body):
        return client.patch(f"/api/cook-logs/{log['id']}", json=body)

    def money(body):
        res = patch(body)
        assert res.status_code == 200, res.get_json()
        got = res.get_json()
        return got["ingredient_cost"], got["saved"]

    assert money({"ingredient_cost": 6500}) == (6500, 11500)
    assert money({"eat_out_price": 10000}) == (6500, 13500)  # 적어 둔 재료비로 다시 계산
    assert money({"eat_out_price": None}) == (6500, None)
    assert money({"eat_out_price": 9000}) == (6500, 11500)
    assert money({"ingredient_cost": None}) == (None, None)
    assert money({"eat_out_price": 8000}) == (None, None)  # 재료비는 모름 그대로
    assert money({"ingredient_cost": 0, "eat_out_price": 9000}) == (0, 18000)
    assert money({"eat_out_price": 9500}) == (0, 19000)  # 아낀 돈이 있어 0원을 적은 줄 안다
    assert money({"rating": 4, "memo": "다음엔 덜 맵게"}) == (0, 19000)
    # ponytail: 사 먹으면 얼마를 비우면 0원과 빈 재료비를 구별하지 못해 모름으로 읽는다(칸 하나로 두려고 받아들인 한계)
    assert money({"eat_out_price": None}) == (None, None)

    for bad, message in (({"ingredient_cost": -1}, COST_ERROR), ({"ingredient_cost": "1"}, COST_ERROR), ({"servings": 3}, BAD), ({"usages": []}, BAD)):
        assert error(patch(bad)) == (400, message)
    got = client.get(f"/api/cook-logs/{log['id']}").get_json()
    assert (got["rating"], got["memo"], got["eat_out_source"]) == (4, "다음엔 덜 맵게", None)


def test_recipe_diary_patch_rejects_manual_fields(client, login):
    login()
    recipe = add_recipe(client, "김치찌개", [{"name": "김치", "amount": "300g"}])
    log = cook(client, recipe["id"], [], eat_out_price=9000).get_json()["log"]
    for body in ({"ingredient_cost": 100}, {"title": "딴 이름"}):  # 레시피 일기의 이름은 레시피에서, 재료비는 쓴 재료에서
        assert error(client.patch(f"/api/cook-logs/{log['id']}", json=body)) == (400, BAD)
    assert client.get(f"/api/cook-logs/{log['id']}").get_json()["title"] == "김치찌개"


def test_manual_patch_title_renames_diary_and_its_food_log(client, login):
    """사용자 결정(2026-09-17): 직접 쓴 일기는 이름을 고칠 수 있다. 함께 만든 이름만 적은 먹은 기록도 같은 이름이면 같이 바꾼다."""
    login()
    log = write(client, food_log=True, meal="dinner").get_json()["log"]
    quiet = write(client, title="라면", cooked_on="2026-09-14").get_json()["log"]  # 먹은 기록 없이 쓴 일기

    def patch(log_id, body):
        return client.patch(f"/api/cook-logs/{log_id}", json=body)

    def food_title():
        return client.get("/api/food-logs?date=2026-09-15").get_json()["logs"][0]["title"]

    res = patch(log["id"], {"title": "  고추장 제육덮밥  "})
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["title"] == "고추장 제육덮밥"
    assert [i["title"] for i in client.get("/api/cook-logs").get_json()["items"]] == ["고추장 제육덮밥", "라면"]
    assert food_title() == "고추장 제육덮밥"
    assert patch(quiet["id"], {"title": "짜파게티"}).get_json()["title"] == "짜파게티"

    # 먹은 기록에서 따로 고친 이름은 그대로 둔다
    assert client.patch(f"/api/food-logs/{log['food_log_id']}", json={"title": "제육덮밥 반 그릇"}).status_code == 200
    assert patch(log["id"], {"title": "제육덮밥"}).status_code == 200
    assert food_title() == "제육덮밥 반 그릇"

    for bad, message in (({"title": ""}, TITLE_ERROR), ({"title": "가" * 61}, TITLE_ERROR), ({"title": None}, TITLE_ERROR), ({"title": "제\x00육"}, BAD)):
        assert error(patch(log["id"], bad)) == (400, message)
    assert client.get(f"/api/cook-logs/{log['id']}").get_json()["title"] == "제육덮밥"


def test_manual_delete_keeps_food_log(client, login, app):
    login()
    log = write(client, food_log=True, meal="dinner").get_json()["log"]
    assert client.delete(f"/api/cook-logs/{log['id']}").status_code == 204
    assert counts(app) == (0, 1)


def test_manual_is_not_a_deleted_recipe(client, login):
    """레시피를 지워 recipe_id가 비은 일기와 직접 쓴 일기를 구별한다."""
    user = login()
    recipe = add_recipe(client, "김치찌개", [{"name": "김치", "amount": "300g"}])
    cooked = cook(client, recipe["id"], []).get_json()["log"]
    written = write(client, title="라면", cooked_on="2026-09-14").get_json()["log"]
    assert client.delete(f"/api/recipes/{recipe['id']}").status_code == 204

    items = client.get("/api/cook-logs").get_json()["items"]
    assert [(i["id"], i["recipe_id"], i["manual"]) for i in items] == [(cooked["id"], None, False), (written["id"], None, True)]
    detail = client.get(f"/api/cook-logs/{written['id']}").get_json()
    assert (detail["manual"], detail["items"], detail["ingredient_cost"]) == (True, [], None)
    assert client.get(f"/api/cook-logs/{cooked['id']}").get_json()["ingredient_cost"] == 0  # 레시피 일기는 0 그대로

    login("other")
    assert client.get(f"/api/cook-logs/{written['id']}").status_code == 404
    assert client.patch(f"/api/cook-logs/{written['id']}", json={"ingredient_cost": 1}).status_code == 404
    as_user(client, user)


def test_report_counts_manual_diaries(client, login):
    login()
    write(client, title="제육덮밥", eat_out_price=9000, ingredient_cost=6500)  # 11,500
    write(client, title="제육 덮밥", cooked_on="2026-09-14", servings=1, eat_out_price=8000, ingredient_cost=4000)  # 4,000
    write(client, title="라면", cooked_on="2026-09-13", eat_out_price=5000)  # 재료비 모름 — 계산 못 함
    report = client.get("/api/cook-report?month=2026-09").get_json()
    assert (report["cooked"], report["counted"], report["saved_total"], report["excluded_ingredients"], report["logged_days"]) == (
        3, 2, 15500, 0, 3,
    )
    assert report["top_saved"] == [{"title": "제육덮밥", "saved": 15500}]  # 같은 이름(공백 무시)끼리 묶어 최근 제목


def test_export_manual_diary_rows(client, login):
    login()
    write(client, title="제육덮밥", cooked_on="2026-09-14", eat_out_price=9000, ingredient_cost=6500)
    write(client, title="라면", eat_out_price=5000)
    files = read_zip(client.get("/api/export"))
    rows = files["cook_logs.csv"][1:]
    # 요리, 사 먹으면, 출처, 재료비, 아낀 돈, 가격 제외 재료 수, 쓴 재료
    assert [[row[1], *row[5:11]] for row in rows] == [
        ["제육덮밥", "9000", "직접", "6500", "11500", "0", "재료비 직접 적음"],
        ["라면", "5000", "직접", "", "", "0", ""],
    ]


def test_demo_account_writes_manual_diary_without_ai(make_app):
    demo_app = make_app(DEMO_LOGIN=True)
    c = demo_app.test_client()
    c.environ_base.update(HTTP_X_REQUESTED_WITH="fetch", REMOTE_ADDR="10.0.0.9")
    assert c.post("/api/demo-login").status_code == 200
    res = write(c, eat_out_price=9000, ingredient_cost=6500, food_log=True, meal="dinner", image=JPEG)
    assert res.status_code == 201, res.get_json()
    assert (res.get_json()["log"]["saved"], res.get_json()["log"]["manual"]) == (11500, True)
    with demo_app.app_context():
        assert AiCall.query.count() == 0


def test_recipe_choices_include_cooked(client, login):
    user = login()
    kimchi = add_recipe(client, "김치찌개", [{"name": "김치", "amount": "300g"}])
    add_recipe(client, "두부조림", [{"name": "두부", "amount": "1모"}])
    assert cook(client, kimchi["id"], [], cooked_on="2026-09-11").status_code == 201
    assert cook(client, kimchi["id"], [], cooked_on="2026-09-14").status_code == 201
    write(client, title="김치찌개")  # 직접 쓴 일기는 레시피에 세지 않는다
    items = {i["title"]: i for i in client.get("/api/recipes/choices").get_json()["items"]}
    assert items["김치찌개"]["cooked"] == {"count": 2, "last_on": "2026-09-14"}
    assert items["두부조림"]["cooked"] is None

    login("other")
    assert client.get("/api/recipes/choices").get_json()["items"] == []
    as_user(client, user)
