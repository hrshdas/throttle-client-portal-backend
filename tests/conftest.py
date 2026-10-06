"""
Test conftest — shared fixtures for the Throttle test suite.

Uses SQLite in-memory database so tests never hit the real PostgreSQL instance.
All tests are fully isolated from production data.
"""

import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.core.database import Base, get_db
from app.core.security import hash_password
from app.core.crypto import encrypt_message
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.models.meta import MetaConnection, MetaConnectionStatus, MetaDailyInsight, MetaInsightLevel, MetaCampaign

import uuid
from datetime import date, datetime, timedelta, timezone

# ── Test database (SQLite in-memory) ──────────────────────────────────────────
# Uses aiosqlite so no PostgreSQL instance is required for tests.
TEST_DATABASE_URL = "sqlite+aiosqlite:///file:testdb?mode=memory&cache=shared&uri=true"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False, "uri": True},
    poolclass=StaticPool,
)
TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)


async def override_get_db():
    async with TestSessionLocal() as session:
        yield session


# Override the DB dependency so every test route uses the in-memory SQLite DB
app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_db():
    """Create all tables once per test session."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="session")
async def seed_data():
    """
    Seed test organizations, users, and Meta connections.

    BLUEFORCE: has a connected Meta account with synced insights
    Acme Corp: has NO Meta connection
    """
    async with TestSessionLocal() as db:
        # ── BLUEFORCE org ─────────────────────────────────────────────────────
        blueforce_org = Organization(
            id=str(uuid.uuid4()),
            name="BLUEFORCE",
            slug="blueforce",
        )
        db.add(blueforce_org)
        await db.flush()

        blueforce_user = User(
            id=str(uuid.uuid4()),
            organization_id=blueforce_org.id,
            name="Raj",
            email="raj@blueforce.com",
            hashed_password=hash_password("password123"),
            role=UserRole.CLIENT_ADMIN,
            is_active=True,
        )
        db.add(blueforce_user)

        # ── Acme Corp org ─────────────────────────────────────────────────────
        acme_org = Organization(
            id=str(uuid.uuid4()),
            name="Acme Corp",
            slug="acme",
        )
        db.add(acme_org)
        await db.flush()

        acme_user = User(
            id=str(uuid.uuid4()),
            organization_id=acme_org.id,
            name="John",
            email="john@acme.com",
            hashed_password=hash_password("password123"),
            role=UserRole.CLIENT_ADMIN,
            is_active=True,
        )
        db.add(acme_user)

        # ── Admin user ────────────────────────────────────────────────────────
        admin_org = Organization(
            id=str(uuid.uuid4()),
            name="Throttle Agency",
            slug="throttle-agency",
        )
        db.add(admin_org)
        await db.flush()

        admin_user = User(
            id=str(uuid.uuid4()),
            organization_id=admin_org.id,
            name="Throttle Admin",
            email="admin@throttle.agency",
            hashed_password=hash_password("admin123"),
            role=UserRole.THROTTLE_ADMIN,
            is_active=True,
        )
        db.add(admin_user)

        # ── BLUEFORCE Meta connection ──────────────────────────────────────────
        meta_conn = MetaConnection(
            id=str(uuid.uuid4()),
            organization_id=blueforce_org.id,
            meta_user_id="meta_user_123",
            ad_account_id="act_1001",
            ad_account_name="BLUEFORCE Official Meta Ads",
            encrypted_access_token=encrypt_message("mock_token_for_tests"),
            status=MetaConnectionStatus.SYNCED,
            last_synced_at=datetime.now(timezone.utc),
        )
        db.add(meta_conn)

        # ── BLUEFORCE campaigns ───────────────────────────────────────────────
        campaign1 = MetaCampaign(
            id=str(uuid.uuid4()),
            organization_id=blueforce_org.id,
            ad_account_id="act_1001",
            meta_campaign_id="cmp_001",
            name="Q3 Performance Max — Conversions & Retargeting",
            status="ACTIVE",
            objective="OUTCOME_SALES",
        )
        campaign2 = MetaCampaign(
            id=str(uuid.uuid4()),
            organization_id=blueforce_org.id,
            ad_account_id="act_1001",
            meta_campaign_id="cmp_002",
            name="High-Intent Lead Gen",
            status="ACTIVE",
            objective="OUTCOME_LEADS",
        )
        campaign3 = MetaCampaign(
            id=str(uuid.uuid4()),
            organization_id=blueforce_org.id,
            ad_account_id="act_1001",
            meta_campaign_id="cmp_003",
            name="Brand Awareness",
            status="PAUSED",
            objective="OUTCOME_AWARENESS",
        )
        db.add_all([campaign1, campaign2, campaign3])

        # ── BLUEFORCE daily insights (last 30 days at account level) ──────────
        today = date.today()
        for i in range(30):
            d = today - timedelta(days=i)
            spend = 500.0 + (i * 10.0)
            impressions = int(spend * 22)
            clicks = int(impressions * 0.024)
            leads = int(clicks * 0.04)
            conversion_value = spend * 4.2

            db.add(MetaDailyInsight(
                id=str(uuid.uuid4()),
                organization_id=blueforce_org.id,
                ad_account_id="act_1001",
                level=MetaInsightLevel.ACCOUNT,
                date=d,
                spend=round(spend, 2),
                impressions=impressions,
                reach=int(impressions * 0.7),
                clicks=clicks,
                link_clicks=int(clicks * 0.8),
                ctr=round(clicks / impressions * 100.0, 4) if impressions else 0.0,
                cpc=round(spend / clicks, 2) if clicks else 0.0,
                cpm=round(spend / impressions * 1000.0, 2) if impressions else 0.0,
                leads=leads,
                cpl=round(spend / leads, 2) if leads else None,
                conversions=int(leads * 0.6),
                conversion_value=round(conversion_value, 2),
                roas=round(conversion_value / spend, 4) if spend else None,
            ))

        await db.commit()

        return {
            "blueforce_org_id": blueforce_org.id,
            "acme_org_id": acme_org.id,
            "admin_org_id": admin_org.id,
            "blueforce_user_email": "raj@blueforce.com",
            "acme_user_email": "john@acme.com",
        }


@pytest_asyncio.fixture(scope="session")
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture(scope="session")
async def blueforce_token(client, seed_data):
    res = await client.post(
        "/api/v1/auth/login",
        json={"email": "raj@blueforce.com", "password": "password123"},
    )
    assert res.status_code == 200, f"BLUEFORCE login failed: {res.text}"
    return res.json()["access_token"]


@pytest_asyncio.fixture(scope="session")
async def acme_token(client, seed_data):
    res = await client.post(
        "/api/v1/auth/login",
        json={"email": "john@acme.com", "password": "password123"},
    )
    assert res.status_code == 200, f"Acme login failed: {res.text}"
    return res.json()["access_token"]


@pytest_asyncio.fixture(scope="session")
async def admin_token(client, seed_data):
    res = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@throttle.agency", "password": "admin123"},
    )
    assert res.status_code == 200, f"Admin login failed: {res.text}"
    return res.json()["access_token"]
