"""Frame a target in the Telescopius Telescope Simulator, in a visible stealth browser.

Telescopius sits behind Cloudflare, which answers stock Playwright and every
headless browser with a 403, so this drives patchright (a Playwright fork with
the automation fingerprints removed) in a headed window. The simulator keeps its
scope/camera settings in localStorage under ``_telescope_simulator_*``; seeding
those before the page loads frames the target with the requested rig. Mosaic
size is not persisted, so it is set on the live ``dso-telescope-simulator``
element afterwards.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

SIMULATOR_URL = "https://telescopius.com/telescope-simulator"
DATA_DIR = Path.home() / ".local/share/telescopius-mcp"
_VIEWPORT = {"width": 1400, "height": 1000}

# Same formula and 2-decimal truncation the simulator uses for its FOV readout.
_RAD = 57.3


def _trunc2(x: float) -> float:
    return int(x * 100) / 100


@dataclass(frozen=True)
class Rig:
    focal_mm: float
    sensor_w_mm: float
    sensor_h_mm: float
    px_w: int | None = None
    px_h: int | None = None

    def fov_deg(self) -> tuple[float, float]:
        return (_trunc2(_RAD * self.sensor_w_mm / self.focal_mm),
                _trunc2(_RAD * self.sensor_h_mm / self.focal_mm))

    def pixel_scale_arcsec(self) -> float | None:
        if not self.px_w:
            return None
        return round(self.sensor_w_mm / self.px_w * 206.265 / self.focal_mm * 1000, 2)


def mosaic_fov_deg(rig: Rig, cols: int, rows: int, overlap_pct: float) -> tuple[float, float]:
    w, h = rig.fov_deg()
    keep = 1 - overlap_pct / 100
    return (round(w + (cols - 1) * w * keep, 2), round(h + (rows - 1) * h * keep, 2))


def parse_pair(text: str, cast=float) -> tuple:
    """'11.136x6.264' or '2x2' -> (a, b)."""
    a, sep, b = text.lower().replace("×", "x").partition("x")
    if not sep:
        raise ValueError(f"expected WIDTHxHEIGHT, got {text!r}")
    return cast(a.strip()), cast(b.strip())


def seed_settings(rig: Rig, ra_h: float, dec_deg: float, rotation: float) -> dict[str, str]:
    """localStorage entries, JSON-encoded the way the simulator stores them."""
    s = lambda v: json.dumps(str(v))  # the simulator stores numeric settings as JSON strings
    return {
        "_telescope_simulator_mode": json.dumps("imaging"),
        "_telescope_simulator_show_intro": "false",
        "_telescope_simulator_equipment_telescope_id": "null",
        "_telescope_simulator_equipment_camera_id": "null",
        "_telescope_simulator_equipment_telescope": "null",
        "_telescope_simulator_equipment_camera": "null",
        "_telescope_simulator_settings_telescope_fl": s(rig.focal_mm),
        "_telescope_simulator_settings_telescope_flm": s(1),
        "_telescope_simulator_settings_sensor_width": s(rig.sensor_w_mm),
        "_telescope_simulator_settings_sensor_height": s(rig.sensor_h_mm),
        "_telescope_simulator_settings_sensor_width_px": s(rig.px_w) if rig.px_w else "null",
        "_telescope_simulator_settings_sensor_height_px": s(rig.px_h) if rig.px_h else "null",
        "_telescope_simulator_settings_sensor_rotation": s(rotation),
        "_telescope_simulator_ra": str(ra_h),
        "_telescope_simulator_dec": str(dec_deg),
    }


# Runs in the page's main world: Polymer properties are invisible from
# patchright's default isolated world.
_FIND_SIMULATOR = """
(() => {
  const walk = (root) => {
    for (const el of root.querySelectorAll('*')) {
      if (el.tagName.toLowerCase() === 'dso-telescope-simulator') return el;
      if (el.shadowRoot) { const hit = walk(el.shadowRoot); if (hit) return hit; }
    }
    return null;
  };
  return walk(document);
})()
"""


class FramingError(RuntimeError):
    pass


class FramingBrowser:
    def __init__(self, profile_dir: Path = DATA_DIR / "browser", shots_dir: Path = DATA_DIR / "framings"):
        self._profile_dir = profile_dir
        self._shots_dir = shots_dir
        self._pw = None
        self._ctx = None
        self._page = None
        self._temp_profile: Path | None = None

    async def _ensure_page(self):
        if self._page is not None and not self._page.is_closed():
            return self._page
        try:
            from patchright.async_api import async_playwright
        except ImportError as e:  # optional dependency
            raise FramingError("Framing needs the 'framing' extra: pip install 'telescopius-mcp[framing]' "
                               "then `patchright install chromium`.") from e
        if self._pw is None:
            self._pw = await async_playwright().start()
        if self._ctx is None:
            self._profile_dir.mkdir(parents=True, exist_ok=True)
            try:
                self._ctx = await self._launch(self._profile_dir)
            except Exception:
                # Chromium allows one browser per profile; a second server instance
                # (another Claude session) gets a throwaway profile instead.
                self._temp_profile = Path(tempfile.mkdtemp(prefix="telescopius-mcp-"))
                self._ctx = await self._launch(self._temp_profile)
        self._page = await self._ctx.new_page()
        return self._page

    async def _launch(self, profile: Path):
        # headless=False is load-bearing: Cloudflare 403s every headless browser.
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            raise FramingError("No DISPLAY or WAYLAND_DISPLAY in the server's environment; the framing "
                               "browser has to open a visible window (Cloudflare blocks headless).")
        return await self._pw.chromium.launch_persistent_context(
            str(profile), headless=False, viewport=_VIEWPORT)

    async def _goto(self, page, url: str) -> None:
        resp = await page.goto(url, wait_until="domcontentloaded")
        if resp is not None and resp.status >= 400:
            raise FramingError(f"Telescopius returned HTTP {resp.status} for {url} "
                               "(a 403 is Cloudflare refusing the browser).")

    async def show(self, *, label: str, ra_h: float, dec_deg: float, rig: Rig, rotation: float = 0,
                   cols: int = 1, rows: int = 1, overlap_pct: float = 10,
                   settle_s: float = 4.0) -> dict:
        page = await self._ensure_page()
        if not page.url.startswith("https://telescopius.com"):
            await self._goto(page, SIMULATOR_URL)  # localStorage is per origin; get onto it first
        await page.evaluate("s => { for (const [k, v] of Object.entries(s)) localStorage.setItem(k, v); }",
                            seed_settings(rig, ra_h, dec_deg, rotation))
        url = f"{SIMULATOR_URL}?ra={ra_h:.6f}&dec={dec_deg:.6f}"
        await self._goto(page, url)

        want_w, want_h = rig.fov_deg()
        deadline = time.monotonic() + 30
        state = None
        while time.monotonic() < deadline:
            state = await page.evaluate(
                f"(() => {{ const el = {_FIND_SIMULATOR}; return el ? "
                "{fovW: el.cameraFovWidth, fovH: el.cameraFovHeight, ra: el.ra, dec: el.dec} : null; })()",
                isolated_context=False)
            if state and state["fovW"] == want_w and state["fovH"] == want_h:
                break
            await page.wait_for_timeout(500)
        else:
            raise FramingError(f"Simulator never showed the requested rig (wanted FOV {want_w}x{want_h}°, "
                               f"page reports {state}).")

        # Always set, 1x1 included: the live element keeps the previous call's mosaic.
        applied = await page.evaluate(
            f"(() => {{ const el = {_FIND_SIMULATOR}; el.mosaicWidth = {int(cols)}; "
            f"el.mosaicHeight = {int(rows)}; el.mosaicOverlap = {float(overlap_pct)}; "
            "return [el.mosaicWidth, el.mosaicHeight]; })()",
            isolated_context=False)
        if [int(v) for v in applied] != [int(cols), int(rows)]:
            raise FramingError(f"Simulator rejected mosaic {cols}x{rows}; it reports {applied}.")
        await page.wait_for_timeout(int(settle_s * 1000))  # survey tiles stream in after the frame draws

        self._shots_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or "target"
        shot = self._shots_dir / f"{slug}-{cols}x{rows}-{time.strftime('%Y%m%d-%H%M%S')}.jpg"
        # JPEG: the survey imagery makes a PNG ~1.5 MB, too heavy to pass back to a phone.
        await page.locator("dso-telescope-simulator").screenshot(path=str(shot), type="jpeg", quality=85)
        await page.bring_to_front()
        return {
            "target": label,
            "simulator_url": page.url,
            "rig": {"focal_mm": rig.focal_mm, "sensor_mm": [rig.sensor_w_mm, rig.sensor_h_mm],
                    "pixel_scale_arcsec": rig.pixel_scale_arcsec()},
            "frame_fov_deg": list(rig.fov_deg()),
            "mosaic": f"{cols}x{rows}",
            "mosaic_fov_deg": list(mosaic_fov_deg(rig, cols, rows, overlap_pct)),
            "rotation_deg": rotation,
            "screenshot": str(shot),
        }

    async def close(self) -> None:
        if self._ctx is not None:
            await self._ctx.close()
        if self._pw is not None:
            await self._pw.stop()
        if self._temp_profile is not None:
            shutil.rmtree(self._temp_profile, ignore_errors=True)
        self._pw = self._ctx = self._page = self._temp_profile = None
