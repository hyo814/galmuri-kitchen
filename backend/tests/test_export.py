import csv
import io
import zipfile
from datetime import datetime, time, timedelta, timezone

import app.export as export_module
from app.ingredients import SEOUL, seoul_today
from app.models import AiCall, PublicRecipe, ShoppingItem, ShoppingNote, ShoppingNotePhoto, User, db, utcnow

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
    "items": [{"name": "고추장", "amount": 2, "unit": "큰술"}, {"name": "설탕", "amount": 0.125, "unit": "큰술"}],
}
INGREDIENT_HEADER = ["이름", "수량", "단위", "보관 위치", "구입일", "유통기한", "가격(원)"]
RECIPE_HEADER = ["제목", "인분", "재료", "만드는 법", "출처", "출처 링크", "사진 주소"]
SEASONING_HEADER = ["이름", "기준", "기준 양", "기준 단위", "주재료", "양념"]
SHOPPING_HEADER = ["이름", "수량", "단위", "생활용품", "살 날", "넣을 위치", "체크", "산 날(재고에 넣은 날)", "출처", "출처 이름", "담은 날"]
MEMO_HEADER = ["장소", "메모", "사진 수", "사진 파일 이름", "고친 시각"]


def read_zip(res):
    files = zipfile.ZipFile(io.BytesIO(res.data))
    out = {}
    for name in files.namelist():
        raw = files.read(name)
        assert raw.startswith(b"\xef\xbb\xbf")  # 엑셀이 한글을 알아보도록 BOM
        out[name] = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline="")))
    return out


def user_id(app, provider_id="1"):
    with app.app_context():
        return User.query.filter_by(provider_id=provider_id).one().id


def export_calls(app):
    with app.app_context():
        return AiCall.query.filter_by(kind="export").count()


def add_calls(app, me, *times):
    with app.app_context():
        db.session.add_all([AiCall(user_id=me, kind="export", created_at=t) for t in times])
        db.session.commit()


def day(delta=0):
    return (seoul_today() - timedelta(days=delta)).isoformat()


def seoul_noon(delta=0):
    """서울 낮 12시(자정 근처 시간대 변환으로 날짜가 밀리지 않게) → UTC."""
    return datetime.combine(seoul_today() - timedelta(days=delta), time(12), tzinfo=SEOUL).astimezone(timezone.utc)


def test_requires_login(client):
    assert client.get("/api/export").status_code == 401
    assert client.get("/api/export/summary").status_code == 401


def test_requires_fetch_header_and_uses_no_quota(client, login, app):
    login()
    for path in ("/api/export", "/api/export/summary"):
        res = client.get(path, headers={"X-Requested-With": "XMLHttpRequest"})
        assert (res.status_code, res.get_json()) == (400, {"error": "잘못된 요청이에요."})
    assert export_calls(app) == 0
    assert client.get("/api/export/summary").get_json()["remaining"] == 5


def test_summary_counts_only_my_data(client, login):
    login("other")
    client.post("/api/recipes", json=RECIPE)
    client.post("/api/ingredients", json={"name": "남의 두부", "purchased_on": day()})
    client.post("/api/seasonings", json=SEASONING)
    client.post("/api/shopping/items", json={"name": "남의 우유"})
    client.post("/api/shopping/notes", json={"body": "남의 메모"})
    login()
    client.post("/api/ingredients", json={"name": "두부", "purchased_on": day()})
    client.post("/api/recipes", json=RECIPE)
    client.post("/api/recipes", json={**RECIPE, "title": "계란말이"})
    client.post("/api/seasonings", json=SEASONING)
    client.post("/api/shopping/items", json={"name": "두부"})
    client.post("/api/shopping/items", json={"name": "대파"})
    client.post("/api/shopping/notes", json={"body": "메모"})
    assert client.get("/api/export/summary").get_json() == {
        "ingredients": 1,
        "recipes": 2,
        "seasonings": 1,
        "shopping": 2,
        "memos": 1,
        "limit": 5,
        "remaining": 5,
    }


def test_export_empty_data_has_header_only_csvs(client, login):
    login()
    res = client.get("/api/export")
    assert res.status_code == 200
    assert read_zip(res) == {
        "ingredients.csv": [INGREDIENT_HEADER],
        "recipes.csv": [RECIPE_HEADER],
        "seasonings.csv": [SEASONING_HEADER],
        "shopping.csv": [SHOPPING_HEADER],
        "shopping_memos.csv": [MEMO_HEADER],
    }


def test_export_zip_contents(client, login, app):
    login("other")
    client.post("/api/recipes", json={**RECIPE, "title": "남의 레시피"})
    client.post("/api/ingredients", json={"name": "남의 우유", "purchased_on": day()})
    client.post("/api/seasonings", json={**SEASONING, "name": "남의 양념"})
    client.post("/api/shopping/items", json={"name": "남의 우유"})
    client.post("/api/shopping/notes", json={"body": "남의 메모"})
    login()
    kimchi = client.post("/api/locations", json={"name": "김치냉장고", "kind": "fridge"}).get_json()
    client.post("/api/ingredients", json={"name": "두부", "purchased_on": day(1)})
    client.post(
        "/api/ingredients",
        json={"name": "@우유", "quantity": 1.5, "unit": "L", "purchased_on": day(2), "expires_on": "2026-12-01", "price": 2980},
    )
    client.post("/api/ingredients", json={"name": "김치🥬", "quantity": 1 / 3, "purchased_on": day(1), "location_id": kimchi["id"]})
    client.post("/api/recipes", json=RECIPE)
    client.post(
        "/api/recipes",
        json={**RECIPE, "title": "백종원 김치찌개", "source": "youtube", "source_url": "https://www.youtube.com/watch?v=abc"},
    )
    with app.app_context():
        db.session.add(PublicRecipe(rcp_seq="1", title="된장찌개", image_url="https://www.foodsafetykorea.go.kr/a.jpg"))
        db.session.commit()
    client.post("/api/recipes", json={**RECIPE, "title": "AI 된장찌개", "source": "ai", "image_url": "https://www.foodsafetykorea.go.kr/a.jpg"})
    client.post("/api/seasonings", json=SEASONING)
    client.post(
        "/api/seasonings",
        json={"name": " 간장조림", "basis": "servings", "basis_amount": 2, "basis_unit": "인분", "items": [{"name": "간장", "amount": 3, "unit": "큰술"}]},
    )

    client.post("/api/shopping/items", json={"name": "두부"})
    daepa = client.post(
        "/api/shopping/items",
        json={"name": "-대파", "quantity": 3, "unit": "단", "planned_on": day(1), "location_id": kimchi["id"], "source": "staple"},
    ).get_json()
    client.patch(f"/api/shopping/items/{daepa['id']}", json={"done": True, "changed_at": datetime.now(timezone.utc).isoformat()})
    client.post("/api/shopping/items", json={"name": "휴지", "unit": "롤"})
    note = client.post("/api/shopping/notes", json={"place": "이마트", "body": "=SUM(A1)"}).get_json()
    with app.app_context():
        me = user_id(app)
        db.session.add(ShoppingItem(user_id=me, name="계란", quantity=1, unit="판", source="recipe", source_label="계란말이", stocked_at=seoul_noon(3), created_at=seoul_noon(3)))
        db.session.add(ShoppingItem(user_id=me, name="오래된 양파", stocked_at=seoul_noon(10), created_at=seoul_noon(10)))  # 7일 지나 안 담긴다
        db.session.add(ShoppingNotePhoto(note_id=note["id"], photo_key="shopping/1/abc.jpg", size=10))
        db.session.add(ShoppingNotePhoto(note_id=note["id"], photo_key="shopping/1/def.png", size=20))
        db.session.commit()

    res = client.get("/api/export")
    assert res.status_code == 200
    assert res.mimetype == "application/zip"
    assert res.headers["Content-Disposition"] == f'attachment; filename="galmuri-kitchen-{seoul_today():%Y%m%d}.zip"'
    assert res.headers["Cache-Control"] == "no-store"
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    files = read_zip(res)
    assert set(files) == {"ingredients.csv", "recipes.csv", "seasonings.csv", "shopping.csv", "shopping_memos.csv"}

    assert files["ingredients.csv"] == [  # 구입일, id 순
        INGREDIENT_HEADER,
        ["'@우유", "1.5", "L", "냉장실", day(2), "2026-12-01", "2980"],
        ["두부", "1", "개", "냉장실", day(1), "", ""],
        ["김치🥬", str(1 / 3), "개", "김치냉장고", day(1), "", ""],
    ]
    assert files["recipes.csv"][0] == RECIPE_HEADER
    steps = "1. 두부를 썰어요.\n2. 양념을 붓고 졸여요."
    assert sorted(files["recipes.csv"][1:]) == sorted(
        [
            ["두부조림", "2", "두부 1모; 대파 1/2대; 물", steps, "직접 입력", "", ""],
            ["백종원 김치찌개", "2", "두부 1모; 대파 1/2대; 물", steps, "유튜브에서 가져옴", "https://www.youtube.com/watch?v=abc", ""],
            ["AI 된장찌개", "2", "두부 1모; 대파 1/2대; 물", steps, "AI가 만든 레시피", "", "https://www.foodsafetykorea.go.kr/a.jpg"],
        ]
    )
    assert files["seasonings.csv"] == [
        SEASONING_HEADER,
        ["'=제육 양념", "주재료 무게", "600", "g", "돼지고기", "고추장 2큰술; 설탕 0.125큰술"],
        ["간장조림", "인분", "2", "인분", "", "간장 3큰술"],
    ]
    assert files["shopping.csv"] == [  # created_at 순: 3일 전 만든 계란이 먼저, 10일 전 산 양파는 7일이 지나 빠진다
        SHOPPING_HEADER,
        ["계란", "1", "판", "", "", "", "", day(3), "레시피", "계란말이", day(3)],
        ["두부", "1", "개", "", "", "", "", "", "직접 담음", "", day()],
        ["'-대파", "3", "단", "", day(1), "김치냉장고", "예", "", "필수품", "", day()],
        ["휴지", "1", "롤", "예", "", "", "", "", "직접 담음", "", day()],
    ]
    assert files["shopping_memos.csv"] == [
        MEMO_HEADER,
        ["이마트", "'=SUM(A1)", "2", "abc.jpg; def.png", note["updated_at"]],
    ]

    with app.app_context():
        call = AiCall.query.one()
        assert (call.kind, call.model, call.input_tokens) == ("export", None, None)
    assert client.get("/api/export/summary").get_json()["remaining"] == 4
    usage = client.get("/api/ai-usage").get_json()
    assert (usage["scan"]["used"], usage["recipe"]["used"]) == (0, 0)


def test_safe_cell_blocks_formulas():
    for value in ("=1+1", "+1", "-1", "@SUM(A1)", "\tx", "\rx", " =1+1", "  @A1", "＝1+1", "＋1", "－1", "＠A1", " ＝1"):
        assert export_module.safe(value) == "'" + value
    for value in ("두부", "1-2", "a=b", ""):
        assert export_module.safe(value) == value
    assert export_module.safe(3) == 3


def test_number_keeps_precision():
    assert export_module.number(1.0) == 1 and isinstance(export_module.number(1.0), int)
    assert str(export_module.number(0.125)) == "0.125"
    assert export_module.number(1 / 3) == 1 / 3


def test_export_daily_limit(client, login, app):
    login()
    me = user_id(app)
    add_calls(app, me, *[utcnow() - timedelta(days=1, hours=1)] * 5)  # 어제 쓴 것은 세지 않는다
    with app.app_context():
        db.session.add_all([AiCall(user_id=me, kind="recipe", model="m", created_at=utcnow()) for _ in range(5)])
        db.session.commit()
    for left in (4, 3, 2, 1, 0):
        assert client.get("/api/export").status_code == 200
        assert client.get("/api/export/summary").get_json()["remaining"] == left
    res = client.get("/api/export")
    assert (res.status_code, res.get_json()) == (429, {"error": "오늘 내보내기는 5번까지 할 수 있어요. 내일 다시 해주세요."})
    assert export_calls(app) == 10  # 한도에 걸린 요청은 기록하지 않는다


def test_export_limit_uses_seoul_midnight(client, login, app):
    login()
    me = user_id(app)
    midnight = datetime.combine(seoul_today(), time.min, tzinfo=SEOUL).astimezone(timezone.utc)
    add_calls(app, me, *[midnight - timedelta(seconds=1)] * 5, midnight)
    assert client.get("/api/export/summary").get_json()["remaining"] == 4
