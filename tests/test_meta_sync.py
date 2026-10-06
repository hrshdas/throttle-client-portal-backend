"""
Tests: Meta sync service (idempotency, status transitions, dev mode).
"""

import pytest
import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from app.models.meta import MetaConnection, MetaConnectionStatus, MetaDailyInsight, MetaCampaign
from tests.conftest import TestSessionLocal
from app.core.crypto import encrypt_message
from app.services.meta_sync_service import sync_organization_meta


@pytest.mark.asyncio
async def test_sync_status_transition(seed_data):
    """
    Sync transitions status: CONNECTED/SYNCED → SYNCING → SYNCED.
    In dev mode (no real Meta credentials), this uses the demo data path.
    """
    async with TestSessionLocal() as db:
        org_id = seed_data["blueforce_org_id"]
        conn = await sync_organization_meta(db, org_id, days_back=7)
        assert conn.status == MetaConnectionStatus.SYNCED
        assert conn.last_synced_at is not None


@pytest.mark.asyncio
async def test_sync_idempotent(seed_data):
    """
    Running sync twice produces no duplicate records (upsert behavior).
    """
    async with TestSessionLocal() as db:
        org_id = seed_data["blueforce_org_id"]

        # First sync
        await sync_organization_meta(db, org_id, days_back=7)

        # Count records after first sync
        res1 = await db.execute(
            select(MetaDailyInsight).where(
                MetaDailyInsight.organization_id == org_id,
            )
        )
        count1 = len(res1.scalars().all())

        # Second sync — same date range
        await sync_organization_meta(db, org_id, days_back=7)

        # Count must not have increased
        res2 = await db.execute(
            select(MetaDailyInsight).where(
                MetaDailyInsight.organization_id == org_id,
            )
        )
        count2 = len(res2.scalars().all())

        assert count2 == count1, f"Sync not idempotent: {count1} → {count2} records"


@pytest.mark.asyncio
async def test_sync_no_connection_raises(seed_data):
    """Syncing an org with no MetaConnection raises ValueError."""
    async with TestSessionLocal() as db:
        with pytest.raises(ValueError, match="No Meta connection"):
            await sync_organization_meta(db, "org_that_does_not_exist")


@pytest.mark.asyncio
async def test_sync_disconnected_raises(seed_data):
    """Syncing a DISCONNECTED connection raises ValueError."""
    async with TestSessionLocal() as db:
        acme_org_id = seed_data["acme_org_id"]

        # Create a disconnected connection for Acme
        conn = MetaConnection(
            id=str(uuid.uuid4()),
            organization_id=acme_org_id,
            encrypted_access_token=encrypt_message("test_token"),
            status=MetaConnectionStatus.DISCONNECTED,
        )
        db.add(conn)
        await db.commit()

        with pytest.raises(ValueError, match="disconnected"):
            await sync_organization_meta(db, acme_org_id)

        # Cleanup
        await db.delete(conn)
        await db.commit()


@pytest.mark.asyncio
async def test_campaign_upsert_on_resync(seed_data):
    """Existing campaigns are updated (not duplicated) on re-sync."""
    async with TestSessionLocal() as db:
        org_id = seed_data["blueforce_org_id"]

        await sync_organization_meta(db, org_id, days_back=7)

        res1 = await db.execute(
            select(MetaCampaign).where(MetaCampaign.organization_id == org_id)
        )
        campaigns_before = res1.scalars().all()
        count_before = len(campaigns_before)
        names_before = {c.name for c in campaigns_before}

        await sync_organization_meta(db, org_id, days_back=7)

        res2 = await db.execute(
            select(MetaCampaign).where(MetaCampaign.organization_id == org_id)
        )
        campaigns_after = res2.scalars().all()
        count_after = len(campaigns_after)
        names_after = {c.name for c in campaigns_after}

        assert count_after == count_before, "Campaigns duplicated on re-sync"
        assert names_after == names_before
