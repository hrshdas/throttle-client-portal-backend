"""
Meta API Client — the single, authoritative HTTP client for all Meta Graph API calls.

All requests to Meta's Graph/Marketing API go through this class.
Never scatter raw httpx calls across the codebase.

Meta API reference: https://developers.facebook.com/docs/marketing-api/
Current supported version: configurable via META_API_VERSION in settings (default v26.0)
"""

import logging
import asyncio
from typing import Any
import httpx
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Meta action types that count as leads
LEAD_ACTION_TYPES = frozenset({
    "lead",
    "offsite_conversion.fb_pixel_lead",
    "leadgen.other",
    "onsite_web_lead",
})

# Meta action types that count as conversions (purchase / registration)
CONVERSION_ACTION_TYPES = frozenset({
    "purchase",
    "complete_registration",
    "offsite_conversion.fb_pixel_purchase",
    "offsite_conversion.fb_pixel_complete_registration",
    "omni_purchase",
})

# Meta action types that carry purchase value
REVENUE_ACTION_TYPES = frozenset({
    "purchase",
    "offsite_conversion.fb_pixel_purchase",
    "omni_purchase",
    "omni_app_purchase",
})


class MetaApiError(Exception):
    """Raised when a Meta API call fails. Message is safe to surface to logs (no tokens)."""
    def __init__(self, message: str, status_code: int = 0, error_code: int = 0):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


class MetaApiClient:
    """
    Async HTTP client for the Meta Graph / Marketing API.

    Args:
        access_token: Decrypted Meta user access token (NEVER log this)
        api_version: e.g. "v26.0" — injected from settings so it can be updated
    """

    BASE_URL = "https://graph.facebook.com"
    MAX_RETRIES = 3
    RETRY_DELAY_BASE = 1.0  # seconds; doubles on each retry (exponential backoff)
    REQUEST_TIMEOUT = 30.0  # seconds per request

    def __init__(self, access_token: str, api_version: str | None = None):
        self._token = access_token
        self._version = api_version or settings.META_API_VERSION

    # ─── Public API Methods ────────────────────────────────────────────────────

    async def get_me(self) -> dict:
        """Fetch basic info about the authenticated Meta user."""
        return await self._get("me", params={"fields": "id,name"})

    async def exchange_for_long_lived_token(self) -> dict:
        """
        Exchange a short-lived user access token for a long-lived one (~60 days).
        See: https://developers.facebook.com/docs/facebook-login/guides/access-tokens/get-long-lived/
        """
        url = f"{self.BASE_URL}/{self._version}/oauth/access_token"
        params = {
            "grant_type": "fb_exchange_token",
            "client_id": settings.META_APP_ID,
            "client_secret": settings.META_APP_SECRET,
            "fb_exchange_token": self._token,
        }
        async with httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                logger.error("Meta token exchange failed: status=%d", resp.status_code)
                raise MetaApiError("Failed to exchange for long-lived token", status_code=resp.status_code)
            return resp.json()

    async def get_ad_accounts(self) -> list[dict]:
        """
        List all ad accounts accessible to the authenticated user.
        Returns list of dicts with: id, name, account_id, account_status, currency.
        """
        data = await self._paginate("me/adaccounts", params={
            "fields": "id,name,account_id,account_status,currency,business",
        })
        return data

    async def get_campaigns(self, ad_account_id: str) -> list[dict]:
        """
        Fetch all campaigns for an ad account (includes ACTIVE, PAUSED, ARCHIVED).
        Returns list of dicts with: id, name, status, objective.
        """
        account_node = _ensure_act_prefix(ad_account_id)
        return await self._paginate(f"{account_node}/campaigns", params={
            "fields": "id,name,status,objective",
            "limit": "100",
        })

    async def get_ad_sets(self, ad_account_id: str) -> list[dict]:
        """
        Fetch all ad sets for an ad account.
        Returns list of dicts with: id, name, status, campaign_id.
        """
        account_node = _ensure_act_prefix(ad_account_id)
        return await self._paginate(f"{account_node}/adsets", params={
            "fields": "id,name,status,campaign_id",
            "limit": "100",
        })

    async def get_ads(self, ad_account_id: str) -> list[dict]:
        """
        Fetch all ads for an ad account.
        Returns list of dicts with: id, name, status, adset_id, campaign_id.
        """
        account_node = _ensure_act_prefix(ad_account_id)
        return await self._paginate(f"{account_node}/ads", params={
            "fields": "id,name,status,adset_id,campaign_id",
            "limit": "100",
        })

    async def get_insights(
        self,
        ad_account_id: str,
        date_start: str,
        date_stop: str,
        level: str = "account",
        extra_fields: list[str] | None = None,
    ) -> list[dict]:
        """
        Fetch daily insights for an ad account at the specified level.

        Args:
            ad_account_id: e.g. "act_123456"
            date_start: "YYYY-MM-DD"
            date_stop: "YYYY-MM-DD"
            level: "account" | "campaign" | "adset" | "ad"
            extra_fields: additional fields to include

        Returns list of daily insight dicts.

        Note: For large date ranges, Meta may return an async report job.
        This implementation uses the synchronous insights endpoint with a
        day-level time increment. For very large ranges (>90d), use async jobs.
        """
        account_node = _ensure_act_prefix(ad_account_id)
        base_fields = [
            "date_start", "date_stop",
            "spend", "impressions", "reach", "clicks",
            "ctr", "cpc", "cpm",
            "actions", "action_values",
        ]
        if level == "campaign":
            base_fields += ["campaign_id", "campaign_name"]
        elif level == "adset":
            base_fields += ["campaign_id", "adset_id", "adset_name"]
        elif level == "ad":
            base_fields += ["campaign_id", "adset_id", "ad_id", "ad_name"]

        if extra_fields:
            base_fields += [f for f in extra_fields if f not in base_fields]

        # Also request inline_link_clicks as a separate field
        if "inline_link_clicks" not in base_fields:
            base_fields.append("inline_link_clicks")

        params = {
            "fields": ",".join(base_fields),
            "level": level,
            "time_range": f'{{"since":"{date_start}","until":"{date_stop}"}}',
            "time_increment": "1",  # one row per day
            "limit": "100",
        }

        return await self._paginate(f"{account_node}/insights", params=params)

    # ─── Internal Helpers ──────────────────────────────────────────────────────

    async def _get(self, node: str, params: dict | None = None) -> dict:
        """Make a single GET request to a Graph API node. Returns the JSON response dict."""
        url = f"{self.BASE_URL}/{self._version}/{node}"
        full_params = {"access_token": self._token}
        if params:
            full_params.update(params)
        return await self._request("GET", url, full_params)

    async def _paginate(self, node: str, params: dict | None = None) -> list[dict]:
        """
        Fetch all pages of a cursor-paginated Meta API endpoint.
        Follows 'paging.next' URLs until exhausted.
        Returns flat list of all items from all pages.
        """
        url = f"{self.BASE_URL}/{self._version}/{node}"
        full_params = {"access_token": self._token}
        if params:
            full_params.update(params)

        results: list[dict] = []
        next_url: str | None = None

        while True:
            if next_url:
                # Subsequent pages include the token in the URL already
                data = await self._request("GET", next_url, {})
            else:
                data = await self._request("GET", url, full_params)

            items = data.get("data", [])
            results.extend(items)

            paging = data.get("paging", {})
            cursors = paging.get("cursors", {})
            next_url = paging.get("next")  # None when no more pages

            if not next_url:
                break

        return results

    async def _request(self, method: str, url: str, params: dict) -> dict:
        """
        Execute an HTTP request with retry and rate-limit handling.
        NEVER logs the access token.
        """
        last_error: Exception | None = None

        for attempt in range(self.MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT) as client:
                    resp = await client.request(method, url, params=params)

                # Check rate limits
                usage_header = resp.headers.get("X-Business-Use-Case-Usage")
                if usage_header:
                    _check_rate_limit_header(usage_header)

                if resp.status_code == 200:
                    return resp.json()

                # Parse Meta error body
                body = resp.json() if resp.content else {}
                error = body.get("error", {})
                error_code = error.get("code", 0)
                error_msg = error.get("message", f"HTTP {resp.status_code}")
                error_type = error.get("type", "")

                # Expired / invalid token — do not retry
                if error_code in (190, 102, 104) or "token" in error_msg.lower():
                    raise MetaApiError(
                        f"Meta access token expired or invalid (code={error_code}). Please reconnect.",
                        status_code=resp.status_code,
                        error_code=error_code,
                    )

                # Rate limit — wait and retry
                if resp.status_code == 429 or error_code == 17:
                    wait = self.RETRY_DELAY_BASE * (2 ** attempt)
                    logger.warning("Meta rate limit hit (attempt %d/%d), waiting %.1fs", attempt + 1, self.MAX_RETRIES, wait)
                    await asyncio.sleep(wait)
                    last_error = MetaApiError(f"Meta API rate limited: {error_msg}", status_code=429, error_code=error_code)
                    continue

                # Server error — retry
                if resp.status_code >= 500:
                    wait = self.RETRY_DELAY_BASE * (2 ** attempt)
                    logger.warning("Meta server error %d (attempt %d/%d), waiting %.1fs", resp.status_code, attempt + 1, self.MAX_RETRIES, wait)
                    await asyncio.sleep(wait)
                    last_error = MetaApiError(f"Meta server error: {error_msg}", status_code=resp.status_code, error_code=error_code)
                    continue

                # Permission / other client error — do not retry
                safe_msg = _safe_error_message(error_code, error_type)
                raise MetaApiError(safe_msg, status_code=resp.status_code, error_code=error_code)

            except MetaApiError:
                raise
            except httpx.TimeoutException:
                wait = self.RETRY_DELAY_BASE * (2 ** attempt)
                logger.warning("Meta API timeout (attempt %d/%d), waiting %.1fs", attempt + 1, self.MAX_RETRIES, wait)
                await asyncio.sleep(wait)
                last_error = MetaApiError("Meta API request timed out", status_code=0)
            except httpx.RequestError as exc:
                logger.error("Meta API network error: %s", type(exc).__name__)
                raise MetaApiError("Unable to reach Meta API. Check network connectivity.") from exc

        raise last_error or MetaApiError("Meta API request failed after retries")


# ─── Standalone Helpers ────────────────────────────────────────────────────────

def _ensure_act_prefix(ad_account_id: str) -> str:
    """Ensure ad account ID has the 'act_' prefix that Meta requires."""
    if ad_account_id.startswith("act_"):
        return ad_account_id
    return f"act_{ad_account_id}"


def _check_rate_limit_header(header_value: str) -> None:
    """Log a warning if we are approaching Meta API rate limits."""
    # Header format: {"<account_id>": [{"call_count": 80, "total_time": 40, ...}]}
    try:
        import json
        data = json.loads(header_value)
        for _account, entries in data.items():
            for entry in (entries or []):
                call_pct = entry.get("call_count", 0)
                if call_pct >= 80:
                    logger.warning("Meta API rate limit at %d%% — slowing down requests", call_pct)
    except Exception:
        pass  # Non-critical — don't crash on header parse failure


def _safe_error_message(error_code: int, error_type: str) -> str:
    """Return a user-safe error message for known Meta error codes."""
    messages = {
        200: "Meta API permission denied. Ensure ads_read and ads_management permissions are granted.",
        294: "Meta API: Managing ads is not allowed for this ad account.",
        100: "Meta API: Invalid parameter.",
        2635: "Meta API: Your access token has expired.",
    }
    return messages.get(error_code, f"Meta API error (code={error_code}, type={error_type})")


def parse_meta_actions(
    actions: list[dict] | None,
    action_values: list[dict] | None,
) -> tuple[int, int, float | None]:
    """
    Parse Meta 'actions' and 'action_values' arrays into leads, conversions, conversion_value.

    The mapping of action_type → business metric is kept here as the single source of truth.
    Update LEAD_ACTION_TYPES / CONVERSION_ACTION_TYPES / REVENUE_ACTION_TYPES at the top
    of this file as your conversion setup evolves.

    Returns:
        (leads, conversions, conversion_value)
        conversion_value is None if no revenue actions are present.
    """
    leads = 0
    conversions = 0
    conversion_value: float | None = None

    action_val_map: dict[str, float] = {}
    if action_values:
        for av in action_values:
            action_val_map[av.get("action_type", "")] = float(av.get("value", 0))

    if actions:
        for action in actions:
            action_type = action.get("action_type", "")
            value = float(action.get("value", 0))

            if action_type in LEAD_ACTION_TYPES:
                leads += int(value)

            if action_type in CONVERSION_ACTION_TYPES:
                conversions += int(value)

            if action_type in REVENUE_ACTION_TYPES:
                rev = action_val_map.get(action_type, value)
                conversion_value = (conversion_value or 0.0) + rev

    return leads, conversions, conversion_value
