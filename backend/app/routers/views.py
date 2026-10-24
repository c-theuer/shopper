"""JSON shapes shared by the routers."""

from datetime import timedelta

from sqlalchemy.orm import Session

from app import clock, wallet
from app.geo import miles_between
from app.models import Approval, ListItem, Order, Product, Settings


def item_view(i: ListItem) -> dict:
    return {
        "id": i.id, "name": i.name, "category": i.category, "quantity": i.quantity, "brand": i.brand,
        "color": i.color, "size": i.size, "max_price": str(i.max_price) if i.max_price is not None else None,
        "substitution": i.substitution, "priority": i.priority,
        "needed_by": i.needed_by.isoformat() if i.needed_by else None, "recurrence": i.recurrence,
        "notes": i.notes, "status": i.status, "status_reason": i.status_reason,
        "clarification_question": i.clarification_question,
        "deferred_until": i.deferred_until.isoformat() if i.deferred_until else None,
        "version": i.version, "updated_at": i.updated_at.isoformat(),
    }


def delivery_status(db: Session, o: Order) -> str:
    if o.status == "canceled":
        return "canceled"
    age = clock.now_utc(db) - o.committed_at
    if age < timedelta(minutes=30):
        return "preparing"
    if age < timedelta(hours=2):
        return "out_for_delivery"
    return "delivered"


def order_view(db: Session, o: Order, cfg: Settings) -> dict:
    return {
        "id": o.id, "store": o.store.name, "store_address": o.store.address,
        "distance_mi": round(miles_between(cfg.lat, cfg.lng, o.store.lat, o.store.lng), 1),
        "status": o.status, "delivery_status": delivery_status(db, o),
        "subtotal": str(o.subtotal), "tax": str(o.tax), "delivery_fee": str(o.delivery_fee),
        "service_fee": str(o.service_fee), "total": str(o.total),
        "card": wallet.paid_with(o), "approval_id": o.approval_id,
        "committed_at": o.committed_at.isoformat(),
        "lines": [{"item_id": ln.item_id, "item": ln.item.name, "product": ln.product.name,
                   "brand": ln.product.brand, "color": ln.product.color, "size": ln.product.size,
                   "quantity": ln.quantity, "unit_price": str(ln.unit_price)} for ln in o.lines],
    }


def approval_view(db: Session, a: Approval, cfg: Settings) -> dict:
    lines = []
    for ln in a.lines:
        p = db.get(Product, ln["product_id"])
        item = db.get(ListItem, ln["item_id"])
        lines.append({"item_id": ln["item_id"], "item": item.name if item else "?", "product": p.name,
                      "brand": p.brand, "color": p.color, "size": p.size, "quantity": ln["quantity"],
                      "unit_price": ln["unit_price"], "is_substitution": ln.get("is_substitution", False),
                      "mismatches": ln.get("mismatches", [])})
    return {
        "id": a.id, "status": a.status, "status_reason": a.status_reason, "store": a.store.name,
        "store_address": a.store.address,
        "distance_mi": round(miles_between(cfg.lat, cfg.lng, a.store.lat, a.store.lng), 1),
        "lines": lines, "quote": a.quote, "reasons": a.reasons, "alternatives": a.alternatives,
        "budget": a.budget, "created_at": a.created_at.isoformat(), "expires_at": a.expires_at.isoformat(),
        "decided_at": a.decided_at.isoformat() if a.decided_at else None,
    }
