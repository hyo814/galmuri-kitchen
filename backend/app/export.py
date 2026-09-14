"""데이터 내보내기(스펙 27절): 재고·내 레시피·내 양념 비율을 CSV 세 개로 묶은 zip. 하루(서울) 5번까지."""

import csv
import io
import zipfile
import zlib

from flask import Blueprint, Response, abort, g, jsonify
from sqlalchemy import text
from sqlalchemy.orm import joinedload

from . import scan
from .auth import login_required
from .ingredients import seoul_today
from .models import AiCall, Ingredient, Recipe, Seasoning, db

bp = Blueprint("export", __name__, url_prefix="/api/export")

DAILY_LIMIT = 5
KINDS = ("export",)  # ai_calls 기록(모델·토큰 없음). AI 한도·사용량에는 세지 않는다
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")
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


def safe(value):
    """엑셀이 수식으로 읽지 않도록 = + - @ 탭 CR로 시작하는 글자 칸 앞에 '를 붙인다(CSV injection)."""
    return "'" + value if isinstance(value, str) and value.startswith(FORMULA_STARTS) else value


def number(value):
    """1.0 → 1, 0.6666… → 0.67 (화면처럼 읽기 쉽게)"""
    value = round(float(value), 2)
    return int(value) if value.is_integer() else value


def csv_bytes(header, rows):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerows([safe(cell) for cell in row] for row in rows)
    return buf.getvalue().encode("utf-8-sig")  # BOM: 엑셀이 UTF-8 한글을 알아본다


def owned(model):
    return model.query.filter_by(user_id=g.user.id)


def remaining():
    return max(0, DAILY_LIMIT - scan.calls_today(g.user.id, KINDS))


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
    # GET이라 X-Requested-With 확인은 다른 GET API처럼 하지 않는다(화면이 링크로 내려받을 수 있게).
    if db.session.get_bind().dialect.name == "postgresql":  # scan.check_ai_limits와 같은 사용자별 잠금
        db.session.execute(
            text("SELECT pg_advisory_xact_lock(:group_key, :user_id)"),
            {"group_key": zlib.crc32(",".join(KINDS).encode()) & 0x7FFFFFFF, "user_id": g.user.id},
        )
    # ponytail: SQLite(개발용)는 잠그지 않는다 — 동시에 보내면 한도를 조금 넘을 수 있다.
    if remaining() <= 0:
        abort(429, f"오늘 내보내기는 {DAILY_LIMIT}번까지 할 수 있어요. 내일 다시 해주세요.")
    db.session.add(AiCall(user_id=g.user.id, kind="export", model=None, created_at=scan.utcnow()))
    db.session.commit()

    # ponytail: 전부 메모리에서 만든다. 상한은 재료 2000개·레시피 1000개(재료 50·단계 30×500자)·양념 100개로
    # 최악 수십 MB. 사용자 데이터 상한을 크게 올리면 임시 파일·스트리밍으로 바꾼다.
    ingredients = owned(Ingredient).options(joinedload(Ingredient.location)).order_by(Ingredient.purchased_on, Ingredient.id)
    recipes = owned(Recipe).order_by(Recipe.updated_at.desc(), Recipe.id.desc())
    seasonings = owned(Seasoning).order_by(Seasoning.id)
    files = {
        "ingredients.csv": csv_bytes(
            ["이름", "수량", "단위", "보관 위치", "구입일", "유통기한", "가격(원)"],
            (
                [i.name, number(i.quantity), i.unit, i.location.name, i.purchased_on, i.expires_on or "", "" if i.price is None else i.price]
                for i in ingredients
            ),
        ),
        "recipes.csv": csv_bytes(
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
        ),
        "seasonings.csv": csv_bytes(
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
        ),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    filename = f"galmuri-kitchen-{seoul_today():%Y%m%d}.zip"
    return Response(buf.getvalue(), mimetype="application/zip", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
