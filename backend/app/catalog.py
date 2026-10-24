"""Mock merchant search: match list items to products at stores."""

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.geo import miles_between
from app.models import ListItem, Product, Settings, Store

_STOP = {"a", "an", "the", "my", "some", "of", "for", "and", "new", "pay"}


def _tokens(text: str) -> set[str]:
    out = set()
    for w in re.findall(r"[a-z0-9%']+", text.lower()):
        if w in _STOP or len(w) < 2:
            continue
        out.add(w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w)
    return out


@dataclass
class Candidate:
    product: Product
    store: Store
    distance_mi: float
    score: int

    def as_dict(self) -> dict:
        p, s = self.product, self.store
        return {
            "product_id": p.id, "name": p.name, "brand": p.brand, "color": p.color, "size": p.size,
            "price": str(p.price), "in_stock": p.in_stock, "store_id": s.id, "store": s.name,
            "distance_mi": round(self.distance_mi, 1), "delivery_fee": str(s.delivery_fee),
            "service_fee": str(s.service_fee),
        }


def search(db: Session, item: ListItem, home: Settings) -> list[Candidate]:
    """All matching products at every store, best match first. Radius filtering is the caller's job."""
    want = _tokens(item.name)
    if not want:
        return []
    stores = db.scalars(select(Store).options(selectinload(Store.products))).all()
    out: list[Candidate] = []
    for store in stores:
        dist = miles_between(home.lat, home.lng, store.lat, store.lng)
        for p in store.products:
            if item.category not in ("other", "") and p.category != item.category and p.category != "medicine":
                continue
            score = len(want & _tokens(f"{p.name} {p.keywords}"))
            if score:
                out.append(Candidate(p, store, dist, score))
    best = max((c.score for c in out), default=0)
    return sorted((c for c in out if c.score == best), key=lambda c: (c.distance_mi, c.product.price))
