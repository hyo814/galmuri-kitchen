import base64
import io
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

import anthropic
import pytest
from pydantic import ValidationError

from app import ai
from app.ingredients import SEOUL, seoul_today
from app.models import AiCall, User, db
from app.scan import MAX_ITEMS, clean_result

TODAY = date(2026, 9, 13)


def upload(client, kind="receipt", data=b"\xff\xd8fake-jpeg", mimetype="image/jpeg"):
    return client.post(f"/api/scan?kind={kind}", data={"image": (io.BytesIO(data), "photo.jpg", mimetype)})


def ai_calls(app):
    with app.app_context():
        return [(c.user_id, c.kind) for c in AiCall.query.order_by(AiCall.id).all()]


def fail_if_called(*args):
    raise AssertionError("AI를 부르면 안 돼요")


# --- clean_result (모델 출력 정리) ---


def test_clean_result_sanitizes_items():
    raw = {
        "items": [
            {"name": "  대파  ", "quantity": 2, "unit": " 단 ", "location_kind": "fridge"},
            {"name": "   ", "quantity": 1, "unit": "개", "location_kind": "fridge"},
            "not-a-dict",
            {"name": "가" * 60, "quantity": 0, "unit": "", "location_kind": "kitchen"},
            {"name": "쌀", "quantity": "많이", "unit": "킬로그램단위표기초과됨", "location_kind": "room"},
            {"name": "생수", "quantity": 1e9, "unit": None, "location_kind": "room"},
            {"name": "우유", "quantity": True, "location_kind": ["fridge"]},
        ],
        "purchased_on": "2026-09-12",
    }
    assert clean_result("receipt", raw, TODAY) == {
        "items": [
            {"name": "대파", "quantity": 2.0, "unit": "단", "location_kind": "fridge"},
            {"name": "가" * 50, "quantity": 1, "unit": "개", "location_kind": "fridge"},
            {"name": "쌀", "quantity": 1, "unit": "킬로그램단위표기초과", "location_kind": "room"},
            {"name": "생수", "quantity": 9999, "unit": "개", "location_kind": "room"},
            {"name": "우유", "quantity": 1, "unit": "개", "location_kind": "fridge"},
        ],
        "purchased_on": "2026-09-12",
    }


@pytest.mark.parametrize(
    "kind, value, expected",
    [
        ("receipt", "2026-09-13", "2026-09-13"),
        ("order", "2026-08-30", "2026-08-30"),
        ("receipt", "2026-09-14", None),  # 오늘 이후 날짜는 버린다
        ("receipt", "어제", None),
        ("order", None, None),
        ("fridge", "2026-09-12", None),  # 냉장고 사진에는 구입일이 없다
    ],
)
def test_clean_result_purchased_on(kind, value, expected):
    assert clean_result(kind, {"items": [], "purchased_on": value}, TODAY)["purchased_on"] == expected


def test_clean_result_caps_items_and_handles_garbage():
    many = {"items": [{"name": f"재료{i}", "quantity": 1, "unit": "개", "location_kind": "room"} for i in range(60)]}
    assert len(clean_result("order", many, TODAY)["items"]) == MAX_ITEMS
    assert clean_result("order", None, TODAY) == {"items": [], "purchased_on": None}
    assert clean_result("order", {"items": "대파"}, TODAY) == {"items": [], "purchased_on": None}


# --- ai.extract (가짜 Anthropic 클라이언트) ---


def fake_anthropic(monkeypatch, response=None, error=None):
    calls = {}

    class FakeClient:
        def __init__(self, **kwargs):
            calls["client"] = kwargs
            self.messages = self

        def parse(self, **kwargs):
            calls["parse"] = kwargs
            if error is not None:
                raise error
            return response

    monkeypatch.setattr(anthropic, "Anthropic", FakeClient)
    return calls


def test_extract_sends_image_prompt_and_schema(app, monkeypatch):
    parsed = ai.ScanResult(
        items=[ai.ScanItem(name="우유", quantity=1, unit="개", location_kind="fridge")], purchased_on="2026-09-12"
    )
    calls = fake_anthropic(monkeypatch, response=SimpleNamespace(stop_reason="end_turn", parsed_output=parsed))
    app.config.update(ANTHROPIC_API_KEY="test-key", CLAUDE_MODEL="claude-sonnet-5")
    with app.app_context():
        result = ai.extract("receipt", b"\xff\xd8jpeg", "image/jpeg")

    assert result == {
        "items": [{"name": "우유", "quantity": 1.0, "unit": "개", "location_kind": "fridge"}],
        "purchased_on": "2026-09-12",
    }
    assert calls["client"] == {"api_key": "test-key", "timeout": 60, "max_retries": 2}
    request = calls["parse"]
    assert (request["model"], request["max_tokens"], request["output_format"]) == ("claude-sonnet-5", 4096, ai.ScanResult)
    image, prompt = request["messages"][0]["content"]
    assert image == {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.standard_b64encode(b"\xff\xd8jpeg").decode()},
    }
    assert prompt == {"type": "text", "text": ai.PROMPTS["receipt"]}


def _validation_error():
    try:
        ai.ScanResult.model_validate({})
    except ValidationError as e:
        return e


@pytest.mark.parametrize(
    "response, error",
    [
        (SimpleNamespace(stop_reason="refusal", parsed_output=None), None),
        (SimpleNamespace(stop_reason="end_turn", parsed_output=None), None),
        (None, anthropic.APIError("boom", request=None, body=None)),
        (None, _validation_error()),
    ],
)
def test_extract_failures_raise_ai_error(app, monkeypatch, response, error):
    fake_anthropic(monkeypatch, response=response, error=error)
    app.config["ANTHROPIC_API_KEY"] = "test-key"
    with app.app_context(), pytest.raises(ai.AiError):
        ai.extract("fridge", b"img", "image/png")


# --- POST /api/scan ---


def test_requires_login(client):
    assert upload(client).status_code == 401


def test_rejects_bad_kind_missing_image_and_non_image(client, login):
    login()
    res = upload(client, kind="memo")
    assert (res.status_code, res.get_json()) == (400, {"error": "스캔 종류가 올바르지 않아요."})
    res = client.post("/api/scan?kind=fridge")
    assert (res.status_code, res.get_json()) == (400, {"error": "사진을 올려 주세요."})
    res = upload(client, data=b"")
    assert (res.status_code, res.get_json()) == (400, {"error": "사진을 올려 주세요."})
    res = upload(client, mimetype="text/plain")
    assert (res.status_code, res.get_json()) == (415, {"error": "사진 파일(JPG·PNG·WEBP)만 올릴 수 있어요."})


def test_too_large_upload_is_413_json(client, login):
    login()
    res = upload(client, data=b"x" * (10 * 1024 * 1024 + 1))
    assert (res.status_code, res.get_json()) == (413, {"error": "파일이 너무 커요. 10MB 이하로 올려 주세요."})


def test_sample_mode_without_key_in_dev(client, login, app, monkeypatch):
    login()
    monkeypatch.setattr(ai, "extract", fail_if_called)
    receipt = upload(client, kind="receipt").get_json()
    fridge = upload(client, kind="fridge").get_json()
    assert (receipt["sample"], receipt["purchased_on"]) == (True, seoul_today().isoformat())
    assert (fridge["sample"], fridge["purchased_on"]) == (True, None)
    assert {"name": "냉동만두", "quantity": 1, "unit": "봉", "location_kind": "freezer"} in fridge["items"]
    assert all(3 <= len(upload(client, kind=k).get_json()["items"]) <= 6 for k in ["fridge", "receipt", "order"])
    assert ai_calls(app) == []


def test_without_key_in_production_is_503(client, login, app, monkeypatch):
    login()
    app.config["DEV_MODE"] = False
    monkeypatch.setattr(ai, "extract", fail_if_called)
    res = upload(client)
    assert (res.status_code, res.get_json()) == (503, {"error": "사진 인식을 지금은 쓸 수 없어요."})


def test_real_scan_cleans_result_and_logs_call(client, login, app, monkeypatch):
    user = login()
    app.config["ANTHROPIC_API_KEY"] = "test-key"
    seen = []

    def fake_extract(kind, image_bytes, media_type):
        seen.append((kind, image_bytes, media_type))
        return {"items": [{"name": " 우유 ", "quantity": 0, "unit": "", "location_kind": "fridge"}], "purchased_on": "2999-01-01"}

    monkeypatch.setattr(ai, "extract", fake_extract)
    res = upload(client, kind="order", data=b"png-bytes", mimetype="image/png")
    assert res.status_code == 200
    assert res.get_json() == {
        "items": [{"name": "우유", "quantity": 1, "unit": "개", "location_kind": "fridge"}],
        "purchased_on": None,
        "sample": False,
    }
    assert seen == [("order", b"png-bytes", "image/png")]
    assert ai_calls(app) == [(user.id, "order")]


def test_ai_failure_is_502_and_not_counted(client, login, app, monkeypatch):
    login()
    app.config["ANTHROPIC_API_KEY"] = "test-key"

    def broken(*args):
        raise ai.AiError("timeout")

    monkeypatch.setattr(ai, "extract", broken)
    res = upload(client)
    assert (res.status_code, res.get_json()) == (502, {"error": "인식에 실패했어요. 직접 입력해 주세요."})
    assert ai_calls(app) == []


def test_daily_limit_counts_scan_kinds_in_seoul_day(client, login, app, monkeypatch):
    user = login()
    app.config.update(ANTHROPIC_API_KEY="test-key", AI_DAILY_SCAN_LIMIT=3)
    monkeypatch.setattr(ai, "extract", lambda *args: {"items": [], "purchased_on": None})
    start = datetime.combine(seoul_today(), time.min, tzinfo=SEOUL).astimezone(timezone.utc)
    with app.app_context():
        other = User(provider="test", provider_id="other", nickname="x")
        db.session.add(other)
        db.session.flush()
        db.session.add_all(
            [
                AiCall(user_id=user.id, kind="fridge", created_at=start + timedelta(seconds=1)),  # 오늘 첫 순간 → 셈
                AiCall(user_id=user.id, kind="order"),  # 지금 → 셈
                AiCall(user_id=user.id, kind="receipt", created_at=start - timedelta(seconds=1)),  # 어제 → 안 셈
                AiCall(user_id=user.id, kind="recipe"),  # 레시피 한도 → 안 셈
                *[AiCall(user_id=other.id, kind="fridge") for _ in range(5)],  # 다른 사용자 → 안 셈
            ]
        )
        db.session.commit()

    assert upload(client).status_code == 200  # 2번 썼으니 3번째는 된다
    res = upload(client)
    assert (res.status_code, res.get_json()) == (429, {"error": "오늘 사진 인식은 3번까지 쓸 수 있어요. 내일 다시 써 주세요."})


def test_scan_requires_fetch_header(raw_client):
    res = raw_client.post("/api/scan?kind=fridge")
    assert (res.status_code, res.get_json()) == (400, {"error": "잘못된 요청이에요."})
