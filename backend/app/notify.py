"""Notification outbox. The demo renders these in the Inbox instead of sending email or SMS."""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import clock, wallet
from app.models import Approval, DemoState, ListItem, Notification, Order, Settings, WalletEntry


def _add(db: Session, cfg: Settings, kind: str, subject: str, body: dict) -> None:
    db.add(Notification(kind=kind, channel=cfg.notify_channel, to=cfg.notify_contact or "(not set)",
                        subject=subject, body=body, at=clock.now_utc(db)))


def order_view(order: Order) -> dict:
    return {
        "order_id": order.id, "store": order.store.name, "total": str(order.total),
        "card": wallet.paid_with(order),
        "lines": [{"name": ln.product.name, "item": ln.item.name, "quantity": ln.quantity,
                   "unit_price": str(ln.unit_price)} for ln in order.lines],
    }


def purchase(db: Session, cfg: Settings, order: Order) -> None:
    if cfg.purchase_notifications:
        _add(db, cfg, "purchase", f"Order placed at {order.store.name}: ${order.total:,.2f}", order_view(order))


def approval_request(db: Session, cfg: Settings, approval: Approval, names: list[str]) -> None:
    """Always sent, even when purchase notifications are off (FR8)."""
    _add(db, cfg, "approval", f"Approval needed: {', '.join(names)} (${Decimal(approval.quote['total']):,.2f})",
         {"approval_id": approval.id, "store": approval.store.name, "items": names, "quote": approval.quote,
          "reasons": [r["message"] for r in approval.reasons]})


def low_balance(db: Session, cfg: Settings, needed: Decimal, balance: Decimal, names: list[str]) -> None:
    """Always sent. Only once per shortfall: skipped if already sent since the last deposit."""
    last_deposit = db.scalar(select(func.max(WalletEntry.at)).where(WalletEntry.kind == "deposit"))
    q = select(Notification.id).where(Notification.kind == "low_balance")
    if last_deposit is not None:
        q = q.where(Notification.at > last_deposit)
    if db.scalars(q.limit(1)).first():
        return
    _add(db, cfg, "low_balance", f"Add funds: your wallet can't cover {', '.join(names)}",
         {"needed": str(needed), "balance": str(balance), "items": names})


def spent_since(db: Session, start) -> Decimal:
    """Committed spend. Canceled orders still count: refunds don't replenish the allowance (FR5)."""
    return db.scalar(select(func.coalesce(func.sum(Order.total), 0)).where(Order.committed_at >= start)) or Decimal(0)


def daily_summary(db: Session, cfg: Settings) -> Notification:
    local = clock.now_local(db, cfg.timezone)
    day0 = clock.day_start(local)
    orders = db.scalars(select(Order).where(Order.committed_at >= day0,
                                            Order.committed_at < day0 + timedelta(days=1))).all()
    week_spent = spent_since(db, clock.week_start(local))
    items = db.scalars(select(ListItem).where(ListItem.deleted.is_(False))).all()

    def by(*statuses):
        return [{"name": i.name, "status": i.status, "reason": i.status_reason or i.clarification_question}
                for i in items if i.status in statuses]

    pending = db.scalars(select(Approval).where(Approval.status == "pending")).all()
    body = {
        "date": str(local.date()),
        "orders": [order_view(o) | {"status": o.status} for o in orders],
        "day_total": str(sum((o.total for o in orders), Decimal(0))),
        "week_spent": str(week_spent),
        "weekly_budget": str(cfg.weekly_budget),
        "remaining_budget": str(max(cfg.weekly_budget - week_spent, Decimal(0))),
        "remaining_items": by("ready", "needs_clarification"),
        "unavailable": by("unavailable"),
        "blocked": by("blocked"),
        "pending_approvals": [{"approval_id": a.id, "store": a.store.name, "total": a.quote["total"]} for a in pending],
    }
    if cfg.payment_method == "wallet":
        body["wallet_balance"] = str(wallet.balance(db))
    _add(db, cfg, "daily_summary", f"Your shopping summary for {local:%A, %B %d}", body)
    state = db.get(DemoState, 1)
    state.last_summary_date = local.date()
    db.commit()
    return db.scalars(select(Notification).order_by(Notification.id.desc()).limit(1)).one()


def summary_due(db: Session, cfg: Settings) -> bool:
    local = clock.now_local(db, cfg.timezone)
    last: date | None = db.get(DemoState, 1).last_summary_date
    return local.time() >= clock.WINDOW_END and last != local.date()
