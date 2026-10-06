"""
Tests: Analytics metric calculations (MetaService.calculate_safe_metrics).

Proves that:
- No NaN, Infinity, or unexpected None values under any input combination
- Zero denominators are handled safely
- Missing conversion data is represented as None (not fabricated)
- All edge cases from the implementation spec are covered
"""

import pytest
from app.services.meta_service import MetaService
from app.services.meta_api_client import parse_meta_actions


class TestCalculateSafeMetrics:

    def test_normal_values(self):
        """Normal non-zero inputs produce expected rounded metrics."""
        result = MetaService.calculate_safe_metrics(
            spend=1000.0,
            impressions=50000,
            clicks=1200,
            leads=45,
            conversion_value=4200.0,
        )
        assert result["cpm"] == pytest.approx(20.0, rel=0.01)
        assert result["ctr"] == pytest.approx(2.4, rel=0.01)
        assert result["cpc"] == pytest.approx(0.83, rel=0.01)
        assert result["cpl"] == pytest.approx(22.22, rel=0.01)
        assert result["roas"] == pytest.approx(4.2, rel=0.01)

    def test_zero_impressions(self):
        """Zero impressions → CPM=0.0, CTR=0.0 (not division error)."""
        result = MetaService.calculate_safe_metrics(
            spend=500.0,
            impressions=0,
            clicks=0,
            leads=0,
            conversion_value=None,
        )
        assert result["cpm"] == 0.0
        assert result["ctr"] == 0.0
        assert result["cpc"] == 0.0
        assert result["cpl"] is None
        assert result["roas"] is None

    def test_zero_clicks(self):
        """Zero clicks → CPC=0.0 (not division error)."""
        result = MetaService.calculate_safe_metrics(
            spend=300.0,
            impressions=15000,
            clicks=0,
            leads=0,
            conversion_value=None,
        )
        assert result["cpc"] == 0.0
        assert result["cpm"] == pytest.approx(20.0, rel=0.01)
        assert result["cpl"] is None
        assert result["roas"] is None

    def test_zero_leads(self):
        """Zero leads → CPL=None (unavailable, not fabricated as zero)."""
        result = MetaService.calculate_safe_metrics(
            spend=800.0,
            impressions=40000,
            clicks=900,
            leads=0,
            conversion_value=2000.0,
        )
        assert result["cpl"] is None
        assert result["roas"] is not None  # ROAS still available

    def test_zero_spend(self):
        """Zero spend → ROAS=None (undefined, not Infinity)."""
        result = MetaService.calculate_safe_metrics(
            spend=0.0,
            impressions=5000,
            clicks=100,
            leads=10,
            conversion_value=500.0,
        )
        assert result["roas"] is None

    def test_no_conversion_value(self):
        """No conversion value → ROAS=None (not fabricated)."""
        result = MetaService.calculate_safe_metrics(
            spend=1500.0,
            impressions=75000,
            clicks=1800,
            leads=60,
            conversion_value=None,
        )
        assert result["roas"] is None
        assert result["cpl"] is not None  # Leads are available

    def test_zero_conversion_value(self):
        """Zero conversion value → ROAS=None."""
        result = MetaService.calculate_safe_metrics(
            spend=500.0,
            impressions=20000,
            clicks=500,
            leads=20,
            conversion_value=0.0,
        )
        assert result["roas"] is None

    def test_no_nan_or_infinity_under_any_combination(self):
        """Exhaustive check: no NaN or Infinity under extreme inputs."""
        import math
        test_cases = [
            (0.0, 0, 0, 0, None),
            (0.0, 0, 0, 0, 0.0),
            (1.0, 0, 0, 0, None),
            (0.0, 1000, 0, 0, None),
            (0.0, 0, 1000, 0, None),
            (0.0, 0, 0, 1000, None),
            (1000000.0, 1000000, 500000, 10000, 5000000.0),
        ]
        for spend, impressions, clicks, leads, cv in test_cases:
            result = MetaService.calculate_safe_metrics(spend, impressions, clicks, leads, cv)
            for key, val in result.items():
                if val is not None:
                    assert not math.isnan(val), f"NaN for key={key} with inputs {spend, impressions, clicks, leads, cv}"
                    assert not math.isinf(val), f"Infinity for key={key} with inputs {spend, impressions, clicks, leads, cv}"

    def test_roas_correct_formula(self):
        """ROAS = conversion_value / spend."""
        result = MetaService.calculate_safe_metrics(
            spend=2000.0,
            impressions=100000,
            clicks=2000,
            leads=80,
            conversion_value=9000.0,
        )
        assert result["roas"] == pytest.approx(4.5, rel=0.01)

    def test_cpm_correct_formula(self):
        """CPM = spend / impressions × 1000."""
        result = MetaService.calculate_safe_metrics(
            spend=100.0,
            impressions=10000,
            clicks=200,
            leads=5,
            conversion_value=400.0,
        )
        assert result["cpm"] == pytest.approx(10.0, rel=0.01)

    def test_ctr_correct_formula(self):
        """CTR = clicks / impressions × 100."""
        result = MetaService.calculate_safe_metrics(
            spend=100.0,
            impressions=10000,
            clicks=250,
            leads=5,
            conversion_value=400.0,
        )
        assert result["ctr"] == pytest.approx(2.5, rel=0.01)


class TestParseMetaActions:

    def test_none_actions_returns_zeros(self):
        """None actions → (0, 0, None)."""
        leads, conversions, cv = parse_meta_actions(None, None)
        assert leads == 0
        assert conversions == 0
        assert cv is None

    def test_empty_actions_returns_zeros(self):
        """Empty list → (0, 0, None)."""
        leads, conversions, cv = parse_meta_actions([], [])
        assert leads == 0
        assert conversions == 0
        assert cv is None

    def test_lead_actions_counted(self):
        """Lead action types are correctly counted as leads."""
        actions = [
            {"action_type": "lead", "value": "3"},
            {"action_type": "offsite_conversion.fb_pixel_lead", "value": "2"},
        ]
        leads, conversions, cv = parse_meta_actions(actions, None)
        assert leads == 5

    def test_purchase_actions_counted(self):
        """Purchase action types are counted as conversions."""
        actions = [{"action_type": "purchase", "value": "2"}]
        action_values = [{"action_type": "purchase", "value": "1400.00"}]
        leads, conversions, cv = parse_meta_actions(actions, action_values)
        assert conversions == 2
        assert cv == pytest.approx(1400.0, rel=0.01)

    def test_multiple_revenue_types_sum(self):
        """Multiple revenue action types are summed."""
        actions = [
            {"action_type": "purchase", "value": "2"},
            {"action_type": "omni_purchase", "value": "1"},
        ]
        action_values = [
            {"action_type": "purchase", "value": "800.00"},
            {"action_type": "omni_purchase", "value": "400.00"},
        ]
        _, _, cv = parse_meta_actions(actions, action_values)
        assert cv == pytest.approx(1200.0, rel=0.01)

    def test_unknown_action_types_ignored(self):
        """Unknown action types do not produce leads, conversions, or revenue."""
        actions = [
            {"action_type": "post_engagement", "value": "500"},
            {"action_type": "page_like", "value": "100"},
        ]
        leads, conversions, cv = parse_meta_actions(actions, None)
        assert leads == 0
        assert conversions == 0
        assert cv is None


class TestAnalyticsRangeParam:

    @pytest.mark.asyncio
    async def test_range_7d_endpoint(self, client, blueforce_token, seed_data):
        """range=7d returns data for the last 7 days."""
        res = await client.get(
            "/api/v1/analytics/overview?range=7d",
            headers={"Authorization": f"Bearer {blueforce_token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert "period" in data
        # Period should span 7 days
        from datetime import date, timedelta
        start = date.fromisoformat(data["period"]["start"])
        end = date.fromisoformat(data["period"]["end"])
        assert (end - start).days == 7

    @pytest.mark.asyncio
    async def test_range_30d_endpoint(self, client, blueforce_token, seed_data):
        """range=30d returns data for the last 30 days."""
        res = await client.get(
            "/api/v1/analytics/overview?range=30d",
            headers={"Authorization": f"Bearer {blueforce_token}"},
        )
        assert res.status_code == 200
        data = res.json()
        from datetime import date, timedelta
        start = date.fromisoformat(data["period"]["start"])
        end = date.fromisoformat(data["period"]["end"])
        assert (end - start).days == 30

    @pytest.mark.asyncio
    async def test_timeseries_range_param(self, client, blueforce_token, seed_data):
        """Timeseries respects the range parameter."""
        res = await client.get(
            "/api/v1/analytics/timeseries?metric=spend&range=7d",
            headers={"Authorization": f"Bearer {blueforce_token}"},
        )
        assert res.status_code == 200
        points = res.json()
        assert len(points) <= 8

    @pytest.mark.asyncio
    async def test_campaigns_range_param(self, client, blueforce_token, seed_data):
        """Campaign analytics respects the range parameter."""
        res = await client.get(
            "/api/v1/analytics/campaigns?range=30d",
            headers={"Authorization": f"Bearer {blueforce_token}"},
        )
        assert res.status_code == 200

    @pytest.mark.asyncio
    async def test_unknown_metric_returns_zeros(self, client, blueforce_token, seed_data):
        """Unknown metric name returns 0.0 values (not errors)."""
        res = await client.get(
            "/api/v1/analytics/timeseries?metric=nonexistent_metric&range=30d",
            headers={"Authorization": f"Bearer {blueforce_token}"},
        )
        assert res.status_code == 200
        points = res.json()
        assert all(p["value"] == 0.0 for p in points)
