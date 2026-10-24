"""Shopping agent: clarifying questions and product choice.

Uses Claude when ANTHROPIC_API_KEY is set, otherwise (or on any failure) simple
keyword rules. Claude only sees catalog data, never card data, and its output is
advisory: guardrails.evaluate() makes every purchase decision.
"""

import json
import logging
from decimal import Decimal

import anthropic
from pydantic import BaseModel

from app.config import settings

log = logging.getLogger(__name__)


class Clarification(BaseModel):
    needs_clarification: bool
    question: str
    restricted: bool
    restricted_reason: str
    brand: str | None
    color: str | None
    size: str | None


class ProductChoice(BaseModel):
    product_id: int | None
    reason: str
    is_substitution: bool
    mismatches: list[str]


CLARIFY_SYSTEM = """You help an older adult maintain a weekly shopping list that an assistant buys from automatically.
Given one list item and the matching products the stores carry, decide whether the item is clear enough to buy.

- Routine groceries and household basics: don't ask. A sensible default is fine.
- Ask one short, friendly question only when a wrong pick would clearly be unwanted, such as the color or style of
  decor or furniture when the options differ, or when the item is too vague to identify.
- Use the item's notes, which may contain earlier answers, to fill in brand, color, and size. Only fill a field
  when the user stated it; use the catalog's spelling (for example "brass").
- Set restricted to true only for medicines or health treatments, bill payments, loans, EMIs, or
  buy-now-pay-later plans. Otherwise false with an empty reason.
- question must be empty when needs_clarification is false."""

CHOOSE_SYSTEM = """You pick the product to buy for one shopping list item from candidate products at nearby stores.
Rules:
- Only choose from the candidates given. Return product_id null if none is a reasonable match.
- Prefer exact matches on the user's brand, color, and size. If the brand they asked for isn't among the
  candidates, a close equivalent is a substitution: set is_substitution true.
- List any requirement the chosen product doesn't meet in mismatches (for example "color is white, you asked
  for black"). Leave it empty for a full match.
- Among equally good matches, prefer lower total cost. A store already in the cart adds no extra delivery or
  service fee.
- Don't consider budgets, limits, or whether purchase is allowed. Separate code decides that.
- reason: one short sentence a user would understand."""


def _claude(system: str, user: dict, schema: type[BaseModel]) -> BaseModel:
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=45, max_retries=1)
    resp = client.beta.messages.parse(
        model=settings.claude_model,
        max_tokens=4000,
        system=system,
        messages=[{"role": "user", "content": json.dumps(user, default=str)}],
        output_format=schema,
        output_config={"effort": "low"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        raise RuntimeError(f"Claude returned no usable output (stop_reason={resp.stop_reason})")
    return resp.parsed_output


def ai_enabled() -> bool:
    return bool(settings.anthropic_api_key)


def _item_view(item) -> dict:
    return {
        "name": item.name, "category": item.category, "quantity": item.quantity, "brand": item.brand,
        "color": item.color, "size": item.size, "notes": item.notes,
        "max_price": str(item.max_price) if item.max_price is not None else None,
    }


def clarify(item, options: list[dict]) -> tuple[Clarification, str]:
    if ai_enabled():
        try:
            out = _claude(CLARIFY_SYSTEM, {"item": _item_view(item), "catalog_options": options[:25]}, Clarification)
            return out, "ai"
        except Exception:
            log.exception("clarify: falling back to rules")
    return _clarify_rules(item, options), "rules"


def _clarify_rules(item, options: list[dict]) -> Clarification:
    colors = sorted({o["color"] for o in options if o.get("color")})
    color = item.color
    if not color:
        # Only the user's own words count: answer lines, not the questions we asked.
        said = " ".join(ln[2:] for ln in (item.notes or "").splitlines() if ln.startswith("A:")).lower()
        color = next((c for c in colors if c.lower() in said), None)
    ask = item.category in ("lifestyle", "furniture") and not color and len(colors) > 1
    return Clarification(
        needs_clarification=ask,
        question=f"What color would you like for the {item.name.lower()}? Options include {', '.join(colors)}." if ask else "",
        restricted=False, restricted_reason="",
        brand=item.brand, color=color, size=item.size,
    )


def choose(item, candidates: list[dict], stores_in_cart: list[int]) -> tuple[ProductChoice, str]:
    in_stock = [c for c in candidates if c["in_stock"]]
    if not in_stock:
        return ProductChoice(product_id=None, reason="No matching product is in stock nearby.",
                             is_substitution=False, mismatches=[]), "rules"
    if ai_enabled():
        try:
            out = _claude(CHOOSE_SYSTEM, {"item": _item_view(item), "candidates": in_stock,
                                          "store_ids_already_in_cart": stores_in_cart}, ProductChoice)
            if out.product_id is None or any(c["product_id"] == out.product_id for c in in_stock):
                return out, "ai"
            log.warning("choose: Claude picked a product outside the candidates; using rules")
        except Exception:
            log.exception("choose: falling back to rules")
    return _choose_rules(item, in_stock, stores_in_cart), "rules"


def _choose_rules(item, cands: list[dict], stores_in_cart: list[int]) -> ProductChoice:
    def eq(a, b):
        return bool(a) and bool(b) and a.strip().lower() == b.strip().lower()

    def cost(c):
        fees = Decimal(0) if c["store_id"] in stores_in_cart else Decimal(c["delivery_fee"]) + Decimal(c["service_fee"])
        return Decimal(c["price"]) * item.quantity + fees

    def misses(c):
        out = []
        if item.color and not eq(item.color, c["color"]):
            out.append(f"color is {c['color'] or 'unspecified'}, you asked for {item.color}")
        if item.size and not eq(item.size, c["size"]):
            out.append(f"size is {c['size'] or 'unspecified'}, you asked for {item.size}")
        return out

    def rank(c):
        brand_ok = not item.brand or eq(item.brand, c["brand"])
        return (not brand_ok, len(misses(c)), cost(c))

    best = min(cands, key=rank)
    sub = bool(item.brand) and not eq(item.brand, best["brand"])
    return ProductChoice(
        product_id=best["product_id"],
        reason=f"Best match at the lowest total cost: {best['name']} at {best['store']} ({best['distance_mi']} mi).",
        is_substitution=sub,
        mismatches=misses(best),
    )
