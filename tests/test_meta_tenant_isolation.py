"""
Tests: Meta tenant isolation.

Proves that:
- BLUEFORCE users see only BLUEFORCE Meta data
- Acme Corp users see only Acme Corp data (empty — no Meta connection)
- Cross-org access is impossible through any analytics or meta endpoint
"""

import pytest


@pytest.mark.asyncio
async def test_blueforce_meta_connection_exists(client, blueforce_token, seed_data):
    """BLUEFORCE has a connected Meta account."""
    res = await client.get(
        "/api/v1/meta/connection",
        headers={"Authorization": f"Bearer {blueforce_token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("CONNECTED", "SYNCED", "SYNCING")
    assert data["ad_account_name"] == "BLUEFORCE Official Meta Ads"
    # Token MUST never be exposed
    assert "encrypted_access_token" not in data
    assert "access_token" not in data


@pytest.mark.asyncio
async def test_acme_meta_connection_not_found(client, acme_token, seed_data):
    """Acme Corp has no Meta connection — must return 404."""
    res = await client.get(
        "/api/v1/meta/connection",
        headers={"Authorization": f"Bearer {acme_token}"},
    )
    assert res.status_code == 404
    assert "not connected" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_blueforce_overview_has_real_data(client, blueforce_token, seed_data):
    """BLUEFORCE overview analytics returns non-zero values from synced insights."""
    res = await client.get(
        "/api/v1/analytics/overview?range=30d",
        headers={"Authorization": f"Bearer {blueforce_token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["spend"] > 0, "BLUEFORCE spend should be positive"
    assert data["impressions"] > 0, "BLUEFORCE impressions should be positive"
    assert data["clicks"] > 0, "BLUEFORCE clicks should be positive"
    assert data["roas"] is not None, "BLUEFORCE ROAS should be available"
    assert data["connection_status"] in ("CONNECTED", "SYNCED")


@pytest.mark.asyncio
async def test_acme_overview_returns_zeros(client, acme_token, seed_data):
    """Acme Corp analytics returns zero-state (no data, not an error)."""
    res = await client.get(
        "/api/v1/analytics/overview?range=30d",
        headers={"Authorization": f"Bearer {acme_token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["spend"] == 0.0
    assert data["impressions"] == 0
    assert data["roas"] is None
    assert data["connection_status"] == "DISCONNECTED"


@pytest.mark.asyncio
async def test_blueforce_campaigns_visible(client, blueforce_token, seed_data):
    """BLUEFORCE user sees their own campaigns."""
    res = await client.get(
        "/api/v1/analytics/campaigns",
        headers={"Authorization": f"Bearer {blueforce_token}"},
    )
    assert res.status_code == 200
    campaigns = res.json()
    assert len(campaigns) >= 3
    names = [c["name"] for c in campaigns]
    assert any("Performance Max" in name for name in names)
    assert any("Lead Gen" in name for name in names)


@pytest.mark.asyncio
async def test_acme_campaigns_empty(client, acme_token, seed_data):
    """Acme Corp user sees empty campaign list (no campaigns seeded for them)."""
    res = await client.get(
        "/api/v1/analytics/campaigns",
        headers={"Authorization": f"Bearer {acme_token}"},
    )
    assert res.status_code == 200
    assert len(res.json()) == 0


@pytest.mark.asyncio
async def test_acme_cannot_access_blueforce_via_org_param(client, acme_token, seed_data):
    """
    Acme user cannot access BLUEFORCE data by passing organization_id query param.
    The backend must ignore the param for non-admin users.
    """
    blueforce_org_id = seed_data["blueforce_org_id"]
    res = await client.get(
        f"/api/v1/analytics/overview?range=30d&organization_id={blueforce_org_id}",
        headers={"Authorization": f"Bearer {acme_token}"},
    )
    assert res.status_code == 200
    # Non-admin: org_id param is ignored, returns their own (zero) data
    assert res.json()["spend"] == 0.0


@pytest.mark.asyncio
async def test_acme_cannot_trigger_blueforce_sync(client, acme_token, seed_data):
    """Acme user cannot trigger a sync for BLUEFORCE's connection."""
    blueforce_org_id = seed_data["blueforce_org_id"]
    # Even passing the org ID should not work for non-admin
    res = await client.post(
        f"/api/v1/meta/sync?organization_id={blueforce_org_id}",
        headers={"Authorization": f"Bearer {acme_token}"},
    )
    # Should either 400 (no connection for acme) or sync acme's own (non-existent) connection
    assert res.status_code in (400, 404, 422)


@pytest.mark.asyncio
async def test_timeseries_tenant_isolation(client, blueforce_token, acme_token, seed_data):
    """Timeseries data is isolated per org."""
    bf_res = await client.get(
        "/api/v1/analytics/timeseries?metric=spend&range=30d",
        headers={"Authorization": f"Bearer {blueforce_token}"},
    )
    acme_res = await client.get(
        "/api/v1/analytics/timeseries?metric=spend&range=30d",
        headers={"Authorization": f"Bearer {acme_token}"},
    )
    assert bf_res.status_code == 200
    assert acme_res.status_code == 200

    bf_data = bf_res.json()
    acme_data = acme_res.json()

    # BLUEFORCE has data
    assert len(bf_data) > 0
    assert all(p["value"] > 0 for p in bf_data)

    # Acme has no data
    assert len(acme_data) == 0


@pytest.mark.asyncio
async def test_unauthenticated_meta_access_rejected(client, seed_data):
    """Unauthenticated requests are rejected."""
    for endpoint in ["/api/v1/meta/connection", "/api/v1/analytics/overview"]:
        res = await client.get(endpoint)
        assert res.status_code == 403, f"Expected 403 for {endpoint}, got {res.status_code}"
