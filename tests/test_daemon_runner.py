from devialetctl.application.daemon import DaemonRunner
from devialetctl.infrastructure.config import DaemonConfig, RuntimeTarget


def test_daemon_runner_routes_events(monkeypatch) -> None:
    class FakeGateway:
        def __init__(self):
            self.calls = []

        def systems(self):
            return {}

        def get_volume(self):
            return 0

        def set_volume(self, volume):
            self.calls.append(("set", volume))

        def volume_up(self):
            self.calls.append("up")

        def volume_down(self):
            self.calls.append("down")

        def mute_toggle(self):
            self.calls.append("mute")

    from devialetctl.domain.events import InputEvent, InputEventType

    class OneShotAdapter:
        def __init__(self, command):
            self.command = command

        def events(self):
            yield InputEvent(kind=InputEventType.VOLUME_UP, source="cec", key="VOLUME_UP")
            raise KeyboardInterrupt()

    monkeypatch.setattr("devialetctl.application.daemon.CecClientAdapter", OneShotAdapter)
    cfg = DaemonConfig(target=RuntimeTarget(ip="10.0.0.2"), min_interval_s=0.0, dedupe_window_s=0.0)
    gw = FakeGateway()
    runner = DaemonRunner(cfg=cfg, gateway=gw)
    try:
        runner.run_cec_forever()
    except KeyboardInterrupt:
        pass
    assert gw.calls == [("set", 1)]


def test_daemon_runner_keyboard_mode(monkeypatch) -> None:
    class FakeGateway:
        def __init__(self):
            self.calls = []

        def systems(self):
            return {}

        def get_volume(self):
            return 10

        def set_volume(self, volume):
            self.calls.append(("set", volume))

        def volume_up(self):
            self.calls.append("up")

        def volume_down(self):
            self.calls.append("down")

        def mute_toggle(self):
            self.calls.append("mute")

    from devialetctl.domain.events import InputEvent, InputEventType

    class FakeKeyboardAdapter:
        def events(self):
            yield InputEvent(kind=InputEventType.VOLUME_DOWN, source="keyboard", key="d")

    monkeypatch.setattr("devialetctl.application.daemon.KeyboardAdapter", FakeKeyboardAdapter)
    cfg = DaemonConfig(target=RuntimeTarget(ip="10.0.0.2"), min_interval_s=0.0, dedupe_window_s=0.0)
    gw = FakeGateway()
    runner = DaemonRunner(cfg=cfg, gateway=gw)
    runner.run_forever(input_name="keyboard")
    assert gw.calls == [("set", 9)]
