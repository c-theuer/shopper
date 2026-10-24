from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock
from app.models import Activity


def log(db: Session, kind: str, message: str, *, item_id: int | None = None, details: dict | None = None,
        source: str = "rules", dedupe: bool = False) -> None:
    """Append to the activity feed. dedupe skips a repeat of the latest entry for the same item."""
    if dedupe:
        last = db.scalars(
            select(Activity).where(Activity.item_id == item_id).order_by(Activity.id.desc()).limit(1)
        ).first()
        if last and last.message == message:
            return
    db.add(Activity(item_id=item_id, kind=kind, message=message, details=details or {}, source=source,
                    at=clock.now_utc(db)))
