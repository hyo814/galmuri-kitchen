from datetime import date, timedelta

import pytest

from app.ingredients import ingredient_status, seoul_today
from app.models import Ingredient, User, db

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


def create(client, **fields):
    body = {"name": "우유", "quantity": 1, "unit": "개", "purchased_on": seoul_today().isoformat(), **fields}
    return client.post("/api/ingredients", json=body)


def test_requires_login(client):
    assert client.get("/api/ingredients").status_code == 401


def test_create_and_list_sorted_by_urgency(client, login):
    login()
    today = seoul_today()
    create(client, name="계란")
    create(client, name="두부", purchased_on=(today - timedelta(days=30)).isoformat())
    res = create(client, name="우유", expires_on=today.isoformat())
    assert res.status_code == 201
    assert res.get_json()["status"] == "urgent"

    items = client.get("/api/ingredients").get_json()
    assert [(i["name"], i["status"]) for i in items] == [("우유", "urgent"), ("두부", "old"), ("계란", "ok")]
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


def test_deleting_user_cascades_ingredients(app):
    with app.app_context():
        user = User(provider="test", provider_id="cascade", nickname="x")
        db.session.add(user)
        db.session.commit()
        db.session.add(Ingredient(user_id=user.id, name="계란", purchased_on=date(2026, 1, 1)))
        db.session.commit()

        db.session.delete(user)
        db.session.commit()

        assert Ingredient.query.filter_by(user_id=user.id).count() == 0
