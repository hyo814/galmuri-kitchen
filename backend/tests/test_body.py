from datetime import date

import pytest

from app.models import BodyProfile, User, db

VALID = {"sex": "female", "birth_year": 1994, "height_cm": 162, "weight_kg": 58, "activity": "light", "goal": "lose"}


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr("app.body.seoul_today", lambda: date(2026, 9, 15))


def put(client, **overrides):
    return client.put("/api/body-profile", json={**VALID, **overrides})


def test_requires_login_and_csrf(client, raw_client):
    assert client.get("/api/body-profile").status_code == 401
    assert raw_client.put("/api/body-profile", json=VALID).status_code == 400


def test_get_empty_then_put_and_get(client, login):
    login()
    res = client.get("/api/body-profile")
    assert res.get_json() == {"profile": None}
    assert res.headers["Cache-Control"] == "no-store"

    res = put(client)
    assert res.status_code == 200
    profile = res.get_json()["profile"]
    assert (profile["height_cm"], profile["weight_kg"]) == (162.0, 58.0)
    assert isinstance(profile["updated_at"], str)

    assert client.get("/api/body-profile").get_json()["profile"] == profile


def test_put_overwrites_single_row(client, login, app):
    login()
    put(client)
    res = put(client, weight_kg=57.46)
    assert res.get_json()["profile"]["weight_kg"] == 57.5
    with app.app_context():
        assert BodyProfile.query.count() == 1


@pytest.mark.parametrize(
    "body, message",
    [
        ({**VALID, "sex": "other"}, "성별을 골라주세요."),
        ({**VALID, "birth_year": 1926}, "태어난 해는 1927~2006 사이 정수로 입력해주세요."),
        ({**VALID, "birth_year": 2007}, "태어난 해는 1927~2006 사이 정수로 입력해주세요."),
        ({**VALID, "birth_year": "1994"}, "태어난 해는 1927~2006 사이 정수로 입력해주세요."),
        ({**VALID, "birth_year": True}, "태어난 해는 1927~2006 사이 정수로 입력해주세요."),
        ({**VALID, "height_cm": 119.9}, "키는 120~230 사이 숫자로 입력해주세요."),
        ({**VALID, "height_cm": 231}, "키는 120~230 사이 숫자로 입력해주세요."),
        ({**VALID, "height_cm": "162"}, "키는 120~230 사이 숫자로 입력해주세요."),
        ({**VALID, "height_cm": None}, "키는 120~230 사이 숫자로 입력해주세요."),
        ({**VALID, "weight_kg": 29}, "몸무게는 30~250 사이 숫자로 입력해주세요."),
        ({**VALID, "weight_kg": 251}, "몸무게는 30~250 사이 숫자로 입력해주세요."),
        ({**VALID, "activity": "none"}, "활동량을 골라주세요."),
        ({**VALID, "goal": "bulk"}, "목표를 골라주세요."),
        ({k: v for k, v in VALID.items() if k != "goal"}, "목표를 골라주세요."),
        ([], "잘못된 요청이에요."),
    ],
)
def test_put_validation(client, login, app, body, message):
    login()
    res = client.put("/api/body-profile", json=body)
    assert (res.status_code, res.get_json()["error"]) == (400, message)
    with app.app_context():
        assert BodyProfile.query.count() == 0


def test_delete_is_idempotent(client, login):
    login()
    put(client)
    assert client.delete("/api/body-profile").status_code == 204
    assert client.get("/api/body-profile").get_json() == {"profile": None}
    assert client.delete("/api/body-profile").status_code == 204


def test_other_user_cannot_see(client, login, app):
    login("1")
    put(client)
    login("2")
    assert client.get("/api/body-profile").get_json() == {"profile": None}
    assert client.delete("/api/body-profile").status_code == 204
    with app.app_context():
        assert BodyProfile.query.count() == 1


def test_user_delete_cascades(client, login, app):
    user = login()
    put(client)
    with app.app_context():
        db.session.delete(db.session.get(User, user.id))
        db.session.commit()
        assert BodyProfile.query.count() == 0
