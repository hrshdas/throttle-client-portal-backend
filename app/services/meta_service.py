"""
MetaService — utility methods for OAuth URL generation, token exchange,
metric calculation, and action parsing.

The MetaApiClient (meta_api_client.py) handles actual HTTP calls to Meta.
This module provides stateless helpers used by routes and the sync service.
"""

import logging
import httpx
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class MetaServiceError(Exception):
    """Raised when a Meta service operation fails."""


class MetaService:

    @staticmethod
    def get_auth_url(state: str) -> str:
        """
        Generate the Meta OAuth 2.0 authorization URL.

        Scopes:
          ads_read         — read ad performance data and insights
          ads_management   — manage and read ad campaigns
          business_management — access Business Manager assets

        Note: 'read_insights' is deprecated and must NOT be used.
        API reference: https://developers.facebook.com/docs/facebook-login/guides/access-tokens/get-long-lived/
        Current API version: configurable via META_API_VERSION (default v26.0)
        """
        base_url = f"https://www.facebook.com/{settings.META_API_VERSION}/dialog/oauth"
        # Use verified, current Meta permission names.
        # Do NOT add 'read_insights' — it is deprecated and will cause OAuth rejection.
        scopes = "ads_read,ads_management,business_management"
        return (
            f"{base_url}?"
            f"client_id={settings.META_APP_ID}"
            f"&redirect_uri={settings.META_REDIRECT_URI}"
            f"&state={state}"
            f"&scope={scopes}"
            f"&response_type=code"
        )

    @staticmethod
    async def exchange_code_for_token(code: str) -> dict:
        """
        Exchange an OAuth authorization code for a short-lived user access token.

        The returned token should then be exchanged for a long-lived token
        via MetaApiClient.exchange_for_long_lived_token().

        Raises MetaServiceError on failure (never exposes raw Meta errors to callers).
        """
        url = f"https://graph.facebook.com/{settings.META_API_VERSION}/oauth/access_token"
        params = {
            "client_id": settings.META_APP_ID,
            "client_secret": settings.META_APP_SECRET,
            "redirect_uri": settings.META_REDIRECT_URI,
            "code": code,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.get(url, params=params)
            if res.status_code != 200:
                # Log without secrets
                logger.error(
                    "Meta token exchange failed: status=%d",
                    res.status_code,
                )
                raise MetaServiceError("Failed to exchange authorization code with Meta API.")
            return res.json()

    @staticmethod
    def calculate_safe_metrics(
        spend: float,
        impressions: int,
        clicks: int,
        leads: int,
        conversion_value: float | None,
    ) -> dict:
        """
        Calculate CPM, CTR, CPC, CPL, ROAS safely.

        Rules:
        - Zero denominators produce 0.0 (not NaN, not Infinity, not None) for rate metrics
        - CPL is None when leads == 0 (unavailable, not fabricated)
        - ROAS is None when spend == 0 or conversion_value is None/zero (unavailable)
        - Never return NaN or Infinity under any inputs

        Returns dict with keys: cpm, ctr, cpc, cpl, roas
        """
        cpm = (spend / impressions * 1000.0) if impressions > 0 else 0.0
        ctr = (clicks / impressions * 100.0) if impressions > 0 else 0.0
        cpc = (spend / clicks) if clicks > 0 else 0.0
        cpl = (spend / leads) if leads > 0 else None
        roas = (
            (conversion_value / spend)
            if (spend > 0 and conversion_value is not None and conversion_value > 0)
            else None
        )

        return {
            "cpm": round(cpm, 2),
            "ctr": round(ctr, 4),
            "cpc": round(cpc, 2),
            "cpl": round(cpl, 2) if cpl is not None else None,
            "roas": round(roas, 4) if roas is not None else None,
        }
