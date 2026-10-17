# telescopius-mcp

Read-only MCP server for the [Telescopius](https://telescopius.com) REST API (v2.2): target planning,
sky times, astronomy weather, events, and the account's observing lists and equipment.

## Setup

```bash
uv venv .venv && uv pip install --python .venv/bin/python -e '.[dev,framing]'
.venv/bin/patchright install chromium   # only for show_framing
cp .env.example .env   # add your API key (Telescopius → Settings → API Keys), home location, default rig
claude mcp add --scope user telescopius -- "$PWD/.venv/bin/telescopius-mcp"
```

The server reads `TELESCOPIUS_*` from the environment first, then from `.env` beside the project
(override the path with `TELESCOPIUS_ENV_FILE`). With no location configured, the API geolocates by IP.

## Tools

| Tool | Endpoint |
|---|---|
| `sky_times` | `/solar-system/times`: sun/moon/planet rise-set, all twilights |
| `tonight_highlights` | `/targets/highlights`: curated targets well placed tonight |
| `search_targets` | `/targets/search`: full catalogue search; size in arcmin, `extra` passes any other API param |
| `target_info` | `/targets/search` by name, exact then fuzzy, with tonight's windows |
| `my_observing_lists`, `observing_list` | `/target-lists`, `/targets/lists/{id}` |
| `weather_forecast` | `/weather/forecast`: nightly summary, optional dark-hour detail |
| `astro_events`, `event_highlights` | `/events/calendar`, `/events/highlights` |
| `my_equipment` | `/equipment/user` |
| `astro_news` | `/news/global` |
| `show_framing`, `close_framing` | Telescope Simulator in a browser window; returns a screenshot |

### Framing

`show_framing("Heart Nebula", mosaic="2x2", rotation=0)` resolves the target through the API, opens
Telescopius' Telescope Simulator framed with your rig, and returns the framing as a JPEG (also saved under
`~/.local/share/telescopius-mcp/framings/`). The window stays open for hands-on tweaking. The default rig
comes from `TELESCOPIUS_FOCAL_MM` / `TELESCOPIUS_SENSOR_MM` / `TELESCOPIUS_SENSOR_PX`; any call can override it.

It needs a desktop session. Cloudflare returns 403 to stock Playwright and to every headless browser, so
it drives [patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright-python) in a headed window. The
simulator keeps its scope and camera settings in `localStorage` (`_telescope_simulator_*`), which the tool
seeds before loading. Mosaic size isn't persisted, so the tool sets it on the live element.

Target results are trimmed to planning fields (pass `raw=True` for the full payload).

## API quirks found while building

- `order=popularity` is a rank: ascending = most popular. `search_targets` picks the useful direction by default.
- `size_min`/`size_max` are arcseconds on the wire; the tool takes arcminutes.
- Weather: daily stats are °C whatever `temp_unit` says. Hourly temperature/dew point came back as different numbers for the same hour on repeated calls, so they're dropped.

## Tests

`.venv/bin/pytest`. Tests run against a mock transport and never call the API.
