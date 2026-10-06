import enum
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum as SQLEnum, Float, Integer, Date, JSON
from sqlalchemy.orm import relationship
from app.core.database import Base


class MetaConnectionStatus(str, enum.Enum):
    CONNECTED = "CONNECTED"
    SYNCING = "SYNCING"
    SYNCED = "SYNCED"
    ERROR = "ERROR"
    DISCONNECTED = "DISCONNECTED"


class MetaInsightLevel(str, enum.Enum):
    ACCOUNT = "ACCOUNT"
    CAMPAIGN = "CAMPAIGN"
    AD_SET = "AD_SET"
    AD = "AD"


class MetaConnection(Base):
    __tablename__ = "meta_connections"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True, unique=True)
    meta_user_id = Column(String, nullable=True)
    business_id = Column(String, nullable=True)
    ad_account_id = Column(String, nullable=True, index=True)
    ad_account_name = Column(String, nullable=True)
    encrypted_access_token = Column(String, nullable=False)
    token_expires_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(SQLEnum(MetaConnectionStatus), default=MetaConnectionStatus.CONNECTED, nullable=False)
    error_message = Column(String, nullable=True)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    organization = relationship("Organization", backref="meta_connection")


class MetaCampaign(Base):
    __tablename__ = "meta_campaigns"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    ad_account_id = Column(String, nullable=False, index=True)
    meta_campaign_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="ACTIVE")
    objective = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class MetaAdSet(Base):
    __tablename__ = "meta_ad_sets"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    ad_account_id = Column(String, nullable=False, index=True)
    meta_campaign_id = Column(String, nullable=False, index=True)
    meta_ad_set_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="ACTIVE")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class MetaAd(Base):
    __tablename__ = "meta_ads"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    ad_account_id = Column(String, nullable=False, index=True)
    meta_ad_set_id = Column(String, nullable=False, index=True)
    meta_ad_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="ACTIVE")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class MetaDailyInsight(Base):
    __tablename__ = "meta_daily_insights"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = Column(String, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    ad_account_id = Column(String, nullable=False, index=True)
    meta_campaign_id = Column(String, nullable=True, index=True)
    meta_ad_set_id = Column(String, nullable=True, index=True)
    meta_ad_id = Column(String, nullable=True, index=True)
    level = Column(SQLEnum(MetaInsightLevel), default=MetaInsightLevel.ACCOUNT, nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    spend = Column(Float, default=0.0, nullable=False)
    impressions = Column(Integer, default=0, nullable=False)
    reach = Column(Integer, default=0, nullable=False)
    clicks = Column(Integer, default=0, nullable=False)
    link_clicks = Column(Integer, default=0, nullable=False)
    ctr = Column(Float, nullable=True)
    cpc = Column(Float, nullable=True)
    cpm = Column(Float, nullable=True)
    leads = Column(Integer, default=0, nullable=False)
    cpl = Column(Float, nullable=True)
    conversions = Column(Integer, default=0, nullable=False)
    conversion_value = Column(Float, nullable=True)
    roas = Column(Float, nullable=True)
    raw_actions = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
