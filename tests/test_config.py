import pytest

from telescopius_mcp.config import MissingApiKeyError, load_config


@pytest.fixture(autouse=True)
def _no_ambient_env(monkeypatch):
    for name in ("TELESCOPIUS_API_KEY", "TELESCOPIUS_LAT", "TELESCOPIUS_LON", "TELESCOPIUS_TZ"):
        monkeypatch.delenv(name, raising=False)


def test_reads_env_file(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# comment\nTELESCOPIUS_API_KEY=abc\nTELESCOPIUS_LAT=51.5\nTELESCOPIUS_LON=-0.1\n"
                   "TELESCOPIUS_TZ=Europe/London\n")
    cfg = load_config(env)
    assert cfg.api_key == "abc"
    assert cfg.location() == {"lat": 51.5, "lon": -0.1, "timezone": "Europe/London"}


def test_environment_overrides_file(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("TELESCOPIUS_API_KEY=file\n")
    monkeypatch.setenv("TELESCOPIUS_API_KEY", "env")
    assert load_config(env).api_key == "env"


def test_missing_key_is_loud(tmp_path):
    with pytest.raises(MissingApiKeyError):
        load_config(tmp_path / "absent.env")


def test_no_location_means_ip_autodetect(tmp_path):
    env = tmp_path / ".env"
    env.write_text("TELESCOPIUS_API_KEY=abc\n")
    assert load_config(env).location() == {}
