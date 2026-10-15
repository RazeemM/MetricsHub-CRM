import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from .config import get_settings
from .db import SessionLocal
from .routers import (
    accounts, activities, contacts, core, dashboard, email, entitlements, imports, opportunities, products, public,
    quotes, sso, webforms,
)
from .jobs import scheduler
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
    task = asyncio.create_task(scheduler()) if settings.run_scheduler else None
    yield
    if task:
        task.cancel()


app = FastAPI(title="MetricsHub & Sentry CRM", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



@app.middleware("http")
async def public_forms_cors(request: Request, call_next):
    """Websites post their forms from their own domains: the form endpoints answer any origin (without cookies).
    Which websites may post is checked per form (allowed origins and secret)."""
    if not request.url.path.startswith("/api/public/forms/"):
        return await call_next(request)
    response = Response(status_code=204) if request.method == "OPTIONS" else await call_next(request)
    if origin := request.headers.get("origin"):
        response.headers.update({
            "Access-Control-Allow-Origin": origin, "Vary": "Origin", "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, X-CRM-Form-Token, X-CRM-Signature, X-CRM-Timestamp, "
                                            "X-Requested-With",
            "Access-Control-Max-Age": "600"})
        if "access-control-allow-credentials" in response.headers:
            del response.headers["access-control-allow-credentials"]
    return response


for r in (core, sso, accounts, contacts, products, opportunities, activities, imports, dashboard, quotes, entitlements,
          email, public, webforms):
    app.include_router(r.router)


@app.get("/api/health", tags=["health"])
def health():
    return {"status": "ok"}
