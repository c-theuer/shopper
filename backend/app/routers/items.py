from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import clock, items
from app.db import get_db
from app.models import ListItem, Settings
from app.routers.views import item_view

router = APIRouter(prefix="/api/items")

Category = Field(pattern="^(groceries|household|lifestyle|furniture|other)$")


class ItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: str = Category
    quantity: int = Field(1, ge=1, le=99)
    brand: str | None = None
    color: str | None = None
    size: str | None = None
    max_price: Decimal | None = Field(None, ge=0)
    substitution: str | None = Field(None, pattern="^(allow|prohibit|approval)$")
    priority: str = Field("normal", pattern="^(high|normal|low)$")
    needed_by: date | None = None
    recurrence: str = Field("once", pattern="^(once|weekly)$")
    notes: str = ""


class ItemPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    category: str | None = Field(None, pattern="^(groceries|household|lifestyle|furniture|other)$")
    quantity: int | None = Field(None, ge=1, le=99)
    brand: str | None = None
    color: str | None = None
    size: str | None = None
    max_price: Decimal | None = Field(None, ge=0)
    substitution: str | None = Field(None, pattern="^(allow|prohibit|approval)$")
    priority: str | None = Field(None, pattern="^(high|normal|low)$")
    needed_by: date | None = None
    recurrence: str | None = Field(None, pattern="^(once|weekly)$")
    notes: str | None = None


def _blank_to_none(d: dict) -> dict:
    return {k: (None if isinstance(v, str) and v.strip() == "" and k in ("brand", "color", "size") else v)
            for k, v in d.items()}


def _get(db: Session, item_id: int) -> ListItem:
    item = db.get(ListItem, item_id)
    if item is None or item.deleted:
        raise HTTPException(404, "Item not found.")
    return item


def _already_ordered(e: items.AlreadyOrdered):
    return HTTPException(409, {"message": "This item has already been ordered, so changing the list won't change "
                                          "that order. You can cancel the order instead.", "order_id": e.order_id})


@router.get("")
def list_items(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(ListItem).where(ListItem.deleted.is_(False)).order_by(ListItem.id)).all()
    return [item_view(i) for i in rows]


@router.post("", status_code=201)
def add_item(body: ItemIn, db: Session = Depends(get_db)) -> dict:
    data = _blank_to_none(body.model_dump())
    if data["substitution"] is None:
        data.pop("substitution")
    return item_view(items.create_item(db, **data))


@router.patch("/{item_id}")
def edit_item(item_id: int, body: ItemPatch, db: Session = Depends(get_db)) -> dict:
    try:
        return item_view(items.update_item(db, _get(db, item_id), _blank_to_none(body.model_dump(exclude_unset=True))))
    except items.AlreadyOrdered as e:
        raise _already_ordered(e) from None


class AnswerIn(BaseModel):
    answer: str = Field(min_length=1, max_length=500)


@router.post("/{item_id}/answer")
def answer(item_id: int, body: AnswerIn, db: Session = Depends(get_db)) -> dict:
    return item_view(items.answer(db, _get(db, item_id), body.answer))


class DeferIn(BaseModel):
    until: date | None = None


@router.post("/{item_id}/defer")
def defer(item_id: int, body: DeferIn, db: Session = Depends(get_db)) -> dict:
    tz = db.get(Settings, 1).timezone
    until = body.until or clock.now_local(db, tz).date() + timedelta(days=1)
    try:
        return item_view(items.defer_item(db, _get(db, item_id), until))
    except items.AlreadyOrdered as e:
        raise _already_ordered(e) from None


@router.delete("/{item_id}", status_code=204)
def remove(item_id: int, db: Session = Depends(get_db)) -> None:
    try:
        items.remove_item(db, _get(db, item_id))
    except items.AlreadyOrdered as e:
        raise _already_ordered(e) from None
