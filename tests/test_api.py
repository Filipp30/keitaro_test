"""API tests with Keitaro mocked by respx (no network)."""

import json

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app
from app.services import clear_offers_cache

KT = "https://keitaro.test/admin_api/v1"
OFFERS = [{"id": 1, "name": "Offer A"}, {"id": 2, "name": "Offer B"}, {"id": 3, "name": "Offer C"}]


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    clear_offers_cache()
    yield


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def kt():
    with respx.mock(base_url=KT, assert_all_called=False) as mock:
        mock.get("/offers").respond(json=OFFERS)
        for o in OFFERS:
            mock.get(f"/offers/{o['id']}").respond(json=o)
        mock.get("/offers/999").respond(404, json={"error": "Not found"})
        yield mock


def _stream(offers, stream_id=10, schema="landings"):
    return {"id": stream_id, "campaign_id": 5, "name": "Offers", "type": "regular", "position": 2,
            "schema": schema, "state": "active", "filters": [], "offers": offers}


def _put_echo(request):
    """Keitaro answers a PUT with the stream holding exactly the offers that were sent."""
    body = json.loads(request.content)
    return httpx.Response(200, json=_stream(body["offers"]))


# --- part 1 ---------------------------------------------------------------

def test_create_campaign_builds_two_streams(client, kt):
    create = kt.post("/campaigns").respond(json={
        "id": 5, "name": "my camp", "alias": "c-abc", "domain": "https://kylovoa.com/"})
    streams = kt.post("/streams").mock(side_effect=[
        httpx.Response(200, json={"id": 11}), httpx.Response(200, json={"id": 12})])

    r = client.post("/api/campaigns", json={
        "name": " my camp ", "country": "de", "offer_id": 2,
        "group_id": 9799, "domain_id": 1813, "traffic_source_id": 836})

    assert r.status_code == 201, r.text
    body = r.json()
    assert body["keitaro_campaign_id"] == 5
    assert body["country"] == "DE"
    assert body["url"] == "https://kylovoa.com/c-abc"
    assert (body["geo_stream_id"], body["offer_stream_id"]) == (11, 12)

    camp = json.loads(create.calls[0].request.content)
    assert camp["name"] == "my camp"
    assert (camp["group_id"], camp["domain_id"], camp["traffic_source_id"]) == (9799, 1813, 836)
    assert camp["alias"]

    geo = json.loads(streams.calls[0].request.content)
    assert geo["position"] == 1 and geo["schema"] == "redirect"
    assert geo["action_payload"] == "https://www.google.com"
    assert geo["filters"] == [{"name": "country", "mode": "accept", "payload": ["DE"]}]

    offer = json.loads(streams.calls[1].request.content)
    assert offer["position"] == 2 and offer["schema"] == "landings"
    assert offer["offers"] == [{"offer_id": 2, "share": 100, "state": "active"}]

    listed = client.get("/api/campaigns/created").json()
    assert [c["keitaro_campaign_id"] for c in listed] == [5]


def test_create_campaign_rolls_back_when_stream_fails(client, kt):
    kt.post("/campaigns").respond(json={"id": 5, "name": "x", "alias": "c-abc"})
    kt.post("/streams").respond(422, json={"error": "bad stream"})
    delete = kt.delete("/campaigns/5").respond(json={})

    r = client.post("/api/campaigns", json={
        "name": "x", "country": "DE", "offer_id": 1,
        "group_id": 1, "domain_id": 1, "traffic_source_id": 1})

    assert r.status_code == 422
    assert delete.called
    assert client.get("/api/campaigns/created").json() == []


def test_create_campaign_rejects_unknown_offer(client, kt):
    create = kt.post("/campaigns").respond(json={"id": 5})
    r = client.post("/api/campaigns", json={
        "name": "x", "country": "DE", "offer_id": 999,
        "group_id": 1, "domain_id": 1, "traffic_source_id": 1})
    assert r.status_code == 422
    assert not create.called


@pytest.mark.parametrize("country", ["D", "DEU", "1A", ""])
def test_create_campaign_validates_country(client, country):
    r = client.post("/api/campaigns", json={
        "name": "x", "country": country, "offer_id": 1,
        "group_id": 1, "domain_id": 1, "traffic_source_id": 1})
    assert r.status_code == 422


# --- part 2 ---------------------------------------------------------------

def test_add_offer_splits_equally(client, kt):
    kt.get("/streams/10").respond(json=_stream([
        {"offer_id": 1, "share": 70, "state": "active"},
        {"offer_id": 2, "share": 30, "state": "active"}]))
    put = kt.put("/streams/10").mock(side_effect=_put_echo)

    r = client.post("/api/streams/10/offers", json={"offer_id": 3})

    assert r.status_code == 200, r.text
    sent = json.loads(put.calls[0].request.content)["offers"]
    assert [(o["offer_id"], o["share"]) for o in sent] == [(1, 34), (2, 33), (3, 33)]
    assert r.json()["shares_total"] == 100 and r.json()["shares_valid"]
    assert [o["name"] for o in r.json()["offers"]] == ["Offer A", "Offer B", "Offer C"]

    hist = client.get("/api/campaigns/5/history").json()
    assert hist[0]["action"] == "add"
    assert hist[0]["shares_before"] == {"1": 70, "2": 30}
    assert hist[0]["shares_after"] == {"1": 34, "2": 33, "3": 33}


def test_add_offer_to_empty_stream_gets_100(client, kt):
    kt.get("/streams/10").respond(json=_stream([]))
    put = kt.put("/streams/10").mock(side_effect=_put_echo)
    assert client.post("/api/streams/10/offers", json={"offer_id": 1}).status_code == 200
    assert json.loads(put.calls[0].request.content)["offers"][0]["share"] == 100


def test_add_duplicate_offer_is_rejected(client, kt):
    kt.get("/streams/10").respond(json=_stream([{"offer_id": 1, "share": 100}]))
    put = kt.put("/streams/10")
    r = client.post("/api/streams/10/offers", json={"offer_id": 1})
    assert r.status_code == 409
    assert not put.called


def test_remove_offer_redistributes_proportionally(client, kt):
    kt.get("/streams/10").respond(json=_stream([
        {"offer_id": 1, "share": 50, "state": "active"},
        {"offer_id": 2, "share": 25, "state": "disabled"},
        {"offer_id": 3, "share": 25, "state": "active"}]))
    put = kt.put("/streams/10").mock(side_effect=_put_echo)

    r = client.delete("/api/streams/10/offers/3")

    assert r.status_code == 200, r.text
    sent = json.loads(put.calls[0].request.content)["offers"]
    assert [(o["offer_id"], o["share"], o["state"]) for o in sent] == [
        (1, 67, "active"), (2, 33, "disabled")]


def test_remove_last_offer_leaves_empty_stream(client, kt):
    kt.get("/streams/10").respond(json=_stream([{"offer_id": 1, "share": 100}]))
    put = kt.put("/streams/10").mock(side_effect=_put_echo)
    r = client.delete("/api/streams/10/offers/1")
    assert r.status_code == 200
    assert json.loads(put.calls[0].request.content)["offers"] == []
    assert r.json()["offers"] == [] and r.json()["shares_valid"]


def test_remove_unknown_offer_is_404(client, kt):
    kt.get("/streams/10").respond(json=_stream([{"offer_id": 1, "share": 100}]))
    assert client.delete("/api/streams/10/offers/2").status_code == 404


def test_update_shares_requires_total_100(client, kt):
    kt.get("/streams/10").respond(json=_stream([
        {"offer_id": 1, "share": 50}, {"offer_id": 2, "share": 50}]))
    put = kt.put("/streams/10").mock(side_effect=_put_echo)

    bad = client.put("/api/streams/10/offers", json={"offers": [
        {"offer_id": 1, "share": 60}, {"offer_id": 2, "share": 50}]})
    assert bad.status_code == 422
    assert not put.called

    ok = client.put("/api/streams/10/offers", json={"offers": [
        {"offer_id": 1, "share": 80}, {"offer_id": 2, "share": 20}]})
    assert ok.status_code == 200
    sent = json.loads(put.calls[0].request.content)["offers"]
    assert [(o["offer_id"], o["share"]) for o in sent] == [(1, 80), (2, 20)]


def test_update_shares_detects_stale_offer_list(client, kt):
    kt.get("/streams/10").respond(json=_stream([{"offer_id": 1, "share": 100}]))
    r = client.put("/api/streams/10/offers", json={"offers": [
        {"offer_id": 1, "share": 50}, {"offer_id": 2, "share": 50}]})
    assert r.status_code == 409


def test_equalize(client, kt):
    kt.get("/streams/10").respond(json=_stream([
        {"offer_id": 1, "share": 90}, {"offer_id": 2, "share": 5}, {"offer_id": 3, "share": 5}]))
    put = kt.put("/streams/10").mock(side_effect=_put_echo)
    assert client.post("/api/streams/10/equalize").status_code == 200
    assert [o["share"] for o in json.loads(put.calls[0].request.content)["offers"]] == [34, 33, 33]


def test_editor_refuses_redirect_streams(client, kt):
    kt.get("/streams/10").respond(json=_stream([], schema="redirect"))
    assert client.post("/api/streams/10/offers", json={"offer_id": 1}).status_code == 422


def test_campaign_detail(client, kt):
    kt.get("/campaigns/5").respond(json={
        "id": 5, "name": "c", "alias": "c-abc", "state": "active", "group": "G",
        "domain": "https://kylovoa.com/"})
    kt.get("/campaigns/5/streams").respond(json=[
        _stream([{"offer_id": 1, "share": 60}, {"offer_id": 2, "share": 30}], stream_id=12),
        {**_stream([], stream_id=11, schema="redirect"), "position": 1,
         "action_payload": "https://www.google.com",
         "filters": [{"name": "country", "mode": "accept", "payload": ["DE"]}]},
    ])
    r = client.get("/api/campaigns/5")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["url"] == "https://kylovoa.com/c-abc"
    assert [s["id"] for s in body["streams"]] == [11, 12]
    offers_stream = body["streams"][1]
    assert offers_stream["schema"] == "landings"
    assert offers_stream["shares_total"] == 90 and not offers_stream["shares_valid"]


def test_meta_collects_dictionaries(client, kt):
    groups = kt.get("/groups", params={"type": "campaigns"}).respond(json=[{"id": 9, "name": "G"}])
    kt.get("/domains").respond(json=[{"id": 8, "name": "d.com"}])
    kt.get("/traffic_sources").respond(json=[{"id": 7, "name": "S"}])
    body = client.get("/api/meta").json()
    assert groups.called
    assert body["groups"] == [{"id": 9, "name": "G"}]
    assert body["domains"] == [{"id": 8, "name": "d.com"}]
    assert body["traffic_sources"] == [{"id": 7, "name": "S"}]
    assert [o["id"] for o in body["offers"]] == [1, 2, 3]


def test_keitaro_errors_are_passed_through(client, kt):
    kt.get("/campaigns/77").respond(404, json={"error": "Not found"})
    r = client.get("/api/campaigns/77")
    assert r.status_code == 404
    assert r.json()["source"] == "keitaro"
