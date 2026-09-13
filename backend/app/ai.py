import base64
from typing import Literal

import anthropic
from flask import current_app
from pydantic import BaseModel, ValidationError

# 스캔 프롬프트 공통 규칙. 결과 형식은 output_format(ScanResult)이 강제한다.
_COMMON = (
    "재료 이름은 한국어 일반 명칭으로 짧게 쓴다(브랜드·용량·광고 문구는 빼되, 알아보기 쉬운 이름은 남긴다. 예: 'CJ 햇반 210g' → '햇반'). "
    "quantity는 숫자, unit은 개·g·ml·팩·봉·병·모·단 같은 짧은 단위로 쓴다. "
    "location_kind는 이 재료를 보관해야 하는 곳이다: 냉장 보관은 fridge, 냉동식품은 freezer, 상온 보관(쌀·라면·햇반·양파·감자 등)은 room. "
    "음식 재료가 하나도 없으면 items를 빈 배열로 둔다."
)

PROMPTS = {
    "fridge": (
        "냉장고 안을 찍은 사진이다. 보이는 음식 재료를 모두 찾아라. "
        "개수와 단위는 사진에서 보이는 만큼 추정한다. 내용물을 알 수 없는 용기·반찬통은 건너뛴다. "
        "purchased_on은 항상 null로 둔다. " + _COMMON
    ),
    "receipt": (
        "마트·시장 영수증 사진이다. 식재료·식품 줄만 골라라. 봉투·세제·휴지·생활용품 같은 식품이 아닌 항목은 뺀다. "
        "수량은 영수증에 적힌 수량을 쓴다. purchased_on은 영수증에 찍힌 구매 날짜(YYYY-MM-DD)이고, 없으면 null. " + _COMMON
    ),
    "order": (
        "온라인 쇼핑몰(쿠팡·네이버스토어·컬리·이마트·홈플러스·롯데마트·G마켓)의 주문완료 또는 주문상세 화면 캡처다. "
        "주문한 상품 중 식품만 골라라. 주문 수량을 quantity로 쓴다(묶음 상품은 알 수 있으면 낱개 수로). "
        "purchased_on은 주문 날짜(YYYY-MM-DD)이고, 없으면 null. " + _COMMON
    ),
}

# 키가 없는 개발 모드에서 화면 흐름을 확인하는 예시 결과
SAMPLES = {
    "fridge": [
        ("대파", 1, "단", "fridge"),
        ("계란", 10, "개", "fridge"),
        ("두부", 1, "모", "fridge"),
        ("냉동만두", 1, "봉", "freezer"),
    ],
    "receipt": [
        ("우유", 1, "개", "fridge"),
        ("돼지고기 앞다리살", 600, "g", "fridge"),
        ("양파", 3, "개", "room"),
        ("냉동 새우", 1, "봉", "freezer"),
        ("콩나물", 1, "봉", "fridge"),
    ],
    "order": [
        ("냉동 블루베리", 1, "봉", "freezer"),
        ("햇반", 6, "개", "room"),
        ("그릭요거트", 2, "개", "fridge"),
        ("애호박", 1, "개", "fridge"),
        ("방울토마토", 500, "g", "fridge"),
    ],
}


class AiError(Exception):
    """AI 호출 실패(API 오류·타임아웃·거절·형식 불일치). 호출 측이 502로 바꾼다."""


class ScanItem(BaseModel):
    name: str
    quantity: float
    unit: str
    location_kind: Literal["fridge", "freezer", "room"]


class ScanResult(BaseModel):
    items: list[ScanItem]
    purchased_on: str | None


def scan_mode():
    """on: API 키 있음 / sample: 키 없음 + 개발 모드(예시 결과) / off: 키 없음 + 운영(기능 숨김)"""
    if current_app.config["ANTHROPIC_API_KEY"]:
        return "on"
    return "sample" if current_app.config["DEV_MODE"] else "off"


def sample_result(kind, today):
    items = [{"name": n, "quantity": q, "unit": u, "location_kind": k} for n, q, u, k in SAMPLES[kind]]
    return {"items": items, "purchased_on": None if kind == "fridge" else today.isoformat()}


def extract(kind, image_bytes, media_type):
    """사진 한 장에서 재료 목록을 뽑는다. (결과, 토큰 사용량)을 돌려주고, 실패하면 AiError."""
    # gthread 워커는 요청 처리 중에도 계속 heartbeat를 보내므로 gunicorn --timeout(120s, Dockerfile)이
    # 이 호출을 끊지 않는다. SDK는 두 번의 시도(45s + 45s) 사이에 retry-after(최대 60s)를 기다릴 수 있어
    # 최악의 경우 약 150초까지 걸릴 수 있다. 그동안 사용자는 화면에서 취소할 수 있다.
    client = anthropic.Anthropic(api_key=current_app.config["ANTHROPIC_API_KEY"], timeout=45, max_retries=1)
    image = base64.standard_b64encode(image_bytes).decode("utf-8")
    try:
        response = client.messages.parse(
            model=current_app.config["CLAUDE_MODEL"],
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image}},
                        {"type": "text", "text": PROMPTS[kind]},
                    ],
                }
            ],
            output_format=ScanResult,
        )
    except (anthropic.APIError, ValidationError) as e:
        current_app.logger.warning("scan %s failed: %s", kind, type(e).__name__)
        raise AiError(type(e).__name__) from e
    if response.stop_reason == "refusal" or response.parsed_output is None:
        current_app.logger.warning("scan %s failed: stop_reason=%s", kind, response.stop_reason)
        raise AiError(response.stop_reason)
    # model은 요청한 이름이 아니라 실제로 답한(과금된) 모델 이름이다.
    usage = {
        "model": response.model,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }
    return response.parsed_output.model_dump(), usage
