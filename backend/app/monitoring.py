"""Health checks and statistics: /api/health/ready, /api/monitoring/status (admin page, MetricsHub) and /api/metrics
(Prometheus). Counters kept in memory (requests, email sends) start again from zero when the API restarts."""
from __future__ import annotations

import datetime as dt
import os
import threading
import time
from collections import deque
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from . import mail
from .config import get_settings
from .models import (
    Account, Activity, Campaign, CampaignRecipient, Contact, Entitlement, FormSubmission, ImportJob, MailingList,
    Opportunity, Quote, Stage, User,
)

VERSION = "0.1.0"
STARTED = time.time()
STATUSES = ("ok", "degraded", "failed")  # worst last
SKIP_PATHS = ("/api/health", "/api/monitoring", "/api/metrics")  # the monitoring tools' own polling
SCHEDULER_STALE_SECONDS = 5 * 60  # campaign sending runs every 30 s
MAIL_FAILURE_WINDOW = dt.timedelta(hours=1)
BACKUP_DEGRADED_HOURS, BACKUP_FAILED_HOURS = 26, 50  # nightly backup: one missed night degrades, two fail
DISK_DEGRADED, DISK_FAILED = 0.10, 0.03  # free space ratio on the backup volume

_lock = threading.Lock()
_http = {"requests": 0, "client_errors": 0, "server_errors": 0, "duration_seconds": 0.0}
_mail = {(p, s): 0 for p in ("transactional", "bulk") for s in ("sent", "failed")}
mail_failures: deque[dict] = deque(maxlen=20)
job_runs: dict[str, float] = {}  # job name -> time of the last completed run


def now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def record_request(path: str, status_code: int, seconds: float) -> None:
    if path.startswith(SKIP_PATHS) or not path.startswith("/api/"):
        return
    with _lock:
        _http["requests"] += 1
        _http["duration_seconds"] += seconds
        if 400 <= status_code < 500:
            _http["client_errors"] += 1
        elif status_code >= 500:
            _http["server_errors"] += 1


def record_mail(purpose: str, ok: bool, msg: mail.Message | None = None, error: str = "") -> None:
    with _lock:
        _mail[("bulk" if purpose == "bulk" else "transactional", "sent" if ok else "failed")] += 1
        if not ok:
            mail_failures.appendleft({"at": now().isoformat(), "purpose": purpose, "error": error[:500],
                                      "sender": msg.sender if msg else None, "to": ", ".join(msg.to) if msg else None})


def record_job(name: str) -> None:
    job_runs[name] = time.time()


def reset() -> None:
    """Tests: start the in-memory counters again."""
    with _lock:
        _http.update(requests=0, client_errors=0, server_errors=0, duration_seconds=0.0)
        _mail.update({k: 0 for k in _mail})
        mail_failures.clear()
        job_runs.clear()


def worst(statuses) -> str:
    return max(statuses, key=STATUSES.index, default="ok")


def _check(name: str, label: str, status: str, message: str, **extra) -> dict:
    return {"name": name, "label": label, "status": status, "message": message, **extra}


# ---------------------------------------------------------------- checks
def check_database(db: Session) -> dict:
    start = time.perf_counter()
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - any driver error means the database is unreachable
        db.rollback()
        return _check("database", "Database", "failed", f"Cannot reach the database: {exc}"[:500])
    ms = round((time.perf_counter() - start) * 1000, 1)
    return _check("database", "Database", "ok", f"Responding in {ms} ms", latency_ms=ms)


def _alembic_head() -> str | None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    ini = Path(__file__).resolve().parents[1] / "alembic.ini"
    return ScriptDirectory.from_config(Config(str(ini))).get_current_head() if ini.exists() else None


def check_migrations(db: Session) -> dict:
    try:
        current = db.scalar(text("SELECT version_num FROM alembic_version LIMIT 1"))
    except Exception:  # noqa: BLE001 - no alembic_version table (tests create the schema directly)
        db.rollback()
        current = None
    head = _alembic_head()
    if current is None:
        return _check("migrations", "Database schema", "ok", "Schema not managed by Alembic here", head=head)
    if head and current != head:
        return _check("migrations", "Database schema", "degraded",
                      f"Database is at revision {current}, the code expects {head}: run `alembic upgrade head`",
                      current=current, head=head)
    return _check("migrations", "Database schema", "ok", f"Up to date ({current})", current=current, head=head)


def check_mail(db: Session) -> dict:
    tx, bulk = mail.status("transactional"), mail.status("bulk")
    info = {"backend": tx["backend"], "bulk_backend": bulk["backend"], "sender": tx["fixed_sender"]}
    problems = [f"{label} email is set to {st['backend']} but its settings are incomplete"
                for label, st in (("Transactional", tx), ("Campaign", bulk))
                if st["backend"] != "disabled" and not st["enabled"]]
    since = (now() - MAIL_FAILURE_WINDOW).isoformat()
    recent = [f for f in mail_failures if f["at"] >= since]
    if recent:
        problems.append(f"{len(recent)} send(s) failed in the last hour. Last: {recent[0]['error']}")
    paused = db.execute(select(Campaign.name, Campaign.last_error).where(Campaign.status == "paused")).all()
    problems += [f"Campaign “{name}” paused: {err or 'no reason recorded'}" for name, err in paused]
    if problems:
        return _check("mail", "Email", "degraded", " · ".join(problems)[:1000], **info)
    if tx["backend"] == "disabled" and bulk["backend"] == "disabled":
        return _check("mail", "Email", "ok", "Email sending is turned off (CRM_MAIL_BACKEND=disabled)", **info)
    return _check("mail", "Email", "ok", f"Sending through {tx['backend']}", **info)


def check_scheduler() -> dict | None:
    if not get_settings().run_scheduler:
        return None  # jobs run from cron: nothing to see from the API
    last = job_runs.get("campaigns")
    if last is None:
        if time.time() - STARTED < SCHEDULER_STALE_SECONDS:
            return _check("scheduler", "Background jobs", "ok", "Starting")
        return _check("scheduler", "Background jobs", "failed", "Campaign sending has not run since the API started")
    age = time.time() - last
    if age > SCHEDULER_STALE_SECONDS:
        return _check("scheduler", "Background jobs", "failed", f"Campaign sending last ran {int(age // 60)} min ago",
                      last_run=dt.datetime.fromtimestamp(last, dt.UTC).isoformat())
    return _check("scheduler", "Background jobs", "ok", f"Last ran {int(age)} s ago",
                  last_run=dt.datetime.fromtimestamp(last, dt.UTC).isoformat())


def backups() -> dict | None:
    """The backup container's dumps, when their folder is mounted into the API (CRM_BACKUP_DIR)."""
    folder = Path(get_settings().backup_dir)
    if not get_settings().backup_dir or not folder.is_dir():
        return None
    files = sorted((p for p in folder.glob("crm-*.dump") if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)
    disk = os.statvfs(folder) if hasattr(os, "statvfs") else None
    total = disk.f_blocks * disk.f_frsize if disk else None
    free = disk.f_bavail * disk.f_frsize if disk else None
    last = files[0] if files else None
    return {
        "count": len(files), "total_bytes": sum(p.stat().st_size for p in files),
        "last_file": last.name if last else None, "last_bytes": last.stat().st_size if last else None,
        "last_at": dt.datetime.fromtimestamp(last.stat().st_mtime, dt.UTC).isoformat() if last else None,
        "age_seconds": int(time.time() - last.stat().st_mtime) if last else None,
        "disk_total_bytes": total, "disk_free_bytes": free,
        "recent": [{"file": p.name, "bytes": p.stat().st_size,
                    "at": dt.datetime.fromtimestamp(p.stat().st_mtime, dt.UTC).isoformat()} for p in files[:7]],
    }


def check_backups(info: dict | None) -> dict | None:
    if info is None:
        return None
    problems, status = [], "ok"
    if not info["count"]:
        status, problems = "failed", ["No backup found"]
    else:
        hours = info["age_seconds"] / 3600
        if hours > BACKUP_FAILED_HOURS:
            status = "failed"
        elif hours > BACKUP_DEGRADED_HOURS:
            status = "degraded"
        if status != "ok":
            problems.append(f"Last backup is {hours:.0f} hours old")
        if not info["last_bytes"]:
            status, problems = "failed", [*problems, "Last backup is empty"]
    if info["disk_total_bytes"]:
        ratio = info["disk_free_bytes"] / info["disk_total_bytes"]
        if ratio < DISK_DEGRADED:
            status = worst([status, "failed" if ratio < DISK_FAILED else "degraded"])
            problems.append(f"Only {ratio:.0%} disk space free")
    message = " · ".join(problems) or f"Last backup {info['last_file']}, {info['age_seconds'] // 3600} h ago"
    return _check("backups", "Backups", status, message)


def checks(db: Session, backup_info: dict | None = None) -> list[dict]:
    db_check = check_database(db)
    if db_check["status"] == "failed":
        return [db_check]
    found = [db_check, check_migrations(db), check_mail(db), check_scheduler(), check_backups(backup_info)]
    return [c for c in found if c]


# ---------------------------------------------------------------- statistics
def _counts(db: Session, column, *where) -> dict[str, int]:
    return dict(db.execute(select(column, func.count()).where(*where).group_by(column)).all())


def records(db: Session) -> dict:
    count = lambda model, *where: db.scalar(select(func.count()).select_from(model).where(*where)) or 0  # noqa: E731
    open_ids = select(Stage.id).where(Stage.kind == "open")
    return {
        "accounts": count(Account), "contacts": count(Contact), "opportunities": count(Opportunity),
        "open_opportunities": count(Opportunity, Opportunity.stage_id.in_(open_ids)),
        "quotes": count(Quote), "licences": count(Entitlement), "activities": count(Activity),
        "campaigns": count(Campaign), "lists": count(MailingList), "users": count(User),
    }


def users(db: Session) -> dict:
    since = lambda **kw: now() - dt.timedelta(**kw)  # noqa: E731
    count = lambda *where: db.scalar(select(func.count()).select_from(User).where(*where)) or 0  # noqa: E731
    return {"enabled": count(User.is_active.is_(True)), "active_24h": count(User.last_login_at >= since(days=1)),
            "active_7d": count(User.last_login_at >= since(days=7))}


def email(db: Session) -> dict:
    recipients = _counts(db, CampaignRecipient.status)
    campaigns = _counts(db, Campaign.status)
    with _lock:
        sends = {f"{p}_{s}": n for (p, s), n in _mail.items()}
    return {
        "backend": mail.backend_for("transactional"), "bulk_backend": mail.backend_for("bulk"),
        **sends,  # since the API started
        "recipients_queued": recipients.get("queued", 0), "recipients_sent": recipients.get("sent", 0),
        "recipients_failed": recipients.get("failed", 0), "recipients_skipped": recipients.get("skipped", 0),
        "campaigns_sending": campaigns.get("sending", 0) + campaigns.get("scheduled", 0),
        "campaigns_paused": campaigns.get("paused", 0),
    }


def forms(db: Session) -> dict:
    by = _counts(db, FormSubmission.status)
    day = db.scalar(select(func.count()).select_from(FormSubmission)
                    .where(FormSubmission.created_at >= now() - dt.timedelta(days=1))) or 0
    return {"accepted": by.get("accepted", 0) + by.get("confirmed", 0), "pending": by.get("pending", 0),
            "spam": by.get("spam", 0), "error": by.get("error", 0), "last_24h": day}


def database(db: Session) -> dict:
    row = db.execute(text("SELECT pg_database_size(current_database()), "
                          "(SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()), "
                          "current_setting('max_connections')::int, current_setting('server_version')")).one()
    return {"size_bytes": row[0], "connections": row[1], "max_connections": row[2], "version": row[3]}


def largest_tables(db: Session, limit: int = 10) -> list[dict]:
    rows = db.execute(text("SELECT relname, n_live_tup, pg_total_relation_size(relid) FROM pg_stat_user_tables "
                           "ORDER BY pg_total_relation_size(relid) DESC LIMIT :n"), {"n": limit}).all()
    return [{"table": r[0], "rows": r[1], "bytes": r[2]} for r in rows]


def recent(db: Session) -> dict:
    failed = db.execute(
        select(CampaignRecipient.email, CampaignRecipient.reason, CampaignRecipient.sent_at, Campaign.name)
        .join(Campaign, Campaign.id == CampaignRecipient.campaign_id)
        .where(CampaignRecipient.status == "failed").order_by(CampaignRecipient.id.desc()).limit(10)).all()
    imports = db.scalars(select(ImportJob).order_by(ImportJob.id.desc()).limit(5)).all()
    logins = db.scalars(select(User).where(User.last_login_at.is_not(None))
                        .order_by(User.last_login_at.desc()).limit(10)).all()
    paused = db.execute(select(Campaign.id, Campaign.name, Campaign.last_error).where(Campaign.status == "paused")).all()
    return {
        "mail_failures": list(mail_failures),
        "campaign_failures": [{"email": r[0], "reason": r[1], "at": r[2].isoformat() if r[2] else None,
                               "campaign": r[3]} for r in failed],
        "paused_campaigns": [{"id": r[0], "name": r[1], "error": r[2]} for r in paused],
        "imports": [{"id": j.id, "entity": j.entity, "filename": j.filename, "total": j.total, "created": j.created,
                     "updated": j.updated, "skipped": j.skipped, "errors": len(j.errors or []),
                     "at": j.created_at.isoformat() if j.created_at else None} for j in imports],
        "logins": [{"name": u.full_name, "email": u.email, "role": u.role, "at": u.last_login_at.isoformat()}
                   for u in logins],
    }


def http() -> dict:
    with _lock:
        h = dict(_http)
    h["duration_seconds"] = round(h["duration_seconds"], 3)
    h["average_ms"] = round(h["duration_seconds"] * 1000 / h["requests"], 1) if h["requests"] else None
    return h


def status(db: Session, detail: bool = True) -> dict:
    backup_info = backups()
    found = checks(db, backup_info)
    out = {
        "service": "metricshub-crm", "version": VERSION, "status": worst(c["status"] for c in found),
        "checked_at": now().isoformat(), "started_at": dt.datetime.fromtimestamp(STARTED, dt.UTC).isoformat(),
        "uptime_seconds": int(time.time() - STARTED), "checks": found,
    }
    if not detail or found[0]["status"] == "failed":
        return out
    out.update(http=http(), records=records(db), users=users(db), email=email(db), forms=forms(db),
               database=database(db), backups=backup_info)
    out["recent"] = recent(db)
    out["tables"] = largest_tables(db)
    return out


# ---------------------------------------------------------------- Prometheus text format
def _labels(**kw) -> str:
    return "{" + ",".join(f'{k}="{v}"' for k, v in kw.items()) + "}" if kw else ""


def prometheus(s: dict) -> str:
    lines: list[str] = []

    def metric(name: str, kind: str, help_: str, values: list[tuple[dict, float | int | None]]) -> None:
        values = [(lbl, v) for lbl, v in values if v is not None]
        if not values:
            return
        lines.extend([f"# HELP {name} {help_}", f"# TYPE {name} {kind}"])
        lines.extend(f"{name}{_labels(**lbl)} {v}" for lbl, v in values)

    metric("crm_up", "gauge", "1 when every check is ok, 0.5 when degraded, 0 when failed",
           [({}, {"ok": 1, "degraded": 0.5, "failed": 0}[s["status"]])])
    metric("crm_check_status", "gauge", "Health check state (1 = in this state)",
           [({"check": c["name"], "state": st}, int(c["status"] == st)) for c in s["checks"] for st in STATUSES])
    metric("crm_uptime_seconds", "gauge", "Seconds since the API started", [({}, s["uptime_seconds"])])
    metric("crm_info", "gauge", "Version", [({"version": s["version"]}, 1)])
    if "http" not in s:
        return "\n".join(lines) + "\n"
    h = s["http"]
    metric("crm_http_requests_total", "counter", "API requests since the API started", [({}, h["requests"])])
    metric("crm_http_errors_total", "counter", "API requests answered with an error",
           [({"class": "4xx"}, h["client_errors"]), ({"class": "5xx"}, h["server_errors"])])
    metric("crm_http_request_duration_seconds_total", "counter", "Time spent answering API requests",
           [({}, h["duration_seconds"])])
    metric("crm_records", "gauge", "Records by object", [({"object": k}, v) for k, v in s["records"].items()])
    metric("crm_users", "gauge", "Users enabled and recently signed in",
           [({"state": k}, v) for k, v in s["users"].items()])
    e = s["email"]
    metric("crm_email_messages_total", "counter", "Emails sent or failed since the API started",
           [({"purpose": p, "state": st}, e[f"{p}_{st}"]) for p in ("transactional", "bulk") for st in ("sent", "failed")])
    metric("crm_campaign_recipients", "gauge", "Campaign recipients by state",
           [({"state": st}, e[f"recipients_{st}"]) for st in ("queued", "sent", "failed", "skipped")])
    metric("crm_campaigns", "gauge", "Campaigns sending or paused",
           [({"state": "sending"}, e["campaigns_sending"]), ({"state": "paused"}, e["campaigns_paused"])])
    metric("crm_form_submissions", "gauge", "Website form submissions by state",
           [({"state": k}, v) for k, v in s["forms"].items() if k != "last_24h"])
    d = s["database"]
    metric("crm_database_size_bytes", "gauge", "Database size", [({}, d["size_bytes"])])
    metric("crm_database_connections", "gauge", "Open database connections", [({}, d["connections"])])
    if b := s.get("backups"):
        metric("crm_backup_age_seconds", "gauge", "Age of the last backup", [({}, b["age_seconds"])])
        metric("crm_backup_size_bytes", "gauge", "Size of the last backup", [({}, b["last_bytes"])])
        metric("crm_backup_files", "gauge", "Backups kept", [({}, b["count"])])
        metric("crm_backup_disk_free_bytes", "gauge", "Free space on the backup volume", [({}, b["disk_free_bytes"])])
    return "\n".join(lines) + "\n"
