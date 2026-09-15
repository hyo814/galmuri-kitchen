import json
from datetime import timedelta

import pytest

from app import foods, outbound
from app.models import AiCall, FoodNutrient, FoodSearch, PublicRecipe, User, db, utcnow


def page(items, total, code="00"):
    return json.dumps({"header": {"resultCode": code, "resultMsg": "NORMAL SERVICE."}, "body": {"totalCount": total, "items": items}})


def item(code, name, group="원재료성", kcal="84", basis="100g", **amt):
    row = {foods.FIELDS["code"]: code, foods.FIELDS["name"]: name, foods.FIELDS["group"]: group, foods.FIELDS["basis"]: basis, foods.FIELDS["kcal"]: kcal}
    for key, value in amt.items():
        row[foods.FIELDS[key]] = value
    return row


def make_fetch(responses):
    """responses: [json_string, ...] 또는 예외 인스턴스. 호출을 calls에 모은다."""
    calls = []

    def fetch(url, params=None, json_body=None, headers=None, seconds=None):
        calls.append({"url": url, "params": params, "seconds": seconds})
        result = responses[len(calls) - 1]
        if isinstance(result, Exception):
            raise result
        return result, "utf-8"

    return fetch, calls


def make_user(provider="test", provider_id="1"):
    user = User(provider=provider, provider_id=provider_id, nickname="u")
    db.session.add(user)
    db.session.commit()
    return user


# --- row_fields ---


def test_row_fields_normal_row():
    result = foods.row_fields(item("F1", "두부", sodium_mg="7"))
    assert result == {
        "food_code": "F1", "name": "두부", "name_key": "두부", "group_name": "원재료성",
        "kcal": 84.0, "carbs_g": None, "protein_g": None, "fat_g": None, "sugars_g": None, "sodium_mg": 7.0,
    }


def test_row_fields_basis_ml_case_and_space_insensitive():
    assert foods.row_fields(item("F1", "우유", basis="100 ML")) is not None


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(basis="1회(30g)"),
        dict(kcal=""),
        dict(kcal="-1"),
    ],
    ids=["not-100g-basis", "blank-kcal", "negative-kcal"],
)
def test_row_fields_invalid_required_fields_are_none(kwargs):
    assert foods.row_fields(item("F1", "두부", **kwargs)) is None


def test_row_fields_code_too_long_is_none():
    assert foods.row_fields(item("x" * 81, "두부")) is None


def test_row_fields_non_numeric_optional_nutrient_is_none():
    result = foods.row_fields(item("F1", "두부", sugars_g="-"))
    assert result is not None and result["sugars_g"] is None


def test_row_fields_name_key_splits_on_underscore_and_comma():
    assert foods.row_fields(item("F1", "김치찌개_돼지고기"))["name_key"] == "김치찌개"
    assert foods.row_fields(item("F1", "돼지고기, 앞다리, 생것"))["name_key"] == "돼지고기"


# --- name_parts ---


def test_name_parts_splits_underscore_all_parts():
    assert foods.name_parts("파_대파_생것") == ["파", "대파", "생것"]


def test_name_parts_drops_parenthesized_detail_within_a_part():
    # matching.normalize는 괄호와 그 안 내용을 통째로 지운다 → "삼겹살(삼겹살)" 조각이 "삼겹살"만 남는다
    assert foods.name_parts("돼지고기_삼겹살(삼겹살)_생것") == ["돼지고기", "삼겹살", "생것"]


def test_name_parts_splits_on_comma_too():
    assert foods.name_parts("돼지고기, 앞다리, 생것") == ["돼지고기", "앞다리", "생것"]


def test_name_parts_single_part_name_has_no_delimiter():
    assert foods.name_parts("두부") == ["두부"]


# --- fetch_page ---


def test_fetch_page_keeps_raw_key_and_reads_items(app, monkeypatch):
    fetch, calls = make_fetch([page([item("F1", "두부")], 1)])
    monkeypatch.setattr(outbound, "fetch_fixed", fetch)
    with app.app_context():
        items, total = foods.fetch_page("ab+c/d==", "두부", 1)
    assert calls[0]["url"] == foods.ENDPOINT + "?serviceKey=ab+c/d=="
    assert calls[0]["params"] == {"FOOD_NM_KR": "두부", "type": "json", "numOfRows": 100, "pageNo": 1}
    assert calls[0]["seconds"] == foods.FETCH_SECONDS
    assert len(items) == 1 and total == 1


def test_fetch_page_single_item_dict_becomes_list(app, monkeypatch):
    body = json.dumps({"header": {"resultCode": "00"}, "body": {"totalCount": 1, "items": {"item": item("F1", "두부")}}})
    fetch, _ = make_fetch([body])
    monkeypatch.setattr(outbound, "fetch_fixed", fetch)
    with app.app_context():
        items, total = foods.fetch_page("k", "두부", 1)
    assert len(items) == 1 and total == 1


def test_fetch_page_bad_result_code_raises_fetch_error(app, monkeypatch):
    fetch, _ = make_fetch([page([], 0, code="30")])
    monkeypatch.setattr(outbound, "fetch_fixed", fetch)
    with app.app_context(), pytest.raises(outbound.FetchError):
        foods.fetch_page("k", "두부", 1)


def test_apis_data_go_kr_is_a_fixed_host():
    assert "apis.data.go.kr" in outbound.FIXED_HOSTS


# --- search_and_cache: on mode ---


def test_search_and_cache_on_mode(make_app, monkeypatch):
    app = make_app(FOOD_NUTRITION_API_KEY="k")
    with app.app_context():
        user = make_user()
        fetch, calls = make_fetch([page([item("F1", "두부"), item("F2", "순두부")], 2)])
        monkeypatch.setattr(outbound, "fetch_fixed", fetch)

        assert foods.search_and_cache("두부", user) is True
        assert FoodNutrient.query.count() == 2
        search_row = FoodSearch.query.one()
        assert (search_row.query_key, search_row.total) == ("두부", 2)
        assert AiCall.query.filter_by(kind="food_fetch").count() == 1
        assert AiCall.query.filter_by(kind="food_fetch").one().model is None

        def fail(*a, **k):
            raise AssertionError("30일 안이면 다시 부르면 안 돼요")

        monkeypatch.setattr(outbound, "fetch_fixed", fail)
        assert foods.search_and_cache("두부", user) is True
        assert len(calls) == 1

        future = utcnow() + timedelta(days=31)
        monkeypatch.setattr(foods, "utcnow", lambda: future)
        fetch2, calls2 = make_fetch([page([item("F1", "두부", kcal="90"), item("F2", "순두부")], 2)])
        monkeypatch.setattr(outbound, "fetch_fixed", fetch2)
        assert foods.search_and_cache("두부", user) is True
        assert len(calls2) == 1
        assert FoodNutrient.query.count() == 2  # 같은 코드는 갱신, 새로 늘지 않는다
        assert FoodNutrient.query.filter_by(food_code="F1").one().kcal == 90.0


def test_tail_paging_fetches_second_page_when_total_fits_in_two_pages(make_app, monkeypatch):
    app = make_app(FOOD_NUTRITION_API_KEY="k")
    with app.app_context():
        user = make_user()
        page1 = [item(f"F{i}", f"두부요리{i}") for i in range(100)]
        page2 = [item(f"G{i}", f"두부요리{100 + i}") for i in range(50)]
        fetch, calls = make_fetch([page(page1, 150), page(page2, 150)])
        monkeypatch.setattr(outbound, "fetch_fixed", fetch)
        assert foods.search_and_cache("두부", user) is True
        assert [c["params"]["pageNo"] for c in calls] == [1, 2]


def test_tail_paging_stops_at_last_page_when_it_is_full(make_app, monkeypatch):
    app = make_app(FOOD_NUTRITION_API_KEY="k")
    with app.app_context():
        user = make_user()
        page1 = [item(f"F{i}", f"두부요리{i}") for i in range(100)]
        last_page = [item(f"R{i}", f"두부_원물{i}", group="원재료성") for i in range(67)]  # 50개 이상(가득 찬 마지막 쪽)
        fetch, calls = make_fetch([page(page1, 3167), page(last_page, 3167)])
        monkeypatch.setattr(outbound, "fetch_fixed", fetch)
        assert foods.search_and_cache("두부", user) is True
        assert [c["params"]["pageNo"] for c in calls] == [1, 32]


def test_tail_paging_also_fetches_page_before_a_short_last_page(make_app, monkeypatch):
    app = make_app(FOOD_NUTRITION_API_KEY="k")
    with app.app_context():
        user = make_user()
        page1 = [item(f"F{i}", f"두부요리{i}") for i in range(100)]
        short_last_page = [item(f"R{i}", f"두부_원물{i}", group="원재료성") for i in range(20)]  # 50개 미만
        page_before_last = [item(f"S{i}", f"두부_원물전{i}") for i in range(100)]
        fetch, calls = make_fetch([page(page1, 3167), page(short_last_page, 3167), page(page_before_last, 3167)])
        monkeypatch.setattr(outbound, "fetch_fixed", fetch)
        assert foods.search_and_cache("두부", user) is True
        assert [c["params"]["pageNo"] for c in calls] == [1, 32, 31]


def test_tail_paging_only_page_one_when_total_fits_one_page(make_app, monkeypatch):
    app = make_app(FOOD_NUTRITION_API_KEY="k")
    with app.app_context():
        user = make_user()
        fetch, calls = make_fetch([page([item("F1", "두부")], 80)])
        monkeypatch.setattr(outbound, "fetch_fixed", fetch)
        assert foods.search_and_cache("두부", user) is True
        assert [c["params"]["pageNo"] for c in calls] == [1]


def test_fetch_failures_leave_no_search_record(make_app, monkeypatch):
    app = make_app(FOOD_NUTRITION_API_KEY="k")
    with app.app_context():
        user = make_user()

        def boom(*a, **k):
            raise outbound.FetchError("TooSlow")

        monkeypatch.setattr(outbound, "fetch_fixed", boom)
        assert foods.search_and_cache("두부", user) is False
        assert FoodSearch.query.count() == 0

        monkeypatch.setattr(outbound, "fetch_fixed", lambda *a, **k: (page([], 0, code="30"), "utf-8"))
        assert foods.search_and_cache("대파", user) is False
        assert FoodSearch.query.count() == 0

        monkeypatch.setattr(outbound, "fetch_fixed", lambda *a, **k: ("not json", "utf-8"))
        assert foods.search_and_cache("양파", user) is False
        assert FoodSearch.query.count() == 0

        assert AiCall.query.filter_by(kind="food_fetch").count() == 3  # 요청마다 남는다(실패해도)


def test_fetch_limits(make_app, monkeypatch):
    def fail(*a, **k):
        raise AssertionError("한도를 넘으면 부르면 안 돼요")

    app = make_app(FOOD_NUTRITION_API_KEY="k")
    with app.app_context():
        user = make_user()
        db.session.add_all([AiCall(user_id=user.id, kind="food_fetch", created_at=utcnow()) for _ in range(300)])
        db.session.commit()
        monkeypatch.setattr(outbound, "fetch_fixed", fail)
        assert foods.search_and_cache("두부", user) is False

    app2 = make_app(FOOD_NUTRITION_API_KEY="k")
    with app2.app_context():
        other = make_user(provider_id="2")
        me = make_user(provider_id="3")
        db.session.add(AiCall(user_id=other.id, kind="food_fetch", created_at=utcnow()))
        db.session.commit()
        monkeypatch.setattr(foods, "GLOBAL_DAILY_FETCHES", 1)
        monkeypatch.setattr(outbound, "fetch_fixed", fail)
        assert foods.search_and_cache("두부", me) is False

    app3 = make_app(FOOD_NUTRITION_API_KEY="k")
    with app3.app_context():
        demo_user = make_user(provider="demo", provider_id="d1")
        db.session.add_all([AiCall(user_id=demo_user.id, kind="food_fetch", created_at=utcnow()) for _ in range(50)])
        db.session.commit()
        monkeypatch.setattr(outbound, "fetch_fixed", fail)
        assert foods.search_and_cache("두부", demo_user) is False


def test_sample_mode_uses_file_without_network(app, monkeypatch):
    with app.app_context():
        user = make_user()

        def fail(*a, **k):
            raise AssertionError("sample 모드는 네트워크를 부르면 안 돼요")

        monkeypatch.setattr(outbound, "fetch_fixed", fail)
        assert foods.search_and_cache("두부", user) is True
        names = {row.name for row in FoodNutrient.query.filter_by(source="sample")}
        assert {"두부", "순두부", "연두부"} <= names
        assert AiCall.query.count() == 0


# --- search_items ordering ---


def test_search_items_ranks_raw_row_above_substring_matches(app):
    with app.app_context():
        now = utcnow()
        db.session.add_all([
            FoodNutrient(food_code="R1", name="파_대파_생것", name_key="파", group_name="원재료성", kcal=27, source="api", fetched_at=now),
            FoodNutrient(food_code="P1", name="대파김치", name_key="대파김치", group_name="가공식품", kcal=18, source="api", fetched_at=now),
            FoodNutrient(food_code="D1", name="꼬치구이_닭고기_대파", name_key="꼬치구이", group_name="음식", kcal=150, source="api", fetched_at=now),
        ])
        db.session.commit()
        names = [row["name"] for row in foods.search_items("대파")]
    assert names.index("파_대파_생것") < names.index("대파김치")
    assert names.index("파_대파_생것") < names.index("꼬치구이_닭고기_대파")


# --- HTTP endpoint ---


def test_search_endpoint_orders_and_filters(client, raw_client, login, app, monkeypatch):
    login()
    with app.app_context():
        now = utcnow()
        db.session.add_all([
            FoodNutrient(food_code="A1", name="두부전", name_key="두부전", group_name="음식", kcal=100, source="sample", fetched_at=now),
            FoodNutrient(food_code="A2", name="두부", name_key="두부", group_name="원재료성", kcal=84, source="sample", fetched_at=now),
            FoodNutrient(food_code="A3", name="두부과자", name_key="두부과자", group_name="가공식품", kcal=400, source="sample", fetched_at=now),
            FoodNutrient(food_code="A4", name="두부", name_key="두부", group_name="원재료성", kcal=84, source="ai", fetched_at=now),
            FoodSearch(query_key="두부", total=4, searched_at=now),
        ])
        db.session.commit()

    def fail(*a, **k):
        raise AssertionError("최근 30일 안에 찾아본 이름은 다시 부르면 안 돼요")

    monkeypatch.setattr(outbound, "fetch_fixed", fail)
    res = client.get("/api/foods/search?q=두부")
    body = res.get_json()
    assert res.status_code == 200
    assert [row["name"] for row in body["items"]] == ["두부", "두부과자", "두부전"]
    assert body["searched"] is True

    assert raw_client.get("/api/foods/search?q=두부").status_code == 401

    res = client.get("/api/foods/search", query_string={"q": "  "})
    assert (res.status_code, res.get_json()["error"]) == (400, "찾을 식품 이름을 입력해주세요.")

    app.config.update(DEV_MODE=False)
    res = client.get("/api/foods/search?q=두부")
    assert (res.status_code, res.get_json()["error"]) == (503, foods.OFF)


def test_search_endpoint_reports_not_searched_when_fetch_fails(make_app, monkeypatch):
    app = make_app(FOOD_NUTRITION_API_KEY="k")
    client = app.test_client()
    client.environ_base["HTTP_X_REQUESTED_WITH"] = "fetch"
    with app.app_context():
        user = make_user()
        user_id = user.id
    with client.session_transaction() as s:
        s["user_id"], s["pid"] = user_id, "1"

    def boom(*a, **k):
        raise outbound.FetchError("HTTP500")

    monkeypatch.setattr(outbound, "fetch_fixed", boom)
    res = client.get("/api/foods/search?q=완전새로운재료")
    body = res.get_json()
    assert res.status_code == 200
    assert body["searched"] is False and body["items"] == []


# --- CLI ---


def test_warm_cli_requires_key(make_app):
    app = make_app()
    result = app.test_cli_runner().invoke(args=["warm-food-nutrients"])
    assert result.exit_code != 0
    assert "FOOD_NUTRITION_API_KEY가 없어요." in result.output


def test_warm_cli_picks_most_common_ingredient_keys(make_app, monkeypatch):
    app = make_app(FOOD_NUTRITION_API_KEY="k")
    with app.app_context():
        db.session.add_all([
            PublicRecipe(rcp_seq="1", title="a", ingredient_keys=["두부", "대파"]),
            PublicRecipe(rcp_seq="2", title="b", ingredient_keys=["두부"]),
            PublicRecipe(rcp_seq="3", title="c", ingredient_keys=["양파"]),
        ])
        db.session.commit()

        seen = []

        def fake_search(name, user):
            seen.append(name)
            return True

        monkeypatch.setattr(foods, "search_and_cache", fake_search)
        result = app.test_cli_runner().invoke(args=["warm-food-nutrients", "--limit", "2"])
        assert result.exit_code == 0
        assert seen == ["두부", "대파"]
        assert "식품 이름 2개를 찾아봤어요." in result.output


def test_warm_cli_reports_when_limit_hit(make_app, monkeypatch):
    app = make_app(FOOD_NUTRITION_API_KEY="k")
    with app.app_context():
        db.session.add(PublicRecipe(rcp_seq="1", title="a", ingredient_keys=["두부", "대파", "양파"]))
        db.session.commit()

        results = iter([True, False])
        monkeypatch.setattr(foods, "search_and_cache", lambda name, user: next(results))
        result = app.test_cli_runner().invoke(args=["warm-food-nutrients", "--limit", "3"])
        assert result.exit_code == 0
        assert "식품 이름 1개를 찾아봤어요. 한도 때문에 2개는 다음에 찾아요." in result.output
