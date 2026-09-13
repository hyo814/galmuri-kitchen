import base64
import io
from datetime import date, datetime, time, timedelta, timezone
from types import SimpleNamespace

import anthropic
import pytest
from pydantic import ValidationError

from app import ai, scan
from app.ingredients import SEOUL, seoul_today
from app.models import AiCall, User, db
from app.scan import MAX_ITEMS, clean_result

TODAY = date(2026, 9, 13)

JPEG_BYTES = b"\xff\xd8\xff" + b"fake-jpeg-body"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fake-png-body"
WEBP_BYTES = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"fake-webp-body"


def upload(client, kind="receipt", data=JPEG_BYTES, mimetype="image/jpeg"):
    return client.post(f"/api/scan?kind={kind}", data={"image": (io.BytesIO(data), "photo.jpg", mimetype)})


def ai_call_costs(app):
    with app.app_context():
        return [(c.model, c.input_tokens, c.output_tokens) for c in AiCall.query.order_by(AiCall.id).all()]


def ai_calls(app):
    with app.app_context():
        return [(c.user_id, c.kind) for c in AiCall.query.order_by(AiCall.id).all()]


USAGE = {"model": "claude-sonnet-5-answered", "input_tokens": 1500, "output_tokens": 120}


def fail_if_called(*args):
    raise AssertionError("AI를 부르면 안 돼요")


# --- clean_result (모델 출력 정리) ---


def test_clean_result_sanitizes_items():
    raw = {
        "items": [
            {"name": "  대파  ", "quantity": 2, "unit": " 단 ", "location_kind": "fridge", "price": 2500},
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
            {"name": "대파", "quantity": 2.0, "unit": "단", "location_kind": "fridge", "price": 2500},
            {"name": "가" * 50, "quantity": 1, "unit": "개", "location_kind": "fridge", "price": None},
            {"name": "쌀", "quantity": 1, "unit": "킬로그램단위표기초과", "location_kind": "room", "price": None},
            {"name": "생수", "quantity": 9999, "unit": "개", "location_kind": "room", "price": None},
            {"name": "우유", "quantity": 1, "unit": "개", "location_kind": "fridge", "price": None},
        ],
        "purchased_on": "2026-09-12",
    }


@pytest.mark.parametrize(
    "value, expected",
    [
        ("3,480원", None),
        (-1, None),
        (0, None),
        (1e12, None),
        (3480.4, 3480),
        (True, None),
        (3480, 3480),
        (None, None),
    ],
)
def test_clean_result_price_garbage(value, expected):
    raw = {"items": [{"name": "대파", "quantity": 1, "unit": "단", "location_kind": "fridge", "price": value}]}
    assert clean_result("receipt", raw, TODAY)["items"][0]["price"] == expected


def test_clean_result_fridge_price_always_none():
    raw = {"items": [{"name": "대파", "quantity": 1, "unit": "단", "location_kind": "fridge", "price": 2500}]}
    assert clean_result("fridge", raw, TODAY)["items"][0]["price"] is None


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


def test_clean_result_negative_quantity_and_empty_name():
    raw = {
        "items": [
            {"name": "당근", "quantity": -5, "unit": "개", "location_kind": "fridge"},
            {"name": "", "quantity": 1, "unit": "개", "location_kind": "fridge"},
        ]
    }
    assert clean_result("receipt", raw, TODAY)["items"] == [
        {"name": "당근", "quantity": 1, "unit": "개", "location_kind": "fridge", "price": None},
    ]


def test_clean_result_quantity_overflow_falls_back_to_one():
    raw = {"items": [{"name": "쌀", "quantity": 10**400, "unit": "포", "location_kind": "room"}]}
    assert clean_result("receipt", raw, TODAY)["items"] == [
        {"name": "쌀", "quantity": 1, "unit": "포", "location_kind": "room", "price": None},
    ]


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
        items=[ai.ScanItem(name="우유", quantity=1, unit="개", location_kind="fridge", price=2980)],
        purchased_on="2026-09-12",
    )
    usage = SimpleNamespace(input_tokens=1500, output_tokens=120)
    calls = fake_anthropic(
        monkeypatch,
        response=SimpleNamespace(stop_reason="end_turn", parsed_output=parsed, usage=usage, model="claude-sonnet-5-answered"),
    )
    app.config.update(ANTHROPIC_API_KEY="test-key", CLAUDE_MODEL="claude-sonnet-5")
    with app.app_context():
        result, tokens = ai.extract("receipt", b"\xff\xd8jpeg", "image/jpeg")

    assert tokens == {"model": "claude-sonnet-5-answered", "input_tokens": 1500, "output_tokens": 120}

    assert result == {
        "items": [{"name": "우유", "quantity": 1.0, "unit": "개", "location_kind": "fridge", "price": 2980}],
        "purchased_on": "2026-09-12",
    }
    assert calls["client"] == {"api_key": "test-key", "timeout": 45, "max_retries": 1}
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
    assert (res.status_code, res.get_json()) == (400, {"error": "사진을 올려주세요."})
    res = upload(client, data=b"")
    assert (res.status_code, res.get_json()) == (400, {"error": "사진을 올려주세요."})
    res = upload(client, data=b"not-an-image-just-plain-bytes", mimetype="text/plain")
    assert (res.status_code, res.get_json()) == (415, {"error": "사진 파일(JPG·PNG·WEBP)만 올릴 수 있어요."})
    # 선언된 Content-Type을 image/jpeg로 위조해도 실제 바이트(서명)가 이미지가 아니면 415
    res = upload(client, data=b"not-an-image-just-plain-bytes", mimetype="image/jpeg")
    assert (res.status_code, res.get_json()) == (415, {"error": "사진 파일(JPG·PNG·WEBP)만 올릴 수 있어요."})


def test_too_large_upload_is_413_json(client, login):
    login()
    res = upload(client, data=b"x" * (10 * 1024 * 1024 + 1))
    assert (res.status_code, res.get_json()) == (413, {"error": "파일이 너무 커요. 10MB 이하로 올려주세요."})


def test_scan_accepts_valid_image_signatures_by_content_not_label(client, login, app, monkeypatch):
    login()
    app.config["ANTHROPIC_API_KEY"] = "test-key"
    monkeypatch.setattr(ai, "extract", lambda *a: ({"items": [], "purchased_on": None}, USAGE))
    for data in (JPEG_BYTES, PNG_BYTES, WEBP_BYTES):
        # 선언된 Content-Type은 항상 text/plain으로 위조하지만, 실제 바이트 서명이 유효하면 통과한다
        assert upload(client, data=data, mimetype="text/plain").status_code == 200


def test_sample_mode_without_key_in_dev(client, login, app, monkeypatch):
    login()
    monkeypatch.setattr(ai, "extract", fail_if_called)
    receipt = upload(client, kind="receipt").get_json()
    fridge = upload(client, kind="fridge").get_json()
    assert (receipt["sample"], receipt["purchased_on"]) == (True, seoul_today().isoformat())
    assert (fridge["sample"], fridge["purchased_on"]) == (True, None)
    assert {"name": "냉동만두", "quantity": 1, "unit": "봉", "location_kind": "freezer", "price": None} in fridge["items"]
    assert all(item["price"] is None for item in fridge["items"])
    assert all(isinstance(item["price"], int) for item in receipt["items"])
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
        raw = {
            "items": [{"name": " 우유 ", "quantity": 0, "unit": "", "location_kind": "fridge", "price": 2980}],
            "purchased_on": "2999-01-01",
        }
        return raw, USAGE

    monkeypatch.setattr(ai, "extract", fake_extract)
    # 선언된 Content-Type은 image/jpeg로 위조하지만 실제 바이트는 PNG 서명 → extract는 스니핑한 image/png를 받는다
    res = upload(client, kind="order", data=PNG_BYTES, mimetype="image/jpeg")
    assert res.status_code == 200
    assert res.get_json() == {
        "items": [{"name": "우유", "quantity": 1, "unit": "개", "location_kind": "fridge", "price": 2980}],
        "purchased_on": None,
        "sample": False,
    }
    assert seen == [("order", PNG_BYTES, "image/png")]
    assert ai_calls(app) == [(user.id, "order")]
    assert ai_call_costs(app) == [("claude-sonnet-5-answered", 1500, 120)]  # 실제로 답한 모델로 덮어쓴다


def test_ai_failure_is_502_and_counted(client, login, app, monkeypatch):
    user = login()
    app.config["ANTHROPIC_API_KEY"] = "test-key"

    def broken(*args):
        raise ai.AiError("timeout")

    monkeypatch.setattr(ai, "extract", broken)
    res = upload(client)
    assert (res.status_code, res.get_json()) == (502, {"error": "인식에 실패했어요. 직접 입력해주세요."})
    # F1: 실패도 비용이 들었으므로 한도에는 센다(업로드 검증 실패만 세지 않는다)
    assert ai_calls(app) == [(user.id, "receipt")]
    assert ai_call_costs(app) == [("claude-sonnet-5", None, None)]  # 실패하면 요청한 모델만 남고 토큰은 비워 둔다


def test_daily_limit_counts_scan_kinds_in_seoul_day(client, login, app, monkeypatch):
    user = login()
    app.config.update(ANTHROPIC_API_KEY="test-key", AI_DAILY_SCAN_LIMIT=3)
    monkeypatch.setattr(ai, "extract", lambda *args: ({"items": [], "purchased_on": None}, USAGE))
    fixed_today = date(2026, 9, 13)
    start = datetime.combine(fixed_today, time.min, tzinfo=SEOUL).astimezone(timezone.utc)
    fixed_now = start + timedelta(hours=12)  # 벽시계와 무관하게 고정 — burst 윈도우가 seed 데이터와 안 겹치게 정오로 둔다
    monkeypatch.setattr(scan, "seoul_today", lambda: fixed_today)
    monkeypatch.setattr(scan, "utcnow", lambda: fixed_now)
    with app.app_context():
        other = User(provider="test", provider_id="other", nickname="x")
        db.session.add(other)
        db.session.flush()
        db.session.add_all(
            [
                AiCall(user_id=user.id, kind="fridge", created_at=start + timedelta(seconds=1)),  # 오늘 첫 순간 → 셈
                AiCall(user_id=user.id, kind="order", created_at=fixed_now - timedelta(seconds=5)),  # 지금 → 셈
                AiCall(user_id=user.id, kind="receipt", created_at=start - timedelta(seconds=1)),  # 어제 → 안 셈
                AiCall(user_id=user.id, kind="recipe", created_at=fixed_now),  # 레시피 한도 → 안 셈
                *[AiCall(user_id=other.id, kind="fridge", created_at=fixed_now) for _ in range(5)],  # 다른 사용자 → 안 셈
            ]
        )
        db.session.commit()

    assert upload(client).status_code == 200  # 2번 썼으니 3번째는 된다
    res = upload(client)
    assert (res.status_code, res.get_json()) == (429, {"error": "오늘 사진 인식은 3번까지 쓸 수 있어요. 내일 다시 써주세요."})


def test_burst_limit_blocks_rapid_calls(client, login, app, monkeypatch):
    user = login()
    app.config.update(ANTHROPIC_API_KEY="test-key", AI_SCAN_BURST_LIMIT=3)
    monkeypatch.setattr(ai, "extract", fail_if_called)
    fixed_now = datetime(2026, 9, 13, 12, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(scan, "utcnow", lambda: fixed_now)
    with app.app_context():
        db.session.add_all(
            [
                AiCall(user_id=user.id, kind="fridge", created_at=fixed_now - timedelta(seconds=10)),
                AiCall(user_id=user.id, kind="receipt", created_at=fixed_now - timedelta(seconds=30)),
                AiCall(user_id=user.id, kind="order", created_at=fixed_now - timedelta(seconds=59)),
            ]
        )
        db.session.commit()
    res = upload(client)
    assert (res.status_code, res.get_json()) == (429, {"error": "잠시 후 다시 시도해주세요."})


def test_burst_limit_ignores_calls_older_than_a_minute(client, login, app, monkeypatch):
    user = login()
    app.config.update(ANTHROPIC_API_KEY="test-key", AI_SCAN_BURST_LIMIT=3)
    monkeypatch.setattr(ai, "extract", lambda *args: ({"items": [], "purchased_on": None}, USAGE))
    fixed_now = datetime(2026, 9, 13, 12, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(scan, "utcnow", lambda: fixed_now)
    with app.app_context():
        db.session.add_all(
            [AiCall(user_id=user.id, kind="fridge", created_at=fixed_now - timedelta(seconds=61)) for _ in range(3)]
        )
        db.session.commit()
    assert upload(client).status_code == 200


def test_scan_requires_fetch_header(raw_client):
    res = raw_client.post("/api/scan?kind=fridge")
    assert (res.status_code, res.get_json()) == (400, {"error": "잘못된 요청이에요."})
