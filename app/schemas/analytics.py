from datetime import date, datetime
from pydantic import BaseModel


class AnalyticsPeriod(BaseModel):
    start: date
    end: date


class AnalyticsOverviewResponse(BaseModel):
    period: AnalyticsPeriod
    spend: float = 0.0
    impressions: int = 0
    reach: int = 0
    clicks: int = 0
    link_clicks: int = 0
    ctr: float | None = None
    cpc: float | None = None
    cpm: float | None = None
    leads: int = 0
    cpl: float | None = None
    conversions: int = 0
    conversion_value: float | None = None
    roas: float | None = None
    last_synced_at: datetime | None = None
    connection_status: str = "DISCONNECTED"


class TimeSeriesPoint(BaseModel):
    date: str
    value: float


class CampaignAnalyticsResponse(BaseModel):
    id: str
    meta_campaign_id: str
    name: str
    status: str
    spend: float = 0.0
    impressions: int = 0
    clicks: int = 0
    ctr: float | None = None
    cpc: float | None = None
    cpm: float | None = None
    leads: int = 0
    cpl: float | None = None
    roas: float | None = None
