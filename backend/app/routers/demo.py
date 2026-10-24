"""Demo controls: move the clock, trigger runs, reset data."""

from datetime import date, time

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import clock, notify, seed, shopping
from app.activity import log
from app.db import get_db
from app.models import Settings
from app.routers.settings import get_clock

router = APIRouter(prefix="/api/demo")


class ClockIn(BaseModel):
    at: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")
    on: date | None = None
    advance_minutes: int | None = Field(None, ge=-10080, le=10080)
    live: bool = False


@router.post("/clock")
def set_clock(body: ClockIn, db: Session = Depends(get_db)) -> dict:
    tz = db.get(Settings, 1).timezone
    if body.live:
        clock.go_live(db)
    elif body.advance_minutes is not None:
        clock.advance(db, body.advance_minutes)
    elif body.at:
        h, m = map(int, body.at.split(":"))
        clock.set_local_time(db, tz, time(h, m), body.on)
    local = clock.now_local(db, tz)
    log(db, "clock", f"Demo clock set to {local:%a %b %d, %-I:%M %p}.")
    db.commit()
    return get_clock(db)


@router.post("/run")
def run(db: Session = Depends(get_db)) -> dict:
    return shopping.run(db).__dict__


@router.post("/summary")
def summary(db: Session = Depends(get_db)) -> dict:
    n = notify.daily_summary(db, db.get(Settings, 1))
    return {"id": n.id, "subject": n.subject}


class ResetIn(BaseModel):
    preload: bool = True


@router.post("/reset")
def reset(body: ResetIn, db: Session = Depends(get_db)) -> dict:
    seed.reset(db, preload=body.preload)
    return {"ok": True}
