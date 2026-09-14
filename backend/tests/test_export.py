import csv
import io
import zipfile
from datetime import timedelta

import app.export as export_module
from app.ingredients import seoul_today
from app.models import AiCall, User, db, utcnow

RECIPE = {
    "title": "두부조림",
    "servings": 2,
    "ingredients": [{"name": "두부", "amount": "1모"}, {"name": "대파", "amount": "1/2대"}, {"name": "물", "amount": ""}],
    "steps": ["두부를 썰어요.", "양념을 붓고 졸여요."],
}
SEASONING = {
    "name": "=제육 양념",
    "basis": "main_weight",
    "basis_amount": 600,
    "basis_unit": "g",
    "main_ingredient": "돼지고기",
    "items": [{"name": "고추장", "amount": 2, "unit": "큰술"}, {"name": "설탕", "amount": 0.5, "unit": "큰술"}],
}


def read_zip(res):
    files = zipfile.ZipFile(io.BytesIO(res.data))
    out = {}
    for name in files.namelist():
        raw = files.read(name)
        assert raw.startswith(b"\xef\xbb\xbf")  # 엑셀이 한글을 알아보도록 BOM
        out[name] = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    return out


def user_id(app, provider_id="1"):
    with app.app_context():
        return User.query.filter_by(provider_id=provider_id).one().id


def test_requires_login(client):
    assert client.get("/api/export").status_code == 401
    assert client.get("/api/export/summary").status_code == 401


def test_summary_counts_only_my_data(client, login):
    login("other")
    client.post("/api/recipes", json=RECIPE)
    login()
    client.post("/api/ingredients", json={"name": "두부", "purchased_on": seoul_today().isoformat()})
    client.post("/api/recipes", json=RECIPE)
    client.post("/api/recipes", json={**RECIPE, "title": "계란말이"})
    client.post("/api/seasonings", json=SEASONING)
    assert client.get("/api/export/summary").get_json() == {
        "ingredients": 1,
        "recipes": 2,
        "seasonings": 1,
        "limit": 5,
        "remaining": 5,
    }


def test_export_zip_contents(client, login, app):
    login("other")
    client.post("/api/recipes", json={**RECIPE, "title": "남의 레시피"})
    login()
    today = seoul_today().isoformat()
    client.post(
        "/api/ingredients",
        json={"name": "@우유", "quantity": 1.5, "unit": "L", "purchased_on": today, "expires_on": "2026-12-01", "price": 2980},
    )
    client.post("/api/ingredients", json={"name": "두부", "purchased_on": today})
    client.post("/api/recipes", json=RECIPE)
    client.post("/api/seasonings", json=SEASONING)

    res = client.get("/api/export")
    assert res.status_code == 200
    assert res.mimetype == "application/zip"
    stamp = seoul_today().strftime("%Y%m%d")
    assert res.headers["Content-Disposition"] == f'attachment; filename="galmuri-kitchen-{stamp}.zip"'
    files = read_zip(res)
    assert set(files) == {"ingredients.csv", "recipes.csv", "seasonings.csv"}

    ingredients = files["ingredients.csv"]
    assert ingredients[0] == ["이름", "수량", "단위", "보관 위치", "구입일", "유통기한", "가격(원)"]
    assert sorted(ingredients[1:]) == sorted(
        [["'@우유", "1.5", "L", "냉장실", today, "2026-12-01", "2980"], ["두부", "1", "개", "냉장실", today, "", ""]]
    )

    recipes = files["recipes.csv"]
    assert recipes[0] == ["제목", "인분", "재료", "만드는 법", "출처", "출처 링크", "사진 주소"]
    assert recipes[1:] == [["두부조림", "2", "두부 1모; 대파 1/2대; 물", "1. 두부를 썰어요.\n2. 양념을 붓고 졸여요.", "직접 입력", "", ""]]

    seasonings = files["seasonings.csv"]
    assert seasonings[0] == ["이름", "기준", "기준 양", "기준 단위", "주재료", "양념"]
    assert seasonings[1:] == [["'=제육 양념", "주재료 무게", "600", "g", "돼지고기", "고추장 2큰술; 설탕 0.5큰술"]]

    with app.app_context():
        call = AiCall.query.one()
        assert (call.kind, call.model, call.input_tokens) == ("export", None, None)
    assert client.get("/api/export/summary").get_json()["remaining"] == 4
    usage = client.get("/api/ai-usage").get_json()
    assert (usage["scan"]["used"], usage["recipe"]["used"]) == (0, 0)


def test_safe_cell_blocks_formulas():
    for value in ("=1+1", "+1", "-1", "@SUM(A1)", "\tx", "\rx"):
        assert export_module.safe(value) == "'" + value
    assert export_module.safe("두부") == "두부"
    assert export_module.safe(3) == 3


def test_export_daily_limit(client, login, app):
    login()
    me = user_id(app)
    with app.app_context():
        yesterday = utcnow() - timedelta(days=1, hours=1)
        earlier = utcnow() - timedelta(minutes=5)
        db.session.add_all([AiCall(user_id=me, kind="export", created_at=yesterday) for _ in range(5)])
        db.session.add_all([AiCall(user_id=me, kind="export", created_at=earlier) for _ in range(4)])
        db.session.add_all([AiCall(user_id=me, kind="recipe", model="m", created_at=earlier) for _ in range(5)])
        db.session.commit()
    assert client.get("/api/export/summary").get_json()["remaining"] == 1
    assert client.get("/api/export").status_code == 200
    assert client.get("/api/export/summary").get_json()["remaining"] == 0
    res = client.get("/api/export")
    assert (res.status_code, res.get_json()) == (429, {"error": "오늘 내보내기는 5번까지 할 수 있어요. 내일 다시 해주세요."})
    with app.app_context():
        assert AiCall.query.filter_by(user_id=me, kind="export").count() == 10  # 한도에 걸린 요청은 기록하지 않는다
