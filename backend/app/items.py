"""Shopping list operations. Every change bumps the item's version and invalidates affected approvals."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import agent, catalog, clock
from app.activity import log
from app.guardrails import RADIUS_MILES, restricted_reason
from app.models import Approval, ListEvent, ListItem, Order, OrderLine, Settings

EDITABLE = ("name", "category", "quantity", "brand", "color", "size", "max_price", "substitution",
            "priority", "needed_by", "recurrence", "notes")


class AlreadyOrdered(Exception):
    def __init__(self, order_id: int | None):
        self.order_id = order_id
        super().__init__("This item has already been ordered.")


def placed_order_for(db: Session, item_id: int) -> Order | None:
    return db.scalars(
        select(Order).join(OrderLine).where(OrderLine.item_id == item_id, Order.status == "placed")
        .order_by(Order.id.desc()).limit(1)
    ).first()


def _event(db: Session, item: ListItem, action: str, changes: dict) -> None:
    db.add(ListEvent(item_id=item.id, action=action, changes=changes, at=clock.now_utc(db)))


def assess(db: Session, item: ListItem) -> None:
    """Readiness check: platform category block, then Claude/rules clarification."""
    reason = restricted_reason(f"{item.name} {item.notes}", item.category)
    if reason:
        item.status, item.status_reason, item.clarification_question = "blocked", reason, ""
        log(db, "blocked", f"Blocked {item.name}: {reason}", item_id=item.id)
        return

    cfg = db.get(Settings, 1)
    options = [c.as_dict() for c in catalog.search(db, item, cfg) if c.distance_mi <= RADIUS_MILES]
    clar, source = agent.clarify(item, options)
    if clar.restricted:
        item.status, item.clarification_question = "blocked", ""
        item.status_reason = clar.restricted_reason or "This kind of purchase isn't supported."
        log(db, "blocked", f"Blocked {item.name}: {item.status_reason}", item_id=item.id, source=source)
        return
    for field in ("brand", "color", "size"):
        value = getattr(clar, field)
        if value and not getattr(item, field):
            setattr(item, field, value)
    if clar.needs_clarification and clar.question:
        item.status, item.status_reason, item.clarification_question = "needs_clarification", "", clar.question
        log(db, "question", f"Asked about {item.name}: {clar.question}", item_id=item.id, source=source)
    else:
        item.status, item.status_reason, item.clarification_question = "ready", "", ""


def create_item(db: Session, **fields) -> ListItem:
    now = clock.now_utc(db)
    cfg = db.get(Settings, 1)
    fields.setdefault("substitution", cfg.substitution_default)
    item = ListItem(**{k: v for k, v in fields.items() if k in EDITABLE}, created_at=now, updated_at=now)
    db.add(item)
    db.flush()
    _event(db, item, "add", {k: str(v) for k, v in fields.items() if v not in (None, "")})
    log(db, "list", f"Added {item.name} to the list.", item_id=item.id)
    assess(db, item)
    db.commit()
    return item


def invalidate_approvals(db: Session, item_id: int, reason: str) -> None:
    approvals = db.scalars(select(Approval).where(Approval.status.in_(("pending", "approved")))).all()
    for a in approvals:
        if item_id not in a.item_ids:
            continue
        a.status, a.status_reason = "invalidated", reason
        for other in a.item_ids:
            o = db.get(ListItem, other)
            if o and o.id != item_id and o.status == "awaiting_approval":
                o.status, o.status_reason = "ready", "Re-planning after a change to the cart."
        log(db, "approval", f"Approval #{a.id} is no longer valid: {reason}", item_id=item_id)


def _guard_not_ordered(db: Session, item: ListItem) -> None:
    if item.status == "purchased":
        order = placed_order_for(db, item.id)
        raise AlreadyOrdered(order.id if order else None)


def update_item(db: Session, item: ListItem, changes: dict) -> ListItem:
    _guard_not_ordered(db, item)
    diff = {}
    for k, v in changes.items():
        if k in EDITABLE and getattr(item, k) != v:
            diff[k] = {"from": str(getattr(item, k)), "to": str(v)}
            setattr(item, k, v)
    if not diff:
        return item
    item.version += 1
    item.updated_at = clock.now_utc(db)
    item.deferred_until = None
    _event(db, item, "edit", diff)
    log(db, "list", f"Edited {item.name}: " + ", ".join(diff), item_id=item.id)
    invalidate_approvals(db, item.id, f"{item.name} was edited.")
    assess(db, item)
    db.commit()
    return item


def answer(db: Session, item: ListItem, text: str) -> ListItem:
    question = item.clarification_question
    item.notes = f"{item.notes}\nQ: {question}\nA: {text}".strip()
    item.version += 1
    item.updated_at = clock.now_utc(db)
    _event(db, item, "answer", {"question": question, "answer": text})
    log(db, "list", f"Answered about {item.name}: {text}", item_id=item.id)
    assess(db, item)
    db.commit()
    return item


def remove_item(db: Session, item: ListItem) -> None:
    _guard_not_ordered(db, item)
    item.deleted, item.status, item.status_reason = True, "removed", ""
    item.version += 1
    item.updated_at = clock.now_utc(db)
    _event(db, item, "remove", {})
    log(db, "list", f"Removed {item.name} from the list.", item_id=item.id)
    invalidate_approvals(db, item.id, f"{item.name} was removed from the list.")
    db.commit()


def defer_item(db: Session, item: ListItem, until: date) -> ListItem:
    _guard_not_ordered(db, item)
    item.deferred_until = until
    item.version += 1
    item.status = "ready" if item.status in ("ready", "awaiting_approval", "unavailable") else item.status
    item.status_reason = f"Deferred until {until:%a %b %d}."
    _event(db, item, "defer", {"until": str(until)})
    invalidate_approvals(db, item.id, f"{item.name} was deferred.")
    db.commit()
    return item
