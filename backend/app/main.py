import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.db import engine
from app.routers import approvals, demo, feed, items, orders, settings, voice, wallet
from app.seed import init_db

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Shopper API", lifespan=lifespan)
for r in (settings.router, items.router, approvals.router, orders.router, feed.router, demo.router,
          wallet.router, voice.router):
    app.include_router(r)


# Cloud Run reserves paths ending in "z" (e.g. /healthz), so use /api/health.
@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/health/db")
def health_db() -> dict:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "database": "reachable"}
