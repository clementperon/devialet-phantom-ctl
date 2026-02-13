from devialetctl.infrastructure.devialet_gateway import DevialetHttpGateway


def test_gateway_get_and_post_low_level(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, payload=None):
            self.payload = payload or {}
            self.raised = False

        def raise_for_status(self):
            self.raised = True

        def json(self):
            return self.payload

    calls = {"get": [], "post": []}

    def fake_get(url, timeout):
        calls["get"].append((url, timeout))
        return FakeResponse({"ok": True})

    def fake_post(url, json, timeout):
        calls["post"].append((url, json, timeout))
        return FakeResponse()

    monkeypatch.setattr("devialetctl.infrastructure.devialet_gateway.requests.get", fake_get)
    monkeypatch.setattr("devialetctl.infrastructure.devialet_gateway.requests.post", fake_post)

    gw = DevialetHttpGateway(address="10.0.0.2", port=80, base_path="/ipcontrol/v1", timeout_s=1.5)
    assert gw._get("/systems") == {"ok": True}
    gw._post("/systems/current/sources/current/soundControl/volumeUp")
    assert calls["get"][0][0].endswith("/ipcontrol/v1/systems")
    assert calls["post"][0][0].endswith(
        "/ipcontrol/v1/systems/current/sources/current/soundControl/volumeUp"
    )


def test_gateway_get_volume_raises_on_unexpected_payload(monkeypatch) -> None:
    gw = DevialetHttpGateway(address="10.0.0.2")
    monkeypatch.setattr(gw, "_get", lambda _path: {"unexpected": 1})
    try:
        gw.get_volume()
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "Unexpected response" in str(exc)


def test_gateway_endpoint_methods(monkeypatch) -> None:
    gw = DevialetHttpGateway(address="10.0.0.2")
    calls = []
    monkeypatch.setattr(gw, "_post", lambda path, payload=None: calls.append((path, payload)))
    monkeypatch.setattr(gw, "_get", lambda _path: {"volume": 12})

    assert gw.get_volume() == 12
    gw.set_volume(101)
    gw.volume_up()
    gw.volume_down()
    gw.mute_toggle()

    assert calls[0] == ("/systems/current/sources/current/soundControl/volume", {"volume": 100})
    assert calls[1][0].endswith("/volumeUp")
    assert calls[2][0].endswith("/volumeDown")
    assert calls[3][0].endswith("/mute")


def test_gateway_systems_falls_back_to_current_on_404(monkeypatch) -> None:
    class Response:
        status_code = 404

    gw = DevialetHttpGateway(address="10.0.0.2")
    calls = []

    def fake_get(path):
        calls.append(path)
        if path == "/systems":
            import requests

            raise requests.HTTPError("not found", response=Response())
        if path == "/systems/current":
            return {"id": "current"}
        raise AssertionError("unexpected path")

    monkeypatch.setattr(gw, "_get", fake_get)
    assert gw.systems() == {"id": "current"}
    assert calls == ["/systems", "/systems/current"]


def test_gateway_mute_toggle_uses_group_mute(monkeypatch) -> None:
    gw = DevialetHttpGateway(address="10.0.0.2")
    post_calls: list[tuple[str, object]] = []
    get_calls = []

    def fake_post(path, payload=None):
        post_calls.append((path, payload))
        return None

    def fake_get(path):
        get_calls.append(path)
        if path == "/groups/current/sources/current":
            return {"muteState": "unmuted"}
        raise AssertionError("unexpected path")

    monkeypatch.setattr(gw, "_post", fake_post)
    monkeypatch.setattr(gw, "_get", fake_get)
    gw.mute_toggle()

    assert post_calls[0][0] == "/groups/current/sources/current/playback/mute"
    assert get_calls == ["/groups/current/sources/current"]


def test_gateway_mute_toggle_uses_group_unmute(monkeypatch) -> None:
    gw = DevialetHttpGateway(address="10.0.0.2")
    post_calls = []

    def fake_post(path, payload=None):
        post_calls.append((path, payload))
        return None

    monkeypatch.setattr(gw, "_post", fake_post)
    monkeypatch.setattr(gw, "_get", lambda _path: {"muteState": "muted"})
    gw.mute_toggle()
    assert post_calls[0][0] == "/groups/current/sources/current/playback/unmute"
