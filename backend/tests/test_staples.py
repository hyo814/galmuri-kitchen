import pytest

from app.models import Staple, db


def test_in_stock_and_order(client, login):
    login()
    # 대파·참기름은 기본 필수품(2026-09-17)이라 이미 있고, 간장·계란은 없어(달걀·진간장 등만 기본) 직접 더한다
    assert client.post("/api/staples", json={"name": "간장", "category": "조미료"}).status_code == 201
    assert client.post("/api/staples", json={"name": "계란"}).status_code == 201

    # 아직 재고가 없으면: 직접 추가한 간장·계란은 바로 missing, 재고 없던 기본 필수품(대파·참기름)은 unstocked
    before = {s["name"]: s["status"] for s in client.get("/api/staples").get_json()}
    assert (before["참기름"], before["대파"], before["간장"], before["계란"]) == ("unstocked", "unstocked", "missing", "missing")

    client.post("/api/ingredients", json={"name": "진간장 (500ml)", "purchased_on": "2026-09-10"})
    client.post("/api/ingredients", json={"name": "계란", "purchased_on": "2026-09-10"})

    body = {s["name"]: s for s in client.get("/api/staples").get_json()}
    assert (body["참기름"]["category"], body["참기름"]["in_stock"], body["참기름"]["status"]) == ("조미료", False, "unstocked")
    assert (body["대파"]["category"], body["대파"]["in_stock"], body["대파"]["status"]) == ("야채", False, "unstocked")
    assert (body["간장"]["category"], body["간장"]["in_stock"], body["간장"]["status"]) == ("조미료", True, "in_stock")
    assert (body["계란"]["category"], body["계란"]["in_stock"], body["계란"]["status"]) == ("기타", True, "in_stock")


def test_new_user_has_no_missing_staples(client, login):
    # 새 사용자: 기본 필수품은 모두 unstocked(재고에서 본 적 없음)라 떨어짐 배너 대상이 없다
    login()
    rows = client.get("/api/staples").get_json()
    assert all(s["status"] == "unstocked" for s in rows)


def test_staple_becomes_missing_only_after_having_stock_then_losing_it(client, login):
    # "가졌던 것만 배너에"(2026-09-17): 재고에 넣은 적 있어야 떨어짐으로 친다
    login()
    before = next(s for s in client.get("/api/staples").get_json() if s["name"] == "대파")
    assert before["status"] == "unstocked"

    item = client.post("/api/ingredients", json={"name": "대파", "purchased_on": "2026-09-10"}).get_json()
    during = next(s for s in client.get("/api/staples").get_json() if s["name"] == "대파")
    assert during["status"] == "in_stock"

    client.delete(f"/api/ingredients/{item['id']}")
    after = next(s for s in client.get("/api/staples").get_json() if s["name"] == "대파")
    assert after["status"] == "missing"  # 한 번 있었다가 없어져서 이제는 배너 대상


def test_manually_added_staple_is_missing_immediately(client, login):
    # 직접 추가는 명시적으로 원한 것이니 재고가 없어도 곧장 missing(unstocked를 거치지 않음)
    login()
    created = client.post("/api/staples", json={"name": "우리집 양념"}).get_json()
    assert created["status"] == "missing"


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
    # 소금·후추는 이제 기본 필수품(2026-09-17)이라 로그인만 해도 있다 — 여기서는 직접 만든 필수품으로 삭제·소유권을 본다
    login("owner")
    staple = client.post("/api/staples", json={"name": "우리집 양념"}).get_json()
    login("intruder")
    assert client.delete(f"/api/staples/{staple['id']}").status_code == 404
    assert staple["id"] not in [s["id"] for s in client.get("/api/staples").get_json()]
    with app.app_context():
        assert db.session.get(Staple, staple["id"]) is not None
    login("owner2")
    mine = client.post("/api/staples", json={"name": "우리집 양념"}).get_json()
    assert client.delete(f"/api/staples/{mine['id']}").status_code == 204
    assert mine["id"] not in [s["id"] for s in client.get("/api/staples").get_json()]


def test_matched_name_and_short_name_false_positive(client, login):
    login()
    client.post("/api/staples", json={"name": "파", "category": "야채"})
    client.post("/api/staples", json={"name": "간장", "category": "조미료"})
    client.post("/api/ingredients", json={"name": "양파", "purchased_on": "2026-09-10"})
    client.post("/api/ingredients", json={"name": "진간장 (500ml)", "purchased_on": "2026-09-10"})
    rows = {s["name"]: s for s in client.get("/api/staples").get_json()}
    assert (rows["파"]["in_stock"], rows["파"]["matched_name"]) == (False, None)
    assert (rows["간장"]["in_stock"], rows["간장"]["matched_name"]) == (True, "진간장 (500ml)")
