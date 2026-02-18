from devialetctl.infrastructure import upnp_gateway


def test_parse_ssdp_headers_lowercases_and_ignores_invalid_lines() -> None:
    payload = (
        b"HTTP/1.1 200 OK\r\n"
        b"LOCATION: http://10.0.0.2:1400/desc.xml\r\n"
        b"ST: urn:schemas-upnp-org:device:MediaRenderer:2\r\n"
        b"USN: uuid:abc::urn:schemas-upnp-org:device:MediaRenderer:2\r\n"
        b"bad line without colon\r\n"
        b"\r\n"
    )
    headers = upnp_gateway._parse_ssdp_headers(payload)
    assert headers["location"] == "http://10.0.0.2:1400/desc.xml"
    assert headers["st"] == "urn:schemas-upnp-org:device:MediaRenderer:2"
    assert headers["usn"] == "uuid:abc::urn:schemas-upnp-org:device:MediaRenderer:2"
    assert "bad line without colon" not in headers


def test_is_devialet_manufacturer_accepts_devialet_tag_and_caps_timeout(monkeypatch) -> None:
    captured = {"timeout": None}

    class FakeResponse:
        text = "<root><manufacturer>  deViaLet </manufacturer></root>"

        @staticmethod
        def raise_for_status():
            return None

    class FakeClient:
        def __init__(self, timeout):
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, location):
            return FakeResponse()

    monkeypatch.setattr(upnp_gateway.httpx, "Client", FakeClient)
    ok = upnp_gateway._is_devialet_manufacturer("http://10.0.0.2:1400/desc.xml", timeout_s=9.0)
    assert ok is True
    assert captured["timeout"] == 1.5


def test_is_devialet_manufacturer_rejects_non_devialet_tag(monkeypatch) -> None:
    class FakeResponse:
        text = "<root><manufacturer>OtherBrand</manufacturer></root>"

        @staticmethod
        def raise_for_status():
            return None

    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, location):
            return FakeResponse()

    monkeypatch.setattr(upnp_gateway.httpx, "Client", FakeClient)
    ok = upnp_gateway._is_devialet_manufacturer("http://10.0.0.3:1400/desc.xml", timeout_s=0.05)
    assert ok is False


def test_is_devialet_manufacturer_returns_false_on_http_error(monkeypatch) -> None:
    class FakeClient:
        def __init__(self, timeout):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, location):
            raise RuntimeError("boom")

    monkeypatch.setattr(upnp_gateway.httpx, "Client", FakeClient)
    ok = upnp_gateway._is_devialet_manufacturer("http://10.0.0.4:1400/desc.xml", timeout_s=1.0)
    assert ok is False


def test_discover_filters_non_devialet_missing_host_and_duplicates(monkeypatch) -> None:
    def fake_iter(timeout_s):
        return iter(
            [
                {"location": "http://10.0.0.2:1400/desc.xml"},
                {"location": "http://10.0.0.2:1400/desc.xml"},
                {"location": "not-a-url"},
                {"location": "http://10.0.0.3:1400/desc.xml"},
            ]
        )

    def fake_is_devialet_manufacturer(location, timeout_s):
        return "10.0.0.3" not in location

    monkeypatch.setattr(upnp_gateway, "_iter_ssdp_responses", fake_iter)
    monkeypatch.setattr(upnp_gateway, "_is_devialet_manufacturer", fake_is_devialet_manufacturer)

    targets = upnp_gateway.UpnpDiscoveryGateway().discover(timeout_s=0.1)
    assert len(targets) == 1
    assert targets[0].address == "10.0.0.2"
    assert targets[0].port == 80
    assert targets[0].base_path == "/ipcontrol/v1"
    assert targets[0].name == "UPnP:10.0.0.2"
