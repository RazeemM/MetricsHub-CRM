import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from . import monitoring as stats
from .config import get_settings
from .db import SessionLocal
from .routers import (
    accounts, activities, compose, contacts, core, dashboard, email, entitlements, imports, insights, marketing,
    monitoring, opportunities, products, public, quotes, sso, views, webforms,
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


API_DESCRIPTION = """CRM for MetricsHub and Sentry Software: accounts, contacts, opportunities, quotes, licences
(BMC MarketZone), campaigns and website forms.

**Authentication:** `POST /api/auth/login` (form fields `username`, `password`) returns `access_token`; send it as
`Authorization: Bearer <token>`. Tokens last 12 hours. For integrations and AI agents, use a dedicated user with the
**readonly** role. In this page, click **Authorize** and sign in the same way.

**Lists** are paged with `page` and `page_size` (max 500) and return `items` and `total`. Bulk exports:
`/api/export/{opportunities,accounts,contacts}?fmt=csv|xlsx`."""

# Docs live under /api so they are reachable through the web container's nginx (which only forwards /api/)
app = FastAPI(title="MetricsHub & Sentry CRM", version=stats.VERSION, lifespan=lifespan, description=API_DESCRIPTION,
              docs_url="/api/docs", redoc_url="/api/redoc", openapi_url="/api/openapi.json",
              swagger_ui_parameters={"persistAuthorization": True})
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def count_requests(request: Request, call_next):
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        stats.record_request(request.url.path, 500, time.perf_counter() - start)
        raise
    stats.record_request(request.url.path, response.status_code, time.perf_counter() - start)
    return response


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
          email, marketing, compose, insights, public, webforms, monitoring, views):
    app.include_router(r.router)


@app.get("/api/health", tags=["monitoring"])
def health():
    """Liveness: the API process answers. /api/health/ready also checks the database and background jobs."""
    return {"status": "ok", "service": "metricshub-crm", "version": stats.VERSION}
