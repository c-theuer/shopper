"""DEMO ONLY wallet: a ledger of deposits from a linked test bank, purchases, and refunds.

Deposits are instant and no money moves. Production needs a bank partner (see BUILD_PLAN.md).
"""

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import clock
from app.activity import log
from app.models import BankAccount, Order, WalletEntry

WALLET = "Wallet"  # stored in Order.card_brand for wallet-paid orders
MAX_DEPOSIT = Decimal("5000.00")


class WalletError(ValueError):
    pass


def balance(db: Session) -> Decimal:
    total = db.scalar(select(func.coalesce(func.sum(WalletEntry.amount), 0)))
    return Decimal(total).quantize(Decimal("0.01"))


def bank(db: Session) -> BankAccount | None:
    return db.scalars(select(BankAccount).order_by(BankAccount.id.desc()).limit(1)).first()


def deposit(db: Session, amount: Decimal) -> WalletEntry:
    acct = bank(db)
    if acct is None:
        raise WalletError("Link a bank account before adding funds.")
    if not Decimal(0) < amount <= MAX_DEPOSIT:
        raise WalletError(f"Deposits must be between $0.01 and ${MAX_DEPOSIT:,.2f}.")
    entry = WalletEntry(kind="deposit", amount=amount, memo=f"From {acct.bank_name} •••• {acct.account_last4}",
                        at=clock.now_utc(db))
    db.add(entry)
    log(db, "wallet", f"Added ${amount:,.2f} to the wallet from {acct.bank_name} •••• {acct.account_last4}.")
    return entry


def debit(db: Session, order: Order) -> None:
    db.add(WalletEntry(kind="purchase", amount=-order.total, order_id=order.id,
                       memo=f"Order #{order.id} at {order.store.name}", at=clock.now_utc(db)))


def refund(db: Session, order: Order) -> None:
    db.add(WalletEntry(kind="refund", amount=order.total, order_id=order.id,
                       memo=f"Refund for canceled order #{order.id}", at=clock.now_utc(db)))


def paid_with(order: Order) -> str:
    return WALLET if order.card_brand == WALLET else f"{order.card_brand} •••• {order.card_last4}"
