"""Settings from the environment, with a git-ignored .env beside the project as fallback."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class MissingApiKeyError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    api_key: str
    lat: float | None
    lon: float | None
    timezone: str | None
    focal_mm: float | None = None
    sensor_mm: str | None = None   # "WIDTHxHEIGHT", e.g. "11.136x6.264"
    sensor_px: str | None = None   # "WIDTHxHEIGHT", e.g. "3840x2160"

    def location(self) -> dict:
        """Default observer location; empty when unset, so the API falls back to IP geolocation."""
        loc: dict = {}
        if self.lat is not None and self.lon is not None:
            loc.update(lat=self.lat, lon=self.lon)
        if self.timezone:
            loc["timezone"] = self.timezone
        return loc


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_config(env_file: Path | None = None) -> Config:
    path = env_file or Path(os.environ.get("TELESCOPIUS_ENV_FILE", DEFAULT_ENV_FILE))
    file_values = _read_env_file(path)

    def get(name: str) -> str | None:
        return os.environ.get(name) or file_values.get(name) or None

    api_key = get("TELESCOPIUS_API_KEY")
    if not api_key:
        raise MissingApiKeyError(f"Set TELESCOPIUS_API_KEY (environment or {path}).")
    lat, lon = get("TELESCOPIUS_LAT"), get("TELESCOPIUS_LON")
    return Config(
        api_key=api_key,
        lat=float(lat) if lat else None,
        lon=float(lon) if lon else None,
        timezone=get("TELESCOPIUS_TZ"),
        focal_mm=float(get("TELESCOPIUS_FOCAL_MM")) if get("TELESCOPIUS_FOCAL_MM") else None,
        sensor_mm=get("TELESCOPIUS_SENSOR_MM"),
        sensor_px=get("TELESCOPIUS_SENSOR_PX"),
    )
