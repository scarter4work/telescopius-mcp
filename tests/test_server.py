import httpx
import pytest

from telescopius_mcp import server
from telescopius_mcp.client import TelescopiusClient
from telescopius_mcp.config import Config


@pytest.fixture
def captured(monkeypatch):
    """Point the server at a mock transport and record each request's query params."""
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        return httpx.Response(200, json={"matched": 0, "page_results": []})

    monkeypatch.setattr(server, "_config", Config("k", 51.48, -0.01, "Europe/London"))
    monkeypatch.setattr(server, "_client", TelescopiusClient("k", transport=httpx.MockTransport(handler)))
    return seen


@pytest.mark.parametrize("order, expected", [("popularity", "1"), ("name", "1"),
                                             ("imaging_time", "0"), ("size", "0")])
async def test_search_sort_direction_defaults(captured, order, expected):
    await server.search_targets(order=order)
    assert captured[-1]["order_asc"] == expected


async def test_search_explicit_direction_wins(captured):
    await server.search_targets(order="popularity", order_asc=False)
    assert captured[-1]["order_asc"] == "0"


async def test_search_uses_home_location_and_arcmin_conversion(captured):
    await server.search_targets(size_min_arcmin=20, extra={"subr_max": 22})
    p = captured[-1]
    assert (p["lat"], p["lon"], p["timezone"]) == ("51.48", "-0.01", "Europe/London")
    assert p["size_min"] == "1200" and p["subr_max"] == "22"
    assert "size_max" not in p


async def test_target_info_falls_back_to_fuzzy_match(captured):
    await server.target_info("Heart")
    assert [p["name_exact"] for p in captured] == ["1", "0"]
