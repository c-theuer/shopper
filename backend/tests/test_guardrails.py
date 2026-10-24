from datetime import datetime
from decimal import Decimal as D
from zoneinfo import ZoneInfo

import pytest

from app.guardrails import Context, Line, Outcome, Proposal, Quote, evaluate, restricted_reason

TZ = ZoneInfo("America/Los_Angeles")
WED_1115 = datetime(2026, 10, 14, 11, 15, tzinfo=TZ)


def ctx(**kw) -> Context:
    base = dict(now_local=WED_1115, paused=False, order_limit=D("1000"), weekly_budget=D("15000"),
                max_delivery_fee=D("100"), week_spent=D("0"), day_spent=D("0"), orders_last_hour=0)
    return Context(**(base | kw))


def prop(total="50.00", distance=3.0, name="Milk", category="groceries", **line_kw) -> Proposal:
    line = Line(item_text=name, item_category=category, product_text=name, product_category=category,
                unit_price=D(total), quantity=1, **line_kw)
    return Proposal(lines=(line,), quote=Quote(D(total), D(0), D(0), D(0)), store_distance_mi=distance,
                    store_verified=True)


def codes(decision) -> set[str]:
    return {r.code for r in decision.reasons}


@pytest.mark.parametrize("total,outcome", [
    ("100.00", Outcome.ALLOW),
    ("100.01", Outcome.NEEDS_APPROVAL),
    ("1000.00", Outcome.NEEDS_APPROVAL),
    ("1000.01", Outcome.BLOCK),
])
def test_order_amount_tiers(total, outcome):
    d = evaluate(prop(total), ctx(day_spent=D("0")), has_valid_approval=False)
    assert d.outcome is outcome


def test_order_cap_includes_fees_and_survives_approval():
    p = Proposal(lines=prop("950").lines, quote=Quote(D("950"), D("40"), D("9"), D("2")), store_distance_mi=1,
                 store_verified=True)
    d = evaluate(p, ctx(), has_valid_approval=True)
    assert d.outcome is Outcome.BLOCK and "order_cap" in codes(d)


def test_user_limit_needs_approval_and_approval_waives_it():
    c = ctx(order_limit=D("200"))
    assert evaluate(prop("240"), c).outcome is Outcome.NEEDS_APPROVAL
    assert evaluate(prop("240"), c, has_valid_approval=True).outcome is Outcome.ALLOW


def test_user_example_from_prd():
    c = ctx(order_limit=D("200"))
    assert evaluate(prop("1050"), c, has_valid_approval=True).outcome is Outcome.BLOCK


def test_weekly_platform_cap():
    d = evaluate(prop("60"), ctx(week_spent=D("14950")), has_valid_approval=True)
    assert d.outcome is Outcome.BLOCK and "weekly_cap" in codes(d)


@pytest.mark.parametrize("distance,blocked", [(10.0, False), (10.01, True), (12.0, True)])
def test_radius(distance, blocked):
    assert ("radius" in codes(evaluate(prop(distance=distance), ctx()))) is blocked


@pytest.mark.parametrize("hh,mm,ss,deferred", [
    (9, 59, 59, True), (10, 0, 0, False), (16, 59, 59, False), (17, 0, 0, True), (17, 15, 0, True),
])
def test_shopping_window(hh, mm, ss, deferred):
    now = WED_1115.replace(hour=hh, minute=mm, second=ss)
    d = evaluate(prop(), ctx(now_local=now))
    assert (d.outcome is Outcome.DEFER) is deferred


def test_window_still_applies_after_approval():
    d = evaluate(prop("240"), ctx(now_local=WED_1115.replace(hour=17, minute=15)), has_valid_approval=True)
    assert d.outcome is Outcome.DEFER


def test_velocity_fourth_order_in_hour_deferred():
    assert evaluate(prop(), ctx(orders_last_hour=2)).outcome is Outcome.ALLOW
    assert evaluate(prop(), ctx(orders_last_hour=3)).outcome is Outcome.DEFER


def test_daily_step_up():
    assert evaluate(prop("60"), ctx(day_spent=D("240"))).outcome is Outcome.ALLOW
    d = evaluate(prop("60.01"), ctx(day_spent=D("240")))
    assert d.outcome is Outcome.NEEDS_APPROVAL and "daily_step_up" in codes(d)


def test_paused_defers():
    assert evaluate(prop(), ctx(paused=True)).outcome is Outcome.DEFER


def test_budget_lowered_below_spent_blocks():
    d = evaluate(prop("10"), ctx(weekly_budget=D("100"), week_spent=D("120")), has_valid_approval=True)
    assert d.outcome is Outcome.BLOCK and "budget_exhausted" in codes(d)


def test_item_max_price_and_spec_mismatch():
    d = evaluate(prop("30", item_max_price=D("25"), spec_mismatches=("color is white, you asked for black",)), ctx())
    assert d.outcome is Outcome.NEEDS_APPROVAL and {"item_max_price", "spec_mismatch"} <= codes(d)


@pytest.mark.parametrize("pref,outcome", [
    ("allow", Outcome.ALLOW), ("approval", Outcome.NEEDS_APPROVAL), ("prohibit", Outcome.BLOCK),
])
def test_substitution_preferences(pref, outcome):
    assert evaluate(prop(is_substitution=True, substitution_pref=pref), ctx()).outcome is outcome


@pytest.mark.parametrize("text", [
    "Ibuprofen", "Tylenol extra strength", "cough syrup", "Pay my credit card bill", "car loan EMI",
    "Afterpay installment",
])
def test_restricted_items(text):
    assert restricted_reason(text) is not None
    assert evaluate(prop(name=text), ctx(), has_valid_approval=True).outcome is Outcome.BLOCK


@pytest.mark.parametrize("text", ["Whole milk", "Dining chair", "Table lamp", "Paper towels"])
def test_ordinary_items_not_restricted(text):
    assert restricted_reason(text) is None


def test_permitted_days():
    assert evaluate(prop(), ctx(permitted_days=(0, 1))).outcome is Outcome.DEFER  # Wednesday not allowed


@pytest.mark.parametrize("balance,outcome", [
    ("50.00", Outcome.ALLOW),
    ("49.99", Outcome.DEFER),
])
def test_wallet_balance_must_cover_order(balance, outcome):
    d = evaluate(prop("50.00"), ctx(wallet_balance=D(balance)))
    assert d.outcome is outcome
    assert ("insufficient_funds" in codes(d)) is (outcome is Outcome.DEFER)


def test_card_payment_has_no_balance_rule():
    assert "insufficient_funds" not in codes(evaluate(prop("50.00"), ctx()))


def test_block_beats_insufficient_funds():
    d = evaluate(prop("20", name="Ibuprofen"), ctx(wallet_balance=D("0")))
    assert d.outcome is Outcome.BLOCK and "insufficient_funds" in codes(d)
