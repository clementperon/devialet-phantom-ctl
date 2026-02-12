import contextlib
import sys
import termios
import tty
from dataclasses import dataclass
from typing import Iterator

from devialetctl.domain.events import InputEvent, InputEventType

_MAP = {
    "u": InputEventType.VOLUME_UP,
    "+": InputEventType.VOLUME_UP,
    "up": InputEventType.VOLUME_UP,
    "d": InputEventType.VOLUME_DOWN,
    "-": InputEventType.VOLUME_DOWN,
    "down": InputEventType.VOLUME_DOWN,
    "m": InputEventType.MUTE,
    "mute": InputEventType.MUTE,
}


def parse_keyboard_command(line: str, source: str = "keyboard") -> InputEvent | None:
    key = line.strip().lower()
    kind = _MAP.get(key)
    if kind is None:
        return None
    return InputEvent(kind=kind, source=source, key=key)


@dataclass
class KeyboardAdapter:
    source: str = "keyboard"

    def events(self) -> Iterator[InputEvent]:
        if sys.stdin.isatty():
            yield from self._events_single_key_mode()
            return
        yield from self._events_line_mode()

    def _events_single_key_mode(self) -> Iterator[InputEvent]:
        with _stdin_cbreak():
            while True:
                ch = sys.stdin.read(1)
                if ch == "":
                    return
                key = ch.strip().lower()
                if not key:
                    continue
                if key in {"q"}:
                    return
                event = parse_keyboard_command(key, source=self.source)
                if event is not None:
                    yield event

    def _events_line_mode(self) -> Iterator[InputEvent]:
        while True:
            try:
                line = input().strip()
            except EOFError:
                return
            if not line:
                continue
            if line.lower() in {"q", "quit", "exit"}:
                return
            event = parse_keyboard_command(line, source=self.source)
            if event is not None:
                yield event


@contextlib.contextmanager
def _stdin_cbreak():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
