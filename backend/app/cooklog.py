"""요리 일기(스펙 29절). 요리했어요 초안·저장·되돌리기·목록·상세. 쓴 재료는 저장할 때 스냅숏(결정 1·7·8)."""

import math

from flask import Blueprint, g, jsonify

from .amounts import SPOON_UNITS, in_unit, parse_amount
from .auth import get_owned_or_404, login_required
from .ingredients import seasoning_names
from .matching import match_prepared, names_match, normalize, prepare
from .models import Recipe
from .nutrition import TRACE_WORDS
from .recipe_parse import ingredient_key
from .recipes import ALWAYS_HAVE, inventory_rows

bp = Blueprint("cooklog", __name__, url_prefix="/api")

SEASONING_SPOONS = SPOON_UNITS - {"컵"}  # 결정 5: 컵은 밀가루·쌀처럼 많이 쓰는 양이라 양념으로 보지 않는다


def is_seasoning(key, amount, staples):
    """결정 5. key는 ingredient_key(재료 이름), staples는 seasoning_names(user_id)."""
    if any(names_match(key, s) for s in staples):
        return True
    text = (amount or "").strip()
    if text in TRACE_WORDS:
        return True
    parsed = parse_amount(text)
    return parsed is not None and parsed[1].lower() in SEASONING_SPOONS


def round_won(value, step=10):
    """0.5는 올린다(파이썬 round의 짝수 반올림을 쓰지 않는다). 음수는 쓰지 않는다."""
    return int(math.floor(value / step + 0.5)) * step


def item_cost(used, price, price_quantity):
    """결정 10·13. 구입 가격 × min(쓴 양 ÷ 구입 수량, 1), 10원 단위. 가격·구입 수량이 없으면 None."""
    if price is None or not price_quantity:
        return None
    return round_won(price * min(used / price_quantity, 1))


def _get(item, key):
    return item.get(key) if isinstance(item, dict) else getattr(item, key, None)


def summarize(eat_out_price, servings, items):
    """items: excluded·cost 속성(또는 키)을 가진 줄. 결정 13·14.
    → {"ingredient_cost": 가격 있는 줄 cost 합, "saved": 사 먹으면 × 인분 − 재료비 | None, "excluded_count": excluded == 'no_price' 수}"""
    costs = [cost for cost in (_get(item, "cost") for item in items) if cost is not None]
    total = sum(costs)
    return {
        "ingredient_cost": total,
        "saved": eat_out_price * servings - total if eat_out_price is not None and costs else None,
        "excluded_count": sum(1 for item in items if _get(item, "excluded") == "no_price"),
    }


def draft_rows(recipe, user_id):
    """결정 4·5. 레시피 재료 → [{name, amount, ingredient_id, stock_name, stock_quantity, stock_unit, base_amount, seasoning}].
    재고 순서는 recipes.inventory_rows(user_id)를 그대로 쓴다(따로 정렬하지 않는다, 개정 1 P18).
    물(normalize(key) in ALWAYS_HAVE)은 뺀다. 재고 한 행은 먼저 맞은 재료 하나에만."""
    staples = seasoning_names(user_id)
    stock = [(item, prepare(item.name)) for item, _ in inventory_rows(user_id)]
    rows = []
    for ingredient in recipe.ingredients:
        key, amount = ingredient_key(ingredient["name"]), ingredient["amount"]
        if normalize(key) in ALWAYS_HAVE:
            continue
        key_prepared = prepare(key)
        index = next((n for n, (_, prepared) in enumerate(stock) if match_prepared(key_prepared, prepared)), None)
        item = stock.pop(index)[0] if index is not None else None
        rows.append({
            "name": ingredient["name"],
            "amount": amount,
            "ingredient_id": item.id if item else None,
            "stock_name": item.name if item else None,
            "stock_quantity": item.quantity if item else None,
            "stock_unit": item.unit if item else None,
            "base_amount": in_unit(amount, item.unit) if item else None,
            "seasoning": is_seasoning(key, amount, staples),
        })
    return rows


@bp.get("/recipes/<int:recipe_id>/cook-draft")
@login_required
def cook_draft(recipe_id):
    recipe = get_owned_or_404(Recipe, recipe_id)
    res = jsonify({
        "recipe_id": recipe.id,
        "title": recipe.title,
        "servings": recipe.servings,
        "eat_out_price": recipe.eat_out_price,
        "eat_out_source": recipe.eat_out_source,
        "rows": draft_rows(recipe, g.user.id),
    })
    res.headers["Cache-Control"] = "no-store"  # 식습관·지출 정보
    return res
