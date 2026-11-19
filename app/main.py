from pathlib import Path

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import services
from app.config import Settings, get_settings
from app.db import get_db
from app.keitaro import KeitaroClient, KeitaroError, get_keitaro
from app.models import CreatedCampaign, OfferChange
from app.schemas import (
    CampaignCreate,
    CampaignDetail,
    CreatedCampaignOut,
    OfferAdd,
    OfferChangeOut,
    SharesUpdate,
    StreamOut,
)

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Keitaro wrapper", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.exception_handler(KeitaroError)
def keitaro_error_handler(_: Request, exc: KeitaroError):
    status = exc.status_code if 400 <= exc.status_code < 500 else 502
    return JSONResponse(status_code=status, content={"detail": exc.detail, "source": "keitaro"})


@app.exception_handler(services.ServiceError)
def service_error_handler(_: Request, exc: services.ServiceError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


# --- dictionaries for the forms --------------------------------------------

@app.get("/api/meta")
def meta(kt: KeitaroClient = Depends(get_keitaro), settings: Settings = Depends(get_settings)):
    """Everything the "create campaign" form needs in one call."""
    groups, domains, sources, offers = services.parallel(
        lambda: kt.list_groups("campaigns"),
        kt.list_domains,
        kt.list_traffic_sources,
        lambda: services.list_offers_cached(kt),
    )
    short = lambda items: [{"id": i["id"], "name": i["name"]} for i in items]  # noqa: E731
    return {
        "groups": short(groups),
        "domains": short(domains),
        "traffic_sources": short(sources),
        "offers": short(offers),
        "defaults": {
            "group_id": settings.default_group_id,
            "domain_id": settings.default_domain_id,
            "traffic_source_id": settings.default_traffic_source_id,
        },
    }


@app.get("/api/offers")
def offers(kt: KeitaroClient = Depends(get_keitaro)):
    return [{"id": o["id"], "name": o["name"], "state": o.get("state")}
            for o in services.list_offers_cached(kt)]


# --- part 1: campaign builder ----------------------------------------------

@app.post("/api/campaigns", response_model=CreatedCampaignOut, status_code=201)
def create_campaign(data: CampaignCreate, db: Session = Depends(get_db),
                    kt: KeitaroClient = Depends(get_keitaro),
                    settings: Settings = Depends(get_settings)):
    return services.create_campaign(db, kt, settings, data)


@app.get("/api/campaigns/created", response_model=list[CreatedCampaignOut])
def created_campaigns(db: Session = Depends(get_db)):
    return db.scalars(select(CreatedCampaign).order_by(CreatedCampaign.id.desc())).all()


# --- part 2: offer editor --------------------------------------------------

@app.get("/api/campaigns")
def list_campaigns(group_id: int | None = Query(default=None),
                   search: str | None = Query(default=None),
                   kt: KeitaroClient = Depends(get_keitaro)):
    items = kt.list_campaigns()
    if group_id is not None:
        items = [c for c in items if c.get("group_id") == group_id]
    if search:
        needle = search.lower()
        items = [c for c in items
                 if needle in (c.get("name") or "").lower() or needle == str(c["id"])]
    items.sort(key=lambda c: c["id"], reverse=True)
    return [
        {"id": c["id"], "name": c.get("name"), "group": c.get("group"), "state": c.get("state")}
        for c in items
    ]


@app.get("/api/campaigns/{campaign_id}", response_model=CampaignDetail, response_model_by_alias=True)
def campaign_detail(campaign_id: int, kt: KeitaroClient = Depends(get_keitaro)):
    return services.get_campaign_detail(kt, campaign_id)


@app.post("/api/streams/{stream_id}/offers", response_model=StreamOut, response_model_by_alias=True)
def add_offer(stream_id: int, data: OfferAdd, db: Session = Depends(get_db),
              kt: KeitaroClient = Depends(get_keitaro)):
    return services.add_offer(db, kt, stream_id, data.offer_id)


@app.delete("/api/streams/{stream_id}/offers/{offer_id}", response_model=StreamOut,
            response_model_by_alias=True)
def remove_offer(stream_id: int, offer_id: int, db: Session = Depends(get_db),
                 kt: KeitaroClient = Depends(get_keitaro)):
    return services.remove_offer(db, kt, stream_id, offer_id)


@app.put("/api/streams/{stream_id}/offers", response_model=StreamOut, response_model_by_alias=True)
def update_shares(stream_id: int, data: SharesUpdate, db: Session = Depends(get_db),
                  kt: KeitaroClient = Depends(get_keitaro)):
    return services.update_shares(db, kt, stream_id, [(o.offer_id, o.share) for o in data.offers])


@app.post("/api/streams/{stream_id}/equalize", response_model=StreamOut, response_model_by_alias=True)
def equalize(stream_id: int, db: Session = Depends(get_db), kt: KeitaroClient = Depends(get_keitaro)):
    return services.equalize(db, kt, stream_id)


@app.get("/api/campaigns/{campaign_id}/history", response_model=list[OfferChangeOut])
def history(campaign_id: int, db: Session = Depends(get_db)):
    return db.scalars(
        select(OfferChange).where(OfferChange.campaign_id == campaign_id)
        .order_by(OfferChange.id.desc()).limit(50)
    ).all()
