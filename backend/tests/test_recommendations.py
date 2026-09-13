import time
from datetime import timedelta

from app.ingredients import seoul_today
from app.models import Ingredient, PublicRecipe, StorageLocation, db
from app.recipe_parse import ingredient_key


def add_ingredient(client, name, **fields):
    body = {"name": name, "purchased_on": seoul_today().isoformat(), **fields}
    assert client.post("/api/ingredients", json=body).status_code == 201


def public(rcp_seq, title, names, is_sample=False):
    ingredients = [{"name": n, "amount": "1개"} for n in names]
    return PublicRecipe(
        rcp_seq=rcp_seq,
        title=title,
        servings=2,
        ingredients_text=", ".join(names),
        ingredients=ingredients,
        ingredient_keys=[ingredient_key(n) for n in names],
        steps=["만들어요."],
        is_sample=is_sample,
    )


def add_public(app, *recipes):
    with app.app_context():
        db.session.add_all(recipes)
        db.session.commit()


def recommend(client, query=""):
    res = client.get(f"/api/recommendations{query}")
    assert res.status_code == 200
    return res.get_json()


def test_requires_login(client):
    assert client.get("/api/recommendations").status_code == 401


def test_empty_inventory_recommends_nothing(client, login, app):
    login()
    add_public(app, public("1", "두부조림", ["두부", "간장"]))
    assert recommend(client) == {"mine": [], "public": [], "sample": False, "inventory_count": 0}


def test_public_cards_are_ranked_by_match_rate_with_missing_names(client, login, app):
    login()
    add_public(
        app,
        public("1", "두부조림", ["두부", "간장", "대파", "고춧가루", "설탕", "참기름", "마늘"]),
        public("2", "계란국", ["계란", "대파", "물"]),
        public("3", "잡채", ["당면", "시금치"]),  # 가진 재료가 하나도 없으면 빠진다
        public("4", "가지볶음", ["가지", "대파"]),
    )
    add_ingredient(client, "대파 1단")
    add_ingredient(client, "유정란 계란 10구")
    add_ingredient(client, "두부 (국산)")
    body = recommend(client)
    assert (body["mine"], body["sample"], body["inventory_count"]) == ([], False, 3)
    assert body["public"] == [
        {
            "kind": "public",
            "id": body["public"][0]["id"],
            "title": "계란국",
            "image_url": None,
            "servings": 2,
            "match_rate": 1.0,
            "have_count": 3,  # 물은 늘 있는 것으로 센다
            "total_count": 3,
            "missing": [],
            "urgent_used": 0,
            "urgent_names": [],
            "score": 1.0,
        },
        {**body["public"][1], "title": "가지볶음", "match_rate": 0.5, "have_count": 1, "total_count": 2, "missing": ["가지"], "score": 0.5},
        {
            **body["public"][2],
            "title": "두부조림",
            "match_rate": 0.29,
            "have_count": 2,
            "total_count": 7,
            "missing": ["간장", "고춧가루", "설탕", "참기름", "마늘"],  # 최대 5개
            "score": 0.29,
        },
    ]


def test_urgent_ingredients_add_score_and_are_named(client, login, app):
    login()
    today = seoul_today()
    add_public(
        app,
        public("1", "가나다 비빔밥", ["밥", "두부", "대파", "애호박"]),
        public("2", "라마바 볶음밥", ["밥", "계란", "대파", "당근"]),
    )
    add_ingredient(client, "밥")
    add_ingredient(client, "계란")
    add_ingredient(client, "애호박", expires_on=today.isoformat())  # urgent
    add_ingredient(client, "두부", purchased_on=(today - timedelta(days=30)).isoformat())  # 품목 규칙 danger
    add_ingredient(client, "대파", expires_on=(today + timedelta(days=1)).isoformat())  # urgent
    cards = {c["title"]: c for c in recommend(client)["public"]}
    bibim, fried = cards["가나다 비빔밥"], cards["라마바 볶음밥"]
    assert (bibim["match_rate"], bibim["urgent_names"], bibim["urgent_used"], bibim["score"]) == (1.0, ["두부", "대파", "애호박"], 3, 1.3)
    assert (fried["match_rate"], fried["urgent_names"], fried["urgent_used"], fried["score"]) == (0.75, ["대파"], 1, 0.85)
    assert [c["title"] for c in recommend(client)["public"]] == ["가나다 비빔밥", "라마바 볶음밥"]


def test_mine_section_limit_and_sample_flag(client, login, app):
    login()
    add_ingredient(client, "계란")
    for title in ["가 계란찜", "나 계란말이", "다 계란국"]:
        assert client.post("/api/recipes", json={"title": title, "ingredients": [{"name": "계란", "amount": "2개"}, {"name": "Milk"}]}).status_code == 201
    add_public(app, public("SAMPLE-01", "계란말이", ["계란"], is_sample=True), public("SAMPLE-02", "계란국", ["계란", "물"], is_sample=True))

    body = recommend(client, "?limit=2")
    assert [(c["kind"], c["title"], c["missing"]) for c in body["mine"]] == [("mine", "가 계란찜", ["Milk"]), ("mine", "나 계란말이", ["Milk"])]
    assert [c["title"] for c in body["public"]] == ["계란국", "계란말이"]
    assert body["sample"] is True
    assert len(recommend(client, "?limit=0")["mine"]) == 1
    assert len(recommend(client, "?limit=abc")["mine"]) == 3

    add_public(app, public("100", "계란밥", ["계란", "밥"]))
    assert recommend(client)["sample"] is False


def test_other_users_recipes_and_inventory_are_not_used(client, login, app):
    login("owner")
    add_ingredient(client, "계란")
    client.post("/api/recipes", json={"title": "주인 계란찜", "ingredients": [{"name": "계란"}]})
    login("other")
    assert recommend(client) == {"mine": [], "public": [], "sample": False, "inventory_count": 0}


def test_recommendations_are_fast_enough_for_full_public_db(client, login, app):
    # 식약처 전체(약 1,100건) × 재고 60개 스모크: 1.5초 안 (스펙 4절 매칭 규칙 그대로)
    user = login()
    words = ["대파", "양파", "두부", "계란", "감자", "당근", "애호박", "돼지고기", "소고기", "닭가슴살",
             "김치", "콩나물", "시금치", "표고버섯", "고추", "마늘", "간장", "고추장", "된장", "설탕"]
    with app.app_context():
        location = StorageLocation.query.filter_by(user_id=user.id).first()
        db.session.add_all(
            Ingredient(user_id=user.id, location_id=location.id, name=f"{words[i % 20]} {i}" if i >= 20 else words[i], purchased_on=seoul_today())
            for i in range(60)
        )
        db.session.add_all(
            # 재료 12개 중 6개는 재고에 있는 이름, 6개는 레시피마다 다른 없는 이름(캐시가 거의 안 먹는 쪽)
            public(str(n), f"레시피 {n}", [words[(n + j) % 20] if j % 2 == 0 else f"양념{n}-{j}" for j in range(12)])
            for n in range(1100)
        )
        db.session.commit()

    started = time.perf_counter()
    body = recommend(client)
    elapsed = time.perf_counter() - started
    assert len(body["public"]) == 20
    assert body["public"][0]["total_count"] == 12
    assert elapsed < 1.5, f"{elapsed:.2f}s"
