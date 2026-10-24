"""Guardrail engine: a pure function over a proposed order and its context.

The LLM proposes products; this module alone decides whether a purchase may
happen. Platform rules can never be overridden by an approval.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from app.clock import in_window

PLATFORM_ORDER_CAP = Decimal("1000.00")
AUTO_APPROVE_CAP = Decimal("100.00")
WEEKLY_CAP = Decimal("15000.00")
DAILY_STEP_UP = Decimal("300.00")
MAX_ORDERS_PER_HOUR = 3
RADIUS_MILES = 10.0

_MEDICINE = re.compile(
    r"\b(medicines?|medications?|prescriptions?|rx|pills?|tablets?|capsules?|antibiotics?|"
    r"ibuprofen|acetaminophen|paracetamol|aspirin|advil|tylenol|motrin|aleve|naproxen|"
    r"benadryl|claritin|zyrtec|nyquil|dayquil|cough syrup|insulin|painkillers?|pain relievers?)\b",
    re.IGNORECASE,
)
_FINANCIAL = re.compile(
    r"\b(credit card (bill|payment)s?|card bill|emis?|installments?|instalments?|"
    r"loan (payment|repayment)s?|bnpl|buy now,? pay later|afterpay|klarna|affirm|"
    r"bill payments?|pay (my|the) .*bill)\b",
    re.IGNORECASE,
)


def restricted_reason(text: str, category: str | None = None) -> str | None:
    """Platform category block (PRD section 4 exclusions). Deterministic; the LLM may only add blocks."""
    if category == "medicine" or _MEDICINE.search(text):
        return (
            "Medicines can't be purchased by the assistant. All medicines are blocked "
            "until prescription verification exists."
        )
    if _FINANCIAL.search(text):
        return (
            "Credit card bills, EMIs, and installment or buy-now-pay-later payments "
            "aren't supported."
        )
    return None


class Outcome(StrEnum):
    ALLOW = "allow"
    NEEDS_APPROVAL = "needs_approval"
    DEFER = "defer"
    BLOCK = "block"


@dataclass(frozen=True)
class Reason:
    code: str
    layer: str  # "platform" or "user"
    effect: Outcome
    message: str


@dataclass(frozen=True)
class Quote:
    subtotal: Decimal
    tax: Decimal
    delivery_fee: Decimal
    service_fee: Decimal
    final: bool = True

    @property
    def total(self) -> Decimal:
        return self.subtotal + self.tax + self.delivery_fee + self.service_fee


@dataclass(frozen=True)
class Line:
    item_text: str
    item_category: str
    product_text: str
    product_category: str
    unit_price: Decimal
    quantity: int
    item_max_price: Decimal | None = None
    is_substitution: bool = False
    substitution_pref: str = "approval"  # allow / prohibit / approval
    spec_mismatches: tuple[str, ...] = ()


@dataclass(frozen=True)
class Proposal:
    """One cart at one store."""

    lines: tuple[Line, ...]
    quote: Quote
    store_distance_mi: float
    store_verified: bool


@dataclass(frozen=True)
class Context:
    now_local: datetime
    paused: bool
    order_limit: Decimal
    weekly_budget: Decimal
    max_delivery_fee: Decimal
    week_spent: Decimal
    day_spent: Decimal
    orders_last_hour: int
    permitted_days: tuple[int, ...] = tuple(range(7))
    always_approve_categories: tuple[str, ...] = ()
    wallet_balance: Decimal | None = None  # None when paying by card


@dataclass
class Decision:
    outcome: Outcome
    reasons: list[Reason] = field(default_factory=list)

    @property
    def approval_reasons(self) -> list[Reason]:
        return [r for r in self.reasons if r.effect is Outcome.NEEDS_APPROVAL]


def _money(v: Decimal) -> str:
    return f"${v:,.2f}"


def evaluate(p: Proposal, ctx: Context, has_valid_approval: bool = False) -> Decision:
    """Block beats defer beats approval. A valid approval only waives approval reasons."""
    total = p.quote.total
    r: list[Reason] = []

    def add(code: str, layer: str, effect: Outcome, message: str) -> None:
        r.append(Reason(code, layer, effect, message))

    # Platform restrictions: approval can never bypass these.
    for ln in p.lines:
        blocked = restricted_reason(ln.item_text, ln.item_category) or restricted_reason(
            ln.product_text, ln.product_category
        )
        if blocked:
            add("restricted_category", "platform", Outcome.BLOCK, f"{ln.item_text}: {blocked}")
    if not p.quote.final:
        add("unconfirmed_charges", "platform", Outcome.BLOCK,
            "The final charges couldn't be confirmed, so the order can't proceed automatically.")
    if total > PLATFORM_ORDER_CAP:
        add("order_cap", "platform", Outcome.BLOCK,
            f"The order total of {_money(total)} is over the {_money(PLATFORM_ORDER_CAP)} platform limit "
            "per order. This can't be approved.")
    if ctx.week_spent + total > WEEKLY_CAP:
        add("weekly_cap", "platform", Outcome.BLOCK,
            f"This would take weekly spending past the {_money(WEEKLY_CAP)} platform limit.")
    if p.store_distance_mi > RADIUS_MILES:
        add("radius", "platform", Outcome.BLOCK,
            f"The store is {p.store_distance_mi:.1f} mi away, outside the {RADIUS_MILES:.0f}-mile radius.")
    if not p.store_verified:
        add("unverified_store", "platform", Outcome.BLOCK, "The store's location couldn't be verified.")

    if ctx.paused:
        add("paused", "platform", Outcome.DEFER, "Shopping is paused.")
    if not in_window(ctx.now_local):
        add("window", "platform", Outcome.DEFER,
            "Orders can only be placed between 10:00 a.m. and 5:00 p.m. local time.")
    if ctx.orders_last_hour >= MAX_ORDERS_PER_HOUR:
        add("velocity", "platform", Outcome.DEFER,
            f"At most {MAX_ORDERS_PER_HOUR} automatic orders can be placed per hour.")
    if ctx.wallet_balance is not None and total > ctx.wallet_balance:
        add("insufficient_funds", "platform", Outcome.DEFER,
            f"Your wallet has {_money(ctx.wallet_balance)}, but this order needs {_money(total)}. "
            "Add funds to continue.")

    if total > AUTO_APPROVE_CAP:
        add("step_up", "platform", Outcome.NEEDS_APPROVAL,
            f"Orders over {_money(AUTO_APPROVE_CAP)} need your confirmation.")
    if ctx.day_spent + total > DAILY_STEP_UP:
        add("daily_step_up", "platform", Outcome.NEEDS_APPROVAL,
            f"This would take today's spending past {_money(DAILY_STEP_UP)}, which needs your confirmation.")

    # User-defined guardrails: exceeding them asks for approval.
    if ctx.now_local.weekday() not in ctx.permitted_days:
        add("permitted_day", "user", Outcome.DEFER, "You haven't allowed shopping on this day of the week.")
    if ctx.week_spent >= ctx.weekly_budget:
        add("budget_exhausted", "user", Outcome.BLOCK,
            f"Your weekly budget of {_money(ctx.weekly_budget)} is already used up "
            f"({_money(ctx.week_spent)} spent). Raise the budget to continue.")
    elif ctx.week_spent + total > ctx.weekly_budget:
        add("weekly_budget", "user", Outcome.NEEDS_APPROVAL,
            f"This would take you to {_money(ctx.week_spent + total)}, over your weekly budget of "
            f"{_money(ctx.weekly_budget)}.")
    if total > ctx.order_limit:
        add("order_limit", "user", Outcome.NEEDS_APPROVAL,
            f"The order total of {_money(total)} is over your {_money(ctx.order_limit)} limit per order.")
    if p.quote.delivery_fee > ctx.max_delivery_fee:
        add("delivery_fee", "user", Outcome.NEEDS_APPROVAL,
            f"The delivery fee of {_money(p.quote.delivery_fee)} is over your maximum of "
            f"{_money(ctx.max_delivery_fee)}.")
    for ln in p.lines:
        name = ln.item_text
        if ln.item_max_price is not None and ln.unit_price > ln.item_max_price:
            add("item_max_price", "user", Outcome.NEEDS_APPROVAL,
                f"{name}: the price of {_money(ln.unit_price)} is over your maximum of {_money(ln.item_max_price)}.")
        if ln.item_category in ctx.always_approve_categories:
            add("category_approval", "user", Outcome.NEEDS_APPROVAL,
                f"{name}: you asked to approve every {ln.item_category} purchase.")
        if ln.is_substitution:
            if ln.substitution_pref == "prohibit":
                add("substitution_prohibited", "user", Outcome.BLOCK,
                    f"{name}: your preferred product isn't available, and substitutions are turned off.")
            elif ln.substitution_pref == "approval":
                add("substitution", "user", Outcome.NEEDS_APPROVAL,
                    f"{name}: your preferred product isn't available. This is a substitute ({ln.product_text}).")
        if ln.spec_mismatches:
            add("spec_mismatch", "user", Outcome.NEEDS_APPROVAL,
                f"{name}: doesn't fully match your requirements ({'; '.join(ln.spec_mismatches)}).")

    effects = {x.effect for x in r}
    if Outcome.BLOCK in effects:
        outcome = Outcome.BLOCK
    elif Outcome.DEFER in effects:
        outcome = Outcome.DEFER
    elif Outcome.NEEDS_APPROVAL in effects and not has_valid_approval:
        outcome = Outcome.NEEDS_APPROVAL
    else:
        outcome = Outcome.ALLOW
    return Decision(outcome, r)
