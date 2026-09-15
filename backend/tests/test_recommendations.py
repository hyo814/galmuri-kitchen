import time
from datetime import timedelta

import app.recipes as recipes_module
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
    assert recommend(client) == {
        "mine": [],
        "mine_total": 0,
        "public": [],
        "public_total": 0,
        "public_count": 1,
        "next_offset": None,
        "sample": False,
        "inventory_count": 0,
    }


def test_water_only_overlap_is_excluded(client, login, app):
    # T-tests: 물만 겹치는 레시피는 재고와 겹치는 재료가 하나도 없는 것으로 본다
    login()
    add_public(app, public("1", "물만있는거", ["물"]))
    add_ingredient(client, "두부")
    body = recommend(client)
    assert body["public"] == []
    assert body["public_total"] == 0


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
    assert (body["mine"], body["sample"], body["inventory_count"], body["public_total"]) == ([], False, 3, 3)
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


def test_missing_shows_display_name_not_matching_key(client, login, app):
    # C1: missing은 매칭용 키가 아니라 화면에 보여줄 이름 그대로
    login()
    ingredients = [{"name": "두부(부침용)", "amount": "1모"}, {"name": "Milk (1L)", "amount": "1개"}]
    add_public(
        app,
        PublicRecipe(
            rcp_seq="1",
            title="두부요리",
            servings=2,
            ingredients_text="",
            ingredients=ingredients,
            ingredient_keys=[ingredient_key(i["name"]) for i in ingredients],
            steps=["만들어요."],
        ),
    )
    add_ingredient(client, "국산 두부")
    body = recommend(client)
    assert body["public"][0]["missing"] == ["Milk (1L)"]


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


def test_urgent_names_dedupe_when_two_ingredients_match_same_stock_item(client, login, app):
    # T-tests: 서로 다른 두 재료 이름이 같은 재고 하나에 매칭되면 urgent_names는 한 번만
    login()
    today = seoul_today()
    add_public(app, public("1", "대파요리", ["대파", "파"]))
    add_ingredient(client, "대파 1단", expires_on=today.isoformat())
    card = recommend(client)["public"][0]
    assert (card["urgent_names"], card["urgent_used"]) == (["대파 1단"], 1)


def test_title_tiebreak_when_id_order_differs_from_title_order(client, login, app):
    # T-tests: 점수가 같으면 제목 오름차순(작성 id 순서와 다르게)
    login()
    add_public(app, public("9", "하나", ["계란"]), public("1", "가나", ["계란"]))
    add_ingredient(client, "계란")
    assert [c["title"] for c in recommend(client)["public"]] == ["가나", "하나"]


def test_mine_top10_and_sample_flag(client, login, app):
    login()
    add_ingredient(client, "계란")
    for title in ["가 계란찜", "나 계란말이", "다 계란국"]:
        assert client.post("/api/recipes", json={"title": title, "ingredients": [{"name": "계란", "amount": "2개"}, {"name": "Milk"}]}).status_code == 201
    add_public(app, public("SAMPLE-01", "계란말이", ["계란"], is_sample=True), public("SAMPLE-02", "계란국", ["계란", "물"], is_sample=True))

    body = recommend(client)
    assert [(c["kind"], c["title"], c["missing"]) for c in body["mine"]] == [
        ("mine", "가 계란찜", ["Milk"]),
        ("mine", "나 계란말이", ["Milk"]),
        ("mine", "다 계란국", ["Milk"]),
    ]
    assert body["mine_total"] == 3
    assert [c["title"] for c in body["public"]] == ["계란국", "계란말이"]
    assert body["sample"] is True

    add_public(app, public("100", "계란밥", ["계란", "밥"]))
    assert recommend(client)["sample"] is False


def test_mine_top10_caps_at_10_even_with_more_recipes(client, login, app):
    login()
    add_ingredient(client, "계란")
    for i in range(12):
        assert client.post("/api/recipes", json={"title": f"레시피{i:02d}", "ingredients": [{"name": "계란"}]}).status_code == 201
    body = recommend(client)
    assert (len(body["mine"]), body["mine_total"]) == (10, 12)


def test_section_public_skips_mine_work(client, login, app, monkeypatch):
    # P-B1: section=public이면 내 레시피는 계산하지 않는다
    login()
    add_ingredient(client, "계란")
    client.post("/api/recipes", json={"title": "레시피", "ingredients": [{"name": "계란"}]})
    add_public(app, public("1", "계란찜", ["계란"]))

    calls = []
    original = recipes_module._ranked_mine

    def spy(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(recipes_module, "_ranked_mine", spy)
    body = recommend(client, "?section=public")
    assert "mine" not in body and "mine_total" not in body
    assert calls == []
    assert [c["title"] for c in body["public"]] == ["계란찜"]


def test_pagination_offset_limit_and_next_offset(client, login, app):
    login()
    add_ingredient(client, "계란")
    add_public(app, *[public(str(n), f"레시피{n:02d}", ["계란"]) for n in range(45)])

    first = recommend(client, "?section=public&limit=20&offset=0")
    assert (len(first["public"]), first["public_total"], first["next_offset"]) == (20, 45, 20)
    second = recommend(client, f"?section=public&limit=20&offset={first['next_offset']}")
    assert (len(second["public"]), second["next_offset"]) == (20, 40)
    third = recommend(client, f"?section=public&limit=20&offset={second['next_offset']}")
    assert (len(third["public"]), third["next_offset"]) == (5, None)

    seen = [c["id"] for c in first["public"] + second["public"] + third["public"]]
    assert len(seen) == len(set(seen)) == 45  # 페이지를 이으면 전체 순위와 같고 중복이 없다


def test_limit_over_50_clamps_and_negative_offset_clamps_to_zero(client, login, app):
    login()
    add_ingredient(client, "계란")
    add_public(app, *[public(str(n), f"레시피{n:02d}", ["계란"]) for n in range(60)])
    body = recommend(client, "?section=public&limit=999&offset=-5")
    assert len(body["public"]) == 50


def test_cache_does_not_recompute_within_ttl(client, login, app, monkeypatch):
    login()
    add_ingredient(client, "계란")
    add_public(app, public("1", "계란찜", ["계란", "대파"]))

    calls = []
    original = recipes_module._match_key_fast

    def spy(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(recipes_module, "_match_key_fast", spy)
    recommend(client)
    assert len(calls) > 0
    calls.clear()
    recommend(client)
    assert calls == []  # TTL 안이라 다시 계산하지 않는다


def test_cache_invalidates_when_inventory_changes(client, login, app):
    login()
    add_ingredient(client, "계란")
    add_public(app, public("1", "계란찜", ["계란", "대파"]))
    before = recommend(client)["public"][0]
    assert before["match_rate"] == 0.5
    add_ingredient(client, "대파")
    after = recommend(client)["public"][0]
    assert after["match_rate"] == 1.0


def test_cache_expires_after_ttl(client, login, app, monkeypatch):
    login()
    add_ingredient(client, "계란")
    add_public(app, public("1", "계란찜", ["계란"]))
    recommend(client)

    calls = []
    original = recipes_module._match_key_fast

    def spy(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(recipes_module, "_match_key_fast", spy)
    real_monotonic = recipes_module.time.monotonic
    monkeypatch.setattr(recipes_module.time, "monotonic", lambda: real_monotonic() + 121)
    recommend(client)
    assert len(calls) > 0  # TTL이 지나 다시 계산한다


def test_other_users_recipes_and_inventory_are_not_used(client, login, app):
    login("owner")
    add_ingredient(client, "계란")
    client.post("/api/recipes", json={"title": "주인 계란찜", "ingredients": [{"name": "계란"}]})
    login("other")
    assert recommend(client) == {
        "mine": [],
        "mine_total": 0,
        "public": [],
        "public_total": 0,
        "public_count": 0,
        "next_offset": None,
        "sample": False,
        "inventory_count": 0,
    }


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


def test_recommendations_first_call_and_cached_call_with_large_inventory(client, login, app):
    # P-B1 성능 추가: 재고 2,000개 × 공공 레시피 1,100건 첫 호출 3초 안, 캐시된 두 번째 호출 0.1초 안
    user = login()
    words = ["대파", "양파", "두부", "계란", "감자", "당근", "애호박", "돼지고기", "소고기", "닭가슴살",
             "김치", "콩나물", "시금치", "표고버섯", "고추", "마늘", "간장", "고추장", "된장", "설탕"]
    with app.app_context():
        location = StorageLocation.query.filter_by(user_id=user.id).first()
        db.session.add_all(
            Ingredient(user_id=user.id, location_id=location.id, name=f"{words[i % 20]} {i}", purchased_on=seoul_today())
            for i in range(2000)
        )
        db.session.add_all(
            public(str(n), f"레시피 {n}", [words[(n + j) % 20] if j % 2 == 0 else f"양념{n}-{j}" for j in range(12)])
            for n in range(1100)
        )
        db.session.commit()

    started = time.perf_counter()
    recommend(client)
    first_elapsed = time.perf_counter() - started
    assert first_elapsed < 3.0, f"{first_elapsed:.2f}s"

    started = time.perf_counter()
    recommend(client)
    cached_elapsed = time.perf_counter() - started
    assert cached_elapsed < 0.1, f"{cached_elapsed:.3f}s"


# --- 3a final review fix wave ---


def test_rank_cache_prunes_expired_entries_on_insert(client, login, app, monkeypatch):
    # I3: 새 사용자 항목을 넣을 때(insert) TTL이 지난 다른 사용자 항목도 같이 치운다
    recipes_module._RANK_CACHE.clear()
    u1 = login("cache-u1")
    add_ingredient(client, "계란")
    add_public(app, public("1", "계란찜", ["계란"]))
    recommend(client)
    assert u1.id in recipes_module._RANK_CACHE

    real_monotonic = recipes_module.time.monotonic
    monkeypatch.setattr(recipes_module.time, "monotonic", lambda: real_monotonic() + 121)  # u1 항목 TTL 지남

    u2 = login("cache-u2")
    add_ingredient(client, "계란")
    recommend(client)  # u2를 새로 넣으면서 만료된 u1도 같이 지워야 한다
    assert u1.id not in recipes_module._RANK_CACHE
    assert u2.id in recipes_module._RANK_CACHE


def test_rank_cache_caps_at_50_users(app):
    with app.app_context():
        recipes_module._RANK_CACHE.clear()
        now = recipes_module.time.monotonic()
        for uid in range(50):
            recipes_module._RANK_CACHE[uid] = {"signature": "sig", "created": now, "mine": None, "public": None}
        recipes_module._rank_cache_entry(999, "새-서명")
        assert len(recipes_module._RANK_CACHE) == 50
        assert 999 in recipes_module._RANK_CACHE


def test_public_count_counts_all_public_rows_even_without_overlap(client, login, app):
    # M11: public_total은 재고와 겹치는 것만 세지만 public_count는 카탈로그 전체를 센다
    login()
    add_public(app, public("1", "무관한 레시피", ["당면", "시금치"]))  # 재고와 하나도 안 겹친다
    add_ingredient(client, "계란")
    body = recommend(client)
    assert (body["public_total"], body["public_count"]) == (0, 1)


def test_public_search_matches_title_ignoring_spaces_and_case_and_keeps_unmatched(client, login, app):
    # 식약처 레시피 검색: 제목에 검색어가 들어가면(공백·대소문자 무시) 재고와 안 겹쳐도, 재료가 0개여도 넣고 일치 점수 순
    login()
    add_public(
        app,
        public("1", "김치 볶음밥", ["김치", "밥"]),
        public("2", "김치찌개", ["김치", "돼지고기"]),
        public("3", "김치전", []),  # 빈 RCP_PARTS_DTLS
        public("4", "잡채", ["당면", "시금치"]),
        public("5", "LA갈비", ["갈비"]),
        public("6", "100% 두부", ["두부"]),
    )
    add_ingredient(client, "김치")
    add_ingredient(client, "돼지고기")

    body = recommend(client, "?section=public&q=김치")
    assert [(c["title"], c["have_count"], c["total_count"]) for c in body["public"]] == [("김치찌개", 2, 2), ("김치 볶음밥", 1, 2), ("김치전", 0, 0)]
    assert (body["public_total"], body["next_offset"], "mine" in body) == (3, None, False)
    assert [c["title"] for c in recommend(client, "?section=public&q=%20김치볶음%20")["public"]] == ["김치 볶음밥"]
    assert [(c["title"], c["missing"]) for c in recommend(client, "?section=public&q=잡채")["public"]] == [("잡채", ["당면", "시금치"])]
    assert [c["title"] for c in recommend(client, "?section=public&q=la")["public"]] == ["LA갈비"]
    assert [c["title"] for c in recommend(client, "?section=public&q=%25")["public"]] == ["100% 두부"]  # %는 와일드카드가 아니다
    assert recommend(client, "?section=public&q=_")["public"] == []

    page = recommend(client, "?section=public&q=김치&limit=2&offset=0")
    assert ([c["title"] for c in page["public"]], page["next_offset"]) == (["김치찌개", "김치 볶음밥"], 2)
    # 검색이 추천 순위 캐시를 바꾸지 않는다: 검색 없는 목록은 여전히 재고와 겹치는 것만
    assert [c["title"] for c in recommend(client, "?section=public")["public"]] == ["김치찌개", "김치 볶음밥"]


def test_public_search_only_with_section_public(client, login, app):
    login()
    assert client.get("/api/recommendations?q=김치").status_code == 400
    assert recommend(client, "?section=public&q=%20%20")["public"] == []  # 공백뿐이면 검색이 아니다(재고가 비어 추천도 없다)
