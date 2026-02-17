from devialetctl.infrastructure import mdns_gateway


def _mk_info(addresses, properties=None, port=80):
    class Info:
        pass

    i = Info()
    i.addresses = addresses
    i.properties = properties or {}
    i.port = port
    return i


def test_listener_add_service_filters_and_adds_devialet(monkeypatch) -> None:
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
    assert len(listener.services) == 1
    assert listener.services[0].address == "192.168.1.10"


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
