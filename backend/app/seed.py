"""Mock stores, catalog, and the 'Mike' demo persona."""

from datetime import UTC, datetime
from decimal import Decimal as D

from sqlalchemy import delete, text
from sqlalchemy.orm import Session

from app import models as m
from app.db import Base, engine

HOME = {"label": "Ferry Building, San Francisco, CA", "lat": 37.7955, "lng": -122.3937}

# (name, address, dlat, dlng, delivery_fee, service_fee, tax_rate, products)
# Offsets from HOME put stores at about 0.8, 1.9, 2.6, 5.6, 9.4 and 12.4 miles.
# Product tuple: (name, category, brand, color, size, price, in_stock, keywords)
STORES = [
    ("Embarcadero Market", "101 Market St", -0.0080, -0.0106, "4.99", "1.99", "0.0000", [
        ("Clover Organic Whole Milk", "groceries", "Clover", None, "1 gal", "6.49", True, "milk whole dairy"),
        ("Organic Valley 2% Milk", "groceries", "Organic Valley", None, "1/2 gal", "4.29", True, "milk 2% reduced fat dairy"),
        ("Acme Sourdough Loaf", "groceries", "Acme", None, "1 loaf", "7.50", True, "bread sourdough loaf"),
        ("Vital Farms Large Brown Eggs", "groceries", "Vital Farms", None, "12 ct", "6.99", True, "eggs dozen"),
        ("Organic Bananas", "groceries", "Market", None, "1 lb", "0.79", True, "banana bananas fruit"),
        ("Honeycrisp Apples", "groceries", "Market", None, "3 lb", "5.99", True, "apple apples fruit"),
        ("Peet's Major Dickason's Blend Coffee", "groceries", "Peet's", None, "12 oz", "13.99", True, "coffee beans ground"),
        ("Advil Ibuprofen 200 mg", "medicine", "Advil", None, "50 ct", "9.99", True, "ibuprofen advil pain reliever medicine"),
        ("Bounty Paper Towels", "household", "Bounty", None, "6 rolls", "15.99", True, "paper towels"),
    ]),
    ("Hayes Home & Lighting", "450 Hayes St", -0.0150, -0.0290, "7.99", "2.99", "0.0863", [
        ("Arc Table Lamp", "lifestyle", "Hayes Home", "black", "18 in", "49.00", True, "lamp table desk light"),
        ("Arc Table Lamp", "lifestyle", "Hayes Home", "white", "18 in", "49.00", True, "lamp table desk light"),
        ("Arc Table Lamp", "lifestyle", "Hayes Home", "brass", "18 in", "64.00", True, "lamp table desk light"),
        ("Linen Floor Lamp", "lifestyle", "Hayes Home", "white", "60 in", "129.00", True, "lamp floor light"),
        ("Linen Throw Pillow", "lifestyle", "Hayes Home", "sage", "20 in", "29.00", True, "pillow cushion throw"),
        ("Wool Throw Blanket", "lifestyle", "Hayes Home", "grey", "50x60 in", "89.00", True, "blanket throw"),
        ("Cedar Scented Candle", "lifestyle", "Hayes Home", None, "8 oz", "24.00", True, "candle"),
    ]),
    ("Mission Fresh Grocers", "2400 Mission St", -0.0350, -0.0170, "3.99", "1.49", "0.0000", [
        ("Straus Organic Whole Milk", "groceries", "Straus", None, "1/2 gal", "5.29", True, "milk whole dairy"),
        ("Clover Organic Whole Milk", "groceries", "Clover", None, "1 gal", "6.99", True, "milk whole dairy"),
        ("Vital Farms Large Brown Eggs", "groceries", "Vital Farms", None, "12 ct", "7.29", True, "eggs dozen"),
        ("Organic Bananas", "groceries", "Market", None, "1 lb", "0.69", True, "banana bananas fruit"),
        ("Tillamook Sharp Cheddar", "groceries", "Tillamook", None, "8 oz", "5.49", True, "cheese cheddar"),
        ("Peet's Major Dickason's Blend Coffee", "groceries", "Peet's", None, "12 oz", "12.99", True, "coffee beans ground"),
        ("Tylenol Extra Strength", "medicine", "Tylenol", None, "100 ct", "12.49", True, "tylenol acetaminophen medicine pain"),
    ]),
    ("Sunset Furniture Co.", "1900 Irving St", -0.0250, -0.0980, "49.00", "0.00", "0.0863", [
        ("Oak Dining Chair", "furniture", "Sunset", "natural oak", "18 in seat", "179.00", True, "chair dining wood"),
        ("Mid-Century Lounge Chair", "furniture", "Sunset", "walnut", "30 in", "549.00", True, "chair lounge armchair"),
        ("Velvet 3-Seat Sofa", "furniture", "Sunset", "emerald", "84 in", "899.00", True, "sofa couch"),
        ("Five-Shelf Bookcase", "furniture", "Sunset", "white", "72 in", "159.00", True, "bookshelf shelf bookcase"),
        ("Round Side Table", "furniture", "Sunset", "oak", "20 in", "119.00", True, "table side end"),
    ]),
    ("Daly City Everyday", "333 Gellert Blvd", -0.1250, -0.0680, "5.99", "1.99", "0.0925", [
        ("Lucerne Whole Milk", "groceries", "Lucerne", None, "1 gal", "4.99", True, "milk whole dairy"),
        ("Organic Valley Whole Milk", "groceries", "Organic Valley", None, "1 gal", "7.49", False, "milk whole dairy"),
        ("Arc Table Lamp", "lifestyle", "Hayes Home", "black", "18 in", "44.00", True, "lamp table desk light"),
        ("Bounty Paper Towels", "household", "Bounty", None, "6 rolls", "13.99", True, "paper towels"),
        ("Tide Liquid Laundry Detergent", "household", "Tide", None, "64 oz", "14.99", True, "laundry detergent"),
    ]),
    ("Bayshore Furniture Outlet", "900 Bayshore Blvd, South San Francisco", -0.1700, -0.0740, "29.00", "0.00", "0.0938", [
        ("Basic Dining Chair", "furniture", "Bayshore", "black", "17 in seat", "69.00", True, "chair dining"),
        ("Classic 3-Seat Sofa", "furniture", "Bayshore", "grey", "80 in", "599.00", True, "sofa couch"),
    ]),
]

MIKE_LIST = [
    # (name, category, quantity, brand, color, notes)
    ("Whole milk", "groceries", 1, "Clover", None, ""),
    ("Coffee beans", "groceries", 1, "Peet's", None, "The usual dark roast"),
    ("Bananas", "groceries", 3, None, None, ""),
    ("Lamp", "lifestyle", 1, None, None, "For the reading nook"),
    ("Dining chair", "furniture", 1, None, None, ""),
    ("Ibuprofen", "groceries", 1, None, None, ""),
    ("Pay my credit card bill", "other", 1, None, None, ""),
]


def default_settings() -> m.Settings:
    return m.Settings(
        id=1,
        location_label=HOME["label"],
        lat=HOME["lat"],
        lng=HOME["lng"],
        timezone="America/Los_Angeles",
        weekly_budget=D("1000.00"),
        order_limit=D("200.00"),
        max_delivery_fee=D("50.00"),
        substitution_default="approval",
        always_approve_categories=[],
        permitted_days=list(range(7)),
        notify_channel="email",
        notify_contact="mike@example.com",
        purchase_notifications=True,
        paused=False,
    )


def seed_catalog(db: Session) -> None:
    for name, address, dlat, dlng, delivery, service, tax, products in STORES:
        store = m.Store(
            name=name, address=address,
            lat=HOME["lat"] + dlat, lng=HOME["lng"] + dlng,
            delivery_fee=D(delivery), service_fee=D(service), tax_rate=D(tax),
        )
        store.products = [
            m.Product(name=n, category=c, brand=b, color=col, size=sz, price=D(p), in_stock=stock, keywords=kw)
            for n, c, b, col, sz, p, stock, kw in products
        ]
        db.add(store)


def init_db() -> None:
    Base.metadata.create_all(engine)
    # No migrations yet: add columns that create_all can't add to existing tables.
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE settings ADD COLUMN IF NOT EXISTS payment_method varchar(8) "
                          "NOT NULL DEFAULT 'card'"))
    with Session(engine) as db:
        if db.get(m.Settings, 1) is None:
            reset(db, preload=False)


def reset(db: Session, preload: bool) -> None:
    """Wipe everything and reseed. Tables are deleted child-first."""
    for table in (m.Notification, m.Activity, m.WalletEntry, m.OrderLine, m.Order, m.Approval, m.ListEvent, m.ListItem,
                  m.Product, m.Store, m.Card, m.BankAccount, m.DemoState, m.Settings):
        db.execute(delete(table))
    db.add(default_settings())
    db.add(m.DemoState(id=1))
    seed_catalog(db)
    db.commit()
    if preload:
        from app.items import create_item  # avoid import cycle

        now = datetime.now(UTC)
        db.add(m.Card(brand="Visa", number="4242424242424242", exp_month=12, exp_year=now.year + 3,
                      name="Mike Rivera", zip="94111", created_at=now))
        db.add(m.BankAccount(bank_name="Stripe Test Bank", routing_number="110000000", account_last4="6789",
                             holder_name="Mike Rivera", created_at=now))
        db.commit()
        for name, category, qty, brand, color, notes in MIKE_LIST:
            create_item(db, name=name, category=category, quantity=qty, brand=brand, color=color, notes=notes)
