import logging
import re
import shlex
import subprocess
from dataclasses import dataclass
from typing import Iterator

from devialetctl.domain.events import InputEvent, InputEventType

LOG = logging.getLogger(__name__)

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


def parse_cec_line(line: str, source: str = "cec") -> InputEvent | None:
    frame_match = _HEX_CEC_FRAME_RE.search(line)
    if frame_match:
        parts = [p.upper() for p in frame_match.group(0).split(":")]
        # CEC USER_CONTROL_PRESSED frame: <srcdst>:44:<keycode>
        if len(parts) >= 3 and parts[1] == "44":
            mapped = _USER_CONTROL_KEYCODE_MAP.get(parts[2])
            if mapped is not None:
                event, key = mapped
                return InputEvent(kind=event, source=source, key=key)

    for pattern, event, key in _PATTERNS:
        if pattern.search(line):
            return InputEvent(kind=event, source=source, key=key)
    return None


@dataclass
class CecClientAdapter:
    command: str = "cec-client -d 8 -t a -o Devialet"
    source: str = "cec"

    def events(self) -> Iterator[InputEvent]:
        cmd = shlex.split(self.command)
        LOG.info("starting cec adapter: %s", self.command)
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        if proc.stdout is None:
            if proc.poll() is None:
                proc.terminate()
            raise RuntimeError("cec-client did not expose a readable stdout pipe")

        try:
            for line in proc.stdout:
                event = parse_cec_line(line, source=self.source)
                if event is not None:
                    yield event
        finally:
            if proc.poll() is None:
                proc.terminate()
