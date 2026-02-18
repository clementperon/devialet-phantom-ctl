import devialetctl.discovery as discovery_module
from devialetctl.api import DevialetClient


def test_devialet_client_delegates_to_gateway(monkeypatch) -> None:
    class FakeGateway:
        def __init__(self, address, port, base_path, timeout_s):
            self.calls = []

        async def systems_async(self):
            self.calls.append("systems")
            return {"ok": True}

        async def get_volume_async(self):
            self.calls.append("get_volume")
            return 42

        async def set_volume_async(self, value):
            self.calls.append(("set_volume", value))

        async def volume_up_async(self):
            self.calls.append("volume_up")

        async def volume_down_async(self):
            self.calls.append("volume_down")

        async def mute_toggle_async(self):
            self.calls.append("mute_toggle")

    monkeypatch.setattr("devialetctl.api.DevialetHttpGateway", FakeGateway)
    c = DevialetClient("127.0.0.1")
    assert c.systems() == {"ok": True}
    assert c.get_volume() == 42
    c.set_volume(11)
    c.volume_up()
    c.volume_down()
    c.mute_toggle()


def test_discovery_wrapper(monkeypatch) -> None:
    class FakeMdnsGateway:
        def __init__(self, service_type):
            self.service_type = service_type

        def discover(self, timeout_s):
            class Row:
                name = "phantom"
                address = "10.0.0.2"
                port = 80
                base_path = "/ipcontrol/v1"

            return [Row()]

    class FakeUpnpGateway:
        def discover(self, timeout_s):
            return []

    # Guardrail: fail immediately if this unit test ever touches real sockets.
    def _forbid_socket(*args, **kwargs):
        raise AssertionError("Network access is not allowed in unit test_discovery_wrapper")

    monkeypatch.setattr("devialetctl.infrastructure.upnp_gateway.socket.socket", _forbid_socket)
    monkeypatch.setattr(discovery_module, "MdnsDiscoveryGateway", FakeMdnsGateway)
    monkeypatch.setattr(discovery_module, "UpnpDiscoveryGateway", lambda: FakeUpnpGateway())
    found = discovery_module.discover(timeout_s=1.0)
    assert len(found) == 1
    assert found[0].address == "10.0.0.2"
