import pytest

from devialetctl.application.samsung_ssc import (
    SOUND_MODE_NIGHT,
    SamsungSscSession,
    SscAction,
    decode_equalizer,
    describe_tv_message,
    encode_equalizer,
    handshake_frames,
    signed_byte,
    sound_mode_frame,
    ssc_frame,
)

HANDSHAKE_STANDARD = [
    "50:89:91:01:01:00:00:00",
    "50:89:91:02:20:00:00:00",
    "50:89:91:04:00:00:00:00",
    "50:89:91:05:00:01:00:00",
    "50:89:91:06:66:66:66:60",
]


def test_ssc_frame_is_always_eight_bytes() -> None:
    assert ssc_frame(0x01, 0x01) == "50:89:91:01:01:00:00:00"
    assert ssc_frame(0x06, 0x12, 0x34, 0x56, 0x78) == "50:89:91:06:12:34:56:78"
    assert ssc_frame(0x85) == "50:89:91:85:00:00:00:00"


@pytest.mark.parametrize(("opcode", "data"), [(0x01, (1, 2, 3, 4, 5)), (0x04, (0x100,))])
def test_ssc_frame_rejects_invalid_payload(opcode: int, data: tuple[int, ...]) -> None:
    with pytest.raises(ValueError):
        ssc_frame(opcode, *data)


def test_handshake_frames_use_protocol_1_and_never_symphony() -> None:
    frames = handshake_frames()
    assert frames == HANDSHAKE_STANDARD
    # SYMPHONY_SUPPORT (0x16) would let the TV offer Q-Symphony.
    assert all(frame.split(":")[3] != "16" for frame in frames)


def test_handshake_frames_announce_night_mode() -> None:
    assert handshake_frames(sound_mode=SOUND_MODE_NIGHT)[2] == "50:89:91:04:05:00:00:00"


def test_sound_mode_frame() -> None:
    assert sound_mode_frame(SOUND_MODE_NIGHT) == "50:89:91:04:05:00:00:00"


def test_decode_equalizer_steps_centered_on_6() -> None:
    # Captured from the TV while raising each band from its lowest step.
    assert decode_equalizer((0x66, 0x66, 0x66, 0x60)) == [0] * 7
    assert decode_equalizer((0x00, 0x00, 0x00, 0x00)) == [-6] * 7
    assert decode_equalizer((0xCC, 0xCC, 0xCC, 0xC0)) == [6] * 7
    assert decode_equalizer((0xC1, 0x00, 0x00, 0x00)) == [6, -5, -6, -6, -6, -6, -6]


def test_encode_equalizer_round_trips_and_clamps() -> None:
    assert encode_equalizer([0] * 7) == (0x66, 0x66, 0x66, 0x60)
    gains = [-6, -3, 0, 1, 2, 5, 6]
    assert decode_equalizer(encode_equalizer(gains)) == gains
    assert encode_equalizer([9, -9]) == (0xC0, 0x66, 0x66, 0x60)


def test_signed_byte() -> None:
    assert signed_byte(0x00) == 0
    assert signed_byte(0x06) == 6
    assert signed_byte(0xF4) == -12


def test_describe_tv_message_variants() -> None:
    assert describe_tv_message(0x03, (0, 0, 0, 0)) == "TV_READY data=00:00:00:00"
    assert describe_tv_message(0x04, (5, 0, 0, 0)).startswith("AUDIO_EFFECT mode=5 (night)")
    assert "level=244 (signed -12)" in describe_tv_message(0x05, (0xF4, 0, 0, 0))
    assert "gains_db=[6, 0, 0, 0, 0, 0, 0]" in describe_tv_message(0x06, (0xC6, 0x66, 0x66, 0x60))
    assert describe_tv_message(0x24, (1, 0, 0, 0)).startswith("ADAPTIVE_PLUS_STATUS")
    assert describe_tv_message(0x7E, ()).startswith("OPCODE_0x7E")


def test_session_asks_for_handshake_on_tv_ready() -> None:
    session = SamsungSscSession()
    assert session.handle_tv_message((0x92, 0x03, 0, 0, 0, 0)) == SscAction(send_handshake=True)
    assert session.handle_tv_message((0x92, 0x03, 0, 0, 0, 0)).send_handshake
    assert session.handshakes_sent == 2
    assert session.protocol_confirmed is False


def test_session_records_protocol_echo() -> None:
    session = SamsungSscSession()
    session.handle_tv_message((0x92, 0x03, 0, 0, 0, 0))
    assert session.handle_tv_message((0x92, 0x01, 0x01, 0, 0, 0)) == SscAction()
    assert session.protocol_confirmed is True
    # A new TV_READY (TV restarted the handshake) clears it.
    session.handle_tv_message((0x92, 0x03, 0, 0, 0, 0))
    assert session.protocol_confirmed is False


@pytest.mark.parametrize(("mode", "expected"), [(0x00, 0), (0x05, 5), (0x02, 2)])
def test_session_reports_sound_mode(mode: int, expected: int) -> None:
    action = SamsungSscSession().handle_tv_message((0x92, 0x04, mode, 0, 0, 0))
    assert action == SscAction(sound_mode=expected)


@pytest.mark.parametrize(
    "payload",
    [
        (0x92, 0x05, 0x02, 0, 0, 0),
        (0x92, 0x06, 0x11, 0x22, 0x33, 0x44),
        (0x92, 0x24, 0x01, 0, 0, 0),
        (0x92, 0x04),
        (0x92,),
        (0x95, 0x03, 0, 0, 0, 0),
    ],
)
def test_session_only_logs_other_messages(payload: tuple[int, ...]) -> None:
    assert SamsungSscSession().handle_tv_message(payload) == SscAction()
