from devialetctl.application.router import EventRouter
from devialetctl.domain.events import InputEvent, InputEventType


def test_router_skips_when_policy_blocks() -> None:
    class FakeService:
        def __init__(self):
            self.called = []

        def volume_up(self):
            self.called.append("up")

        def volume_down(self):
            self.called.append("down")

        def mute(self):
            self.called.append("mute")

    class BlockAllPolicy:
        def should_emit(self, _event):
            return False

    svc = FakeService()
    router = EventRouter(service=svc, policy=BlockAllPolicy())
    result = router.handle(InputEvent(kind=InputEventType.VOLUME_UP, source="test", key="u"))
    assert result is False
    assert svc.called == []


def test_router_routes_known_events() -> None:
    class FakeService:
        def __init__(self):
            self.called = []

        def volume_up(self):
            self.called.append("up")

        def volume_down(self):
            self.called.append("down")

        def mute(self):
            self.called.append("mute")

    class AllowPolicy:
        def should_emit(self, _event):
            return True

    svc = FakeService()
    router = EventRouter(service=svc, policy=AllowPolicy())
    assert router.handle(InputEvent(kind=InputEventType.VOLUME_UP, source="t", key="u")) is True
    assert router.handle(InputEvent(kind=InputEventType.VOLUME_DOWN, source="t", key="d")) is True
    assert router.handle(InputEvent(kind=InputEventType.MUTE, source="t", key="m")) is True
    assert svc.called == ["up", "down", "mute"]


def test_router_returns_false_for_unknown_kind() -> None:
    class FakeService:
        def volume_up(self):
            return None

        def volume_down(self):
            return None

        def mute(self):
            return None

    class AllowPolicy:
        def should_emit(self, _event):
            return True

    router = EventRouter(service=FakeService(), policy=AllowPolicy())
    event = InputEvent(kind="unknown", source="t", key="x")  # type: ignore[arg-type]
    assert router.handle(event) is False
