import httpx
import pytest

from telescopius_mcp.client import TelescopiusClient, TelescopiusError, _clean


def test_clean_drops_none_and_encodes_bools():
    assert _clean({"a": None, "b": True, "c": False, "d": 0, "e": "x"}) == {"b": 1, "c": 0, "d": 0, "e": "x"}


async def test_get_sends_key_header_and_params():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["Authorization"]
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"ok": True})

    client = TelescopiusClient("k123", transport=httpx.MockTransport(handler))
    assert await client.get("/quote-of-the-day", {"lat": 40, "skip": None, "flag": True}) == {"ok": True}
    await client.close()
    assert seen["auth"] == "Key k123"
    assert seen["url"] == "https://api.telescopius.com/v2.2/quote-of-the-day?lat=40&flag=1"


async def test_non_200_raises_with_status_and_body():
    client = TelescopiusClient("bad", transport=httpx.MockTransport(
        lambda r: httpx.Response(401, text="invalid key")))
    with pytest.raises(TelescopiusError) as err:
        await client.get("/equipment/user")
    await client.close()
    assert err.value.status == 401
    assert "invalid key" in str(err.value)
