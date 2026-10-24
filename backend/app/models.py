from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

Money = Numeric(10, 2)


class Settings(Base):
    """Single-row user settings (the MVP has exactly one user)."""

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    location_label: Mapped[str] = mapped_column(String(200))
    lat: Mapped[float]
    lng: Mapped[float]
    timezone: Mapped[str] = mapped_column(String(64))
    weekly_budget: Mapped[Decimal] = mapped_column(Money)
    order_limit: Mapped[Decimal] = mapped_column(Money)
    max_delivery_fee: Mapped[Decimal] = mapped_column(Money)
    substitution_default: Mapped[str] = mapped_column(String(16), default="approval")
    always_approve_categories: Mapped[list[str]] = mapped_column(JSON, default=list)
    # 0 = Monday ... 6 = Sunday
    permitted_days: Mapped[list[int]] = mapped_column(JSON, default=lambda: list(range(7)))
    notify_channel: Mapped[str] = mapped_column(String(8), default="email")
    notify_contact: Mapped[str] = mapped_column(String(200), default="")
    purchase_notifications: Mapped[bool] = mapped_column(default=True)
    paused: Mapped[bool] = mapped_column(default=False)
    payment_method: Mapped[str] = mapped_column(String(8), default="card")  # card / wallet


class Card(Base):
    """DEMO ONLY: plaintext test card. Only allowlisted test numbers are accepted."""

    __tablename__ = "cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand: Mapped[str] = mapped_column(String(32))
    number: Mapped[str] = mapped_column(String(19))
    exp_month: Mapped[int]
    exp_year: Mapped[int]
    name: Mapped[str] = mapped_column(String(200))
    zip: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime]

    @property
    def last4(self) -> str:
        return self.number[-4:]


class BankAccount(Base):
    """DEMO ONLY: a linked test bank account. Only allowlisted test numbers are accepted; only last 4 is kept."""

    __tablename__ = "bank_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    bank_name: Mapped[str] = mapped_column(String(100))
    routing_number: Mapped[str] = mapped_column(String(9))
    account_last4: Mapped[str] = mapped_column(String(4))
    holder_name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime]


class WalletEntry(Base):
    """Append-only wallet ledger. The balance is the sum of amounts (deposits and refunds +, purchases -)."""

    __tablename__ = "wallet_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))  # deposit / purchase / refund
    amount: Mapped[Decimal] = mapped_column(Money)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    memo: Mapped[str] = mapped_column(String(200), default="")
    at: Mapped[datetime]


class ListItem(Base):
    __tablename__ = "list_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(32))
    quantity: Mapped[int] = mapped_column(default=1)
    brand: Mapped[str | None] = mapped_column(String(100))
    color: Mapped[str | None] = mapped_column(String(50))
    size: Mapped[str | None] = mapped_column(String(50))
    max_price: Mapped[Decimal | None] = mapped_column(Money)
    substitution: Mapped[str] = mapped_column(String(16), default="approval")
    priority: Mapped[str] = mapped_column(String(8), default="normal")
    needed_by: Mapped[date | None]
    recurrence: Mapped[str] = mapped_column(String(8), default="once")
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="ready")
    status_reason: Mapped[str] = mapped_column(Text, default="")
    clarification_question: Mapped[str] = mapped_column(Text, default="")
    deferred_until: Mapped[date | None]
    version: Mapped[int] = mapped_column(default=1)
    deleted: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]


class ListEvent(Base):
    __tablename__ = "list_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("list_items.id"))
    action: Mapped[str] = mapped_column(String(16))
    changes: Mapped[dict] = mapped_column(JSON, default=dict)
    at: Mapped[datetime]


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str] = mapped_column(String(200))
    lat: Mapped[float]
    lng: Mapped[float]
    delivery_fee: Mapped[Decimal] = mapped_column(Money)
    service_fee: Mapped[Decimal] = mapped_column(Money)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    verified: Mapped[bool] = mapped_column(default=True)

    products: Mapped[list["Product"]] = relationship(back_populates="store")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"))
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(32))
    brand: Mapped[str] = mapped_column(String(100))
    color: Mapped[str | None] = mapped_column(String(50))
    size: Mapped[str | None] = mapped_column(String(50))
    price: Mapped[Decimal] = mapped_column(Money)
    in_stock: Mapped[bool] = mapped_column(default=True)
    keywords: Mapped[str] = mapped_column(Text, default="")

    store: Mapped[Store] = relationship(back_populates="products")


class Order(Base):
    """One merchant order: a store's cart. Lines link back to list items."""

    __tablename__ = "orders"
    __table_args__ = (UniqueConstraint("idempotency_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"))
    subtotal: Mapped[Decimal] = mapped_column(Money)
    tax: Mapped[Decimal] = mapped_column(Money)
    delivery_fee: Mapped[Decimal] = mapped_column(Money)
    service_fee: Mapped[Decimal] = mapped_column(Money)
    total: Mapped[Decimal] = mapped_column(Money)
    status: Mapped[str] = mapped_column(String(16), default="placed")  # placed / canceled
    idempotency_key: Mapped[str] = mapped_column(String(64))
    card_brand: Mapped[str] = mapped_column(String(32))  # "Wallet" when paid from the wallet
    card_last4: Mapped[str] = mapped_column(String(4))
    approval_id: Mapped[int | None] = mapped_column(ForeignKey("approvals.id"))
    committed_at: Mapped[datetime]
    canceled_at: Mapped[datetime | None]

    store: Mapped[Store] = relationship()
    lines: Mapped[list["OrderLine"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderLine(Base):
    __tablename__ = "order_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    item_id: Mapped[int] = mapped_column(ForeignKey("list_items.id"))
    item_version: Mapped[int]
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int]
    unit_price: Mapped[Decimal] = mapped_column(Money)

    order: Mapped[Order] = relationship(back_populates="lines")
    product: Mapped[Product] = relationship()
    item: Mapped[ListItem] = relationship()


class Approval(Base):
    """A request to approve one exact cart. Any change to the cart invalidates it."""

    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"))
    # [{item_id, item_version, product_id, quantity, unit_price}]
    lines: Mapped[list[dict]] = mapped_column(JSON)
    item_ids: Mapped[list[int]] = mapped_column(JSON)
    quote: Mapped[dict] = mapped_column(JSON)
    reasons: Mapped[list[dict]] = mapped_column(JSON)
    alternatives: Mapped[list[dict]] = mapped_column(JSON, default=list)
    budget: Mapped[dict] = mapped_column(JSON, default=dict)
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    status_reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime]
    expires_at: Mapped[datetime]
    decided_at: Mapped[datetime | None]

    store: Mapped[Store] = relationship()


class Activity(Base):
    """Agent activity log and guardrail decisions, shown on the Activity page."""

    __tablename__ = "activity"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int | None] = mapped_column(ForeignKey("list_items.id"))
    kind: Mapped[str] = mapped_column(String(24))
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(8), default="rules")  # "ai" or "rules"
    at: Mapped[datetime]


class Notification(Base):
    """Outbox. Nothing is sent for real in the demo; the Inbox page renders these."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(24))
    channel: Mapped[str] = mapped_column(String(8))
    to: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[dict] = mapped_column(JSON)
    at: Mapped[datetime]


class DemoState(Base):
    """Single-row demo clock. When frozen_at is set, the app's 'now' is that instant (UTC)."""

    __tablename__ = "demo_state"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    frozen_at: Mapped[datetime | None]
    last_summary_date: Mapped[date | None]
