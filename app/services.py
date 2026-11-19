"""Business logic: the campaign builder (part 1) and the offer editor (part 2)."""

import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session

from app import shares as share_math
from app.config import Settings
from app.keitaro import KeitaroClient, KeitaroError
from app.models import CreatedCampaign, OfferChange
from app.schemas import CampaignCreate


class ServiceError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


# Every Keitaro call takes ~0.8 s, so independent calls run in parallel.
_pool = ThreadPoolExecutor(max_workers=8)


def parallel(*calls):
    futures = [_pool.submit(call) for call in calls]
    return [f.result() for f in futures]


# --------------------------------------------------------------------------
# Part 1: campaign builder
# --------------------------------------------------------------------------

def _pick(value: int | None, default: int | None, field: str) -> int:
    if value is not None:
        return value
    if default is not None:
        return default
    raise ServiceError(422, f"'{field}' is required (no default configured)")


def _ensure_offer(kt: KeitaroClient, offer_id: int) -> dict:
    try:
        return kt.get_offer(offer_id)
    except KeitaroError as exc:
        if exc.status_code == 404:
            raise ServiceError(422, f"Offer {offer_id} does not exist in Keitaro") from exc
        raise


def _campaign_url(campaign: dict) -> str | None:
    domain, alias = campaign.get("domain"), campaign.get("alias")
    if not domain or not alias:
        return None
    return domain.rstrip("/") + "/" + alias


def create_campaign(db: Session, kt: KeitaroClient, settings: Settings,
                    data: CampaignCreate) -> CreatedCampaign:
    group_id = _pick(data.group_id, settings.default_group_id, "group_id")
    domain_id = _pick(data.domain_id, settings.default_domain_id, "domain_id")
    source_id = _pick(data.traffic_source_id, settings.default_traffic_source_id,
                      "traffic_source_id")

    # Fail fast on a wrong offer id, before anything is created in Keitaro.
    _ensure_offer(kt, data.offer_id)

    campaign = kt.create_campaign({
        "name": data.name,
        "alias": "c-" + secrets.token_hex(5),
        "type": "position",
        "state": "active",
        "group_id": group_id,
        "domain_id": domain_id,
        "traffic_source_id": source_id,
    })
    campaign_id = campaign["id"]

    try:
        # Stream 1: everyone from the selected country -> Google.
        geo_stream = kt.create_stream({
            "campaign_id": campaign_id,
            "type": "regular",
            "name": f"{data.country} -> Google",
            "position": 1,
            "state": "active",
            "schema": "redirect",
            "action_type": "http",
            "action_payload": settings.geo_redirect_url,
            "filters": [{"name": "country", "mode": "accept", "payload": [data.country]}],
        })
        # Stream 2: everybody else -> the selected offer.
        offer_stream = kt.create_stream({
            "campaign_id": campaign_id,
            "type": "regular",
            "name": "Offers",
            "position": 2,
            "state": "active",
            "schema": "landings",
            "action_type": "http",
            "offers": [{"offer_id": data.offer_id, "share": 100, "state": "active"}],
        })
    except KeitaroError:
        # Don't leave a half-built campaign behind.
        try:
            kt.delete_campaign(campaign_id)
        except KeitaroError:
            pass
        raise

    record = CreatedCampaign(
        keitaro_campaign_id=campaign_id,
        name=campaign.get("name", data.name),
        alias=campaign["alias"],
        country=data.country,
        offer_id=data.offer_id,
        group_id=group_id,
        domain_id=domain_id,
        traffic_source_id=source_id,
        geo_stream_id=geo_stream["id"],
        offer_stream_id=offer_stream["id"],
        url=_campaign_url(campaign),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


# --------------------------------------------------------------------------
# Part 2: offer editor
# --------------------------------------------------------------------------

OFFERS_TTL = 60.0
_offers_cache: dict = {"at": 0.0, "items": None}
_offers_lock = threading.Lock()


def list_offers_cached(kt: KeitaroClient) -> list[dict]:
    """Offer list changes rarely; caching it saves a Keitaro round trip per action."""
    with _offers_lock:
        if _offers_cache["items"] is not None and time.monotonic() - _offers_cache["at"] < OFFERS_TTL:
            return _offers_cache["items"]
    items = kt.list_offers()
    with _offers_lock:
        _offers_cache.update(at=time.monotonic(), items=items)
    return items


def clear_offers_cache() -> None:
    with _offers_lock:
        _offers_cache.update(at=0.0, items=None)


def _offer_names(kt: KeitaroClient) -> dict[int, str]:
    return {o["id"]: o["name"] for o in list_offers_cached(kt)}


def serialize_stream(stream: dict, names: dict[int, str]) -> dict:
    offers = [
        {
            "offer_id": o["offer_id"],
            "name": names.get(o["offer_id"], f"Offer #{o['offer_id']}"),
            "share": int(o.get("share") or 0),
            "state": o.get("state", "active"),
        }
        for o in stream.get("offers") or []
    ]
    share_list = [o["share"] for o in offers]
    return {
        "id": stream["id"],
        "name": stream.get("name") or f"Stream #{stream['id']}",
        "type": stream.get("type"),
        "position": stream.get("position"),
        "schema": stream.get("schema"),
        "state": stream.get("state"),
        "action_payload": stream.get("action_payload"),
        "filters": [
            {"name": f.get("name"), "mode": f.get("mode"), "payload": f.get("payload")}
            for f in stream.get("filters") or []
        ],
        "offers": offers,
        "shares_total": sum(share_list),
        "shares_valid": share_math.is_valid(share_list),
    }


def get_campaign_detail(kt: KeitaroClient, campaign_id: int) -> dict:
    campaign, streams, names = parallel(
        lambda: kt.get_campaign(campaign_id),
        lambda: kt.list_streams(campaign_id),
        lambda: _offer_names(kt),
    )
    streams = sorted(streams, key=lambda s: (s.get("position") or 0, s["id"]))
    return {
        "id": campaign["id"],
        "name": campaign.get("name"),
        "alias": campaign.get("alias"),
        "state": campaign.get("state"),
        "group": campaign.get("group"),
        "domain": campaign.get("domain"),
        "url": _campaign_url(campaign),
        "streams": [serialize_stream(s, names) for s in streams],
    }


def _load_offer_stream(kt: KeitaroClient, stream_id: int) -> dict:
    stream = kt.get_stream(stream_id)
    if stream.get("schema") != "landings":
        raise ServiceError(
            422, "This stream is not an offer stream (schema must be 'landings')")
    return stream


def _copy_offers(stream: dict) -> list[dict]:
    # Copy each offer: the original stream must stay untouched for the audit log.
    return [dict(o) for o in stream.get("offers") or []]


def _shares_map(offers: list[dict]) -> dict[str, int]:
    return {str(o["offer_id"]): int(o.get("share") or 0) for o in offers}


def _save_offers(db: Session, kt: KeitaroClient, stream: dict, new_offers: list[dict],
                 action: str, offer_id: int | None) -> dict:
    before = _shares_map(stream.get("offers") or [])
    payload = [
        {"offer_id": o["offer_id"], "share": o["share"], "state": o.get("state", "active")}
        for o in new_offers
    ]
    # Keitaro replaces the whole offer list on PUT.
    updated = kt.update_stream(stream["id"], {"offers": payload})
    db.add(OfferChange(
        campaign_id=stream["campaign_id"],
        stream_id=stream["id"],
        action=action,
        offer_id=offer_id,
        shares_before=before,
        shares_after=_shares_map(updated.get("offers") or payload),
    ))
    db.commit()
    return serialize_stream(updated, _offer_names(kt))


def add_offer(db: Session, kt: KeitaroClient, stream_id: int, offer_id: int) -> dict:
    stream, _ = parallel(lambda: _load_offer_stream(kt, stream_id),
                         lambda: _ensure_offer(kt, offer_id))
    offers = _copy_offers(stream)
    if any(o["offer_id"] == offer_id for o in offers):
        raise ServiceError(409, f"Offer {offer_id} is already in this stream")

    offers.append({"offer_id": offer_id, "share": 0, "state": "active"})
    # A new offer gets an equal part: shares are split evenly over all offers.
    for o, share in zip(offers, share_math.equal_split(len(offers))):
        o["share"] = share
    return _save_offers(db, kt, stream, offers, "add", offer_id)


def remove_offer(db: Session, kt: KeitaroClient, stream_id: int, offer_id: int) -> dict:
    stream = _load_offer_stream(kt, stream_id)
    offers = _copy_offers(stream)
    remaining = [o for o in offers if o["offer_id"] != offer_id]
    if len(remaining) == len(offers):
        raise ServiceError(404, f"Offer {offer_id} is not in this stream")
    # The removed offer's share goes to the others, proportionally to their shares.
    for o, share in zip(remaining, share_math.redistribute([int(o.get("share") or 0) for o in remaining])):
        o["share"] = share
    return _save_offers(db, kt, stream, remaining, "remove", offer_id)


def equalize(db: Session, kt: KeitaroClient, stream_id: int) -> dict:
    stream = _load_offer_stream(kt, stream_id)
    offers = _copy_offers(stream)
    for o, share in zip(offers, share_math.equal_split(len(offers))):
        o["share"] = share
    return _save_offers(db, kt, stream, offers, "equalize", None)


def update_shares(db: Session, kt: KeitaroClient, stream_id: int,
                  new_shares: list[tuple[int, int]]) -> dict:
    stream = _load_offer_stream(kt, stream_id)
    offers = _copy_offers(stream)
    current_ids = sorted(o["offer_id"] for o in offers)
    if sorted(oid for oid, _ in new_shares) != current_ids:
        raise ServiceError(
            409, "The offer list has changed in Keitaro; reload the campaign and try again")
    values = [share for _, share in new_shares]
    if not share_math.is_valid(values):
        raise ServiceError(422, f"Shares must add up to 100 (got {sum(values)})")
    by_id = dict(new_shares)
    for o in offers:
        o["share"] = by_id[o["offer_id"]]
    return _save_offers(db, kt, stream, offers, "update", None)
