from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock, shopping
from app.activity import log
from app.db import get_db
from app.models import Approval, ListItem, Settings
from app.routers.views import approval_view

router = APIRouter(prefix="/api/approvals")


@router.get("")
def list_approvals(db: Session = Depends(get_db)) -> list[dict]:
    cfg = db.get(Settings, 1)
    rows = db.scalars(select(Approval).order_by(Approval.id.desc()).limit(50)).all()
    return [approval_view(db, a, cfg) for a in rows]


def _pending(db: Session, approval_id: int) -> Approval:
    a = db.get(Approval, approval_id)
    if a is None:
        raise HTTPException(404, "Approval not found.")
    if a.status != "pending":
        raise HTTPException(409, f"This request is {a.status} and can no longer be answered.")
    if a.expires_at <= clock.now_utc(db):
        raise HTTPException(409, "This request has expired.")
    return a


@router.post("/{approval_id}/approve")
def approve(approval_id: int, db: Session = Depends(get_db)) -> dict:
    """Approve once. Applies only to this exact cart and never changes settings.

    If it's shopping hours, run shopping right away; every rule is rechecked at that point."""
    a = _pending(db, approval_id)
    a.status, a.decided_at = "approved", clock.now_utc(db)
    log(db, "approval", f"You approved request #{a.id}.")
    db.commit()
    result = shopping.run(db)
    db.refresh(a)
    return {"approval": approval_view(db, a, db.get(Settings, 1)), "run": result.__dict__}


@router.post("/{approval_id}/reject")
def reject(approval_id: int, db: Session = Depends(get_db)) -> dict:
    a = _pending(db, approval_id)
    a.status, a.decided_at = "rejected", clock.now_utc(db)
    for item_id in a.item_ids:
        item = db.get(ListItem, item_id)
        if item and item.status == "awaiting_approval":
            item.status = "blocked"
            item.status_reason = "You rejected this purchase. Edit the item to try again."
    log(db, "approval", f"You rejected request #{a.id}. Nothing was bought.")
    db.commit()
    return approval_view(db, a, db.get(Settings, 1))
