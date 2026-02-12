from devialetctl.domain.events import InputEvent, InputEventType
from devialetctl.domain.policy import EventPolicy


def test_policy_deduplicates_same_key_within_window() -> None:
    p = EventPolicy(dedupe_window_s=0.5, min_interval_s=0.0)
    ev = InputEvent(kind=InputEventType.VOLUME_UP, source="cec", key="VOLUME_UP")
    assert p.should_emit(ev, now=1.0) is True
    assert p.should_emit(ev, now=1.1) is False
    assert p.should_emit(ev, now=1.6) is True


def test_policy_rate_limits_different_keys() -> None:
    p = EventPolicy(dedupe_window_s=0.0, min_interval_s=0.5)
    up = InputEvent(kind=InputEventType.VOLUME_UP, source="cec", key="VOLUME_UP")
    down = InputEvent(kind=InputEventType.VOLUME_DOWN, source="cec", key="VOLUME_DOWN")
    assert p.should_emit(up, now=1.0) is True
    assert p.should_emit(down, now=1.2) is False
    assert p.should_emit(down, now=1.7) is True
