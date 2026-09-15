from datetime import date, datetime, time, timedelta, timezone

from app import ai, scan
from app.ingredients import SEOUL
from app.models import AiCall, Recipe, User, db
from tests.test_meals import add_recipe
from tests.test_scan import USAGE, ai_calls, fail_if_called

FAIL = "사 먹는 가격을 추정하지 못했어요. 직접 입력해주세요."
OFF = "사 먹는 가격을 지금은 추정할 수 없어요."


def estimate(client, recipe_id):
    return client.post(f"/api/recipes/{recipe_id}/eat-out-estimate")


def test_sample_mode_stores_once_without_record(client, login, app):
    login()
    recipe = add_recipe(client, "김치찌개", [{"name": "김치", "amount": "300g"}])
    res = estimate(client, recipe["id"])
    assert (res.status_code, res.get_json()) == (200, {"eat_out_price": 9000, "eat_out_source": "sample"})
    with app.app_context():
        assert AiCall.query.count() == 0
    got = client.get(f"/api/recipes/{recipe['id']}").get_json()
    assert (got["eat_out_price"], got["eat_out_source"]) == (9000, "sample")

    res2 = estimate(client, recipe["id"])
    assert (res2.status_code, res2.get_json()) == (200, {"eat_out_price": 9000, "eat_out_source": "sample"})


def test_on_mode_calls_ai_once_and_counts_recipe_group(client, login, app, monkeypatch):
    user = login()
    app.config["ANTHROPIC_API_KEY"] = "k"
    recipe = add_recipe(client, "부대찌개", [{"name": "햄", "amount": "100g"}, {"name": "김치", "amount": "200g"}])
    calls = []

    def fake(title, names):
        calls.append((title, names))
        return {"price": 12000}, USAGE

    monkeypatch.setattr(ai, "estimate_eat_out", fake)
    res = estimate(client, recipe["id"])
    assert (res.status_code, res.get_json()) == (200, {"eat_out_price": 12000, "eat_out_source": "ai"})
    assert calls == [("부대찌개", ["햄", "김치"])]
    assert ai_calls(app) == [(user.id, "eat_out")]
    with app.app_context():
        call = AiCall.query.one()
        assert (call.model, call.input_tokens, call.output_tokens) == (USAGE["model"], USAGE["input_tokens"], USAGE["output_tokens"])

    monkeypatch.setattr(ai, "estimate_eat_out", fail_if_called)
    res2 = estimate(client, recipe["id"])
    assert (res2.status_code, res2.get_json()) == (200, {"eat_out_price": 12000, "eat_out_source": "ai"})

    assert client.get("/api/ai-usage").get_json()["recipe"]["used"] == 1


def test_limits_and_failures(client, login, app, monkeypatch):
    user = login()
    app.config["ANTHROPIC_API_KEY"] = "k"
    recipe = add_recipe(client, "된장찌개", [{"name": "두부", "amount": "1모"}])

    today = date(2026, 9, 13)
    start = datetime.combine(today, time.min, tzinfo=SEOUL).astimezone(timezone.utc)
    clock = {"now": start + timedelta(hours=12)}
    monkeypatch.setattr(scan, "seoul_today", lambda: today)
    monkeypatch.setattr(scan, "utcnow", lambda: clock["now"])

    # ① 오늘 recipe 그룹 10번 -> 429, 값은 그대로 None
    with app.app_context():
        db.session.add_all(AiCall(user_id=user.id, kind="recipe", created_at=start + timedelta(minutes=i)) for i in range(10))
        db.session.commit()
    monkeypatch.setattr(ai, "estimate_eat_out", fail_if_called)
    res = estimate(client, recipe["id"])
    assert (res.status_code, res.get_json()) == (429, {"error": "오늘 AI 레시피는 10번까지 쓸 수 있어요. 내일 다시 써주세요."})
    assert client.get(f"/api/recipes/{recipe['id']}").get_json()["eat_out_price"] is None

    with app.app_context():
        AiCall.query.delete()
        db.session.commit()

    # ② AiError -> 502, AiCall 1행(토큰 None), 값 None
    clock["now"] += timedelta(minutes=5)
    monkeypatch.setattr(ai, "estimate_eat_out", lambda *a: (_ for _ in ()).throw(ai.AiError("x")))
    res = estimate(client, recipe["id"])
    assert (res.status_code, res.get_json()) == (502, {"error": FAIL})
    with app.app_context():
        rows = AiCall.query.all()
        assert len(rows) == 1 and rows[0].kind == "eat_out" and rows[0].input_tokens is None
    assert client.get(f"/api/recipes/{recipe['id']}").get_json()["eat_out_price"] is None

    # ③ 범위 밖 가격(500·150000)·불리언(True) -> 502, 값 None
    for bad_price in (500, 150000, True):
        clock["now"] += timedelta(minutes=5)
        monkeypatch.setattr(ai, "estimate_eat_out", lambda *a, p=bad_price: ({"price": p}, USAGE))
        res = estimate(client, recipe["id"])
        assert (res.status_code, res.get_json()) == (502, {"error": FAIL})
        assert client.get(f"/api/recipes/{recipe['id']}").get_json()["eat_out_price"] is None

    # ④ DEV_MODE False·키 없음 -> 503
    app.config.update(ANTHROPIC_API_KEY=None, DEV_MODE=False)
    monkeypatch.setattr(ai, "estimate_eat_out", fail_if_called)
    res = estimate(client, recipe["id"])
    assert (res.status_code, res.get_json()) == (503, {"error": OFF})


def test_user_value_wins_race(client, login, app, monkeypatch):
    login()
    app.config["ANTHROPIC_API_KEY"] = "k"
    recipe = add_recipe(client, "김치찌개", [{"name": "김치", "amount": "300g"}])

    def fake(title, names):
        # AI가 도는 사이 다른 요청이 사용자 값을 먼저 저장한 것처럼 만든다
        Recipe.query.filter_by(id=recipe["id"]).update({"eat_out_price": 7000, "eat_out_source": "user"})
        db.session.commit()
        return {"price": 12000}, USAGE

    monkeypatch.setattr(ai, "estimate_eat_out", fake)
    res = estimate(client, recipe["id"])
    assert (res.status_code, res.get_json()) == (200, {"eat_out_price": 7000, "eat_out_source": "user"})


def test_keeps_recipe_list_order(client, login):
    login()
    a = add_recipe(client, "김치찌개", [{"name": "김치", "amount": "300g"}])
    b = add_recipe(client, "된장찌개", [{"name": "두부", "amount": "1모"}])
    assert estimate(client, a["id"]).status_code == 200
    items = client.get("/api/recipes").get_json()["items"]
    assert items[0]["id"] == b["id"]


def test_ownership(client, login, raw_client):
    login("owner")
    recipe = add_recipe(client, "김치찌개", [{"name": "김치", "amount": "300g"}])
    rid = recipe["id"]
    login("intruder")
    assert estimate(client, rid).status_code == 404
    assert estimate(client, 2**31).status_code == 404
    assert raw_client.post(f"/api/recipes/{rid}/eat-out-estimate").status_code == 400


def test_requires_login(client):
    assert estimate(client, 1).status_code == 401
