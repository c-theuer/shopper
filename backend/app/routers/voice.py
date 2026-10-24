from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import voice
from app.db import get_db

router = APIRouter(prefix="/api")


class VoiceIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    answering_item_id: int | None = None  # the item whose question was just read aloud


@router.post("/voice")
def command(body: VoiceIn, db: Session = Depends(get_db)) -> dict:
    r = voice.handle(db, body.text.strip(), body.answering_item_id)
    return {"reply": r.text, "action": r.action, "source": r.source, "awaiting_answer_item_id": r.awaiting_answer_item_id}
