import json
from types import SimpleNamespace

import pytest
import requests

import app.public_recipes as public_module
from app.matching import normalize
from app.models import PublicRecipe
from app.public_recipes import SAMPLE_FILE, row_fields

ROWS = [
    {
        "RCP_SEQ": "28",
        "RCP_NM": "새우 두부 계란찜",
        "RCP_PAT2": "반찬",
        "RCP_WAY2": "찌기",
        "INFO_ENG": "220",
        "RCP_PARTS_DTLS": "새우두부계란찜\n연두부 75g(3/4모), 칵테일새우 20g(5마리), 달걀 30g(1/2개)\n고명\n시금치 10g(3줄기)",
        "MANUAL01": "1. 손질된 새우를 끓는 물에 데쳐 건진다.a",
        "MANUAL02": "2. 연두부와 달걀을 믹서에 갈아 새우와 섞는다.b",
        "MANUAL03": "",
        "ATT_FILE_NO_MAIN": "http://www.foodsafetykorea.go.kr/uploadimg/cook/10_00028_2.png",
    },
    {
        "RCP_SEQ": "29",
        "RCP_NM": "부추 콩가루 찜",
        "RCP_PAT2": "반찬",
        "RCP_WAY2": "찌기",
        "INFO_ENG": "",
        "RCP_PARTS_DTLS": "[1인분]조선부추 50g, 날콩가루 7g(1⅓작은술)\n·양념장 : 저염간장 3g(2/3작은술), 참깨 약간",
        "MANUAL01": "1. 부추를 씻어 5cm 길이로 썬다.",
        "ATT_FILE_NO_MAIN": "",
    },
]


def _raw_response(body):
    """실제 requests(stream=True) 응답을 흉내 낸다: raw.read(n, decode_content=True)는 최대 n바이트를 준다."""
    data = json.dumps(body).encode("utf-8")

    def read(n, decode_content=True):
        return data[:n]

    return SimpleNamespace(raise_for_status=lambda: None, raw=SimpleNamespace(read=read))


def page(rows, total=None, code="INFO-000"):
    body = {"COOKRCP01": {"total_count": str(len(rows) if total is None else total), "row": rows, "RESULT": {"MSG": "", "CODE": code}}}
    return _raw_response(body)


def fake_get(monkeypatch, *responses):
    calls = []

    def get(url, timeout, **kwargs):
        calls.append((url, timeout))
        response = responses[len(calls) - 1]
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(requests, "get", get)
    return calls


def run(app, command):
    return app.test_cli_runner().invoke(args=[command])


def public_rows(app):
    with app.app_context():
        return [(r.rcp_seq, r.title, r.is_sample) for r in PublicRecipe.query.order_by(PublicRecipe.rcp_seq)]


def test_row_fields_maps_cookrcp01_row():
    fields = row_fields(ROWS[0])
    assert fields == {
        "rcp_seq": "28",
        "title": "새우 두부 계란찜",
        "category": "반찬",
        "method": "찌기",
        "kcal": 220.0,
        "servings": 2,
        "ingredients_text": ROWS[0]["RCP_PARTS_DTLS"],
        "ingredients": [
            {"name": "연두부", "amount": "75g(3/4모)"},
            {"name": "칵테일새우", "amount": "20g(5마리)"},
            {"name": "달걀", "amount": "30g(1/2개)"},
            {"name": "시금치", "amount": "10g(3줄기)"},
        ],
        "ingredient_keys": ["연두부", "칵테일새우", "달걀", "시금치"],
        "steps": ["손질된 새우를 끓는 물에 데쳐 건진다.", "연두부와 달걀을 믹서에 갈아 새우와 섞는다."],
        "image_url": "https://www.foodsafetykorea.go.kr/uploadimg/cook/10_00028_2.png",  # S2: http → https로 정리
        "is_sample": False,
    }
    second = row_fields(ROWS[1])
    assert (second["servings"], second["kcal"], second["image_url"]) == (1, None, None)


@pytest.mark.parametrize(
    "value, expected",
    [
        ("http://www.foodsafetykorea.go.kr/x.png", "https://www.foodsafetykorea.go.kr/x.png"),
        ("http://openapi.foodsafetykorea.go.kr/x.png", "https://openapi.foodsafetykorea.go.kr/x.png"),
        ("https://www.foodsafetykorea.go.kr/x.png", "https://www.foodsafetykorea.go.kr/x.png"),
        ("http://evil.example.com/x.png", None),  # 다른 호스트는 http를 https로 바꿔주지 않고 버린다
        ("https://evil.example.com/x.png", "https://evil.example.com/x.png"),  # 이미 https면 호스트를 가리지 않는다
        ("javascript:alert(1)", None),
        ("ftp://www.foodsafetykorea.go.kr/x.png", None),
        ("", None),
        (None, None),
        (123, None),
    ],
)
def test_image_url_normalizes_known_hosts_to_https(value, expected):
    assert public_module._image_url(value) == expected


def test_sync_without_key_points_to_sample_seed(app, monkeypatch):
    calls = fake_get(monkeypatch)
    result = run(app, "sync-public-recipes")
    assert result.exit_code == 1
    assert "FOODSAFETY_API_KEY가 없어요" in result.output
    assert "flask seed-sample-recipes" in result.output
    assert calls == []


def test_sync_fetches_pages_and_upserts(app, monkeypatch):
    app.config["FOODSAFETY_API_KEY"] = "test-key"
    monkeypatch.setattr(public_module, "PAGE_SIZE", 1)
    calls = fake_get(monkeypatch, page(ROWS[:1], total=2), page(ROWS[1:], total=2))
    assert run(app, "seed-sample-recipes").exit_code == 0

    result = run(app, "sync-public-recipes")
    assert result.exit_code == 0, result.output
    assert calls == [
        ("https://openapi.foodsafetykorea.go.kr/api/test-key/COOKRCP01/json/1/1", 30),
        ("https://openapi.foodsafetykorea.go.kr/api/test-key/COOKRCP01/json/2/2", 30),
    ]
    assert "식약처 레시피 2건을 받았어요. 새로 2건, 바뀐 것 0건, 예시 레시피 12건은 지웠어요." in result.output
    assert public_rows(app) == [("28", "새우 두부 계란찜", False), ("29", "부추 콩가루 찜", False)]

    changed = {**ROWS[0], "RCP_NM": "새우 두부 계란찜(개정)"}
    fake_get(monkeypatch, page([changed], total=2), page(ROWS[1:], total=2))
    result = run(app, "sync-public-recipes")
    assert "새로 0건, 바뀐 것 2건, 예시 레시피 0건은 지웠어요." in result.output
    assert public_rows(app)[0] == ("28", "새우 두부 계란찜(개정)", False)


def test_sync_page_boundaries_with_total_2500(app, monkeypatch):
    # T-tests: 기본 PAGE_SIZE(1000)일 때 total 2500 → 1/1000, 1001/2000, 2001/3000
    app.config["FOODSAFETY_API_KEY"] = "test-key"
    calls = fake_get(monkeypatch, page(ROWS[:1], total=2500), page(ROWS[:1], total=2500), page(ROWS[1:], total=2500))
    result = run(app, "sync-public-recipes")
    assert result.exit_code == 0, result.output
    assert [c[0] for c in calls] == [
        "https://openapi.foodsafetykorea.go.kr/api/test-key/COOKRCP01/json/1/1000",
        "https://openapi.foodsafetykorea.go.kr/api/test-key/COOKRCP01/json/1001/2000",
        "https://openapi.foodsafetykorea.go.kr/api/test-key/COOKRCP01/json/2001/3000",
    ]


def test_sync_info_200_first_page_is_empty_result(app, monkeypatch):
    # T-tests: INFO-200 첫 페이지 → 0건, 성공(exit 0), 예시 레시피도 그대로(진짜 레시피가 없으면 지우지 않는다)
    app.config["FOODSAFETY_API_KEY"] = "test-key"
    run(app, "seed-sample-recipes")
    fake_get(monkeypatch, page([], code="INFO-200"))
    result = run(app, "sync-public-recipes")
    assert result.exit_code == 0, result.output
    assert "식약처 레시피 0건을 받았어요. 새로 0건, 바뀐 것 0건, 예시 레시피 0건은 지웠어요." in result.output
    assert len(public_rows(app)) == 12


def test_sync_stops_at_total_row_ceiling(app, monkeypatch):
    # S1: total_count가 999999라고 우겨도 MAX_TOTAL_ROWS(5000)에서 멈춘다 → 기본 PAGE_SIZE로 5번만 요청
    app.config["FOODSAFETY_API_KEY"] = "test-key"
    calls = fake_get(monkeypatch, *[page(ROWS[:1], total=999999) for _ in range(5)])
    result = run(app, "sync-public-recipes")
    assert result.exit_code == 0, result.output
    assert len(calls) == 5
    assert calls[-1][0] == "https://openapi.foodsafetykorea.go.kr/api/test-key/COOKRCP01/json/4001/5000"


def test_sync_response_too_large_is_rejected(app, monkeypatch):
    # S1: 스트리밍으로 MAX_RESPONSE_BYTES+1을 넘게 받으면 그 자리에서 그만두고 아무것도 쓰지 않는다
    app.config["FOODSAFETY_API_KEY"] = "test-key"
    monkeypatch.setattr(public_module, "MAX_RESPONSE_BYTES", 10)
    run(app, "seed-sample-recipes")
    fake_get(monkeypatch, page(ROWS[:1]))
    result = run(app, "sync-public-recipes")
    assert result.exit_code == 1
    assert "식약처 응답이 예상보다 커요" in result.output
    assert "test-key" not in result.output
    assert len(public_rows(app)) == 12


@pytest.mark.parametrize(
    "response, message",
    [
        (requests.ConnectionError("https://openapi.foodsafetykorea.go.kr/api/test-key/..."), "식약처 레시피를 받지 못했어요(1~1000번, ConnectionError)."),
        (_raw_response({"oops": 1}), "식약처 레시피를 받지 못했어요(1~1000번, KeyError)."),
        (page([], code="INFO-100"), "식약처 API가 오류를 돌려줬어요(INFO-100)."),
    ],
)
def test_sync_failure_writes_nothing_and_hides_key(app, monkeypatch, response, message):
    app.config["FOODSAFETY_API_KEY"] = "test-key"
    fake_get(monkeypatch, response)
    run(app, "seed-sample-recipes")
    result = run(app, "sync-public-recipes")
    assert result.exit_code == 1
    assert message in result.output
    assert "test-key" not in result.output
    assert len(public_rows(app)) == 12  # 예시 레시피도 그대로


def test_seed_sample_recipes_is_idempotent(app):
    first = run(app, "seed-sample-recipes")
    assert "예시 레시피 12개를 넣었어요. 새로 12개, 바뀐 것 0개." in first.output
    second = run(app, "seed-sample-recipes")
    assert "새로 0개, 바뀐 것 12개." in second.output
    with app.app_context():
        recipes = PublicRecipe.query.order_by(PublicRecipe.rcp_seq).all()
        assert [r.rcp_seq for r in recipes] == [f"SAMPLE-{n:02d}" for n in range(1, 13)]
        assert {r.title for r in recipes} == {
            "된장찌개", "김치찌개", "계란말이", "두부조림", "애호박볶음", "제육볶음",
            "감자조림", "콩나물무침", "계란국", "대파 계란볶음밥", "어묵볶음", "시금치나물",
        }
        for r in recipes:
            assert r.is_sample and r.image_url is None and r.category
            assert 1 <= r.servings <= 20 and 4 <= len(r.steps) <= 7
            assert all(i["name"] and i["amount"] for i in r.ingredients)
            assert [normalize(k) for k in r.ingredient_keys] == [normalize(i["name"]) for i in r.ingredients]


def test_sample_file_names_are_unique_per_recipe():
    for item in json.loads(SAMPLE_FILE.read_text(encoding="utf-8")):
        names = [normalize(i["name"]) for i in item["ingredients"]]
        assert len(names) == len(set(names)), item["title"]


def test_sync_stream_read_failure_is_clean_and_hides_key(app, monkeypatch):
    # 본문을 읽는 도중 연결이 끊겨도(urllib3 오류) 깔끔한 안내로 끝나고 키가 출력에 나오지 않는다
    import urllib3

    class Broken:
        status_code = 200

        def raise_for_status(self):
            pass

        class raw:
            @staticmethod
            def read(*_args, **_kwargs):
                raise urllib3.exceptions.ProtocolError("connection reset")

    app.config["FOODSAFETY_API_KEY"] = "test-key"
    monkeypatch.setattr("app.public_recipes.requests.get", lambda *a, **k: Broken())
    result = app.test_cli_runner().invoke(args=["sync-public-recipes"])
    assert result.exit_code != 0
    assert "test-key" not in result.output
