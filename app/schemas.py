from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    country: str = Field(description="ISO 3166-1 alpha-2 country code, e.g. DE")
    offer_id: int = Field(gt=0)
    group_id: int | None = Field(default=None, gt=0)
    domain_id: int | None = Field(default=None, gt=0)
    traffic_source_id: int | None = Field(default=None, gt=0)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name must not be empty")
        return v

    @field_validator("country")
    @classmethod
    def normalize_country(cls, v: str) -> str:
        v = v.strip().upper()
        if len(v) != 2 or not v.isalpha():
            raise ValueError("Country must be a 2-letter ISO code, e.g. DE")
        return v


class CreatedCampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    keitaro_campaign_id: int
    name: str
    alias: str
    country: str
    offer_id: int
    group_id: int
    domain_id: int
    traffic_source_id: int
    geo_stream_id: int
    offer_stream_id: int
    url: str | None
    created_at: datetime


class OfferAdd(BaseModel):
    offer_id: int = Field(gt=0)


class OfferShare(BaseModel):
    offer_id: int = Field(gt=0)
    share: int = Field(ge=0, le=100)


class SharesUpdate(BaseModel):
    offers: list[OfferShare]


class StreamOfferOut(BaseModel):
    offer_id: int
    name: str
    share: int
    state: str


class StreamOut(BaseModel):
    id: int
    name: str
    type: str
    position: int | None
    schema_: str | None = Field(alias="schema", serialization_alias="schema")
    state: str
    action_payload: str | None = None
    filters: list[dict] = []
    offers: list[StreamOfferOut] = []
    shares_total: int
    shares_valid: bool

    model_config = ConfigDict(populate_by_name=True)


class CampaignDetail(BaseModel):
    id: int
    name: str
    alias: str | None
    state: str | None
    group: str | None = None
    domain: str | None = None
    url: str | None = None
    streams: list[StreamOut]


class OfferChangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    campaign_id: int
    stream_id: int
    action: str
    offer_id: int | None
    shares_before: dict
    shares_after: dict
    created_at: datetime
