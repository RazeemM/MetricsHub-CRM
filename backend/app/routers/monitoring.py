import base64
import binascii
import hmac

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session

from .. import monitoring
from ..config import get_settings
from ..db import get_db
from ..security import get_current_user

router = APIRouter(prefix="/api", tags=["monitoring"])


def require_monitoring(request: Request, db: Session = Depends(get_db)) -> None:
    """The monitoring token (Bearer, or Basic with the token as password, for tools that only do Basic),
    or a signed-in administrator."""
    scheme, _, credentials = request.headers.get("authorization", "").partition(" ")
    token = get_settings().monitoring_token
    if token and scheme.lower() == "basic":
        try:
            credentials = base64.b64decode(credentials).decode().partition(":")[2]
        except (binascii.Error, UnicodeDecodeError):
            credentials = ""
    if token and hmac.compare_digest(credentials.encode(), token.encode()):
        return
    if scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Monitoring token or administrator sign-in required",
                            headers={"WWW-Authenticate": "Bearer"})
    if get_current_user(credentials, db).role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator role required")


@router.get("/health/ready")
def ready(db: Session = Depends(get_db)):
    """Readiness: 200 unless a check failed (database down, background jobs stopped, backups missing). Degraded checks
    (email problems, pending migrations) still answer 200. Open to all; details need /api/monitoring/status."""
    s = monitoring.status(db, detail=False)
    body = {"status": s["status"], "checks": {c["name"]: c["status"] for c in s["checks"]}}
    return JSONResponse(body, status_code=503 if s["status"] == "failed" else 200)


@router.get("/monitoring/status", dependencies=[Depends(require_monitoring)])
def monitoring_status(db: Session = Depends(get_db)):
    """Checks with their messages, and statistics: requests, records, users, email, forms, database, backups."""
    return monitoring.status(db)


@router.get("/metrics", dependencies=[Depends(require_monitoring)], response_class=PlainTextResponse)
def metrics(db: Session = Depends(get_db)):
    """The same figures in Prometheus text format."""
    return PlainTextResponse(monitoring.prometheus(monitoring.status(db)),
                             media_type="text/plain; version=0.0.4; charset=utf-8")
