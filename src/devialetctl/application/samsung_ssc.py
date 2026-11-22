"""Samsung soundbar protocol carried in CEC vendor command 0x89.

Samsung TVs talk to their soundbars with a small protocol of their own
(handled on the TV by ``ssc-service``), tunnelled in two vendor
sub-commands:

- ``0x92`` TV -> soundbar: ``05:89:92:<op>:<d1>:<d2>:<d3>:<d4>``
- ``0x91`` soundbar -> TV: ``50:89:91:<op>:<d1>:<d2>:<d3>:<d4>``

Every message is one opcode plus four data bytes. The TV only accepts 0x91
from a device that reported vendor ID ``00:00:F0``, and 0x91 frames must be
exactly 8 bytes (longer ones are read as 16 bytes).

At power-on the TV sends TV_READY (``92:03``) every 5 s, 26 times, until the
soundbar completes the handshake. With protocol version 1 the handshake is:
PROTOCOL (01), FEATURE_LIST (02), AUDIO_EFFECT (04), WOOFER_LEVEL (05) and
EQUALIZER (06). Once complete, the TV enables its soundbar sound menu and
sends 04/05/06 whenever the user changes those settings. The daemon maps
sound modes Standard and Night to the Devialet night mode.

SYMPHONY_SUPPORT (0x16) is never sent: it is what lets the TV offer
Q-Symphony (TV speakers playing together with the soundbar).

This module is the protocol layer only; it does not touch the speakers.
"""

import logging
from dataclasses import dataclass

LOG = logging.getLogger(__name__)

SSC_TO_TV = 0x91
SSC_FROM_TV = 0x92

# Opcodes, TV -> soundbar (0x92).
TV_PROTOCOL = 0x01
TV_READY = 0x03
TV_AUDIO_EFFECT = 0x04
TV_WOOFER_LEVEL = 0x05
TV_EQUALIZER = 0x06

TV_OPCODE_NAMES: dict[int, str] = {
    0x01: "PROTOCOL",
    0x03: "TV_READY",
    0x04: "AUDIO_EFFECT",
    0x05: "WOOFER_LEVEL",
    0x06: "EQUALIZER",
    0x09: "TV_BT_MAC",
    0x13: "3D_COLLABO_INFO",
    0x17: "EXTRA_INFO",
    0x18: "TV_YEAR",
    0x21: "OOBE_REQUEST",
    0x23: "GAME_GENRE",
    0x24: "ADAPTIVE_PLUS_STATUS",
    0x25: "TV_YEAR_GENRE_MAC_INFO",
    0x81: "SYMPHONY_STATUS",
    0x83: "TV_MODEL_INFO",
    0x84: "DYNAMIC_SOUND_MODE_LIST",
    0x86: "VLOG_INFO",
    0x87: "FRL_INFO",
    0x89: "SB_SPL_INFO",
    0x90: "TV_SPL_INFO",
}

# Opcodes, soundbar -> TV (0x91).
SB_PROTOCOL = 0x01
SB_FEATURE_LIST = 0x02
SB_AUDIO_EFFECT = 0x04
SB_WOOFER_LEVEL = 0x05
SB_EQUALIZER = 0x06

# Sound mode ids used by AUDIO_EFFECT in both directions.
SOUND_MODE_NAMES: dict[int, str] = {
    0: "standard",
    1: "music",
    2: "clear_voice",
    3: "sports",
    4: "movie",
    5: "night",
    6: "surround",
    7: "smart",
    8: "game",
    9: "adaptive",
    10: "dts_virtual_x",
    11: "bass_boost",
    12: "adaptive_plus",
}
SOUND_MODE_STANDARD = 0
SOUND_MODE_NIGHT = 5

# FEATURE_LIST byte: the high nibble selects which sound modes the TV offers
# (1: standard+surround, 2: standard+night, 3: +clear voice and surround...).
# Any non-zero value also enables the TV's woofer and equalizer menus.
FEATURE_STANDARD_NIGHT = 0x20

PROTOCOL_VERSION = 1
# Neutral values announced during the handshake. The woofer state byte is
# not decoded yet; with 1 the TV shows its woofer setting greyed out.
NEUTRAL_WOOFER_LEVEL = 0
NEUTRAL_WOOFER_STATE = 1

# EQUALIZER: 7 bands (150 Hz, 300 Hz, 600 Hz, 1.2 kHz, 2.5 kHz, 5 kHz, 10 kHz)
# plus an unused slot, one nibble each, high nibble first. Each band has 13
# steps (0..12) observed on the TV; 6 is taken as 0 dB (range -6..+6 dB).
EQ_BANDS = 7
EQ_STEP_FLAT = 6


def ssc_frame(opcode: int, *data: int) -> str:
    """Build an 8-byte soundbar -> TV frame (0x91), zero-padded."""
    if len(data) > 4:
        raise ValueError("an SSC message carries at most 4 data bytes")
    body = [opcode, *data, *([0] * (4 - len(data)))]
    for byte in body:
        if not 0 <= byte <= 0xFF:
            raise ValueError(f"SSC byte out of range: {byte}")
    return "50:89:91:" + ":".join(f"{byte:02X}" for byte in body)


def signed_byte(value: int) -> int:
    value &= 0xFF
    return value - 256 if value >= 128 else value


def decode_equalizer(data: tuple[int, ...]) -> list[int]:
    """Unpack the EQUALIZER payload into per-band gains in dB."""
    steps: list[int] = []
    for byte in data[:4]:
        steps.extend((byte >> 4, byte & 0x0F))
    return [step - EQ_STEP_FLAT for step in steps[:EQ_BANDS]]


def encode_equalizer(gains_db: list[int]) -> tuple[int, int, int, int]:
    steps = [max(0, min(12, gain + EQ_STEP_FLAT)) for gain in gains_db[:EQ_BANDS]]
    steps += [EQ_STEP_FLAT] * (EQ_BANDS - len(steps)) + [0]
    packed = [(steps[i] << 4) | steps[i + 1] for i in range(0, 8, 2)]
    return packed[0], packed[1], packed[2], packed[3]


def sound_mode_frame(mode: int) -> str:
    return ssc_frame(SB_AUDIO_EFFECT, mode)


def handshake_frames(
    sound_mode: int = SOUND_MODE_STANDARD,
    feature_byte: int = FEATURE_STANDARD_NIGHT,
) -> list[str]:
    """Frames that complete the protocol-1 handshake (flat EQ, neutral woofer)."""
    return [
        ssc_frame(SB_PROTOCOL, PROTOCOL_VERSION),
        ssc_frame(SB_FEATURE_LIST, feature_byte),
        sound_mode_frame(sound_mode),
        ssc_frame(SB_WOOFER_LEVEL, NEUTRAL_WOOFER_LEVEL, NEUTRAL_WOOFER_STATE),
        ssc_frame(SB_EQUALIZER, *encode_equalizer([0] * EQ_BANDS)),
    ]


def describe_tv_message(opcode: int, data: tuple[int, ...]) -> str:
    name = TV_OPCODE_NAMES.get(opcode, f"OPCODE_0x{opcode:02X}")
    raw = ":".join(f"{byte:02X}" for byte in data)
    if opcode == TV_AUDIO_EFFECT and data:
        mode = SOUND_MODE_NAMES.get(data[0], "unknown")
        return f"{name} mode={data[0]} ({mode}) data={raw}"
    if opcode == TV_WOOFER_LEVEL and data:
        return f"{name} level={data[0]} (signed {signed_byte(data[0])}) data={raw}"
    if opcode == TV_EQUALIZER:
        return f"{name} gains_db={decode_equalizer(data)} data={raw}"
    if opcode == TV_PROTOCOL and data:
        return f"{name} version={data[0]} data={raw}"
    return f"{name} data={raw}"


@dataclass(frozen=True)
class SscAction:
    """What the daemon should do after a TV message."""

    send_handshake: bool = False
    sound_mode: int | None = None


class SamsungSscSession:
    """Tracks the TV's soundbar handshake and decodes what the TV asks for.

    Speaker I/O stays in the daemon: this class only says what to do.
    """

    def __init__(self, feature_byte: int = FEATURE_STANDARD_NIGHT) -> None:
        self.feature_byte = feature_byte
        self.handshakes_sent = 0
        self.protocol_confirmed = False

    def handle_tv_message(self, payload: tuple[int, ...]) -> SscAction:
        """Handle a 0x92 vendor payload (0x92, op, d1..d4)."""
        if len(payload) < 2 or payload[0] != SSC_FROM_TV:
            return SscAction()
        opcode = payload[1]
        data = tuple(payload[2:])
        LOG.info("Samsung SSC from TV: %s", describe_tv_message(opcode, data))

        if opcode == TV_READY:
            self.handshakes_sent += 1
            self.protocol_confirmed = False
            LOG.info(
                "Samsung SSC: TV ready, sending handshake #%d (feature list 0x%02X)",
                self.handshakes_sent,
                self.feature_byte,
            )
            return SscAction(send_handshake=True)

        if opcode == TV_PROTOCOL:
            self.protocol_confirmed = True
            version = data[0] if data else None
            LOG.info("Samsung SSC: TV acknowledged protocol version %s", version)
            return SscAction()

        if opcode == TV_AUDIO_EFFECT and data:
            return SscAction(sound_mode=data[0])
        return SscAction()
