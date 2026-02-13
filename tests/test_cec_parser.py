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


def test_parse_cec_hex_traffic_user_control_pressed() -> None:
    up = parse_cec_line("TRAFFIC: [ 2735]\t>> 05:44:41")
    down = parse_cec_line("TRAFFIC: [ 4071]\t>> 05:44:42")
    mute = parse_cec_line("TRAFFIC: [ 9999]\t>> 05:44:43")
    assert up is not None and up.kind == InputEventType.VOLUME_UP
    assert down is not None and down.kind == InputEventType.VOLUME_DOWN
    assert mute is not None and mute.kind == InputEventType.MUTE


def test_parse_cec_give_audio_status() -> None:
    status = parse_cec_line("TRAFFIC: [ 3000]\t>> 05:71")
    assert status is not None
    assert status.kind == InputEventType.GIVE_AUDIO_STATUS


def test_parse_cec_hex_traffic_ignores_non_pressed_frames() -> None:
    assert parse_cec_line("TRAFFIC: [ 2870]\t>> 05:45") is None
    assert parse_cec_line("TRAFFIC: [ 1331]\t<< 50:47:44:65:76:69:61:6c:65:74") is None
