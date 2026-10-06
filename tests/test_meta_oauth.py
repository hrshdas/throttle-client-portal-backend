"""
Tests: Meta OAuth state management (CSRF protection).
"""

import pytest
import time
from unittest.mock import patch
from app.core import oauth_state


@pytest.mark.asyncio
async def test_generate_and_validate_state():
    """A freshly generated state validates successfully and returns the org_id."""
    state = oauth_state.generate_state("org_abc123")
    result = oauth_state.validate_state(state)
    assert result == "org_abc123"


@pytest.mark.asyncio
async def test_state_is_single_use():
    """A state token can only be used once — second use returns None."""
    state = oauth_state.generate_state("org_single_use")
    assert oauth_state.validate_state(state) == "org_single_use"
    assert oauth_state.validate_state(state) is None  # Already consumed


@pytest.mark.asyncio
async def test_unknown_state_returns_none():
    """An unknown state token returns None (CSRF protection)."""
    result = oauth_state.validate_state("totally_fake_state_token_xyzzy")
    assert result is None


@pytest.mark.asyncio
async def test_empty_state_returns_none():
    """Empty string state returns None."""
    assert oauth_state.validate_state("") is None


@pytest.mark.asyncio
async def test_expired_state_returns_none():
    """A state that has passed its TTL returns None."""
    state = oauth_state.generate_state("org_expired")
    # Manually set the expiry to the past
    oauth_state._store[state] = ("org_expired", time.monotonic() - 1.0)
    result = oauth_state.validate_state(state)
    assert result is None


@pytest.mark.asyncio
async def test_multiple_orgs_get_distinct_states():
    """Different organizations get distinct, non-colliding states."""
    state_a = oauth_state.generate_state("org_a")
    state_b = oauth_state.generate_state("org_b")

    assert state_a != state_b

    result_b = oauth_state.validate_state(state_b)
    result_a = oauth_state.validate_state(state_a)

    assert result_a == "org_a"
    assert result_b == "org_b"


@pytest.mark.asyncio
async def test_callback_rejects_invalid_state(client, seed_data):
    """OAuth callback with an invalid state returns an error redirect, not 200."""
    res = await client.get(
        "/api/v1/meta/connect/callback?code=fake_code&state=invalid_csrf_state",
        follow_redirects=False,
    )
    # Must redirect (not 200), to an error URL
    assert res.status_code in (302, 307, 308)
    location = res.headers.get("location", "")
    assert "error" in location.lower()
    assert "invalid_state" in location or "error" in location


@pytest.mark.asyncio
async def test_callback_rejects_missing_code(client, seed_data):
    """OAuth callback with missing code returns an error redirect."""
    res = await client.get(
        "/api/v1/meta/connect/callback?state=some_state",
        follow_redirects=False,
    )
    assert res.status_code in (302, 307, 308)
    location = res.headers.get("location", "")
    assert "error" in location.lower()


@pytest.mark.asyncio
async def test_callback_handles_user_denial(client, seed_data):
    """OAuth callback with error param (user denied) redirects gracefully."""
    res = await client.get(
        "/api/v1/meta/connect/callback?error=access_denied&error_description=User+denied+access",
        follow_redirects=False,
    )
    assert res.status_code in (302, 307, 308)
    location = res.headers.get("location", "")
    assert "error" in location.lower()


@pytest.mark.asyncio
async def test_start_connect_requires_auth(client, seed_data):
    """Starting the OAuth flow requires authentication."""
    res = await client.post("/api/v1/meta/connect/start")
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_start_connect_returns_url(client, blueforce_token, seed_data):
    """Authenticated start returns a valid Meta OAuth URL."""
    res = await client.post(
        "/api/v1/meta/connect/start",
        headers={"Authorization": f"Bearer {blueforce_token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "auth_url" in data
    assert "state" in data
    assert "facebook.com" in data["auth_url"]
    assert "ads_read" in data["auth_url"]
    assert "read_insights" not in data["auth_url"]  # Must not use deprecated scope
    assert "response_type=code" in data["auth_url"]
