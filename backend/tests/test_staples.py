import pytest

from app.models import Staple, db


def test_in_stock_and_order(client, login):
    login()
    for body in [
        {"name": "간장", "category": "조미료"},
        {"name": "참기름", "category": "조미료"},
        {"name": "대파", "category": "야채"},
        {"name": "계란"},
    ]:
        assert client.post("/api/staples", json=body).status_code == 201
    client.post("/api/ingredients", json={"name": "진간장 (500ml)", "purchased_on": "2026-09-10"})
    client.post("/api/ingredients", json={"name": "계란", "purchased_on": "2026-09-10"})

    body = client.get("/api/staples").get_json()
    assert [(s["name"], s["category"], s["in_stock"]) for s in body] == [
        ("참기름", "조미료", False),
        ("대파", "야채", False),
        ("간장", "조미료", True),
        ("계란", "기타", True),
    ]


@pytest.mark.parametrize(
    "body",
    [
        {"name": ""},
        {"name": "가" * 51},
        {"name": 1},
        {"name": "소금", "category": "가" * 11},
        {"name": "소금", "category": 3},
    ],
)
def test_create_validation(client, login, body):
    login()
    res = client.post("/api/staples", json=body)
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_duplicate_name_rejected(client, login):
    login()
    client.post("/api/staples", json={"name": "소금"})
    res = client.post("/api/staples", json={"name": " 소금 "})
    assert res.status_code == 400
    assert res.get_json()["error"] == "이미 등록된 필수품이에요."


def test_delete_and_ownership(client, login, app):
    login("owner")
    staple = client.post("/api/staples", json={"name": "소금"}).get_json()
    login("intruder")
    assert client.delete(f"/api/staples/{staple['id']}").status_code == 404
    assert client.get("/api/staples").get_json() == []
    with app.app_context():
        assert db.session.get(Staple, staple["id"]) is not None
    login("owner2")
    mine = client.post("/api/staples", json={"name": "후추"}).get_json()
    assert client.delete(f"/api/staples/{mine['id']}").status_code == 204
    assert client.get("/api/staples").get_json() == []
