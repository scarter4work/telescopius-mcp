"""MCP server exposing the Telescopius API as read-only planning tools."""
from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from .client import TelescopiusClient
from .compact import compact_targets, compact_weather
from .config import Config, load_config

mcp = MCPServer("telescopius")

# Every tool is a GET against Telescopius; nothing here changes account state.
_READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=True)

_config: Config | None = None
_client: TelescopiusClient | None = None


def _get() -> tuple[Config, TelescopiusClient]:
    global _config, _client
    if _client is None:
        _config = load_config()
        _client = TelescopiusClient(_config.api_key)
    return _config, _client


def _where(lat: float | None, lon: float | None, timezone: str | None) -> dict:
    """Explicit location if given, otherwise the configured home location."""
    config, _ = _get()
    loc = config.location()
    if lat is not None and lon is not None:
        loc.update(lat=lat, lon=lon)
    if timezone:
        loc["timezone"] = timezone
    return loc


# Sort keys where bigger is better; every other key (incl. popularity, a rank) reads best ascending.
_DESCENDING_BY_DEFAULT = frozenset({"imaging_time", "size"})


def _arcsec(arcmin: float | None) -> float | None:
    return None if arcmin is None else round(arcmin * 60)


@mcp.tool(annotations=_READ_ONLY)
async def sky_times(date: str | None = None, lat: float | None = None,
                    lon: float | None = None, timezone: str | None = None) -> dict:
    """Rise/transit/set for the Sun, Moon and planets, plus every twilight time
    (astronomical darkness = sun.twilights.darkest_sunset .. darkest_sunrise).

    date: "YYYY-MM-DD" or "YYYY-MM-DD HH:mm:ss"; default now. Location defaults to home.
    """
    _, client = _get()
    return await client.get("/solar-system/times", {**_where(lat, lon, timezone), "datetime": date})


@mcp.tool(annotations=_READ_ONLY)
async def tonight_highlights(types: str = "DEEP_SKY_OBJECT", date: str | None = None,
                             min_alt: float | None = 30, min_alt_minutes: int | None = None,
                             moon_dist_min: str | None = None, lat: float | None = None,
                             lon: float | None = None, timezone: str | None = None,
                             raw: bool = False) -> dict:
    """Telescopius' curated popular targets that are well placed on the given night.

    types: comma list, e.g. DEEP_SKY_OBJECT, GXY, COMET, ASTEROID.
    min_alt: degrees the target must reach; min_alt_minutes: time it must spend above that.
    moon_dist_min: minimum Moon separation in degrees at transit (string, the API also
    accepts its moon-avoidance presets). Each result carries tonight's imaging windows
    with moon illumination and distance. raw=True returns the untrimmed payload.
    """
    _, client = _get()
    payload = await client.get("/targets/highlights", {
        **_where(lat, lon, timezone), "types": types, "datetime": date,
        "min_alt": min_alt, "min_alt_minutes": min_alt_minutes, "moon_dist_min": moon_dist_min,
    })
    return payload if raw else compact_targets(payload)


@mcp.tool(annotations=_READ_ONLY)
async def search_targets(types: str = "DEEP_SKY_OBJECT", name: str | None = None,
                         date: str | None = None, min_alt: float | None = None,
                         min_alt_minutes: int | None = None, moon_dist_min: str | None = None,
                         size_min_arcmin: float | None = None, size_max_arcmin: float | None = None,
                         mag_max: float | None = None, con: str | None = None, cat: str | None = None,
                         az_quadrants: str | None = None, hour_min: str | None = None,
                         hour_max: str | None = None, order: str = "popularity",
                         order_asc: bool | None = None, results: int = 20, page: int = 1,
                         extra: dict[str, Any] | None = None, lat: float | None = None,
                         lon: float | None = None, timezone: str | None = None,
                         raw: bool = False) -> dict:
    """Advanced target search across Telescopius' full catalogue.

    name: fuzzy name match (forces name-score ordering). size_*_arcmin: apparent size
    bounds in arcminutes. con: IAU constellation abbreviations, comma separated.
    cat: catalogue acronyms (e.g. M, NGC, IC, SH2). az_quadrants: NE,NW,SW,SE in view.
    hour_min/hour_max: session window as a decimal hour or a twilight keyword such as
    "astronomical_sunset" / "astronomical_sunrise". order: name, con, dec, mag, ra, rise,
    set, transit, size, subr, type, imaging_time, popularity, opposition.
    order_asc: default picks the useful direction: most popular first, and the longest
    imaging time / largest size first (popularity is a rank, so ascending = most popular).
    results: 1-120 per page. extra: any other API parameter passed through verbatim
    (e.g. {"subr_max": 22, "dec_min": 20}). raw=True returns the untrimmed payload.
    """
    _, client = _get()
    params = {
        **_where(lat, lon, timezone), "types": types, "name": name, "datetime": date,
        "min_alt": min_alt, "min_alt_minutes": min_alt_minutes, "moon_dist_min": moon_dist_min,
        "size_min": _arcsec(size_min_arcmin), "size_max": _arcsec(size_max_arcmin),
        "mag_max": mag_max, "con": con, "cat": cat, "az_quadrants": az_quadrants,
        "hour_min": hour_min, "hour_max": hour_max, "order": order,
        "order_asc": (order not in _DESCENDING_BY_DEFAULT) if order_asc is None else order_asc,
        "results_per_page": results, "page": page, **(extra or {}),
    }
    payload = await client.get("/targets/search", params)
    return payload if raw else compact_targets(payload)


@mcp.tool(annotations=_READ_ONLY)
async def target_info(name: str, date: str | None = None, ephemeris: str | None = None,
                      lat: float | None = None, lon: float | None = None,
                      timezone: str | None = None) -> dict:
    """One named target (e.g. "IC 1805", "Heart Nebula") with tonight's visibility windows.

    ephemeris: "daily" (positions through the night) or "yearly" (next 12 months).
    Falls back to a fuzzy match when the exact name finds nothing.
    """
    _, client = _get()
    base = {**_where(lat, lon, timezone), "types": "DEEP_SKY_OBJECT,COMET,ASTEROID",
            "name": name, "datetime": date, "compute_current": 1, "results_per_page": 5}
    payload = await client.get("/targets/search", {**base, "name_exact": True, "ephemeris": ephemeris})
    if not payload.get("page_results"):
        payload = await client.get("/targets/search", {**base, "name_exact": False})
    return compact_targets(payload)


@mcp.tool(annotations=_READ_ONLY)
async def my_observing_lists() -> dict:
    """The account's saved observing lists (id, name, target count)."""
    _, client = _get()
    return await client.get("/target-lists")


@mcp.tool(annotations=_READ_ONLY)
async def observing_list(list_id: str, date: str | None = None, lat: float | None = None,
                         lon: float | None = None, timezone: str | None = None) -> dict:
    """One observing list's targets with visibility for the given night."""
    _, client = _get()
    return await client.get(f"/targets/lists/{list_id}", {**_where(lat, lon, timezone), "datetime": date})


@mcp.tool(annotations=_READ_ONLY)
async def weather_forecast(hourly_nights: int = 0, lat: float | None = None,
                           lon: float | None = None, timezone: str | None = None) -> dict:
    """Astronomy forecast: per night cloud cover, seeing, transparency, humidity, wind,
    temperature, dew risk and moon illumination (seeing/transparency are 0-100 scores).

    hourly_nights: also return the dark hours of the first N nights (0 = summary only).
    Nightly temperature is in °C: the API ignores temp_unit for the daily stats. Hourly
    rows carry no temperature or dew point, because the API returned different values
    for the same hour on repeated calls. Use relative_humidity and dew_risk instead.
    """
    _, client = _get()
    payload = await client.get("/weather/forecast", {
        **_where(lat, lon, timezone), "include_hourly": hourly_nights > 0,
    })
    return compact_weather(payload, hourly_nights)


@mcp.tool(annotations=_READ_ONLY)
async def astro_events(days: int = 30, date: str | None = None,
                       max_conjunction_deg: float | None = None) -> dict:
    """Astronomical calendar (conjunctions, occultations, moon phases, showers...) for
    the next `days` (7-365) from `date` (default today), computed for home."""
    _, client = _get()
    return await client.get("/events/calendar", {
        **_where(None, None, None), "days": days, "date": date,
        "max_conjunction_deg": max_conjunction_deg,
    })


@mcp.tool(annotations=_READ_ONLY)
async def event_highlights(limit: int = 10) -> dict:
    """The most notable upcoming sky events (1-50), with local visibility flags."""
    _, client = _get()
    return await client.get("/events/highlights", {**_where(None, None, None), "limit": limit})


@mcp.tool(annotations=_READ_ONLY)
async def my_equipment() -> dict:
    """Telescopes, cameras and other gear saved in the Telescopius account."""
    _, client = _get()
    return await client.get("/equipment/user")


@mcp.tool(annotations=_READ_ONLY)
async def astro_news() -> Any:
    """Latest headlines from Telescopius' astronomy news feeds."""
    _, client = _get()
    return await client.get("/news/global")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
