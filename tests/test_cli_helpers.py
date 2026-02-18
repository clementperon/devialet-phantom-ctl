from types import SimpleNamespace

import pytest

from devialetctl.interfaces import cli
from devialetctl.infrastructure.config import DaemonConfig, RuntimeTarget


def _service(name="dev", address="10.0.0.2", port=80, base_path="/ipcontrol/v1"):
    return SimpleNamespace(name=name, address=address, port=port, base_path=base_path)


def test_pick_raises_on_empty_list() -> None:
    with pytest.raises(RuntimeError, match="No service"):
        cli._pick([])


def test_target_from_args_uses_daemon_overrides() -> None:
    cfg = DaemonConfig(target=RuntimeTarget())
    args = SimpleNamespace(
        cmd="daemon",
        ip="10.0.0.9",
        port=8080,
        discover_timeout=None,
        system=None,
    )
    resolved = cli._effective_options(args, cfg)
    target = cli._target_from_resolved(resolved)
    assert target.address == "10.0.0.9"
    assert target.port == 8080
    assert target.base_path == "/ipcontrol/v1"
