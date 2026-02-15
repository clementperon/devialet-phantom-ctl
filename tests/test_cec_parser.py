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


def test_parse_cec_ignores_key_released_human_line() -> None:
    assert parse_cec_line("key released: volume down (42) D:152ms") is None


def test_parse_cec_hex_traffic_user_control_pressed() -> None:
    up = parse_cec_line("TRAFFIC: [ 2735]\t>> 05:44:41")
    down = parse_cec_line("TRAFFIC: [ 4071]\t>> 05:44:42")
    mute = parse_cec_line("TRAFFIC: [ 9999]\t>> 05:44:43")
    released = parse_cec_line("TRAFFIC: [ 10000]\t>> 05:45")
    assert up is not None and up.kind == InputEventType.VOLUME_UP
    assert down is not None and down.kind == InputEventType.VOLUME_DOWN
    assert mute is not None and mute.kind == InputEventType.MUTE
    assert released is not None and released.kind == InputEventType.USER_CONTROL_RELEASED


def test_parse_cec_give_audio_status() -> None:
    status = parse_cec_line("TRAFFIC: [ 3000]\t>> 05:71")
    assert status is not None
    assert status.kind == InputEventType.GIVE_AUDIO_STATUS


def test_parse_cec_system_audio_and_arc_requests() -> None:
    sys_mode_req = parse_cec_line("TRAFFIC: [ 3001]\t>> 05:70")
    sys_mode_status = parse_cec_line("TRAFFIC: [ 3002]\t>> 05:7d")
    arc_init = parse_cec_line("TRAFFIC: [ 3003]\t>> 05:c3")
    arc_term = parse_cec_line("TRAFFIC: [ 3004]\t>> 05:c4")
    sad_req = parse_cec_line("TRAFFIC: [ 3006]\t>> 05:a4:02:0a")
    assert (
        sys_mode_req is not None and sys_mode_req.kind == InputEventType.SYSTEM_AUDIO_MODE_REQUEST
    )
    assert (
        sys_mode_status is not None
        and sys_mode_status.kind == InputEventType.GIVE_SYSTEM_AUDIO_MODE_STATUS
    )
    assert arc_init is not None and arc_init.kind == InputEventType.REQUEST_ARC_INITIATION
    assert arc_term is not None and arc_term.kind == InputEventType.REQUEST_ARC_TERMINATION
    assert sad_req is not None and sad_req.kind == InputEventType.REQUEST_SHORT_AUDIO_DESCRIPTOR


def test_parse_cec_set_audio_volume_level() -> None:
    event = parse_cec_line("TRAFFIC: [ 3005]\t>> 05:73:9A")
    assert event is not None
    assert event.kind == InputEventType.SET_AUDIO_VOLUME_LEVEL
    assert event.value == 0x1A
    assert event.muted is True


def test_parse_cec_ignores_outgoing_set_audio_volume_level_echo() -> None:
    assert parse_cec_line("TRAFFIC: [ 54375]\t<< 50:73:19") is None


def test_parse_cec_hex_traffic_ignores_non_pressed_frames() -> None:
    assert parse_cec_line("TRAFFIC: [ 2870]\t>> 05:46") is None
    assert parse_cec_line("TRAFFIC: [ 1331]\t<< 50:47:44:65:76:69:61:6c:65:74") is None
