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


def parse_cec_line(line: str, source: str = "cec") -> InputEvent | None:
    for pattern, event, key in _PATTERNS:
        if pattern.search(line):
            return InputEvent(kind=event, source=source, key=key)
    return None


@dataclass
class CecClientAdapter:
    command: str = "cec-client -d 8"
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
