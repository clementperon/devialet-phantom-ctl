from devialetctl.infrastructure.devialet_gateway import DevialetHttpGateway, normalize_base_path


def test_normalize_base_path_defaults_when_empty_or_root() -> None:
    assert normalize_base_path(None) == "/ipcontrol/v1"
    assert normalize_base_path("") == "/ipcontrol/v1"
    assert normalize_base_path("/") == "/ipcontrol/v1"


def test_normalize_base_path_accepts_without_leading_slash() -> None:
    assert normalize_base_path("ipcontrol/v1") == "/ipcontrol/v1"


def test_gateway_uses_normalized_base_path() -> None:
    gw = DevialetHttpGateway(address="192.168.1.184", port=80, base_path="/")
    assert gw.base_url == "http://192.168.1.184:80/ipcontrol/v1"
