from devialetctl.domain.events import InputEventType
from devialetctl.infrastructure.cec_adapter import format_cec_frame_human, parse_cec_frame


def test_parse_cec_user_control_pressed_variants() -> None:
    event = parse_cec_frame("05:44:41")
    assert event is not None
    assert event.kind == InputEventType.VOLUME_UP

    event2 = parse_cec_frame("05:44:42")
    assert event2 is not None
    assert event2.kind == InputEventType.VOLUME_DOWN

    event3 = parse_cec_frame("05:44:43")
    assert event3 is not None
    assert event3.kind == InputEventType.MUTE


def test_parse_cec_user_control_released() -> None:
    released = parse_cec_frame("05:45")
    assert released is not None
    assert released.kind == InputEventType.USER_CONTROL_RELEASED


def test_parse_cec_give_audio_status() -> None:
    status = parse_cec_frame("05:71")
    assert status is not None
    assert status.kind == InputEventType.GIVE_AUDIO_STATUS


def test_parse_cec_system_audio_and_arc_requests() -> None:
    sys_mode_req = parse_cec_frame("05:70")
    sys_mode_status = parse_cec_frame("05:7d")
    arc_init = parse_cec_frame("05:c3")
    arc_term = parse_cec_frame("05:c4")
    sad_req = parse_cec_frame("05:a4:02:0a")
    give_power = parse_cec_frame("05:8f")
    give_vendor = parse_cec_frame("05:8c")
    give_osd = parse_cec_frame("05:46")
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
    assert give_power is not None and give_power.kind == InputEventType.GIVE_DEVICE_POWER_STATUS
    assert give_vendor is not None and give_vendor.kind == InputEventType.GIVE_DEVICE_VENDOR_ID
    assert give_osd is not None and give_osd.kind == InputEventType.GIVE_OSD_NAME


def test_parse_cec_set_audio_volume_level() -> None:
    event = parse_cec_frame("05:73:9A")
    assert event is not None
    assert event.kind == InputEventType.SET_AUDIO_VOLUME_LEVEL
    assert event.value == 0x1A
    assert event.muted is True


def test_parse_cec_parses_outgoing_set_audio_volume_level_echo() -> None:
    event = parse_cec_frame("50:73:19")
    assert event is not None
    assert event.kind == InputEventType.SET_AUDIO_VOLUME_LEVEL
    assert event.value == 0x19
    assert event.muted is False


def test_parse_cec_ignores_non_pressed_frames() -> None:
    assert parse_cec_frame("50:47:44:65:76:69:61:6c:65:74") is None


def test_parse_samsung_vendor_89_sync_tv_volume() -> None:
    event = parse_cec_frame("05:89:95:ff")
    assert event is not None
    assert event.kind == InputEventType.SAMSUNG_VENDOR_COMMAND
    assert event.vendor_subcommand == 0x95
    assert event.vendor_payload == (0x95, 0xFF)


def test_parse_samsung_vendor_89_mode_26() -> None:
    event = parse_cec_frame("05:89:92:26:91:00:00:00")
    assert event is not None
    assert event.kind == InputEventType.SAMSUNG_VENDOR_COMMAND
    assert event.vendor_subcommand == 0x92
    assert event.vendor_mode == 0x26
    assert event.vendor_payload == (0x92, 0x26, 0x91, 0x00, 0x00, 0x00)


def test_parse_samsung_vendor_a0_with_id() -> None:
    event = parse_cec_frame("05:A0:00:00:F0:95:FF")
    assert event is not None
    assert event.kind == InputEventType.SAMSUNG_VENDOR_COMMAND_WITH_ID
    assert event.vendor_payload == (0x00, 0x00, 0xF0, 0x95, 0xFF)


def test_format_human_readable_samsung_vendor_sync_volume() -> None:
    text = format_cec_frame_human("05:89:96:19")
    assert "TV -> Audio System" in text
    assert "SAMSUNG_VENDOR_COMMAND (SYNC_TV_VOLUME)" in text
    assert "payload=96:19" in text


def test_format_human_readable_samsung_vendor_model_name() -> None:
    text = format_cec_frame_human("05:89:88:12:34")
    assert "SAMSUNG_VENDOR_COMMAND (MODEL_NAME)" in text
    assert "payload=88:12:34" in text
