from devialetctl.infrastructure.mdns_gateway import _is_likely_devialet


def test_mdns_filter_accepts_devialet_name() -> None:
    assert _is_likely_devialet("Phantom I Gold._http._tcp.local.", None) is True


def test_mdns_filter_accepts_ipcontrol_txt_path() -> None:
    assert _is_likely_devialet("Unknown Device._http._tcp.local.", "/ipcontrol/v1") is True


def test_mdns_filter_rejects_unrelated_http_service() -> None:
    assert _is_likely_devialet("Freebox Server._http._tcp.local.", None) is False
