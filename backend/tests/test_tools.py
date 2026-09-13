from datetime import date, timedelta

import pytest

from app.ingredients import seoul_today
from app.tools import add_months


@pytest.mark.parametrize(
    "day, months, expected",
    [
        (date(2026, 1, 31), 1, date(2026, 2, 28)),
        (date(2026, 11, 15), 3, date(2027, 2, 15)),
        (date(2024, 8, 31), 6, date(2025, 2, 28)),
        (date(2026, 3, 10), 12, date(2027, 3, 10)),
    ],
)
def test_add_months_clamps_month_end(day, months, expected):
    assert add_months(day, months) == expected


def create(client, **fields):
    return client.post("/api/tools", json={"name": "코팅 프라이팬", "category": "조리기구", **fields})


def test_requires_login(client):
    assert client.get("/api/tools").status_code == 401


def test_pan_due_after_cycle_then_checked_and_replaced(client, login):
    login()
    today = seoul_today()
    bought = add_months(today, -7)
    res = create(client, bought_on=bought.isoformat(), check_every_months=6)
    assert res.status_code == 201
    tool = res.get_json()
    assert tool["is_due"] is True
    assert tool["due_on"] == add_months(bought, 6).isoformat()
    assert tool["days_until_due"] < 0

    checked = client.post(f"/api/tools/{tool['id']}/checked").get_json()
    assert checked["last_checked_on"] == today.isoformat()
    assert checked["is_due"] is False
    assert checked["due_on"] == add_months(today, 6).isoformat()

    replaced = client.post(f"/api/tools/{tool['id']}/replaced").get_json()
    assert (replaced["bought_on"], replaced["last_checked_on"]) == (today.isoformat(), today.isoformat())


def test_without_cycle_never_due(client, login):
    login()
    tool = client.post("/api/tools", json={"name": "뒤집개"}).get_json()
    assert (tool["category"], tool["due_on"], tool["is_due"], tool["days_until_due"]) == ("조리도구", None, False, None)


def test_created_date_is_base_when_no_dates(client, login):
    login()
    tool = create(client, check_every_months=1).get_json()
    assert tool["due_on"] == add_months(seoul_today(), 1).isoformat()


def test_list_sorts_due_first(client, login):
    login()
    today = seoul_today()
    create(client, name="뒤집개", category="조리도구")
    create(client, name="국자", category="조리도구", check_every_months=3)
    create(client, name="코팅 프라이팬", bought_on=add_months(today, -8).isoformat(), check_every_months=6)
    names = [t["name"] for t in client.get("/api/tools").get_json()]
    assert names == ["코팅 프라이팬", "국자", "뒤집개"]


@pytest.mark.parametrize(
    "fields",
    [
        {"name": ""},
        {"name": "가" * 31},
        {"category": "냄비"},
        {"check_every_months": 0},
        {"check_every_months": 61},
        {"check_every_months": True},
        {"check_every_months": "6"},
        {"bought_on": "어제"},
    ],
)
def test_create_validation(client, login, fields):
    login()
    res = create(client, **fields)
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_patch_clears_cycle_and_dates(client, login):
    login()
    tool = create(client, bought_on="2026-01-01", check_every_months=6).get_json()
    res = client.patch(f"/api/tools/{tool['id']}", json={"check_every_months": None, "bought_on": None, "name": "무쇠 팬"})
    assert res.status_code == 200
    body = res.get_json()
    assert (body["name"], body["check_every_months"], body["bought_on"], body["due_on"]) == ("무쇠 팬", None, None, None)


def test_other_users_tool_is_hidden(client, login):
    login("owner")
    tool = create(client).get_json()
    login("intruder")
    assert client.get("/api/tools").get_json() == []
    for method, path in [
        ("patch", f"/api/tools/{tool['id']}"),
        ("delete", f"/api/tools/{tool['id']}"),
        ("post", f"/api/tools/{tool['id']}/checked"),
        ("post", f"/api/tools/{tool['id']}/replaced"),
    ]:
        kwargs = {"json": {"name": "x"}} if method == "patch" else {}
        assert getattr(client, method)(path, **kwargs).status_code == 404


def test_delete(client, login):
    login()
    tool = create(client).get_json()
    assert client.delete(f"/api/tools/{tool['id']}").status_code == 204
    assert client.get("/api/tools").get_json() == []
