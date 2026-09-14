import pytest

from app.models import Seasoning, User, db

ITEMS = [{"name": "고추장", "amount": 2, "unit": "큰술"}, {"name": "설탕", "amount": 2 / 3, "unit": "큰술"}]
BODY = {
    "name": "제육볶음 양념",
    "basis": "main_weight",
    "basis_amount": 600,
    "basis_unit": "g",
    "main_ingredient": "돼지고기",
    "items": ITEMS,
}


def create(client, **fields):
    return client.post("/api/seasonings", json={**BODY, **fields})


def names(client):
    return [s["name"] for s in client.get("/api/seasonings").get_json()["items"]]


def test_requires_login(client, raw_client):
    assert client.get("/api/seasonings").status_code == 401
    assert client.get("/api/seasonings/1").status_code == 401
    for method, path in [("post", "/api/seasonings"), ("put", "/api/seasonings/1"), ("delete", "/api/seasonings/1")]:
        res = getattr(raw_client, method)(path, json=BODY)
        assert (res.status_code, res.get_json()) == (400, {"error": "잘못된 요청이에요."})


def test_create_list_get_update_delete(client, login):
    login()
    res = create(client, name=" 제육볶음 양념 ", items=[{**ITEMS[0], "name": " 고추장 ", "extra": 1}, ITEMS[1]])
    assert res.status_code == 201
    first = res.get_json()
    assert first == {
        "id": first["id"],
        "name": "제육볶음 양념",
        "basis": "main_weight",
        "basis_amount": 600,
        "basis_unit": "g",
        "main_ingredient": "돼지고기",
        "items": ITEMS,
        "source": "user",
        "source_note": None,
        "updated_at": first["updated_at"],
    }
    second = create(client, name="초고추장", basis="yield", basis_amount=0.5, basis_unit="컵", main_ingredient=None).get_json()
    assert names(client) == ["초고추장", "제육볶음 양념"]
    assert client.get(f"/api/seasonings/{first['id']}").get_json() == first

    body = {
        "name": "간장조림 양념",
        "basis": "servings",
        "basis_amount": 2,
        "basis_unit": "인분",
        "items": [{"name": "간장", "amount": 3, "unit": "큰술"}],
    }
    res = client.put(f"/api/seasonings/{first['id']}", json=body)
    assert res.status_code == 200
    updated = res.get_json()
    assert {k: updated[k] for k in (*body, "main_ingredient")} == {**body, "main_ingredient": None}
    assert updated["updated_at"] != first["updated_at"]
    assert names(client) == ["간장조림 양념", "초고추장"]

    assert client.delete(f"/api/seasonings/{second['id']}").status_code == 204
    assert client.get(f"/api/seasonings/{second['id']}").status_code == 404
    assert names(client) == ["간장조림 양념"]


BASIS_ERROR = "기준을 다시 확인해주세요."
AMOUNT_ERROR = "기준 양을 다시 확인해주세요."


@pytest.mark.parametrize(
    "fields, error",
    [
        ({"name": None}, "이름은 1~30자로 입력해주세요."),
        ({"name": " "}, "이름은 1~30자로 입력해주세요."),
        ({"name": "가" * 31}, "이름은 1~30자로 입력해주세요."),
        ({"basis": "yield", "basis_unit": "g"}, BASIS_ERROR),
        ({"basis": "weight"}, BASIS_ERROR),
        ({"basis": ["main_weight"]}, BASIS_ERROR),
        ({"basis": "servings", "basis_unit": "인분", "basis_amount": 1.5}, AMOUNT_ERROR),
        ({"basis": "servings", "basis_unit": "인분", "basis_amount": 0}, AMOUNT_ERROR),
        ({"basis": "servings", "basis_unit": "인분", "basis_amount": 21}, AMOUNT_ERROR),
        ({"basis_amount": True}, AMOUNT_ERROR),
        ({"basis_amount": "600"}, AMOUNT_ERROR),
        ({"basis_amount": 0}, AMOUNT_ERROR),
        ({"basis_amount": 10001}, AMOUNT_ERROR),
        ({"basis_amount": float("inf")}, AMOUNT_ERROR),
        ({"main_ingredient": "가" * 51}, "주재료는 50자까지 입력해주세요."),
        ({"main_ingredient": 1}, "주재료는 50자까지 입력해주세요."),
        ({"items": []}, "양념을 1~30개 입력해주세요."),
        ({"items": ITEMS[:1] * 31}, "양념을 1~30개 입력해주세요."),
        ({"items": "고추장"}, "양념을 1~30개 입력해주세요."),
        ({"items": ["고추장"]}, "잘못된 요청이에요."),
        ({"items": [ITEMS[0], {**ITEMS[0], "name": "가" * 31}]}, "2번째 양념 이름은 1~30자로 입력해주세요."),
        ({"items": [{**ITEMS[0], "amount": 0}]}, "1번째 양념 양을 다시 확인해주세요."),
        ({"items": [{**ITEMS[0], "amount": True}]}, "1번째 양념 양을 다시 확인해주세요."),
        ({"items": [{**ITEMS[0], "amount": "2"}]}, "1번째 양념 양을 다시 확인해주세요."),
        ({"items": [{**ITEMS[0], "amount": 10001}]}, "1번째 양념 양을 다시 확인해주세요."),
        ({"items": [{**ITEMS[0], "amount": float("nan")}]}, "1번째 양념 양을 다시 확인해주세요."),
        ({"items": [{**ITEMS[0], "unit": "숟가락"}]}, "1번째 양념 단위를 다시 골라주세요."),
    ],
)
def test_validation(client, login, fields, error):
    login()
    res = create(client, **fields)
    assert (res.status_code, res.get_json()) == (400, {"error": error})
    assert names(client) == []


def test_accepts_every_unit_basis_and_boundary(client, login):
    login()
    units = ["큰술", "작은술", "컵", "ml", "g", "개", "꼬집"]
    items = [{"name": f"양념{i}", "amount": 10000 if i else 0.25, "unit": u} for i, u in enumerate(units)]
    assert create(client, name="가" * 30, basis_amount=10000, main_ingredient="가" * 50, items=items).status_code == 201
    assert create(client, name="완성 ml", basis="yield", basis_amount=300, basis_unit="ml").status_code == 201
    assert create(client, name="20인분", basis="servings", basis_amount=20, basis_unit="인분").status_code == 201
    assert create(client, name="주재료 빈칸", main_ingredient=" ").get_json()["main_ingredient"] is None
    assert client.post("/api/seasonings", json=["name"]).status_code == 400


def test_main_ingredient_only_for_main_weight(client, login):
    login()
    res = create(client, basis="servings", basis_amount=2, basis_unit="인분", main_ingredient="돼지고기")
    assert (res.status_code, res.get_json()["main_ingredient"]) == (201, None)


def test_duplicate_name_400_and_cap_100(client, login, app):
    user = login()
    assert create(client).status_code == 201
    res = create(client)
    assert (res.status_code, res.get_json()) == (400, {"error": "같은 이름의 비율이 있어요."})
    other = create(client, name="불고기 양념").get_json()
    res = client.put(f"/api/seasonings/{other['id']}", json=BODY)
    assert (res.status_code, res.get_json()) == (400, {"error": "같은 이름의 비율이 있어요."})

    with app.app_context():
        db.session.add_all(
            Seasoning(user_id=user.id, name=f"비율{i}", basis="servings", basis_amount=2, basis_unit="인분", items=ITEMS)
            for i in range(98)
        )
        db.session.commit()
    res = create(client, name="101번째")
    assert (res.status_code, res.get_json()) == (400, {"error": "양념 비율은 100개까지 저장할 수 있어요."})


def test_other_users_seasoning_is_404(client, login):
    login("owner")
    seasoning = create(client).get_json()
    login("intruder")
    assert names(client) == []
    assert client.get(f"/api/seasonings/{seasoning['id']}").status_code == 404
    assert client.put(f"/api/seasonings/{seasoning['id']}", json=BODY).status_code == 404
    assert client.delete(f"/api/seasonings/{seasoning['id']}").status_code == 404
    assert client.get(f"/api/seasonings/{2**40}").status_code == 404


def test_user_delete_cascades(client, login, app):
    user = login()
    seasoning_id = create(client).get_json()["id"]
    with app.app_context():
        db.session.delete(db.session.get(User, user.id))
        db.session.commit()
        assert db.session.get(Seasoning, seasoning_id) is None
