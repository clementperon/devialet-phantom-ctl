import sys

import pytest

from devialetctl.interfaces import cli


def test_cli_list_prints_discovered_services(monkeypatch, capsys) -> None:
    class FakeDiscovery:
        def discover(self, timeout_s):
            class Row:
                name = "phantom"
                address = "10.0.0.2"
                port = 80
                base_path = "/ipcontrol/v1"

            return [Row()]

    monkeypatch.setattr(cli, "MdnsDiscoveryGateway", lambda: FakeDiscovery())
    monkeypatch.setattr(sys, "argv", ["devialetctl", "list"])
    cli.main()
    out = capsys.readouterr().out
    assert "10.0.0.2:80/ipcontrol/v1" in out


def test_cli_getvol_uses_gateway(monkeypatch, capsys) -> None:
    class FakeDiscovery:
        def discover(self, timeout_s):
            class Row:
                name = "phantom"
                address = "10.0.0.2"
                port = 80
                base_path = "/ipcontrol/v1"

            return [Row()]

    class FakeGateway:
        def __init__(self, address, port, base_path):
            self.address = address

        async def systems_async(self):
            return {}

        async def get_volume_async(self):
            return 31

        async def set_volume_async(self, value):
            return None

        async def volume_up_async(self):
            return None

        async def volume_down_async(self):
            return None

        async def mute_toggle_async(self):
            return None

    monkeypatch.setattr(cli, "MdnsDiscoveryGateway", lambda: FakeDiscovery())
    monkeypatch.setattr(cli, "DevialetHttpGateway", FakeGateway)
    monkeypatch.setattr(sys, "argv", ["devialetctl", "getvol"])
    cli.main()
    out = capsys.readouterr().out
    assert out.strip() == "31"


def test_cli_daemon_keyboard_selects_runner_mode(monkeypatch) -> None:
    class FakeDiscovery:
        def discover(self, timeout_s):
            class Row:
                name = "phantom"
                address = "10.0.0.2"
                port = 80
                base_path = "/ipcontrol/v1"

            return [Row()]

    class FakeGateway:
        def __init__(self, address, port, base_path):
            self.address = address

    class FakeRunner:
        called_with = None

        def __init__(self, cfg, gateway):
            self.cfg = cfg
            self.gateway = gateway

        def run_forever(self, input_name):
            FakeRunner.called_with = input_name

    monkeypatch.setattr(cli, "MdnsDiscoveryGateway", lambda: FakeDiscovery())
    monkeypatch.setattr(cli, "DevialetHttpGateway", FakeGateway)
    monkeypatch.setattr(cli, "DaemonRunner", FakeRunner)
    monkeypatch.setattr(sys, "argv", ["devialetctl", "daemon", "--input", "keyboard"])
    cli.main()
    assert FakeRunner.called_with == "keyboard"


def test_cli_daemon_accepts_subcommand_index(monkeypatch) -> None:
    class FakeDiscovery:
        def discover(self, timeout_s):
            class S0:
                name = "dev0"
                address = "10.0.0.10"
                port = 80
                base_path = "/ipcontrol/v1"

            class S1:
                name = "dev1"
                address = "10.0.0.11"
                port = 80
                base_path = "/ipcontrol/v1"

            return [S0(), S1()]

    class FakeGateway:
        picked_address = None

        def __init__(self, address, port, base_path):
            FakeGateway.picked_address = address

    class FakeRunner:
        def __init__(self, cfg, gateway):
            self.cfg = cfg
            self.gateway = gateway

        def run_forever(self, input_name):
            return None

    monkeypatch.setattr(cli, "MdnsDiscoveryGateway", lambda: FakeDiscovery())
    monkeypatch.setattr(cli, "DevialetHttpGateway", FakeGateway)
    monkeypatch.setattr(cli, "DaemonRunner", FakeRunner)
    monkeypatch.setattr(
        sys,
        "argv",
        ["devialetctl", "daemon", "--input", "keyboard", "--index", "1"],
    )
    cli.main()
    assert FakeGateway.picked_address == "10.0.0.11"


def test_cli_list_when_empty(monkeypatch, capsys) -> None:
    class FakeDiscovery:
        def discover(self, timeout_s):
            return []

    monkeypatch.setattr(cli, "MdnsDiscoveryGateway", lambda: FakeDiscovery())
    monkeypatch.setattr(sys, "argv", ["devialetctl", "list"])
    cli.main()
    out = capsys.readouterr().out
    assert "No service detected." in out


def test_cli_daemon_handles_runtime_error(monkeypatch, capsys) -> None:
    class FakeDiscovery:
        def discover(self, timeout_s):
            class Row:
                name = "phantom"
                address = "10.0.0.2"
                port = 80
                base_path = "/ipcontrol/v1"

            return [Row()]

    class FakeGateway:
        def __init__(self, address, port, base_path):
            self.address = address

    class FakeRunner:
        def __init__(self, cfg, gateway):
            self.cfg = cfg
            self.gateway = gateway

        def run_forever(self, input_name):
            raise RuntimeError("boom")

    monkeypatch.setattr(cli, "MdnsDiscoveryGateway", lambda: FakeDiscovery())
    monkeypatch.setattr(cli, "DevialetHttpGateway", FakeGateway)
    monkeypatch.setattr(cli, "DaemonRunner", FakeRunner)
    monkeypatch.setattr(sys, "argv", ["devialetctl", "daemon", "--input", "keyboard"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "Daemon error: boom" in err
