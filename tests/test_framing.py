import json

import pytest

from telescopius_mcp import server
from telescopius_mcp.config import Config
from telescopius_mcp.framing import Rig, mosaic_fov_deg, parse_pair, seed_settings

RIG_71F_585 = Rig(490, 11.136, 6.264, 3840, 2160)


def test_fov_matches_simulator_readout():
    # The simulator showed "FOV 1.30 x 0.73° · 1.22"/px" for this rig.
    assert RIG_71F_585.fov_deg() == (1.30, 0.73)
    assert RIG_71F_585.pixel_scale_arcsec() == 1.22


def test_mosaic_fov_matches_simulator_readout():
    # 2x2 at 10% overlap read "FOV 2.47 x 1.39°" on the simulator.
    assert mosaic_fov_deg(RIG_71F_585, 2, 2, 10) == (2.47, 1.39)
    assert mosaic_fov_deg(RIG_71F_585, 1, 1, 10) == (1.30, 0.73)


@pytest.mark.parametrize("text, cast, expected", [("11.136x6.264", float, (11.136, 6.264)),
                                                  ("2 × 3", int, (2, 3)), ("3X2", int, (3, 2))])
def test_parse_pair(text, cast, expected):
    assert parse_pair(text, cast) == expected


def test_parse_pair_rejects_single_value():
    with pytest.raises(ValueError):
        parse_pair("490")


def test_seed_settings_use_simulator_encoding():
    seed = seed_settings(RIG_71F_585, 2.547333, 61.471111, 90)
    assert json.loads(seed["_telescope_simulator_settings_telescope_fl"]) == "490"
    assert json.loads(seed["_telescope_simulator_settings_sensor_rotation"]) == "90"
    assert seed["_telescope_simulator_ra"] == "2.547333"
    assert seed["_telescope_simulator_show_intro"] == "false"


def test_seed_settings_without_pixel_counts():
    seed = seed_settings(Rig(400, 36, 24), 0, 0, 0)
    assert seed["_telescope_simulator_settings_sensor_width_px"] == "null"


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(server, "_config", Config("k", None, None, None, 490, "11.136x6.264", "3840x2160"))
    monkeypatch.setattr(server, "_client", object())


def test_rig_defaults_from_config(configured):
    assert server._rig(None, None, None) == RIG_71F_585


def test_rig_override_sensor_drops_default_pixel_count(configured):
    assert server._rig(1800, "36x24", None) == Rig(1800, 36, 24)


def test_rig_missing_is_loud(monkeypatch):
    monkeypatch.setattr(server, "_config", Config("k", None, None, None))
    monkeypatch.setattr(server, "_client", object())
    with pytest.raises(ValueError, match="No rig"):
        server._rig(None, None, None)
