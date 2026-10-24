"""The PRD 'Mike' storyline end to end through the API (rules agent, no Claude)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.config import settings


def _ensure_test_db():
    admin = create_engine(settings.database_url.rsplit("/", 1)[0] + "/postgres", isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        if not c.execute(text("SELECT 1 FROM pg_database WHERE datname = 'shopper_test'")).scalar():
            c.execute(text("CREATE DATABASE shopper_test"))
    admin.dispose()


_ensure_test_db()

from app.main import app  # noqa: E402


@pytest.fixture
def api():
    with TestClient(app) as c:
        assert c.post("/api/demo/reset", json={"preload": True}).status_code == 200
        c.post("/api/demo/clock", json={"at": "10:15", "on": "2026-10-14"})  # a Wednesday
        yield c


def items_by_name(api) -> dict:
    return {i["name"]: i for i in api.get("/api/items").json()}


def test_preloaded_list_readiness(api):
    items = items_by_name(api)
    assert items["Ibuprofen"]["status"] == "blocked"
    assert items["Pay my credit card bill"]["status"] == "blocked"
    assert items["Lamp"]["status"] == "needs_clarification"
    assert "color" in items["Lamp"]["clarification_question"]
    assert items["Whole milk"]["status"] == "ready"


def test_full_day(api):
    api.post(f"/api/items/{items_by_name(api)['Lamp']['id']}/answer", json={"answer": "brass please"})
    assert items_by_name(api)["Lamp"]["color"] == "brass"

    run = api.post("/api/demo/run").json()
    items = items_by_name(api)
    assert items["Whole milk"]["status"] == "purchased"
    assert items["Lamp"]["status"] == "purchased"
    assert items["Dining chair"]["status"] == "awaiting_approval"  # $243 > $200 limit
    assert len(run["placed"]) >= 2 and len(run["approvals"]) == 1

    activity = " ".join(a["message"] for a in api.get("/api/activity").json())
    assert "Bayshore Furniture Outlet" in activity and "12.4 mi" in activity

    # The lamp was bought from Hayes Home & Lighting in brass.
    orders = api.get("/api/orders").json()
    lamp = next(ln for o in orders for ln in o["lines"] if ln["item"] == "Lamp")
    assert lamp["color"] == "brass"
    assert all(o["card"] == "Visa •••• 4242" for o in orders)

    # Running again creates no duplicate orders.
    assert api.post("/api/demo/run").json()["placed"] == []
    assert len(api.get("/api/orders").json()) == len(orders)

    # Editing a purchased item reports the existing order instead.
    r = api.patch(f"/api/items/{items['Whole milk']['id']}", json={"quantity": 2})
    assert r.status_code == 409 and r.json()["detail"]["order_id"]

    # Removing the chair invalidates its pending approval.
    approval_id = run["approvals"][0]
    api.delete(f"/api/items/{items['Dining chair']['id']}")
    statuses = {a["id"]: a["status"] for a in api.get("/api/approvals").json()}
    assert statuses[approval_id] == "invalidated"
    assert api.post(f"/api/approvals/{approval_id}/approve").status_code == 409


def test_sofa_blocked_even_though_approvable_rules_apply(api):
    sofa = api.post("/api/items", json={"name": "Sofa", "category": "furniture", "color": "emerald"}).json()
    api.post("/api/demo/run")
    item = next(i for i in api.get("/api/items").json() if i["id"] == sofa["id"])
    assert item["status"] == "blocked"
    assert "can't be approved" in item["status_reason"]


def test_approval_then_purchase(api):
    api.post("/api/demo/run")
    approval = next(a for a in api.get("/api/approvals").json() if a["status"] == "pending")
    assert {r["code"] for r in approval["reasons"]} >= {"order_limit", "step_up"}
    assert approval["budget"]["remaining_after"]
    res = api.post(f"/api/approvals/{approval['id']}/approve").json()
    assert res["approval"]["status"] == "used" and res["run"]["placed"]
    assert items_by_name(api)["Dining chair"]["status"] == "purchased"


def test_approval_after_hours_waits_for_next_window(api):
    api.post("/api/demo/run")
    approval = next(a for a in api.get("/api/approvals").json() if a["status"] == "pending")
    api.post("/api/demo/clock", json={"at": "17:15", "on": "2026-10-14"})
    res = api.post(f"/api/approvals/{approval['id']}/approve").json()
    assert res["approval"]["status"] == "approved" and res["run"]["placed"] == []
    api.post("/api/demo/clock", json={"at": "10:00", "on": "2026-10-15"})
    assert api.post("/api/demo/run").json()["placed"]
    assert items_by_name(api)["Dining chair"]["status"] == "purchased"


def test_outside_hours_and_pause(api):
    api.post("/api/demo/clock", json={"at": "08:30", "on": "2026-10-14"})
    assert "Outside shopping hours" in api.post("/api/demo/run").json()["note"]
    api.post("/api/demo/clock", json={"at": "11:00", "on": "2026-10-14"})
    api.patch("/api/settings", json={"paused": True})
    assert api.post("/api/demo/run").json()["note"] == "Shopping is paused."
    assert api.get("/api/orders").json() == []


def test_daily_summary(api):
    api.post("/api/demo/run")
    api.post("/api/demo/clock", json={"at": "17:05", "on": "2026-10-14"})
    api.post("/api/demo/run")  # auto-sends the summary after the window closes
    summary = next(n for n in api.get("/api/notifications").json() if n["kind"] == "daily_summary")
    body = summary["body"]
    assert body["orders"] and body["pending_approvals"] and body["blocked"]
    assert body["remaining_budget"]


def test_card_api_never_returns_full_number(api):
    r = api.put("/api/card", json={"number": "5555 5555 5555 4444", "exp_month": 1, "exp_year": 2030,
                                   "cvc": "123", "name": "Mike", "zip": "94111"})
    assert r.status_code == 200
    assert "5555555555554444" not in r.text and r.json()["card"]["last4"] == "4444"
    bad = api.put("/api/card", json={"number": "4012888888881881", "exp_month": 1, "exp_year": 2030,
                                     "name": "Mike"})
    assert bad.status_code == 422


def test_wallet_flow(api):
    from decimal import Decimal

    api.post(f"/api/items/{items_by_name(api)['Lamp']['id']}/answer", json={"answer": "brass please"})
    api.patch("/api/settings", json={"payment_method": "wallet"})
    assert api.get("/api/settings").json()["setup_complete"]  # preload links the test bank

    # $0 balance: carts wait and one low-balance notice goes out, even across runs.
    run = api.post("/api/demo/run").json()
    assert run["placed"] == [] and run["deferred"] >= 2
    milk = items_by_name(api)["Whole milk"]
    assert milk["status"] == "ready" and "Add funds" in milk["status_reason"]
    api.post("/api/demo/run")
    notices = [n for n in api.get("/api/notifications").json() if n["kind"] == "low_balance"]
    assert len(notices) == 1

    assert api.post("/api/wallet/deposits", json={"amount": "250.00"}).json()["balance"] == "250.00"
    run = api.post("/api/demo/run").json()
    assert len(run["placed"]) >= 2
    orders = api.get("/api/orders").json()
    assert all(o["card"] == "Wallet" for o in orders)
    spent = sum(Decimal(o["total"]) for o in orders)
    w = api.get("/api/wallet").json()
    assert Decimal(w["balance"]) == Decimal("250.00") - spent
    assert sorted(e["kind"] for e in w["entries"]).count("purchase") == len(orders)

    # Canceling refunds the wallet but not the weekly allowance.
    api.post(f"/api/orders/{orders[0]['id']}/cancel")
    w = api.get("/api/wallet").json()
    assert Decimal(w["balance"]) == Decimal("250.00") - spent + Decimal(orders[0]["total"])
    assert w["entries"][0]["kind"] == "refund"
    api.post("/api/demo/summary")
    summary = next(n for n in api.get("/api/notifications").json() if n["kind"] == "daily_summary")
    assert Decimal(summary["body"]["week_spent"]) == spent
    assert summary["body"]["wallet_balance"] == w["balance"]


def test_wallet_bank_linking(api):
    api.post("/api/demo/reset", json={"preload": False})
    assert api.post("/api/wallet/deposits", json={"amount": "10"}).status_code == 409
    api.patch("/api/settings", json={"payment_method": "wallet"})
    assert "Link a bank account" in api.post("/api/demo/run").json()["note"]

    bad = api.put("/api/wallet/bank", json={"routing_number": "021000021", "account_number": "000123456789",
                                            "holder_name": "Mike"})
    assert bad.status_code == 422
    r = api.put("/api/wallet/bank", json={"routing_number": "110000000", "account_number": "000123456789",
                                          "holder_name": "Mike"})
    assert r.status_code == 200 and r.json()["bank"]["last4"] == "6789"
    assert "000123456789" not in r.text
    assert api.post("/api/wallet/deposits", json={"amount": "0"}).status_code == 422
    assert api.post("/api/wallet/deposits", json={"amount": "5000.01"}).status_code == 422
