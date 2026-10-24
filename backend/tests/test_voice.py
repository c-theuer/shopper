"""Voice commands through the API with the rules interpreter (no Claude)."""

from tests.test_flow import api, items_by_name  # noqa: F401  (fixture)


def say(api, text, answering=None):
    r = api.post("/api/voice", json={"text": text, "answering_item_id": answering})
    assert r.status_code == 200
    return r.json()


def test_add_items_with_quantities(api):
    r = say(api, "Add two bananas and paper towels to my list")
    assert r["action"] == "add" and r["source"] == "rules"
    items = items_by_name(api)
    assert items["Bananas"]["quantity"] == 2
    assert items["Paper towels"]["category"] == "household"
    assert "Added 2 Bananas and Paper towels." == r["reply"]


def test_question_is_spoken_and_answer_routes_back(api):
    r = say(api, "I need a lamp")
    lamp_id = r["awaiting_answer_item_id"]
    assert lamp_id and "color" in r["reply"]
    r = say(api, "brass please", answering=lamp_id)
    assert r["action"] == "answer" and "ready to buy" in r["reply"]
    lamp = next(i for i in api.get("/api/items").json() if i["id"] == lamp_id)
    assert lamp["color"] == "brass" and lamp["status"] == "ready"


def test_blocked_item_is_explained(api):
    r = say(api, "buy some ibuprofen")
    assert "can't buy" in r["reply"]


def test_remove_and_status(api):
    r = say(api, "remove the whole milk")
    assert r["reply"] == "Removed Whole milk."
    assert "Whole milk" not in items_by_name(api)
    r = say(api, "what's on my list?")
    assert r["action"] == "status" and "on your list" in r["reply"]


def test_money_and_approvals_are_not_voice_actions(api):
    lamp = items_by_name(api)["Lamp"]
    r = say(api, "approve the dining chair")
    assert r["action"] == "unknown" and "in the app" in r["reply"]
    assert items_by_name(api)["Lamp"]["notes"] == lamp["notes"]  # not taken as an answer
    assert api.get("/api/orders").json() == []
