import types
from datetime import date, datetime, timedelta

import pytest

from app.ingredients import seoul_today
from app.tools import add_months, check_base, to_json

TOMORROW = (seoul_today() + timedelta(days=1)).isoformat()


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


def clear_defaults(client):
    """기본 주방 도구 13개(defaults.DEFAULT_TOOLS)를 지운다 — 이 파일의 목록 검사는 테스트가 만든 도구만 본다."""
    for tool in client.get("/api/tools").get_json():
        client.delete(f"/api/tools/{tool['id']}")


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
    clear_defaults(client)
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
        {"bought_on": "9999-12-31"},
        {"bought_on": TOMORROW},
    ],
)
def test_create_validation(client, login, fields):
    login()
    res = create(client, **fields)
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_patch_future_bought_on_rejected(client, login):
    login()
    tool = create(client).get_json()
    res = client.patch(f"/api/tools/{tool['id']}", json={"bought_on": "9999-12-31"})
    assert res.status_code == 400
    assert "error" in res.get_json()
    assert client.get("/api/tools").status_code == 200


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
    clear_defaults(client)
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
    clear_defaults(client)
    tool = create(client).get_json()
    assert client.delete(f"/api/tools/{tool['id']}").status_code == 204
    assert client.get("/api/tools").get_json() == []


def test_patch_name_only_keeps_other_fields(client, login):
    login()
    tool = create(client, bought_on="2026-01-01", check_every_months=6).get_json()
    res = client.patch(f"/api/tools/{tool['id']}", json={"name": "새 이름"})
    assert res.status_code == 200
    body = res.get_json()
    assert (body["name"], body["check_every_months"], body["bought_on"]) == ("새 이름", 6, "2026-01-01")


def test_check_base_uses_later_of_check_and_purchase():
    tool = types.SimpleNamespace(last_checked_on=date(2025, 1, 1), bought_on=date(2025, 6, 1), created_at=None)
    assert check_base(tool) == date(2025, 6, 1)


def test_check_base_falls_back_to_created_at_seoul_date_near_midnight():
    tool = types.SimpleNamespace(
        last_checked_on=None, bought_on=None, created_at=datetime(2026, 9, 13, 15, 30)
    )
    assert check_base(tool) == date(2026, 9, 14)


def test_check_base_falls_back_to_created_at_seoul_date_before_midnight():
    tool = types.SimpleNamespace(
        last_checked_on=None, bought_on=None, created_at=datetime(2026, 9, 13, 14, 59)
    )
    assert check_base(tool) == date(2026, 9, 13)


def test_is_due_when_due_exactly_today():
    fixed_today = date(2026, 6, 15)
    tool = types.SimpleNamespace(
        id=1,
        name="팬",
        category="조리도구",
        bought_on=None,
        check_every_months=6,
        last_checked_on=date(2025, 12, 15),
        created_at=None,
    )
    result = to_json(tool, fixed_today)
    assert result["due_on"] == "2026-06-15"
    assert result["is_due"] is True


def test_bought_on_rejects_compact_date(client, login):
    login()
    res = create(client, bought_on="20260101")
    assert (res.status_code, res.get_json()) == (400, {"error": "구매일은 YYYY-MM-DD 형식으로 입력해주세요."})
