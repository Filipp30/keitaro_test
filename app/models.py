from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CreatedCampaign(Base):
    """A campaign created through the campaign builder (local record of Keitaro objects)."""

    __tablename__ = "created_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keitaro_campaign_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    alias: Mapped[str] = mapped_column(String(64))
    country: Mapped[str] = mapped_column(String(2))
    offer_id: Mapped[int] = mapped_column(Integer)
    group_id: Mapped[int] = mapped_column(Integer)
    domain_id: Mapped[int] = mapped_column(Integer)
    traffic_source_id: Mapped[int] = mapped_column(Integer)
    geo_stream_id: Mapped[int] = mapped_column(Integer)
    offer_stream_id: Mapped[int] = mapped_column(Integer)
    url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class OfferChange(Base):
    """Audit log of every change the editor makes to a stream's offers."""

    __tablename__ = "offer_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(Integer, index=True)
    stream_id: Mapped[int] = mapped_column(Integer, index=True)
    action: Mapped[str] = mapped_column(String(16))  # add | remove | update | equalize
    offer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shares_before: Mapped[dict] = mapped_column(JSON)
    shares_after: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
