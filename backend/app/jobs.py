"""Scheduled jobs. Run inside the API process (CRM_RUN_SCHEDULER=true) or from cron:

  python -m app.jobs renewals
"""
from __future__ import annotations

import asyncio
import logging
import sys

from sqlalchemy import text

from .db import SessionLocal
from .entitlements import send_renewal_notices

log = logging.getLogger("crm.jobs")
LOCK_ID = 74210601  # pg advisory lock: only one API worker runs the job at a time
INTERVAL_SECONDS = 6 * 3600  # the job is idempotent, so checking a few times a day is harmless


def run_renewals() -> int:
    with SessionLocal() as db:
        if not db.scalar(text("SELECT pg_try_advisory_xact_lock(:id)"), {"id": LOCK_ID}):
            return 0
        n = send_renewal_notices(db)  # commits, which also releases the lock
        if n:
            log.info("Renewal notices sent for %s account(s)", n)
        return n


async def scheduler() -> None:
    await asyncio.sleep(30)  # let the API finish starting
    while True:
        try:
            await asyncio.to_thread(run_renewals)
        except Exception:  # noqa: BLE001 - keep the loop alive; the next run retries
            log.exception("Renewal check failed")
        await asyncio.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    if sys.argv[1:] != ["renewals"]:
        print("usage: python -m app.jobs renewals", file=sys.stderr)
        raise SystemExit(2)
    print(f"Accounts notified: {run_renewals()}")
