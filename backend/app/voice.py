"""Voice commands: turn what the user said (transcribed by Chrome) into list changes, and a reply to speak.

Claude interprets the words when ANTHROPIC_API_KEY is set, otherwise simple keyword rules. Voice can only
change the shopping list and answer the assistant's questions. Approvals, money, and settings stay in the UI.
"""

import logging
import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import agent, catalog, items
from app.activity import log
from app.models import ListItem, Settings

logger = logging.getLogger(__name__)

Category = Literal["groceries", "household", "lifestyle", "furniture", "other"]


class VoiceItem(BaseModel):
    name: str
    category: Category
    quantity: int
    brand: str | None
    color: str | None
    size: str | None


class VoiceCommand(BaseModel):
    action: Literal["add", "remove", "answer", "status", "unknown"]
    items: list[VoiceItem]
    item_ids: list[int]
    answer_item_id: int | None
    answer: str


@dataclass
class Reply:
    text: str
    action: str
    source: str
    awaiting_answer_item_id: int | None = None


SYSTEM = """You turn one spoken sentence from an older adult into a command for their shopping list app.
The words came from speech recognition, so allow for small transcription mistakes.

action:
- "add": they want things bought. Put each distinct product in items. name is the plain product name
  ("whole milk", "lamp"); move brand, color, and size into their own fields only when they said them.
  quantity defaults to 1. Pick the closest category.
- "remove": they want items taken off the list. Put the matching ids from current_list in item_ids.
- "answer": they're answering one of the assistant's questions (items with a clarification_question).
  Set answer_item_id and copy their answer into answer. If answering_item_id is given, a reply that isn't
  clearly another command answers that item.
- "status": they ask what's on the list or how things are going.
- "unknown": anything else, including requests to approve orders, spend money, add funds, or change
  settings. Those aren't possible by voice.
Leave unused fields empty: items [], item_ids [], answer_item_id null, answer ""."""


def _current_list(db: Session) -> list[ListItem]:
    return list(db.scalars(select(ListItem).where(ListItem.deleted.is_(False)).order_by(ListItem.id)).all())


def interpret(db: Session, text: str, answering_item_id: int | None) -> tuple[VoiceCommand, str]:
    current = _current_list(db)
    if agent.ai_enabled():
        try:
            cmd = agent._claude(SYSTEM, {
                "said": text, "answering_item_id": answering_item_id,
                "current_list": [{"id": i.id, "name": i.name, "status": i.status,
                                  "clarification_question": i.clarification_question} for i in current],
            }, VoiceCommand)
            known = {i.id for i in current}
            cmd.item_ids = [i for i in cmd.item_ids if i in known]
            if cmd.answer_item_id not in known:
                cmd.answer_item_id = None
            return cmd, "ai"
        except Exception:
            logger.exception("voice: falling back to rules")
    return _rules(db, text, answering_item_id, current), "rules"


_NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
            "eight": 8, "nine": 9, "ten": 10, "a couple of": 2, "a dozen": 12}
_ADD = re.compile(r"^(please\s+)?(add|buy|get|order|i need|we need|i want|pick up)\b\s*", re.I)
_REMOVE = re.compile(r"^(please\s+)?(remove|delete|take off|cancel|drop)\b\s*", re.I)
_STATUS = re.compile(r"\b(what'?s|what is|read|tell me)\b.*\b(list|status|on it)\b|\bhow.*going\b", re.I)


def _split(rest: str) -> list[str]:
    rest = re.sub(r"\b(to|from|on|off) (my|the) (shopping )?list\b|\bplease\b", "", rest, flags=re.I)
    return [p.strip(" .") for p in re.split(r",|\band\b", rest) if p.strip(" .")]


def _guess_category(db: Session, name: str) -> str:
    cands = catalog.search(db, ListItem(name=name, category="other"), db.get(Settings, 1))
    cat = cands[0].product.category if cands else "other"
    return cat if cat in Category.__args__ else "other"


def _rules(db: Session, text: str, answering_item_id: int | None, current: list[ListItem]) -> VoiceCommand:
    empty = dict(items=[], item_ids=[], answer_item_id=None, answer="")
    said = text.strip()
    if m := _ADD.match(said):
        out = []
        for part in _split(said[m.end():]):
            qty = 1
            for word, n in sorted(_NUMBERS.items(), key=lambda kv: -len(kv[0])):
                if part.lower().startswith(word + " "):
                    qty, part = n, part[len(word) + 1:]
                    break
            else:
                if dm := re.match(r"(\d+)\s+", part):
                    qty, part = int(dm.group(1)), part[dm.end():]
            part = re.sub(r"^(some|of)\s+", "", part, flags=re.I).strip()
            if part:
                out.append(VoiceItem(name=part[:1].upper() + part[1:], category=_guess_category(db, part),
                                     quantity=min(qty, 99), brand=None, color=None, size=None))
        return VoiceCommand(action="add", **(empty | {"items": out}))
    if m := _REMOVE.match(said):
        wanted = [p.lower() for p in _split(said[m.end():])]
        ids = [i.id for i in current if any(w in i.name.lower() or i.name.lower() in w for w in wanted)]
        return VoiceCommand(action="remove", **(empty | {"item_ids": ids}))
    if _STATUS.search(said):
        return VoiceCommand(action="status", **empty)
    # Only treat it as an answer right after a question was read aloud.
    target = next((i for i in current if i.id == answering_item_id and i.status == "needs_clarification"), None)
    if target:
        return VoiceCommand(action="answer", **(empty | {"answer_item_id": target.id, "answer": said}))
    return VoiceCommand(action="unknown", **empty)


def _join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def _followups(changed: list[ListItem]) -> tuple[list[str], int | None]:
    """Spoken notes about items that were blocked or need an answer, plus the item now awaiting an answer."""
    notes, asking = [], None
    for i in changed:
        if i.status == "blocked":
            notes.append(f"I can't buy {i.name}. {i.status_reason}")
        elif i.status == "needs_clarification" and asking is None:
            notes.append(i.clarification_question)
            asking = i.id
    return notes, asking


def handle(db: Session, text: str, answering_item_id: int | None = None) -> Reply:
    cmd, source = interpret(db, text, answering_item_id)
    log(db, "voice", f'Heard: "{text}"', source=source)
    db.commit()

    if cmd.action == "add" and cmd.items:
        added = [items.create_item(db, **(v.model_dump() | {"name": (v.name[:1].upper() + v.name[1:])[:200], "quantity": max(1, min(v.quantity, 99))}))
                 for v in cmd.items]
        notes, asking = _followups(added)
        labels = [f"{a.quantity} {a.name}" if a.quantity > 1 else a.name for a in added]
        return Reply(" ".join([f"Added {_join(labels)}."] + notes), "add", source, asking)

    if cmd.action == "remove" and cmd.item_ids:
        removed, ordered = [], []
        for item_id in cmd.item_ids:
            item = db.get(ListItem, item_id)
            try:
                items.remove_item(db, item)
                removed.append(item.name)
            except items.AlreadyOrdered:
                ordered.append(item.name)
        parts = [f"Removed {_join(removed)}."] if removed else []
        if ordered:
            parts.append(f"{_join(ordered)} was already ordered. You can cancel it on the Orders page.")
        return Reply(" ".join(parts), "remove", source)

    if cmd.action == "answer" and cmd.answer_item_id and cmd.answer:
        item = items.answer(db, db.get(ListItem, cmd.answer_item_id), cmd.answer)
        notes, asking = _followups([item])
        text_out = " ".join(notes) if notes else f"Thanks. {item.name} is ready to buy."
        return Reply(text_out, "answer", source, asking)

    if cmd.action == "status":
        current = _current_list(db)
        return Reply(_status(current), "status", source,
                     next((i.id for i in current if i.status == "needs_clarification"), None))

    if cmd.action in ("add", "remove"):
        return Reply("Sorry, I didn't catch which items you meant. Could you say that again?", cmd.action, source)
    return Reply("Sorry, I can only add or remove list items, answer my questions, or tell you what's on your "
                 "list. Approvals, money, and settings are in the app.", "unknown", source)


def _status(current: list[ListItem]) -> str:
    if not current:
        return "Your list is empty."
    groups = [("ready to buy", "ready"), ("bought", "purchased"), ("waiting for your approval", "awaiting_approval"),
              ("unavailable nearby", "unavailable"), ("blocked", "blocked")]
    parts = [f"You have {len(current)} item{'s' if len(current) != 1 else ''} on your list."]
    for label, status in groups:
        names = [i.name for i in current if i.status == status]
        if names:
            parts.append(f"{label.capitalize()}: {_join(names)}.")
    asking = [i for i in current if i.status == "needs_clarification"]
    if asking:
        parts.append(f"I have a question about {asking[0].name}. {asking[0].clarification_question}")
    return " ".join(parts)
