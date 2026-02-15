import logging
import re
import shlex
import subprocess
from dataclasses import dataclass
from typing import Iterator

from devialetctl.domain.events import InputEvent, InputEventType

LOG = logging.getLogger(__name__)
_LOGICAL_ADDRESS_NAMES: dict[int, str] = {
    0x0: "TV",
    0x1: "Recorder 1",
    0x2: "Recorder 2",
    0x3: "Tuner 1",
    0x4: "Playback 1",
    0x5: "Audio System",
    0x6: "Tuner 2",
    0x7: "Tuner 3",
    0x8: "Playback 2",
    0x9: "Recorder 3",
    0xA: "Tuner 4",
    0xB: "Playback 3",
    0xC: "Reserved 1",
    0xD: "Reserved 2",
    0xE: "Free Use",
    0xF: "Broadcast",
}
_CEC_OPCODE_NAMES: dict[str, str] = {
    "00": "FEATURE_ABORT",
    "44": "USER_CONTROL_PRESSED",
    "45": "USER_CONTROL_RELEASED",
    "70": "SYSTEM_AUDIO_MODE_REQUEST",
    "71": "GIVE_AUDIO_STATUS",
    "72": "SET_SYSTEM_AUDIO_MODE",
    "73": "SET_AUDIO_VOLUME_LEVEL",
    "7A": "REPORT_AUDIO_STATUS",
    "7D": "GIVE_SYSTEM_AUDIO_MODE_STATUS",
    "7E": "SYSTEM_AUDIO_MODE_STATUS",
    "84": "REPORT_PHYSICAL_ADDRESS",
    "87": "DEVICE_VENDOR_ID",
    "8C": "GIVE_DEVICE_VENDOR_ID",
    "8F": "GIVE_DEVICE_POWER_STATUS",
    "90": "REPORT_POWER_STATUS",
    "A3": "REPORT_SHORT_AUDIO_DESCRIPTOR",
    "A4": "REQUEST_SHORT_AUDIO_DESCRIPTOR",
    "C0": "INITIATE_ARC",
    "C1": "REPORT_ARC_INITIATED",
    "C2": "REPORT_ARC_TERMINATED",
    "C3": "REQUEST_ARC_INITIATION",
    "C4": "REQUEST_ARC_TERMINATION",
    "C5": "TERMINATE_ARC",
}

_PATTERNS: list[tuple[re.Pattern[str], InputEventType, str]] = [
    (
        re.compile(r"\bVOLUME[_\s-]?UP\b", flags=re.IGNORECASE),
        InputEventType.VOLUME_UP,
        "VOLUME_UP",
    ),
    (
        re.compile(r"\bVOLUME[_\s-]?DOWN\b", flags=re.IGNORECASE),
        InputEventType.VOLUME_DOWN,
        "VOLUME_DOWN",
    ),
    (re.compile(r"\bMUTE(D)?\b", flags=re.IGNORECASE), InputEventType.MUTE, "MUTE"),
]

_HEX_CEC_FRAME_RE = re.compile(r"\b(?:[0-9A-Fa-f]{2}:){1,}[0-9A-Fa-f]{2}\b")
_USER_CONTROL_KEYCODE_MAP: dict[str, tuple[InputEventType, str]] = {
    "41": (InputEventType.VOLUME_UP, "VOLUME_UP"),
    "42": (InputEventType.VOLUME_DOWN, "VOLUME_DOWN"),
    "43": (InputEventType.MUTE, "MUTE"),
}
_SYSTEM_REQUEST_OPCODE_MAP: dict[str, tuple[InputEventType, str]] = {
    "70": (InputEventType.SYSTEM_AUDIO_MODE_REQUEST, "SYSTEM_AUDIO_MODE_REQUEST"),
    "7D": (InputEventType.GIVE_SYSTEM_AUDIO_MODE_STATUS, "GIVE_SYSTEM_AUDIO_MODE_STATUS"),
    "C3": (InputEventType.REQUEST_ARC_INITIATION, "REQUEST_ARC_INITIATION"),
    "C4": (InputEventType.REQUEST_ARC_TERMINATION, "REQUEST_ARC_TERMINATION"),
    "A4": (
        InputEventType.REQUEST_SHORT_AUDIO_DESCRIPTOR,
        "REQUEST_SHORT_AUDIO_DESCRIPTOR",
    ),
}


def parse_cec_line(line: str, source: str = "cec") -> InputEvent | None:
    upper_line = line.upper()
    # libCEC emits human-readable "key released: volume ..." lines in addition to
    # TRAFFIC frames. Treating those as volume events duplicates one key press.
    if "KEY RELEASED" in upper_line:
        return None
    # libCEC traffic lines with "<<" are transmit echoes / adapter chatter.
    # Only parse inbound CEC traffic (" >> ") to avoid feedback loops.
    if "TRAFFIC:" in upper_line and ">>" not in line:
        return None

    frame_match = _HEX_CEC_FRAME_RE.search(line)
    if frame_match:
        parts = [p.upper() for p in frame_match.group(0).split(":")]
        # CEC GIVE_AUDIO_STATUS frame: <srcdst>:71
        if len(parts) >= 2 and parts[1] == "71":
            return InputEvent(
                kind=InputEventType.GIVE_AUDIO_STATUS,
                source=source,
                key="GIVE_AUDIO_STATUS",
            )
        # CEC USER_CONTROL_PRESSED frame: <srcdst>:44:<keycode>
        if len(parts) >= 3 and parts[1] == "44":
            mapped = _USER_CONTROL_KEYCODE_MAP.get(parts[2])
            if mapped is not None:
                event, key = mapped
                return InputEvent(kind=event, source=source, key=key)
        # CEC USER_CONTROL_RELEASED frame: <srcdst>:45
        if len(parts) >= 2 and parts[1] == "45":
            return InputEvent(
                kind=InputEventType.USER_CONTROL_RELEASED,
                source=source,
                key="USER_CONTROL_RELEASED",
            )
        # CEC SET_AUDIO_VOLUME_LEVEL frame: <srcdst>:73:<status-byte>
        if len(parts) >= 3 and parts[1] == "73":
            status = int(parts[2], 16)
            return InputEvent(
                kind=InputEventType.SET_AUDIO_VOLUME_LEVEL,
                source=source,
                key="SET_AUDIO_VOLUME_LEVEL",
                value=status & 0x7F,
                muted=bool(status & 0x80),
            )
        # CEC system-audio / ARC requests.
        if len(parts) >= 2:
            mapped = _SYSTEM_REQUEST_OPCODE_MAP.get(parts[1])
            if mapped is not None:
                event, key = mapped
                return InputEvent(kind=event, source=source, key=key)

    for pattern, event, key in _PATTERNS:
        if pattern.search(line):
            return InputEvent(kind=event, source=source, key=key)
    return None


def format_cec_frame_human(frame: str) -> str:
    parts = [p.upper() for p in frame.split(":")]
    if len(parts) < 2 or len(parts[0]) != 2:
        return frame

    try:
        header = int(parts[0], 16)
    except ValueError:
        return frame

    initiator = (header >> 4) & 0x0F
    destination = header & 0x0F
    opcode = parts[1]
    initiator_name = _LOGICAL_ADDRESS_NAMES.get(initiator, f"LA{initiator:X}")
    destination_name = _LOGICAL_ADDRESS_NAMES.get(destination, f"LA{destination:X}")
    opcode_name = _CEC_OPCODE_NAMES.get(opcode, f"OPCODE_0x{opcode}")
    payload = ""
    if len(parts) > 2:
        payload = f" payload={':'.join(parts[2:])}"
    return f"{initiator_name} -> {destination_name} : {opcode_name}{payload}"


@dataclass
class CecClientAdapter:
    command: str = "cec-client -d 8 -t a -o Devialet"
    source: str = "cec"
    _proc: subprocess.Popen | None = None

    def events(self) -> Iterator[InputEvent]:
        cmd = shlex.split(self.command)
        LOG.info("starting cec adapter: %s", self.command)
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self._proc = proc
        if proc.stdout is None:
            if proc.poll() is None:
                proc.terminate()
            raise RuntimeError("cec-client did not expose a readable stdout pipe")

        try:
            for line in proc.stdout:
                LOG.debug("CEC RX: %s", line.rstrip())
                frame_match = _HEX_CEC_FRAME_RE.search(line)
                if frame_match:
                    frame = frame_match.group(0).upper()
                    LOG.debug("CEC RX decoded: %s -> %s", frame, format_cec_frame_human(frame))
                event = parse_cec_line(line, source=self.source)
                if event is not None:
                    yield event
        finally:
            self._proc = None
            if proc.poll() is None:
                proc.terminate()

    def send_tx(self, frame: str) -> bool:
        proc = self._proc
        if proc is None or proc.stdin is None or proc.poll() is not None:
            return False
        LOG.debug("CEC TX: tx %s", frame)
        LOG.debug("CEC TX decoded: %s -> %s", frame.upper(), format_cec_frame_human(frame))
        proc.stdin.write(f"tx {frame}\n")
        proc.stdin.flush()
        return True
