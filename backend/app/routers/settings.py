from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo, available_timezones

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import agent, cards, clock, wallet
from app.activity import log
from app.db import get_db
from app.guardrails import (AUTO_APPROVE_CAP, DAILY_STEP_UP, MAX_ORDERS_PER_HOUR, PLATFORM_ORDER_CAP,
                            RADIUS_MILES, WEEKLY_CAP)
from app.models import Card, Settings

router = APIRouter(prefix="/api")

PLATFORM_RULES = [
    f"Orders over ${PLATFORM_ORDER_CAP:,.0f} (including tax and fees) are always blocked.",
    f"Weekly spending can never go over ${WEEKLY_CAP:,.0f}.",
    f"Orders over ${AUTO_APPROVE_CAP:,.0f} always need your confirmation.",
    f"Going past ${DAILY_STEP_UP:,.0f} in a day needs your confirmation.",
    f"At most {MAX_ORDERS_PER_HOUR} automatic orders per hour.",
    f"Only stores within {RADIUS_MILES:.0f} miles of your location.",
    "Orders are placed only between 10:00 a.m. and 5:00 p.m. your time.",
    "Medicines, credit card bills, EMIs, and buy-now-pay-later are never purchased.",
    "When paying from your wallet, an order waits until your balance covers it.",
]


def _card_view(card: Card | None) -> dict | None:
    if card is None:
        return None
    return {"brand": card.brand, "last4": card.last4, "exp_month": card.exp_month, "exp_year": card.exp_year,
            "name": card.name}


def settings_view(db: Session) -> dict:
    s = db.get(Settings, 1)
    card = db.scalars(select(Card).order_by(Card.id.desc()).limit(1)).first()
    bank = wallet.bank(db)
    payment_ready = bank is not None if s.payment_method == "wallet" else card is not None
    return {
        "location_label": s.location_label, "lat": s.lat, "lng": s.lng, "timezone": s.timezone,
        "weekly_budget": str(s.weekly_budget), "order_limit": str(s.order_limit),
        "max_delivery_fee": str(s.max_delivery_fee), "substitution_default": s.substitution_default,
        "always_approve_categories": s.always_approve_categories, "permitted_days": s.permitted_days,
        "notify_channel": s.notify_channel, "notify_contact": s.notify_contact,
        "purchase_notifications": s.purchase_notifications, "paused": s.paused,
        "payment_method": s.payment_method, "wallet_balance": str(wallet.balance(db)),
        "bank": {"bank_name": bank.bank_name, "last4": bank.account_last4} if bank else None,
        "card": _card_view(card), "setup_complete": payment_ready and bool(s.notify_contact),
        "platform_rules": PLATFORM_RULES, "agent_mode": "ai" if agent.ai_enabled() else "rules",
    }


class SettingsIn(BaseModel):
    location_label: str | None = None
    lat: float | None = Field(None, ge=-90, le=90)
    lng: float | None = Field(None, ge=-180, le=180)
    timezone: str | None = None
    weekly_budget: Decimal | None = Field(None, ge=0, le=15000)
    order_limit: Decimal | None = Field(None, ge=0, le=1000)
    max_delivery_fee: Decimal | None = Field(None, ge=0)
    substitution_default: str | None = Field(None, pattern="^(allow|prohibit|approval)$")
    always_approve_categories: list[str] | None = None
    permitted_days: list[int] | None = None
    notify_channel: str | None = Field(None, pattern="^(email|sms)$")
    notify_contact: str | None = None
    purchase_notifications: bool | None = None
    paused: bool | None = None
    payment_method: str | None = Field(None, pattern="^(card|wallet)$")


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)) -> dict:
    return settings_view(db)


@router.patch("/settings")
def update_settings(body: SettingsIn, db: Session = Depends(get_db)) -> dict:
    s = db.get(Settings, 1)
    changes = body.model_dump(exclude_unset=True)
    if "timezone" in changes and changes["timezone"] not in available_timezones():
        raise HTTPException(422, "Unknown timezone.")
    for k, v in changes.items():
        setattr(s, k, v)
    if "paused" in changes:
        log(db, "control", "Shopping paused." if s.paused else "Shopping resumed.")
    if "payment_method" in changes:
        log(db, "control", "Paying from the wallet." if s.payment_method == "wallet" else "Paying with the card.")
    db.commit()
    return settings_view(db)


class CardIn(BaseModel):
    number: str
    exp_month: int
    exp_year: int
    cvc: str = ""  # accepted for realism, never stored
    name: str
    zip: str = ""


@router.put("/card")
def save_card(body: CardIn, db: Session = Depends(get_db)) -> dict:
    tz = db.get(Settings, 1).timezone
    try:
        brand = cards.validate(body.number, body.exp_month, body.exp_year, datetime.now(ZoneInfo(tz)).date())
    except cards.CardError as e:
        raise HTTPException(422, str(e)) from None
    db.execute(delete(Card))
    db.add(Card(brand=brand, number=cards.normalize(body.number), exp_month=body.exp_month,
                exp_year=body.exp_year, name=body.name, zip=body.zip, created_at=datetime.now(UTC)))
    log(db, "control", f"Saved {brand} card ending in {cards.normalize(body.number)[-4:]}.")
    db.commit()
    return settings_view(db)


@router.get("/clock")
def get_clock(db: Session = Depends(get_db)) -> dict:
    s = db.get(Settings, 1)
    local = clock.now_local(db, s.timezone)
    return {"now": local.isoformat(), "frozen": clock.is_frozen(db), "in_window": clock.in_window(local),
            "timezone": s.timezone}
