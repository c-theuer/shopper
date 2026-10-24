from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Activity, Notification

router = APIRouter(prefix="/api")


@router.get("/activity")
def activity(limit: int = 200, db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(Activity).order_by(Activity.id.desc()).limit(min(limit, 500))).all()
    return [{"id": a.id, "kind": a.kind, "message": a.message, "details": a.details, "source": a.source,
             "item_id": a.item_id, "at": a.at.isoformat()} for a in rows]


@router.get("/notifications")
def notifications(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(Notification).order_by(Notification.id.desc()).limit(100)).all()
    return [{"id": n.id, "kind": n.kind, "channel": n.channel, "to": n.to, "subject": n.subject,
             "body": n.body, "at": n.at.isoformat()} for n in rows]
