"""식약처 공공 레시피 동기화·예시 레시피 CLI. 화면 API는 recipes.py에 있다."""

import json
import math
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import click
import requests
from flask import Blueprint, current_app

from .models import PublicRecipe, db
from .recipe_parse import ingredient_key, parse_ingredients, parse_servings, split_steps

bp = Blueprint("public_recipes", __name__, cli_group=None)  # 명령을 `flask sync-public-recipes`처럼 최상위에 둔다

# http도 되지만 URL에 인증키가 들어가므로 https로 부른다 (2026-09-13 https 200 확인)
API_URL = "https://openapi.foodsafetykorea.go.kr/api/{key}/COOKRCP01/json/{start}/{end}"
PAGE_SIZE = 1000
MAX_RESPONSE_BYTES = 20 * 1024 * 1024  # fix round 1 (S1): 응답 크기를 미리 제한해 메모리 고갈을 막는다
MAX_TOTAL_ROWS = 5000  # fix round 1 (S1): total_count를 그대로 믿지 않고 상한을 둔다(식약처는 실제로 약 1,100건)
SAMPLE_FILE = Path(__file__).parent / "data" / "sample_recipes.json"
_IMAGE_HTTPS_HOSTS = {"www.foodsafetykorea.go.kr", "openapi.foodsafetykorea.go.kr"}  # fix round 1 (S2)
MAX_IMAGE_URL = 500


def _short(value, limit):
    value = value.strip() if isinstance(value, str) else ""
    return value[:limit] or None


def _image_url(value):
    """식약처 이미지 주소만 https로 정리한다. 그 외 호스트·스킴은 안전하지 않다고 보고 버린다(None)."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme == "http" and parsed.hostname in _IMAGE_HTTPS_HOSTS:
        parsed = parsed._replace(scheme="https")
    if parsed.scheme != "https" or not parsed.netloc:
        return None
    return urlunparse(parsed)[:MAX_IMAGE_URL] or None


def _kcal(value):
    try:
        kcal = float(value)
    except (TypeError, ValueError):
        return None
    return kcal if math.isfinite(kcal) else None


def row_fields(row):
    """COOKRCP01 한 행 → PublicRecipe 필드."""
    title = _short(row.get("RCP_NM"), 120) or "이름 없는 레시피"
    parts = row.get("RCP_PARTS_DTLS") if isinstance(row.get("RCP_PARTS_DTLS"), str) else ""
    ingredients = parse_ingredients(parts, title)
    return {
        "rcp_seq": str(row["RCP_SEQ"]).strip()[:20],
        "title": title,
        "category": _short(row.get("RCP_PAT2"), 30),
        "method": _short(row.get("RCP_WAY2"), 30),
        "kcal": _kcal(row.get("INFO_ENG")),
        "servings": parse_servings(parts),
        "ingredients_text": parts,
        "ingredients": ingredients,
        "ingredient_keys": [ingredient_key(i["name"]) for i in ingredients],
        "steps": split_steps(row),
        "image_url": _image_url(row.get("ATT_FILE_NO_MAIN")),
        "is_sample": False,
    }


def sample_fields(item):
    """sample_recipes.json 한 항목 → PublicRecipe 필드."""
    ingredients = item["ingredients"]
    return {
        "rcp_seq": item["rcp_seq"],
        "title": item["title"],
        "category": item["category"],
        "method": item["method"],
        "kcal": None,
        "servings": item["servings"],
        "ingredients_text": ", ".join(f"{i['name']} {i['amount']}" for i in ingredients),
        "ingredients": ingredients,
        "ingredient_keys": [ingredient_key(i["name"]) for i in ingredients],
        "steps": item["steps"],
        "image_url": None,
        "is_sample": True,
    }


def upsert(items):
    """rcp_seq 기준으로 넣거나 바꾼다. (새로 넣은 수, 바꾼 수)"""
    by_seq = {r.rcp_seq: r for r in PublicRecipe.query.all()}
    created = updated = 0
    for fields in items:
        recipe = by_seq.get(fields["rcp_seq"])
        if recipe is None:
            by_seq[fields["rcp_seq"]] = recipe = PublicRecipe(**fields)
            db.session.add(recipe)
            created += 1
        else:
            for key, value in fields.items():
                setattr(recipe, key, value)
            updated += 1
    db.session.commit()
    return created, updated


def fetch_rows(key):
    """전체 행을 PAGE_SIZE씩 받는다. 한 페이지라도 실패하면 아무것도 쓰지 않고 멈춘다.
    fix round 1 (S1): 응답은 스트리밍으로 읽어 MAX_RESPONSE_BYTES를 넘으면 즉시 그만두고,
    total_count는 MAX_TOTAL_ROWS로 상한을 둔다(악의적이거나 잘못된 응답이 무한정 페이지를 돌게 하지 않는다)."""
    rows, start, total = [], 1, None
    while total is None or start <= total:
        end = start + PAGE_SIZE - 1
        try:
            res = requests.get(API_URL.format(key=key, start=start, end=end), timeout=30, stream=True)
            res.raise_for_status()
            data = res.raw.read(MAX_RESPONSE_BYTES + 1, decode_content=True)
            if len(data) > MAX_RESPONSE_BYTES:
                raise click.ClickException("식약처 응답이 예상보다 커요. 잠시 후 다시 시도해주세요.")
            body = json.loads(data)["COOKRCP01"]
            code = body["RESULT"]["CODE"]
            page = body.get("row") or []
            total = min(int(body.get("total_count") or 0), MAX_TOTAL_ROWS)
        except click.ClickException:
            raise
        except (requests.RequestException, ValueError, KeyError, TypeError) as e:
            # 요청 URL에 인증키가 들어 있으니 예외 내용은 찍지 않는다
            raise click.ClickException(f"식약처 레시피를 받지 못했어요({start}~{end}번, {type(e).__name__}).")
        if code == "INFO-200":  # 해당하는 데이터가 없음
            break
        if code != "INFO-000":
            raise click.ClickException(f"식약처 API가 오류를 돌려줬어요({code}).")
        if not page:
            break
        rows.extend(page)
        start = end + 1
    return rows


@bp.cli.command("sync-public-recipes")
def sync_public_recipes():
    """식약처 COOKRCP01 레시피 전체를 받아 public_recipes에 넣는다."""
    key = current_app.config["FOODSAFETY_API_KEY"]
    if not key:
        raise click.ClickException(
            "FOODSAFETY_API_KEY가 없어요. 키 없이 화면을 확인하려면 flask seed-sample-recipes로 예시 레시피를 넣어주세요."
        )
    items = [row_fields(r) for r in fetch_rows(key) if isinstance(r, dict) and str(r.get("RCP_SEQ") or "").strip()]
    # 진짜 레시피를 받았으면 예시 레시피는 지운다(내 레시피로 저장한 복사본은 public_recipe_id만 비워진다)
    removed = PublicRecipe.query.filter_by(is_sample=True).delete() if items else 0
    created, updated = upsert(items)
    click.echo(f"식약처 레시피 {len(items)}건을 받았어요. 새로 {created}건, 바뀐 것 {updated}건, 예시 레시피 {removed}건은 지웠어요.")


@bp.cli.command("seed-sample-recipes")
def seed_sample_recipes():
    """키 없이 추천 화면을 확인하는 예시 레시피 12개를 넣는다(여러 번 실행해도 같다)."""
    items = [sample_fields(item) for item in json.loads(SAMPLE_FILE.read_text(encoding="utf-8"))]
    created, updated = upsert(items)
    click.echo(f"예시 레시피 {len(items)}개를 넣었어요. 새로 {created}개, 바뀐 것 {updated}개.")
