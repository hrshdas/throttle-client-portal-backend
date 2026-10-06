"""
Scheduled Meta Sync Script

Runs a Meta data synchronization for all organizations with active connections.
Designed to be invoked by an external scheduler (cron, systemd timer, etc.)

Usage:
    python scripts/scheduled_sync.py

Cron example (sync every 30 minutes):
    */30 * * * * cd /path/to/throttle-backend && python scripts/scheduled_sync.py >> /var/log/throttle_sync.log 2>&1

Systemd timer example:
    See docs/META_SETUP.md for systemd configuration.
"""

import asyncio
import logging
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("scheduled_sync")


async def run_sync():
    from sqlalchemy import select
    from app.core.database import AsyncSessionLocal
    from app.models.meta import MetaConnection, MetaConnectionStatus
    from app.services.meta_sync_service import sync_organization_meta

    async with AsyncSessionLocal() as db:
        # Fetch all orgs with active (non-disconnected) connections
        res = await db.execute(
            select(MetaConnection).where(
                MetaConnection.status != MetaConnectionStatus.DISCONNECTED
            )
        )
        connections = res.scalars().all()

        if not connections:
            logger.info("No active Meta connections to sync.")
            return

        logger.info("Starting scheduled sync for %d organization(s)...", len(connections))

        success_count = 0
        error_count = 0

        for conn in connections:
            try:
                logger.info("Syncing org=%s (account=%s)...", conn.organization_id, conn.ad_account_id)
                async with AsyncSessionLocal() as sync_db:
                    await sync_organization_meta(sync_db, conn.organization_id)
                success_count += 1
                logger.info("✓ Sync complete for org=%s", conn.organization_id)
            except Exception as exc:
                error_count += 1
                logger.error("✗ Sync failed for org=%s: %s", conn.organization_id, exc)

        logger.info(
            "Scheduled sync finished: %d succeeded, %d failed.",
            success_count,
            error_count,
        )


if __name__ == "__main__":
    asyncio.run(run_sync())
