import pytest

from devialetctl.domain.events import InputEventType
from devialetctl.infrastructure.cec_adapter import format_cec_frame_human, parse_cec_frame


@pytest.mark.parametrize(
    ("frame", "expected_kind"),
    [
        ("05:44:41", InputEventType.VOLUME_UP),
        ("05:44:42", InputEventType.VOLUME_DOWN),
        ("05:44:43", InputEventType.MUTE),
        ("05:45", InputEventType.USER_CONTROL_RELEASED),
        ("05:71", InputEventType.GIVE_AUDIO_STATUS),
        ("05:70", InputEventType.SYSTEM_AUDIO_MODE_REQUEST),
        ("05:7D", InputEventType.GIVE_SYSTEM_AUDIO_MODE_STATUS),
        ("05:C3", InputEventType.REQUEST_ARC_INITIATION),
        ("05:C4", InputEventType.REQUEST_ARC_TERMINATION),
        ("05:A4:02:0A", InputEventType.REQUEST_SHORT_AUDIO_DESCRIPTOR),
        ("05:8F", InputEventType.GIVE_DEVICE_POWER_STATUS),
        ("05:8C", InputEventType.GIVE_DEVICE_VENDOR_ID),
        ("05:46", InputEventType.GIVE_OSD_NAME),
    ],
)
def test_parse_cec_basic_event_kind(frame: str, expected_kind: InputEventType) -> None:
    event = parse_cec_frame(frame)
    assert event is not None
    assert event.kind == expected_kind


@pytest.mark.parametrize(
    ("frame", "expected_value", "expected_muted"),
    [
        ("05:73:9A", 0x1A, True),
        ("50:73:19", 0x19, False),
    ],
)
def test_parse_cec_audio_volume_level(
    frame: str,
    expected_value: int,
    expected_muted: bool,
) -> None:
    event = parse_cec_frame(frame)
    assert event is not None
    assert event.kind == InputEventType.SET_AUDIO_VOLUME_LEVEL
    assert event.value == expected_value
    assert event.muted == expected_muted


def test_parse_cec_ignores_non_pressed_frames() -> None:
    assert parse_cec_frame("50:47:44:65:76:69:61:6C:65:74") is None


@pytest.mark.parametrize(
    ("frame", "subcommand", "mode", "payload"),
    [
        ("05:89:95:FF", 0x95, None, (0x95, 0xFF)),
        (
            "05:89:92:26:91:00:00:00",
            0x92,
            0x26,
            (0x92, 0x26, 0x91, 0x00, 0x00, 0x00),
        ),
    ],
)
def test_parse_samsung_vendor_89(
    frame: str,
    subcommand: int,
    mode: int | None,
    payload: tuple[int, ...],
) -> None:
    event = parse_cec_frame(frame)
    assert event is not None
    assert event.kind == InputEventType.SAMSUNG_VENDOR_COMMAND
    assert event.vendor_subcommand == subcommand
    assert event.vendor_mode == mode
    assert event.vendor_payload == payload


def test_parse_samsung_vendor_a0_with_id() -> None:
    event = parse_cec_frame("05:A0:00:00:F0:95:FF")
    assert event is not None
    assert event.kind == InputEventType.SAMSUNG_VENDOR_COMMAND_WITH_ID
    assert event.vendor_payload == (0x00, 0x00, 0xF0, 0x95, 0xFF)


@pytest.mark.parametrize(
    ("frame", "expected_fragment"),
    [
        ("05:89:96:19", "SAMSUNG_VENDOR_COMMAND (SYNC_TV_VOLUME) payload=96:19"),
        ("05:89:88:12:34", "SAMSUNG_VENDOR_COMMAND (MODEL_NAME) payload=88:12:34"),
        ("0F:36", "TV -> Broadcast : STANDBY"),
        ("0F:80:00:00:10:00", "TV -> Broadcast : ROUTING_CHANGE payload=00:00:10:00"),
        ("0F:86:10:00", "TV -> Broadcast : SET_STREAM_PATH payload=10:00"),
    ],
)
def test_format_human_readable_variants(frame: str, expected_fragment: str) -> None:
    text = format_cec_frame_human(frame)
    assert expected_fragment in text
