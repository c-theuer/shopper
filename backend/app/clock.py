"""Demo clock. Every rule and job reads time from here so the demo can jump through a day."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.models import DemoState

WINDOW_START = time(10, 0)
WINDOW_END = time(17, 0)


def _state(db: Session) -> DemoState:
    state = db.get(DemoState, 1)
    if state is None:
        state = DemoState(id=1)
        db.add(state)
        db.flush()
    return state


def now_utc(db: Session) -> datetime:
    frozen = _state(db).frozen_at
    return frozen.astimezone(UTC) if frozen else datetime.now(UTC)


def now_local(db: Session, tz: str) -> datetime:
    return now_utc(db).astimezone(ZoneInfo(tz))


def set_local_time(db: Session, tz: str, at: time, on: date | None = None) -> datetime:
    local_date = on or now_local(db, tz).date()
    frozen = datetime.combine(local_date, at, tzinfo=ZoneInfo(tz))
    _state(db).frozen_at = frozen.astimezone(UTC)
    return frozen


def advance(db: Session, minutes: int) -> None:
    _state(db).frozen_at = now_utc(db) + timedelta(minutes=minutes)


def go_live(db: Session) -> None:
    _state(db).frozen_at = None


def is_frozen(db: Session) -> bool:
    return _state(db).frozen_at is not None


def in_window(local: datetime) -> bool:
    """Purchases may be submitted from 10:00 inclusive until 17:00 exclusive (FR7)."""
    return WINDOW_START <= local.time() < WINDOW_END


def week_start(local: datetime) -> datetime:
    """Weeks run Monday 00:00 to Sunday 23:59 in the user's timezone (FR5)."""
    monday = local.date() - timedelta(days=local.weekday())
    return datetime.combine(monday, time(0), tzinfo=local.tzinfo)


def day_start(local: datetime) -> datetime:
    return datetime.combine(local.date(), time(0), tzinfo=local.tzinfo)


def next_window_open(local: datetime) -> datetime:
    today_open = datetime.combine(local.date(), WINDOW_START, tzinfo=local.tzinfo)
    if local < today_open:
        return today_open
    return today_open + timedelta(days=1)
