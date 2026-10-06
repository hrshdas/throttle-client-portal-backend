"""
OAuth state store for Meta CSRF protection.

Stores a short-lived mapping of  state_token → organization_id  so that
the OAuth callback can verify the state parameter has not been forged.

For single-process deployments this in-memory store is sufficient.
For multi-process / multi-instance deployments (multiple uvicorn workers or
Kubernetes pods), replace the _store dict with a shared Redis key-value store.

Usage:
    state = generate_state(organization_id)   # before redirect to Meta
    org_id = validate_state(state)            # inside callback handler
"""

import logging
import secrets
import time
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# { state_token: (organization_id, expiry_timestamp) }
_store: dict[str, tuple[str, float]] = {}


def generate_state(organization_id: str) -> str:
    """
    Create a cryptographically secure random state token bound to the given org.

    The token is stored server-side for META_OAUTH_STATE_TTL_SECONDS seconds.
    Returns the state string to embed in the OAuth authorization URL.
    """
    _evict_expired()
    state = secrets.token_urlsafe(32)
    expiry = time.monotonic() + settings.META_OAUTH_STATE_TTL_SECONDS
    _store[state] = (organization_id, expiry)
    logger.info("OAuth state generated for org=%s (expires in %ds)", organization_id, settings.META_OAUTH_STATE_TTL_SECONDS)
    return state


def validate_state(state: str) -> str | None:
    """
    Validate and consume a state token.

    Returns the bound organization_id if the state is valid and not expired.
    Returns None if the state is unknown, already used, or expired (CSRF detected).

    Each state can only be used once (single-use).
    """
    _evict_expired()
    if not state or state not in _store:
        logger.warning("OAuth state validation failed: unknown state (possible CSRF attempt)")
        return None

    org_id, expiry = _store.pop(state)  # Consume immediately — single-use

    if time.monotonic() > expiry:
        logger.warning("OAuth state validation failed: expired state for org=%s", org_id)
        return None

    logger.info("OAuth state validated for org=%s", org_id)
    return org_id


def _evict_expired() -> None:
    """Remove all expired entries from the store (lazy GC)."""
    now = time.monotonic()
    expired = [k for k, (_, exp) in _store.items() if now > exp]
    for k in expired:
        del _store[k]
