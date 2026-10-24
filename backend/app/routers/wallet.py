"""DEMO ONLY wallet: link a test bank account, add funds, and see the ledger."""

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import bank, wallet
from app.activity import log
from app.db import get_db
from app.models import BankAccount, WalletEntry

router = APIRouter(prefix="/api/wallet")


def wallet_view(db: Session) -> dict:
    acct = wallet.bank(db)
    entries = db.scalars(select(WalletEntry).order_by(WalletEntry.id.desc()).limit(100)).all()
    return {
        "balance": str(wallet.balance(db)),
        "bank": {"bank_name": acct.bank_name, "last4": acct.account_last4, "holder_name": acct.holder_name}
        if acct else None,
        "entries": [{"id": e.id, "kind": e.kind, "amount": str(e.amount), "order_id": e.order_id, "memo": e.memo,
                     "at": e.at.isoformat()} for e in entries],
    }


@router.get("")
def get_wallet(db: Session = Depends(get_db)) -> dict:
    return wallet_view(db)


class BankIn(BaseModel):
    routing_number: str
    account_number: str
    holder_name: str = Field(min_length=1, max_length=200)


@router.put("/bank")
def link_bank(body: BankIn, db: Session = Depends(get_db)) -> dict:
    try:
        name = bank.validate(body.routing_number, body.account_number)
    except bank.BankError as e:
        raise HTTPException(422, str(e)) from None
    last4 = bank.normalize(body.account_number)[-4:]
    db.execute(delete(BankAccount))
    db.add(BankAccount(bank_name=name, routing_number=bank.normalize(body.routing_number), account_last4=last4,
                       holder_name=body.holder_name, created_at=datetime.now(UTC)))
    log(db, "control", f"Linked {name} account ending in {last4}.")
    db.commit()
    return wallet_view(db)


class DepositIn(BaseModel):
    amount: Decimal = Field(decimal_places=2)


@router.post("/deposits")
def add_funds(body: DepositIn, db: Session = Depends(get_db)) -> dict:
    if wallet.bank(db) is None:
        raise HTTPException(409, "Link a bank account before adding funds.")
    try:
        wallet.deposit(db, body.amount)
    except wallet.WalletError as e:
        raise HTTPException(422, str(e)) from None
    db.commit()
    return wallet_view(db)
