from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock, wallet
from app.activity import log
from app.db import get_db
from app.models import ListItem, Order, Settings
from app.routers.views import delivery_status, order_view

router = APIRouter(prefix="/api/orders")


@router.get("")
def list_orders(db: Session = Depends(get_db)) -> list[dict]:
    cfg = db.get(Settings, 1)
    return [order_view(db, o, cfg) for o in db.scalars(select(Order).order_by(Order.id.desc())).all()]


@router.get("/{order_id}")
def get_order(order_id: int, db: Session = Depends(get_db)) -> dict:
    o = db.get(Order, order_id)
    if o is None:
        raise HTTPException(404, "Order not found.")
    return order_view(db, o, db.get(Settings, 1))


@router.post("/{order_id}/cancel")
def cancel(order_id: int, db: Session = Depends(get_db)) -> dict:
    o = db.get(Order, order_id)
    if o is None:
        raise HTTPException(404, "Order not found.")
    if o.status == "canceled":
        raise HTTPException(409, "This order is already canceled.")
    if delivery_status(db, o) == "delivered":
        raise HTTPException(409, "This order was already delivered. Start a return with the store instead.")
    o.status, o.canceled_at = "canceled", clock.now_utc(db)
    for ln in o.lines:
        item = db.get(ListItem, ln.item_id)
        if item and not item.deleted and item.status == "purchased":
            item.status, item.status_reason = "ready", f"Order #{o.id} was canceled; this item is back on the list."
            item.version += 1
    refund_to = "your card"
    if o.card_brand == wallet.WALLET:
        wallet.refund(db, o)
        refund_to = "your wallet"
    log(db, "order", f"Canceled order #{o.id} at {o.store.name}. Refunded ${o.total:,.2f} to {refund_to}. "
        "The refund doesn't restore the weekly allowance.")
    db.commit()
    return order_view(db, o, db.get(Settings, 1))
