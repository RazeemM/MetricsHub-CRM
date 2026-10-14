from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import SessionLocal
from .routers import accounts, activities, contacts, core, dashboard, imports, opportunities, products, quotes, sso
from .seed import seed


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    if "localhost" not in settings.app_url and (
        settings.secret_key.startswith("dev-only") or len(settings.secret_key) < 32
    ):
        raise RuntimeError("Set CRM_SECRET_KEY to a long random value before running in production")
    with SessionLocal() as db:
        seed(db)
    yield


app = FastAPI(title="MetricsHub & Sentry CRM", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (core, sso, accounts, contacts, products, opportunities, activities, imports, dashboard, quotes):
    app.include_router(r.router)


@app.get("/api/health", tags=["health"])
def health():
    return {"status": "ok"}
