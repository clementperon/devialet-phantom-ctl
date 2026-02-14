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


def test_daemon_runner_reports_cec_audio_status(monkeypatch) -> None:
    class FakeGateway:
        def systems(self):
            return {}

        def get_volume(self):
            return 11

        def get_mute_state(self):
            return True

        def set_volume(self, volume):
            return None

        def volume_up(self):
            return None

        def volume_down(self):
            return None

        def mute_toggle(self):
            return None

    from devialetctl.domain.events import InputEvent, InputEventType

    sent_frames: list[str] = []

    class OneShotAdapter:
        def __init__(self, command):
            self.command = command

        def events(self):
            yield InputEvent(
                kind=InputEventType.GIVE_AUDIO_STATUS,
                source="cec",
                key="GIVE_AUDIO_STATUS",
            )
            raise KeyboardInterrupt()

        def send_tx(self, frame: str) -> bool:
            sent_frames.append(frame)
            return True

    monkeypatch.setattr("devialetctl.application.daemon.CecClientAdapter", OneShotAdapter)
    cfg = DaemonConfig(target=RuntimeTarget(ip="10.0.0.2"), min_interval_s=0.0, dedupe_window_s=0.0)
    runner = DaemonRunner(cfg=cfg, gateway=FakeGateway())
    try:
        runner.run_cec_forever()
    except KeyboardInterrupt:
        pass

    # muted bit set (0x80) + volume (11)
    assert sent_frames == ["50:7A:8B", "50:73:8B"]


def test_daemon_runner_replies_system_audio_and_arc_requests(monkeypatch) -> None:
    class FakeGateway:
        def systems(self):
            return {}

        def get_volume(self):
            return 11

        def get_mute_state(self):
            return False

        def set_volume(self, volume):
            return None

        def volume_up(self):
            return None

        def volume_down(self):
            return None

        def mute_toggle(self):
            return None

    from devialetctl.domain.events import InputEvent, InputEventType

    sent_frames: list[str] = []

    class OneShotAdapter:
        def __init__(self, command):
            self.command = command

        def events(self):
            yield InputEvent(
                kind=InputEventType.SYSTEM_AUDIO_MODE_REQUEST,
                source="cec",
                key="SYSTEM_AUDIO_MODE_REQUEST",
            )
            yield InputEvent(
                kind=InputEventType.GIVE_SYSTEM_AUDIO_MODE_STATUS,
                source="cec",
                key="GIVE_SYSTEM_AUDIO_MODE_STATUS",
            )
            yield InputEvent(
                kind=InputEventType.REQUEST_ARC_INITIATION,
                source="cec",
                key="REQUEST_ARC_INITIATION",
            )
            yield InputEvent(
                kind=InputEventType.REQUEST_ARC_TERMINATION,
                source="cec",
                key="REQUEST_ARC_TERMINATION",
            )
            raise KeyboardInterrupt()

        def send_tx(self, frame: str) -> bool:
            sent_frames.append(frame)
            return True

    monkeypatch.setattr("devialetctl.application.daemon.CecClientAdapter", OneShotAdapter)
    cfg = DaemonConfig(target=RuntimeTarget(ip="10.0.0.2"), min_interval_s=0.0, dedupe_window_s=0.0)
    runner = DaemonRunner(cfg=cfg, gateway=FakeGateway())
    try:
        runner.run_cec_forever()
    except KeyboardInterrupt:
        pass

    assert sent_frames == ["50:72:01", "50:7E:01", "50:C1", "50:C2"]


def test_daemon_runner_handles_set_audio_volume_level(monkeypatch) -> None:
    class FakeGateway:
        def __init__(self):
            self.calls = []
            self.muted = True

        def systems(self):
            return {}

        def get_volume(self):
            return 26

        def get_mute_state(self):
            return self.muted

        def set_volume(self, volume):
            self.calls.append(("set", volume))

        def volume_up(self):
            return None

        def volume_down(self):
            return None

        def mute_toggle(self):
            self.calls.append("mute")
            self.muted = not self.muted

    from devialetctl.domain.events import InputEvent, InputEventType

    sent_frames: list[str] = []

    class OneShotAdapter:
        def __init__(self, command):
            self.command = command

        def events(self):
            yield InputEvent(
                kind=InputEventType.SET_AUDIO_VOLUME_LEVEL,
                source="cec",
                key="SET_AUDIO_VOLUME_LEVEL",
                value=26,
                muted=False,
            )
            raise KeyboardInterrupt()

        def send_tx(self, frame: str) -> bool:
            sent_frames.append(frame)
            return True

    monkeypatch.setattr("devialetctl.application.daemon.CecClientAdapter", OneShotAdapter)
    cfg = DaemonConfig(target=RuntimeTarget(ip="10.0.0.2"), min_interval_s=0.0, dedupe_window_s=0.0)
    gw = FakeGateway()
    runner = DaemonRunner(cfg=cfg, gateway=gw)
    try:
        runner.run_cec_forever()
    except KeyboardInterrupt:
        pass

    assert gw.calls == [("set", 26), "mute"]
    assert sent_frames == ["50:7A:1A", "50:73:1A"]
