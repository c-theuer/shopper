"""One shopping run: plan carts from the latest list, check guardrails, then order, ask, defer, or block."""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import agent, catalog, clock, notify, wallet
from app.activity import log
from app.db import engine
from app.geo import miles_between
from app.guardrails import RADIUS_MILES, Context, Line, Outcome, Proposal, Quote, evaluate
from app.models import Approval, Card, ListItem, Order, OrderLine, Product, Settings, Store

PRIORITY = {"high": 0, "normal": 1, "low": 2}
TICK_LOCK = 4242
CENTS = Decimal("0.01")


@dataclass
class Planned:
    item: ListItem
    version: int
    product: Product
    is_substitution: bool = False
    mismatches: list[str] = field(default_factory=list)


@dataclass
class Result:
    placed: list[int] = field(default_factory=list)
    approvals: list[int] = field(default_factory=list)
    blocked: int = 0
    deferred: int = 0
    unavailable: int = 0
    note: str = ""


def run(db: Session) -> Result:
    """Single-flight via a Postgres advisory lock held on its own connection."""
    with engine.connect() as lock_conn:
        if not lock_conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": TICK_LOCK}).scalar():
            return Result(note="A shopping run is already in progress.")
        try:
            return _run(db)
        finally:
            lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": TICK_LOCK})


def _run(db: Session) -> Result:
    res = Result()
    cfg = db.get(Settings, 1)
    local = clock.now_local(db, cfg.timezone)
    _expire_approvals(db)

    # card stays None when paying from the wallet.
    card = None
    if cfg.payment_method != "wallet":
        card = db.scalars(select(Card).order_by(Card.id.desc()).limit(1)).first()
    if cfg.payment_method == "wallet" and wallet.bank(db) is None:
        res.note = "Link a bank account to your wallet before shopping can start."
    elif cfg.payment_method != "wallet" and card is None:
        res.note = "Add a test card in Settings before shopping can start."
    elif cfg.paused:
        res.note = "Shopping is paused."
    elif not clock.in_window(local):
        opens = clock.next_window_open(local)
        res.note = f"Outside shopping hours. Orders resume at {opens:%-I:%M %p} on {opens:%a}."
    if res.note:
        log(db, "run", res.note, dedupe=True)
        if notify.summary_due(db, cfg):
            notify.daily_summary(db, cfg)
        db.commit()
        return res

    log(db, "run", f"Shopping run started at {local:%-I:%M %p}.")
    for appr in db.scalars(select(Approval).where(Approval.status == "approved")).all():
        _run_approved(db, cfg, card, appr, res)

    carts: dict[int, list[Planned]] = {}
    for item in _ready_items(db, local.date()):
        planned = _plan_item(db, cfg, item, list(carts), res)
        if planned:
            carts.setdefault(planned.product.store_id, []).append(planned)
    for store_id, lines in carts.items():
        _commit_cart(db, cfg, card, db.get(Store, store_id), lines, None, res)

    db.commit()
    return res


def _ready_items(db: Session, today) -> list[ListItem]:
    items = db.scalars(select(ListItem).where(ListItem.deleted.is_(False), ListItem.status == "ready")).all()
    items = [i for i in items if i.deferred_until is None or i.deferred_until <= today]
    return sorted(items, key=lambda i: (PRIORITY.get(i.priority, 1), i.needed_by or today + timedelta(days=365), i.id))


def _expire_approvals(db: Session) -> None:
    now = clock.now_utc(db)
    for a in db.scalars(select(Approval).where(Approval.status == "pending", Approval.expires_at <= now)).all():
        a.status, a.status_reason = "expired", "No response before the request expired."
        for item_id in a.item_ids:
            item = db.get(ListItem, item_id)
            if item and item.status == "awaiting_approval":
                item.status = "blocked"
                item.status_reason = "The approval request expired, so nothing was bought. Edit the item to try again."
        log(db, "approval", f"Approval #{a.id} expired without a response, so nothing was bought.")


def _plan_item(db: Session, cfg: Settings, item: ListItem, stores_in_cart: list[int], res: Result) -> Planned | None:
    cands = catalog.search(db, item, cfg)
    near = [c for c in cands if c.distance_mi <= RADIUS_MILES]
    for far in {c.store.id: c for c in cands if c.distance_mi > RADIUS_MILES}.values():
        log(db, "skip", f"Skipped {far.store.name} for {item.name}: it's {far.distance_mi:.1f} mi away, "
            f"outside the {RADIUS_MILES:.0f}-mile radius.", item_id=item.id, dedupe=True)
    if not near:
        far = [c for c in cands if c.distance_mi > RADIUS_MILES]
        item.status = "unavailable"
        item.status_reason = "No store within 10 miles carries this." + (
            f" The nearest option is {far[0].distance_mi:.1f} mi away at {far[0].store.name}." if far else "")
        log(db, "unavailable", f"{item.name}: {item.status_reason}", item_id=item.id, dedupe=True)
        res.unavailable += 1
        return None

    choice, source = agent.choose(item, [c.as_dict() for c in near], stores_in_cart)
    pick = next((c for c in near if c.product.id == choice.product_id), None)
    if pick is None:
        item.status, item.status_reason = "unavailable", choice.reason
        log(db, "unavailable", f"{item.name}: {choice.reason}", item_id=item.id, source=source, dedupe=True)
        res.unavailable += 1
        return None
    log(db, "choose", f"{item.name}: picked {pick.product.name}"
        f"{f' ({pick.product.color})' if pick.product.color else ''} at {pick.store.name} "
        f"({pick.distance_mi:.1f} mi), ${pick.product.price}. {choice.reason}",
        item_id=item.id, source=source, details={"mismatches": choice.mismatches})
    return Planned(item, item.version, pick.product, choice.is_substitution, choice.mismatches)


def _quote(store: Store, lines: list[Planned]) -> Quote:
    subtotal = sum((p.product.price * p.item.quantity for p in lines), Decimal(0))
    tax = (subtotal * store.tax_rate).quantize(CENTS, ROUND_HALF_UP)
    return Quote(subtotal=subtotal, tax=tax, delivery_fee=store.delivery_fee, service_fee=store.service_fee)


def _snapshot(store: Store, lines: list[Planned], quote: Quote) -> str:
    key = [store.id, sorted((p.item.id, p.version, p.product.id, p.item.quantity, str(p.product.price)) for p in lines),
           str(quote.total)]
    return hashlib.sha256(json.dumps(key).encode()).hexdigest()


def _context(db: Session, cfg: Settings) -> Context:
    local = clock.now_local(db, cfg.timezone)
    hour_ago = clock.now_utc(db) - timedelta(hours=1)
    return Context(
        now_local=local, paused=cfg.paused, order_limit=cfg.order_limit, weekly_budget=cfg.weekly_budget,
        max_delivery_fee=cfg.max_delivery_fee,
        week_spent=notify.spent_since(db, clock.week_start(local)),
        day_spent=notify.spent_since(db, clock.day_start(local)),
        orders_last_hour=db.scalar(select(func.count(Order.id)).where(Order.committed_at >= hour_ago)) or 0,
        permitted_days=tuple(cfg.permitted_days), always_approve_categories=tuple(cfg.always_approve_categories),
        wallet_balance=wallet.balance(db) if cfg.payment_method == "wallet" else None,
    )


def _proposal(store: Store, lines: list[Planned], quote: Quote, cfg: Settings) -> Proposal:
    return Proposal(
        lines=tuple(Line(
            item_text=p.item.name, item_category=p.item.category,
            product_text=f"{p.product.name} {p.product.keywords}", product_category=p.product.category,
            unit_price=p.product.price, quantity=p.item.quantity, item_max_price=p.item.max_price,
            is_substitution=p.is_substitution, substitution_pref=p.item.substitution,
            spec_mismatches=tuple(p.mismatches),
        ) for p in lines),
        quote=quote,
        store_distance_mi=miles_between(cfg.lat, cfg.lng, store.lat, store.lng),
        store_verified=store.verified,
    )


def _reason_dicts(reasons) -> list[dict]:
    return [{"code": r.code, "layer": r.layer, "effect": r.effect.value, "message": r.message} for r in reasons]


def _commit_cart(db: Session, cfg: Settings, card: Card | None, store: Store, lines: list[Planned],
                 approval: Approval | None, res: Result) -> None:
    names = [p.item.name for p in lines]
    quote = _quote(store, lines)
    snapshot = _snapshot(store, lines, quote)
    if approval is not None and approval.snapshot_hash != snapshot:
        approval.status, approval.status_reason = "invalidated", "The price or cart changed after you approved it."
        for p in lines:
            p.item.status, p.item.status_reason = "ready", "Re-planning: the cart changed after approval."
        log(db, "approval", f"Approval #{approval.id} no longer matches the cart, so it was discarded.")
        return

    ctx = _context(db, cfg)
    decision = evaluate(_proposal(store, lines, quote, cfg), ctx, has_valid_approval=approval is not None)
    reasons = _reason_dicts(decision.reasons)
    log(db, "decision", f"{store.name} cart ({', '.join(names)}), ${quote.total:,.2f}: {decision.outcome.value}.",
        details={"reasons": reasons, "quote": _quote_dict(quote)}, dedupe=True)

    if decision.outcome is Outcome.BLOCK:
        msg = " ".join(r.message for r in decision.reasons if r.effect is Outcome.BLOCK)
        for p in lines:
            p.item.status, p.item.status_reason = "blocked", msg
        if approval is not None:
            approval.status, approval.status_reason = "blocked", msg
        res.blocked += len(lines)
    elif decision.outcome is Outcome.DEFER:
        msg = " ".join(r.message for r in decision.reasons if r.effect is Outcome.DEFER)
        for p in lines:
            p.item.status_reason = f"Waiting: {msg}"
        if any(r.code == "insufficient_funds" for r in decision.reasons):
            notify.low_balance(db, cfg, quote.total, ctx.wallet_balance, names)
        res.deferred += len(lines)
    elif decision.outcome is Outcome.NEEDS_APPROVAL:
        _request_approval(db, cfg, store, lines, quote, snapshot, decision, res)
    else:
        _place(db, cfg, card, store, lines, quote, approval, res)


def _quote_dict(q: Quote) -> dict:
    return {"subtotal": str(q.subtotal), "tax": str(q.tax), "delivery_fee": str(q.delivery_fee),
            "service_fee": str(q.service_fee), "total": str(q.total)}


def _request_approval(db, cfg, store, lines, quote, snapshot, decision, res) -> None:
    if db.scalars(select(Approval).where(Approval.status == "pending", Approval.snapshot_hash == snapshot)).first():
        return
    ctx = _context(db, cfg)
    now = clock.now_utc(db)
    alternatives = []
    for p in lines:
        for c in catalog.search(db, p.item, cfg):
            if c.product.id != p.product.id and c.distance_mi <= RADIUS_MILES and c.product.in_stock:
                alternatives.append({"item": p.item.name, "product": c.product.name, "color": c.product.color,
                                     "store": c.store.name, "price": str(c.product.price),
                                     "distance_mi": round(c.distance_mi, 1)})
    approval = Approval(
        store_id=store.id,
        lines=[{"item_id": p.item.id, "item_version": p.version, "product_id": p.product.id,
                "quantity": p.item.quantity, "unit_price": str(p.product.price),
                "is_substitution": p.is_substitution, "mismatches": p.mismatches} for p in lines],
        item_ids=[p.item.id for p in lines],
        quote=_quote_dict(quote),
        reasons=_reason_dicts(decision.approval_reasons),
        alternatives=alternatives[:4],
        budget={"week_spent": str(ctx.week_spent), "weekly_budget": str(ctx.weekly_budget),
                "after": str(ctx.week_spent + quote.total),
                "remaining_after": str(ctx.weekly_budget - ctx.week_spent - quote.total)},
        snapshot_hash=snapshot, status="pending", created_at=now, expires_at=now + timedelta(hours=24),
    )
    db.add(approval)
    db.flush()
    for p in lines:
        p.item.status, p.item.status_reason = "awaiting_approval", f"Waiting for your approval (request #{approval.id})."
    notify.approval_request(db, cfg, approval, [p.item.name for p in lines])
    log(db, "approval", f"Asked for approval #{approval.id}: {', '.join(p.item.name for p in lines)} "
        f"at {store.name}, ${quote.total:,.2f}.")
    res.approvals.append(approval.id)


def _place(db, cfg, card, store, lines, quote, approval, res) -> None:
    """Purchase commitment point. Rechecks the latest list under row locks before ordering."""
    db.execute(select(Settings).where(Settings.id == 1).with_for_update())
    ids = [p.item.id for p in lines]
    fresh = {i.id: i for i in db.scalars(
        select(ListItem).where(ListItem.id.in_(ids)).with_for_update().execution_options(populate_existing=True))}
    for p in lines:
        cur = fresh[p.item.id]
        if cur.deleted or cur.version != p.version:
            log(db, "recheck", f"{store.name} order skipped: {cur.name} changed right before ordering. "
                "It will be re-planned.", item_id=cur.id)
            return
    if card is None and wallet.balance(db) < quote.total:
        log(db, "recheck", f"{store.name} order skipped: the wallet balance no longer covers "
            f"${quote.total:,.2f}. It will be retried.")
        return

    key = hashlib.sha256(json.dumps([store.id, sorted((p.item.id, p.version) for p in lines)]).encode()).hexdigest()
    order = Order(
        store_id=store.id, subtotal=quote.subtotal, tax=quote.tax, delivery_fee=quote.delivery_fee,
        service_fee=quote.service_fee, total=quote.total, status="placed", idempotency_key=key,
        card_brand=card.brand if card else wallet.WALLET, card_last4=card.last4 if card else "",
        approval_id=approval.id if approval else None,
        committed_at=clock.now_utc(db),
        lines=[OrderLine(item_id=p.item.id, item_version=p.version, product_id=p.product.id,
                         quantity=p.item.quantity, unit_price=p.product.price) for p in lines],
    )
    try:
        with db.begin_nested():
            db.add(order)
            db.flush()
    except IntegrityError:
        log(db, "duplicate", f"Prevented a duplicate order at {store.name}.")
        return
    for p in lines:
        p.item.status, p.item.status_reason = "purchased", f"Ordered from {store.name} (order #{order.id})."
    if approval is not None:
        approval.status = "used"
    db.flush()
    db.refresh(order)
    if card is None:
        wallet.debit(db, order)
    log(db, "purchase", f"Placed order #{order.id} at {store.name}: {', '.join(p.item.name for p in lines)}, "
        f"${quote.total:,.2f} {'from your wallet' if card is None else f'on {card.brand} •••• {card.last4}'}.")
    notify.purchase(db, cfg, order)
    res.placed.append(order.id)


def _run_approved(db: Session, cfg: Settings, card: Card | None, appr: Approval, res: Result) -> None:
    lines = []
    for ln in appr.lines:
        item = db.get(ListItem, ln["item_id"])
        if item is None or item.deleted or item.version != ln["item_version"]:
            appr.status, appr.status_reason = "invalidated", "The list changed after you approved."
            return
        lines.append(Planned(item, ln["item_version"], db.get(Product, ln["product_id"]),
                             ln.get("is_substitution", False), ln.get("mismatches", [])))
    _commit_cart(db, cfg, card, appr.store, lines, appr, res)
