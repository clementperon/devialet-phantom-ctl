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

    for pattern, event, key in _PATTERNS:
        if pattern.search(line):
            return InputEvent(kind=event, source=source, key=key)
    return None


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
        proc.stdin.write(f"tx {frame}\n")
        proc.stdin.flush()
        return True
