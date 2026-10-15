"""Scheduled jobs. Run inside the API process (CRM_RUN_SCHEDULER=true) or from cron:

  python -m app.jobs renewals      licence renewal notices
  python -m app.jobs campaigns     send the next batch of queued campaign email (cron: every minute)
"""
from __future__ import annotations

import asyncio
import logging
import sys

from sqlalchemy import text

from . import campaigns
from .db import SessionLocal, engine
from .entitlements import send_renewal_notices

log = logging.getLogger("crm.jobs")
LOCK_ID = 74210601  # pg advisory locks: only one API worker runs a job at a time
CAMPAIGN_LOCK_ID = 74210602
INTERVAL_SECONDS = 6 * 3600  # renewal check: idempotent, so a few times a day is harmless
CAMPAIGN_INTERVAL_SECONDS = 30


def run_renewals() -> int:
    with SessionLocal() as db:
        if not db.scalar(text("SELECT pg_try_advisory_xact_lock(:id)"), {"id": LOCK_ID}):
            return 0
        n = send_renewal_notices(db)  # commits, which also releases the lock
        if n:
            log.info("Renewal notices sent for %s account(s)", n)
        return n


def run_campaigns() -> int:
    # The batch commits several times, so a transaction lock won't do. The session lock lives on a dedicated
    # connection, released on that same connection: a pooled session could unlock on another connection and leave
    # the lock held for good.
    with engine.connect() as lock_conn:
        if not lock_conn.scalar(text("SELECT pg_try_advisory_lock(:id)"), {"id": CAMPAIGN_LOCK_ID}):
            return 0
        try:
            with SessionLocal() as db:
                return campaigns.process(db, interval_seconds=CAMPAIGN_INTERVAL_SECONDS)
        finally:
            lock_conn.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": CAMPAIGN_LOCK_ID})
            lock_conn.commit()


async def _loop(job, interval: int, name: str) -> None:
    await asyncio.sleep(30)  # let the API finish starting
    while True:
        try:
            await asyncio.to_thread(job)
        except Exception:  # noqa: BLE001 - keep the loop alive; the next run retries
            log.exception("%s failed", name)
        await asyncio.sleep(interval)


async def scheduler() -> None:
    await asyncio.gather(_loop(run_renewals, INTERVAL_SECONDS, "Renewal check"),
                         _loop(run_campaigns, CAMPAIGN_INTERVAL_SECONDS, "Campaign sending"))


if __name__ == "__main__":
    jobs = {"renewals": run_renewals, "campaigns": run_campaigns}
    if len(sys.argv) != 2 or sys.argv[1] not in jobs:
        print("usage: python -m app.jobs renewals|campaigns", file=sys.stderr)
        raise SystemExit(2)
    print(f"Done: {jobs[sys.argv[1]]()}")
