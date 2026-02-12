from devialetctl.domain.events import InputEventType
from devialetctl.infrastructure.cec_adapter import parse_cec_line


def test_parse_cec_volume_up_variants() -> None:
    event = parse_cec_line("key pressed: volume up")
    assert event is not None
    assert event.kind == InputEventType.VOLUME_UP

    event2 = parse_cec_line("USER_CONTROL_PRESSED: VOLUME_UP")
    assert event2 is not None
    assert event2.kind == InputEventType.VOLUME_UP


def test_parse_cec_volume_down_variants() -> None:
    event = parse_cec_line("user_control_pressed volume down")
    assert event is not None
    assert event.kind == InputEventType.VOLUME_DOWN


def test_parse_cec_mute_variants() -> None:
    event = parse_cec_line("MUTED")
    assert event is not None
    assert event.kind == InputEventType.MUTE


def test_parse_cec_ignores_non_volume_key() -> None:
    assert parse_cec_line("USER_CONTROL_PRESSED: PLAY") is None
