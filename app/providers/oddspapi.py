"""
OddsPapi REST client.

Docs: https://oddspapi.io/blog/esports-odds-api-guide
"""

import httpx
import structlog
from datetime import datetime, timedelta
from typing import Any

from app.core.config import get_settings

log = structlog.get_logger()

SPORT_IDS = {
    "cs2": 17, "csgo": 17, "lol": 18,
    "dota2": 16, "valorant": 61, "cod": 56, "rocketleague": 59,
}


class OddsPapiClient:
    """Thin async wrapper around OddsPapi v4."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        s = get_settings()
        self.api_key = api_key or s.oddspapi_api_key
        self.base_url = base_url or s.oddspapi_base_url
        self._client = httpx.AsyncClient(timeout=30)

    # ---- low-level ----

    async def _get(self, path: str, params: dict | None = None) -> Any:
        params = params or {}
        params["apiKey"] = self.api_key
        resp = await self._client.get(f"{self.base_url}{path}", params=params)
        resp.raise_for_status()
        return resp.json()

    # ---- public ----

    async def fetch_fixtures(
        self,
        sport: str = "cs2",
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        has_odds: bool = True,
    ) -> list[dict]:
        sport_id = SPORT_IDS.get(sport.lower())
        if not sport_id:
            raise ValueError(f"Unknown sport {sport}")
        from_date = from_date or datetime.utcnow()
        to_date = to_date or from_date + timedelta(days=7)
        params = {
            "sportId": sport_id,
            "from": from_date.strftime("%Y-%m-%d"),
            "to": to_date.strftime("%Y-%m-%d"),
        }
        if has_odds:
            params["hasOdds"] = "true"
        data = await self._get("/fixtures", params)
        log.info("fetched_fixtures", sport=sport, count=len(data))
        return data

    async def fetch_odds(self, fixture_id: str) -> dict:
        return await self._get("/odds", {"fixtureId": fixture_id})

    async def fetch_historical_odds(
        self, fixture_id: str, bookmakers: list[str] | None = None, market_id: int = 171,
    ) -> dict:
        params: dict[str, Any] = {"fixtureId": fixture_id, "marketId": market_id}
        if bookmakers:
            params["bookmakers"] = ",".join(bookmakers[:3])
        return await self._get("/historical-odds", params)

    async def close(self):
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()
