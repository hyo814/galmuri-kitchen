"""데이터 내보내기(스펙 27절): 재고·내 레시피·내 양념 비율을 CSV 세 개로 묶은 zip. 하루(서울) 5번까지."""

import csv
import io
import tempfile
import zipfile
import zlib

from flask import Blueprint, abort, g, jsonify, request, send_file
from sqlalchemy import text
from sqlalchemy.orm import joinedload

from . import scan
from .auth import login_required
from .ingredients import seoul_today
from .models import AiCall, Ingredient, Recipe, Seasoning, db

bp = Blueprint("export", __name__, url_prefix="/api/export")

DAILY_LIMIT = 5
KINDS = ("export",)  # ai_calls 기록(모델·토큰 없음). AI 한도·사용량에는 세지 않는다
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r", "＝", "＋", "－", "＠")
SOURCE_LABELS = {  # 화면 format.ts의 SOURCE_LABEL과 같게(화면은 mine을 비워 두지만 CSV는 칸이 비지 않게 이름을 붙인다)
    "mine": "직접 입력",
    "public": "추천에서 저장",
    "ai": "AI가 만든 레시피",
    "youtube": "유튜브에서 가져옴",
    "instagram": "인스타그램에서 가져옴",
    "blog": "블로그에서 가져옴",
    "text": "붙여넣은 글에서 가져옴",
}
BASIS_LABELS = {"main_weight": "주재료 무게", "servings": "인분", "yield": "완성량"}
SPOOL_BYTES = 5_000_000  # 이보다 크면 메모리 대신 임시 파일에 zip을 만든다
BATCH = 200


@bp.before_request
def require_fetch_header():
    # 내려받기는 하루 한도를 쓰므로 GET이어도 다른 사이트의 링크로 부를 수 없게 한다(__init__.require_fetch_header와 같은 헤더).
    if request.headers.get("X-Requested-With") != "fetch":
        abort(400, "잘못된 요청이에요.")


def safe(value):
    """엑셀이 수식으로 읽지 않도록 = + - @ 탭 CR(전각 포함)로 시작하는 글자 칸 앞에 '를 붙인다(CSV injection). 앞 공백은 건너뛰고도 본다."""
    if isinstance(value, str) and (value.startswith(FORMULA_STARTS) or value.lstrip().startswith(FORMULA_STARTS)):
        return "'" + value
    return value


def number(value):
    """1.0 → 1, 나머지는 그대로(csv가 가장 짧은 표현으로 쓴다)."""
    return int(value) if float(value).is_integer() else float(value)


def write_csv(archive, name, header, rows):
    with io.TextIOWrapper(archive.open(name, "w"), encoding="utf-8-sig", newline="") as out:  # BOM: 엑셀이 UTF-8 한글을 알아본다
        writer = csv.writer(out)
        writer.writerow(header)
        for row in rows:
            writer.writerow([safe(cell) for cell in row])


def owned(model):
    return model.query.filter_by(user_id=g.user.id)


def remaining(day=None):
    return max(0, DAILY_LIMIT - scan.calls_today(g.user.id, KINDS, day))


@bp.get("/summary")
@login_required
def summary():
    return jsonify(
        ingredients=owned(Ingredient).count(),
        recipes=owned(Recipe).count(),
        seasonings=owned(Seasoning).count(),
        limit=DAILY_LIMIT,
        remaining=remaining(),
    )


@bp.get("")
@login_required
def export():
    if db.session.get_bind().dialect.name == "postgresql":  # scan.check_ai_limits와 같은 사용자별 잠금
        db.session.execute(
            text("SELECT pg_advisory_xact_lock(:group_key, :user_id)"),
            {"group_key": zlib.crc32(",".join(KINDS).encode()) & 0x7FFFFFFF, "user_id": g.user.id},
        )
    # ponytail: SQLite(개발용)는 잠그지 않는다 — 동시에 보내면 한도를 조금 넘을 수 있다.
    today = seoul_today()
    if remaining(today) <= 0:
        abort(429, f"오늘 내보내기는 {DAILY_LIMIT}번까지 할 수 있어요. 내일 다시 해주세요.")
    # ponytail: 만들기 전에 기록하고 커밋한다(잠금 해제) — 만들다 오류가 나도 한 번 쓴 것으로 센다. 잦으면 실패 때 기록을 지운다.
    db.session.add(AiCall(user_id=g.user.id, kind="export", model=None, created_at=scan.utcnow()))
    db.session.commit()

    # ponytail: 행은 BATCH개씩 읽고 zip은 SPOOL_BYTES를 넘으면 임시 파일로 넘긴다. 상한은 재료 2000개·레시피 1000개
    # (재료 50·단계 30×500자)·양념 100개라 최악 수십 MB. 상한을 크게 올리면 비동기 작업·저장소 링크로 바꾼다.
    ingredients = (
        owned(Ingredient).options(joinedload(Ingredient.location)).order_by(Ingredient.purchased_on, Ingredient.id).yield_per(BATCH)
    )
    recipes = owned(Recipe).order_by(Recipe.updated_at.desc(), Recipe.id.desc()).yield_per(BATCH)
    seasonings = owned(Seasoning).order_by(Seasoning.id).yield_per(BATCH)
    spool = tempfile.SpooledTemporaryFile(max_size=SPOOL_BYTES)
    with zipfile.ZipFile(spool, "w", zipfile.ZIP_DEFLATED) as archive:
        write_csv(
            archive,
            "ingredients.csv",
            ["이름", "수량", "단위", "보관 위치", "구입일", "유통기한", "가격(원)"],
            (
                [i.name, number(i.quantity), i.unit, i.location.name, i.purchased_on, i.expires_on or "", "" if i.price is None else i.price]
                for i in ingredients
            ),
        )
        write_csv(
            archive,
            "recipes.csv",
            ["제목", "인분", "재료", "만드는 법", "출처", "출처 링크", "사진 주소"],
            (
                [
                    r.title,
                    r.servings,
                    "; ".join(f"{x['name']} {x['amount']}".strip() for x in r.ingredients),
                    "\n".join(f"{n}. {step}" for n, step in enumerate(r.steps, 1)),  # 따옴표로 감싼 칸 안 줄바꿈(엑셀이 한 칸으로 읽는다)
                    SOURCE_LABELS.get(r.source, r.source),
                    r.source_url or "",
                    r.image_url or "",
                ]
                for r in recipes
            ),
        )
        write_csv(
            archive,
            "seasonings.csv",
            ["이름", "기준", "기준 양", "기준 단위", "주재료", "양념"],
            (
                [
                    s.name,
                    BASIS_LABELS.get(s.basis, s.basis),
                    number(s.basis_amount),
                    s.basis_unit,
                    s.main_ingredient or "",
                    "; ".join(f"{x['name']} {number(x['amount'])}{x['unit']}" for x in s.items),
                ]
                for s in seasonings
            ),
        )
    spool.seek(0)
    filename = f"galmuri-kitchen-{today:%Y%m%d}.zip"
    res = send_file(spool, mimetype="application/zip", as_attachment=True, download_name=filename)
    res.headers["Content-Disposition"] = f'attachment; filename="{filename}"'  # 화면과 맞춘 따옴표 형식(send_file은 따옴표를 뺀다)
    res.headers["Cache-Control"] = "no-store"
    res.headers["X-Content-Type-Options"] = "nosniff"
    return res
