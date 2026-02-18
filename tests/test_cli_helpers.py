from types import SimpleNamespace

import pytest

from devialetctl.interfaces import cli


def _service(name="dev", address="10.0.0.2", port=80, base_path="/ipcontrol/v1"):
    return SimpleNamespace(name=name, address=address, port=port, base_path=base_path)


def test_pick_raises_on_empty_list() -> None:
    with pytest.raises(RuntimeError, match="No service"):
        cli._pick([])


def test_target_from_args_uses_daemon_overrides() -> None:
    args = SimpleNamespace(
        cmd="daemon",
        ip=None,
        port=80,
        discover_timeout=3.0,
        system=None,
        daemon_ip="10.0.0.9",
        daemon_port=8080,
        daemon_discover_timeout=1.0,
        daemon_system=None,
    )
    target = cli._target_from_args(args)
    assert target.address == "10.0.0.9"
    assert target.port == 8080
    assert target.base_path == "/ipcontrol/v1"
