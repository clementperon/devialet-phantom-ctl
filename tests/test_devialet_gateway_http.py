import asyncio

from devialetctl.infrastructure.devialet_gateway import DevialetHttpGateway


def test_gateway_get_and_post_low_level(monkeypatch) -> None:
    gw = DevialetHttpGateway(address="10.0.0.2", port=80, base_path="/ipcontrol/v1", timeout_s=1.5)
    calls = {"get": [], "post": []}

    async def fake_aget(path):
        calls["get"].append(path)
        return {"ok": True}

    async def fake_apost(path, payload=None):
        calls["post"].append((path, payload))
        return None

    monkeypatch.setattr(gw, "_aget", fake_aget)
    monkeypatch.setattr(gw, "_apost", fake_apost)

    assert asyncio.run(gw._aget("/systems")) == {"ok": True}
    asyncio.run(gw._apost("/systems/current/sources/current/soundControl/volumeUp"))
    assert calls["get"] == ["/systems"]
    assert calls["post"][0][0].endswith("/soundControl/volumeUp")


def test_gateway_get_volume_raises_on_unexpected_payload(monkeypatch) -> None:
    gw = DevialetHttpGateway(address="10.0.0.2")
    async def fake_aget(_path):
        return {"unexpected": 1}

    monkeypatch.setattr(gw, "_aget", fake_aget)
    try:
        asyncio.run(gw.get_volume_async())
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "Unexpected response" in str(exc)


def test_gateway_endpoint_methods(monkeypatch) -> None:
    gw = DevialetHttpGateway(address="10.0.0.2")
    calls = []

    async def fake_apost(path, payload=None):
        calls.append((path, payload))
        return None

    async def fake_aget(path):
        if path.endswith("/volume"):
            return {"volume": 12}
        return {"muteState": "unmuted"}

    monkeypatch.setattr(gw, "_apost", fake_apost)
    monkeypatch.setattr(gw, "_aget", fake_aget)

    assert asyncio.run(gw.get_volume_async()) == 12
    assert asyncio.run(gw.get_mute_state_async()) is False
    asyncio.run(gw.set_volume_async(101))
    asyncio.run(gw.volume_up_async())
    asyncio.run(gw.volume_down_async())
    asyncio.run(gw.mute_toggle_async())

    assert calls[0] == ("/systems/current/sources/current/soundControl/volume", {"volume": 100})
    assert calls[1][0].endswith("/volumeUp")
    assert calls[2][0].endswith("/volumeDown")
    assert calls[3][0] == "/groups/current/sources/current/playback/mute"


def test_gateway_systems_falls_back_to_current_on_404(monkeypatch) -> None:
    import httpx

    gw = DevialetHttpGateway(address="10.0.0.2")
    calls = []

    async def fake_aget(path):
        calls.append(path)
        if path == "/systems":
            request = httpx.Request("GET", "http://test/systems")
            response = httpx.Response(404, request=request)
            raise httpx.HTTPStatusError("not found", request=request, response=response)
        if path == "/systems/current":
            return {"id": "current"}
        raise AssertionError("unexpected path")

    monkeypatch.setattr(gw, "_aget", fake_aget)
    assert asyncio.run(gw.systems_async()) == {"id": "current"}
    assert calls == ["/systems", "/systems/current"]


def test_gateway_mute_toggle_uses_group_mute(monkeypatch) -> None:
    gw = DevialetHttpGateway(address="10.0.0.2")
    post_calls: list[tuple[str, object]] = []
    get_calls = []

    async def fake_apost(path, payload=None):
        post_calls.append((path, payload))
        return None

    async def fake_aget(path):
        get_calls.append(path)
        if path == "/groups/current/sources/current":
            return {"muteState": "unmuted"}
        raise AssertionError("unexpected path")

    monkeypatch.setattr(gw, "_apost", fake_apost)
    monkeypatch.setattr(gw, "_aget", fake_aget)
    asyncio.run(gw.mute_toggle_async())

    assert post_calls[0][0] == "/groups/current/sources/current/playback/mute"
    assert get_calls == ["/groups/current/sources/current"]


def test_gateway_mute_toggle_uses_group_unmute(monkeypatch) -> None:
    gw = DevialetHttpGateway(address="10.0.0.2")
    post_calls = []

    async def fake_apost(path, payload=None):
        post_calls.append((path, payload))
        return None

    async def fake_aget(_path):
        return {"muteState": "muted"}

    monkeypatch.setattr(gw, "_apost", fake_apost)
    monkeypatch.setattr(gw, "_aget", fake_aget)
    asyncio.run(gw.mute_toggle_async())
    assert post_calls[0][0] == "/groups/current/sources/current/playback/unmute"
