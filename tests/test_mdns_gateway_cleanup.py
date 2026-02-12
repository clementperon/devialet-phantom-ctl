import pytest

from devialetctl.infrastructure import mdns_gateway


def test_discovery_closes_zeroconf_on_interrupt(monkeypatch) -> None:
    class FakeZeroconf:
        def __init__(self):
            self.closed = False

        def close(self) -> None:
            self.closed = True

    fake_zc = FakeZeroconf()

    monkeypatch.setattr(mdns_gateway, "Zeroconf", lambda: fake_zc)
    monkeypatch.setattr(mdns_gateway, "ServiceBrowser", lambda *_args, **_kwargs: None)

    def _sleep_and_interrupt(_timeout: float) -> None:
        raise KeyboardInterrupt()

    monkeypatch.setattr(mdns_gateway.time, "sleep", _sleep_and_interrupt)

    gateway = mdns_gateway.MdnsDiscoveryGateway()
    with pytest.raises(KeyboardInterrupt):
        gateway.discover(timeout_s=0.1)
    assert fake_zc.closed is True
