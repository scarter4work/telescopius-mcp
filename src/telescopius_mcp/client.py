"""Thin async client for the Telescopius REST API (v2.2). Errors are raised, never swallowed."""
from __future__ import annotations

from typing import Any

import httpx

BASE_URL = "https://api.telescopius.com/v2.2"


class TelescopiusError(RuntimeError):
    def __init__(self, status: int, path: str, body: str):
        super().__init__(f"Telescopius {path} returned HTTP {status}: {body[:500]}")
        self.status = status
        self.path = path
        self.body = body


def _clean(params: dict[str, Any]) -> dict[str, Any]:
    """Drop unset values and encode booleans the way the API expects (1/0)."""
    out: dict[str, Any] = {}
    for key, value in params.items():
        if value is None:
            continue
        out[key] = int(value) if isinstance(value, bool) else value
    return out


class TelescopiusClient:
    def __init__(self, api_key: str, *, base_url: str = BASE_URL,
                 transport: httpx.AsyncBaseTransport | None = None, timeout: float = 30.0):
        self._http = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Key {api_key}"},
            transport=transport,
            timeout=timeout,
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        resp = await self._http.get(path, params=_clean(params or {}))
        if resp.status_code != 200:
            raise TelescopiusError(resp.status_code, path, resp.text)
        return resp.json()
