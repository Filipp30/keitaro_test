"""Thin client for the Keitaro Admin API (https://admin-api.docs.keitaro.io)."""

from typing import Any

import httpx

from app.config import get_settings


class KeitaroError(Exception):
    def __init__(self, status_code: int, detail: Any):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Keitaro API error {status_code}: {detail}")


class KeitaroClient:
    def __init__(self, base_url: str, api_key: str, timeout: float = 30.0,
                 transport: httpx.BaseTransport | None = None):
        self._http = httpx.Client(
            base_url=base_url.rstrip("/") + "/admin_api/v1",
            headers={"Api-Key": api_key, "Accept": "application/json"},
            timeout=timeout,
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def _request(self, method: str, path: str, **kwargs) -> Any:
        try:
            resp = self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise KeitaroError(502, f"Keitaro is unreachable: {exc}") from exc
        if resp.status_code >= 400:
            try:
                detail = resp.json()
            except ValueError:
                detail = resp.text[:500]
            raise KeitaroError(resp.status_code, detail)
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError as exc:
            raise KeitaroError(502, f"Unexpected response from Keitaro: {resp.text[:300]}") from exc

    # --- dictionaries -------------------------------------------------------
    def list_groups(self, group_type: str = "campaigns") -> list[dict]:
        return self._request("GET", "/groups", params={"type": group_type})

    def list_domains(self) -> list[dict]:
        return self._request("GET", "/domains")

    def list_traffic_sources(self) -> list[dict]:
        return self._request("GET", "/traffic_sources")

    def list_offers(self) -> list[dict]:
        return self._request("GET", "/offers")

    def get_offer(self, offer_id: int) -> dict:
        return self._request("GET", f"/offers/{offer_id}")

    # --- campaigns ----------------------------------------------------------
    def list_campaigns(self) -> list[dict]:
        return self._request("GET", "/campaigns")

    def get_campaign(self, campaign_id: int) -> dict:
        return self._request("GET", f"/campaigns/{campaign_id}")

    def create_campaign(self, payload: dict) -> dict:
        return self._request("POST", "/campaigns", json=payload)

    def delete_campaign(self, campaign_id: int) -> None:
        self._request("DELETE", f"/campaigns/{campaign_id}")

    # --- streams ------------------------------------------------------------
    def list_streams(self, campaign_id: int) -> list[dict]:
        return self._request("GET", f"/campaigns/{campaign_id}/streams")

    def get_stream(self, stream_id: int) -> dict:
        return self._request("GET", f"/streams/{stream_id}")

    def create_stream(self, payload: dict) -> dict:
        return self._request("POST", "/streams", json=payload)

    def update_stream(self, stream_id: int, payload: dict) -> dict:
        return self._request("PUT", f"/streams/{stream_id}", json=payload)


def get_keitaro():
    settings = get_settings()
    client = KeitaroClient(settings.keitaro_url, settings.keitaro_api_key, settings.keitaro_timeout)
    try:
        yield client
    finally:
        client.close()
