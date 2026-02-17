from devialetctl.infrastructure import mdns_gateway


def _mk_info(addresses, properties=None, port=80):
    class Info:
        pass

    i = Info()
    i.addresses = addresses
    i.properties = properties or {}
    i.port = port
    return i


def test_listener_add_service_rejects_http_service_type(monkeypatch) -> None:
    listener = mdns_gateway._Listener()

    class FakeZC:
        def get_service_info(self, service_type, name, timeout):
            assert service_type == "_http._tcp.local."
            assert timeout == 2000
            return _mk_info(
                addresses=[bytes([192, 168, 1, 10])],
                properties={b"path": b"/ipcontrol/v1"},
                port=80,
            )

    listener.add_service(FakeZC(), "_http._tcp.local.", "Phantom._http._tcp.local.")
    assert listener.services == []


def test_listener_add_service_ignores_missing_or_non_ipv4() -> None:
    listener = mdns_gateway._Listener()

    class ZcMissing:
        def get_service_info(self, *_args, **_kwargs):
            return None

    class ZcNoIPv4:
        def get_service_info(self, *_args, **_kwargs):
            return _mk_info(addresses=[bytes([0] * 16)], properties={b"path": b"/ipcontrol/v1"})

    listener.add_service(ZcMissing(), "_http._tcp.local.", "x")
    listener.add_service(ZcNoIPv4(), "_http._tcp.local.", "x")
    assert listener.services == []


def test_listener_update_remove_methods_return_none() -> None:
    listener = mdns_gateway._Listener()
    assert listener.update_service(None, "_http._tcp.local.", "x") is None
    assert listener.remove_service(None, "_http._tcp.local.", "x") is None


def test_listener_add_service_rejects_root_path_for_http_service() -> None:
    listener = mdns_gateway._Listener()

    class FakeZC:
        def get_service_info(self, *_args, **_kwargs):
            return _mk_info(
                addresses=[bytes([192, 168, 1, 50])],
                properties={b"path": b"/"},
                port=80,
            )

    listener.add_service(FakeZC(), "_http._tcp.local.", "Salon._http._tcp.local.")
    assert listener.services == []


def test_listener_add_service_accepts_whatsup_and_normalizes_http_endpoint() -> None:
    listener = mdns_gateway._Listener()

    class FakeZC:
        def get_service_info(self, *_args, **_kwargs):
            return _mk_info(
                addresses=[bytes([192, 168, 1, 184])],
                properties={},
                port=41085,
            )

    listener.add_service(
        FakeZC(),
        "_whatsup._tcp.local.",
        "af610936-40ea-44c2-a2cd-f16fcd42451f@J50P002444U06._whatsup._tcp.local.",
    )
    assert len(listener.services) == 1
    assert listener.services[0].address == "192.168.1.184"
    assert listener.services[0].port == 80
    assert listener.services[0].base_path == "/ipcontrol/v1"


def test_discover_deduplicates_services(monkeypatch) -> None:
    class FakeZC:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    fake_zc = FakeZC()
    monkeypatch.setattr(mdns_gateway, "Zeroconf", lambda: fake_zc)

    def fake_browser(_zc, _service_type, listener):
        listener.services.append(
            mdns_gateway.MdnsService(
                name="a", address="10.0.0.2", port=80, base_path="/ipcontrol/v1"
            )
        )
        listener.services.append(
            mdns_gateway.MdnsService(
                name="b", address="10.0.0.2", port=80, base_path="/ipcontrol/v1"
            )
        )
        return None

    monkeypatch.setattr(mdns_gateway, "ServiceBrowser", fake_browser)
    monkeypatch.setattr(mdns_gateway.time, "sleep", lambda _t: None)

    found = mdns_gateway.MdnsDiscoveryGateway().discover(timeout_s=0.01)
    assert len(found) == 1
    assert found[0].address == "10.0.0.2"
    assert fake_zc.closed is True


def test_discover_browses_whatsup_only_by_default(monkeypatch) -> None:
    class FakeZC:
        def close(self) -> None:
            return None

    seen_types: list[str] = []

    monkeypatch.setattr(mdns_gateway, "Zeroconf", lambda: FakeZC())

    def fake_browser(_zc, service_type, _listener):
        seen_types.append(service_type)
        return None

    monkeypatch.setattr(mdns_gateway, "ServiceBrowser", fake_browser)
    monkeypatch.setattr(mdns_gateway.time, "sleep", lambda _t: None)

    mdns_gateway.MdnsDiscoveryGateway().discover(timeout_s=0.01)
    assert seen_types == ["_whatsup._tcp.local."]


def test_discover_keeps_browser_alive_during_sleep(monkeypatch) -> None:
    class FakeZC:
        def close(self) -> None:
            return None

    finalized = {"value": False}

    class FakeBrowser:
        def __init__(self, _zc, _service_type, _listener):
            pass

        def __del__(self) -> None:
            finalized["value"] = True

    monkeypatch.setattr(mdns_gateway, "Zeroconf", lambda: FakeZC())
    monkeypatch.setattr(mdns_gateway, "ServiceBrowser", FakeBrowser)

    def _sleep(_timeout: float) -> None:
        assert finalized["value"] is False

    monkeypatch.setattr(mdns_gateway.time, "sleep", _sleep)
    mdns_gateway.MdnsDiscoveryGateway().discover(timeout_s=0.01)
    assert finalized["value"] is True
