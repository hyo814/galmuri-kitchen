import pytest


def test_new_user_gets_default_locations(client, login):
    login()
    body = client.get("/api/locations").get_json()
    assert [(l["name"], l["kind"], l["item_count"]) for l in body] == [
        ("냉장실", "fridge", 0),
        ("냉동실", "freezer", 0),
        ("실온", "room", 0),
    ]


def test_dev_login_seeds_defaults_once(client):
    client.post("/api/dev-login")
    assert len(client.get("/api/locations").get_json()) == 3
    client.post("/api/dev-login")
    assert len(client.get("/api/locations").get_json()) == 3


def test_create_rename_and_order(client, login):
    login()
    res = client.post("/api/locations", json={"name": " 김치냉장고 ", "kind": "fridge"})
    assert res.status_code == 201
    location = res.get_json()
    assert (location["name"], location["item_count"]) == ("김치냉장고", 0)
    assert client.get("/api/locations").get_json()[-1]["name"] == "김치냉장고"

    res = client.patch(f"/api/locations/{location['id']}", json={"name": "찬장", "kind": "room"})
    assert res.status_code == 200
    assert (res.get_json()["name"], res.get_json()["kind"]) == ("찬장", "room")


@pytest.mark.parametrize(
    "body",
    [
        {"name": "", "kind": "fridge"},
        {"name": "가" * 21, "kind": "fridge"},
        {"name": 3, "kind": "fridge"},
        {"name": "베란다", "kind": "garage"},
        {"name": "냉장실", "kind": "fridge"},
    ],
)
def test_create_validation(client, login, body):
    login()
    res = client.post("/api/locations", json=body)
    assert res.status_code == 400
    assert "error" in res.get_json()


def test_delete_rules_and_item_count(client, login):
    login()
    fridge, freezer, room = (l["id"] for l in client.get("/api/locations").get_json())
    client.post("/api/ingredients", json={"name": "우유", "purchased_on": "2026-09-10", "location_id": fridge})
    assert client.get("/api/locations").get_json()[0]["item_count"] == 1

    res = client.delete(f"/api/locations/{fridge}")
    assert res.status_code == 400
    assert res.get_json()["error"] == "이 위치에 있는 재료를 먼저 옮겨 주세요."

    assert client.delete(f"/api/locations/{freezer}").status_code == 204
    assert client.delete(f"/api/locations/{room}").status_code == 204

    item = client.get("/api/ingredients").get_json()[0]
    client.delete(f"/api/ingredients/{item['id']}")
    res = client.delete(f"/api/locations/{fridge}")
    assert res.status_code == 400
    assert res.get_json()["error"] == "위치는 하나 이상 있어야 해요."


def test_other_users_location_is_hidden(client, login):
    login("owner")
    location_id = client.get("/api/locations").get_json()[0]["id"]
    login("intruder")
    assert client.patch(f"/api/locations/{location_id}", json={"name": "x"}).status_code == 404
    assert client.delete(f"/api/locations/{location_id}").status_code == 404
    res = client.post("/api/ingredients", json={"name": "우유", "purchased_on": "2026-09-10", "location_id": location_id})
    assert res.status_code == 400
    assert res.get_json()["error"] == "보관 위치를 다시 선택해 주세요."
