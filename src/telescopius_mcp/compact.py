"""Trim verbose API payloads down to what matters for planning a session.

Target results run ~1.3 KB each, mostly catalogue cross-ids and image URLs; a
20-result search would otherwise flood the model's context.
"""
from __future__ import annotations

from typing import Any

_MAX_TYPES = 4


def _arcmin(arcsec: Any) -> float | None:
    return round(arcsec / 60, 1) if isinstance(arcsec, (int, float)) else None


def compact_target(result: dict) -> dict:
    obj = result.get("object", {})
    vis = result.get("tonight_visibility") or {}
    out: dict[str, Any] = {
        "id": obj.get("main_id"),
        "name": obj.get("main_name"),
        "types": (obj.get("types") or [])[:_MAX_TYPES],
        "con": obj.get("con"),
        "ra_h": obj.get("ra"),
        "dec_deg": obj.get("dec"),
        "mag": obj.get("visual_mag"),
        "size_arcmin": [_arcmin(obj.get("major_axis")), _arcmin(obj.get("minor_axis"))],
        "surface_brightness": obj.get("subr"),
        "tonight": result.get("tonight_times"),
        "max_alt": vis.get("max_altitude"),
        "max_alt_time": vis.get("max_altitude_hour"),
        "windows": vis.get("windows"),
        "url": obj.get("url"),
    }
    for key in ("current_observation", "ephemeris"):
        if key in result:
            out[key] = result[key]
    return {k: v for k, v in out.items() if v not in (None, [], [None, None])}


def compact_targets(payload: dict) -> dict:
    return {
        "matched": payload.get("matched"),
        "results": [compact_target(r) for r in payload.get("page_results", [])],
    }


# Temperature and dew point are left out on purpose: the same hour came back as
# 223 on one call and 433 on the next, so their unit can't be trusted.
_HOURLY_FIELDS = ("total_cloud_cover", "seeing", "transparency", "relative_humidity",
                  "surface_wind", "precipitation_chance", "moon_illumination", "dew_risk")


def compact_weather(payload: dict, hourly_nights: int = 0) -> dict:
    """Per-night summary; with hourly_nights > 0, also the dark hours of the first N nights.

    The raw hourly feed is ~165 entries (~70 KB), daylight included, so it is
    cut to hours with the sun down that fall within the requested nights.
    """
    days = []
    for day in payload.get("daily", []):
        sun = day.get("sun_times") or {}
        days.append({
            "date": day.get("date"),
            "astro_dark": [sun.get("darkest_sunset"), sun.get("darkest_sunrise")],
            "night": day.get("nighttime_stats"),
        })
    out: dict[str, Any] = {"daily": days}
    if hourly_nights > 0 and days:
        nights = days[:hourly_nights]
        start = f"{nights[0]['date']} 12:00:00"
        last_dark_end = nights[-1]["astro_dark"][1] or ""
        end = f"{last_dark_end[:10]} 12:00:00" if last_dark_end else None
        hours = []
        for h in payload.get("hourly", []):
            stats, when = h.get("stats") or {}, h.get("datetime") or ""
            if stats.get("sun_illumination") or when < start or (end and when >= end):
                continue
            hours.append({"time": when, **{k: stats.get(k) for k in _HOURLY_FIELDS}})
        out["hourly"] = hours
    return out
