import importlib
import logging
import queue
import re
from dataclasses import dataclass
from typing import Any, Iterator

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
_SYSTEM_REQUEST_OPCODE_MAP: dict[str, tuple[InputEventType, str]] = {
    "70": (InputEventType.SYSTEM_AUDIO_MODE_REQUEST, "SYSTEM_AUDIO_MODE_REQUEST"),
    "7D": (InputEventType.GIVE_SYSTEM_AUDIO_MODE_STATUS, "GIVE_SYSTEM_AUDIO_MODE_STATUS"),
    "C3": (InputEventType.REQUEST_ARC_INITIATION, "REQUEST_ARC_INITIATION"),
    "C4": (InputEventType.REQUEST_ARC_TERMINATION, "REQUEST_ARC_TERMINATION"),
}
_KEYPRESS_CODE_MAP: dict[int, tuple[InputEventType, str]] = {
    0x41: (InputEventType.VOLUME_UP, "VOLUME_UP"),
    0x42: (InputEventType.VOLUME_DOWN, "VOLUME_DOWN"),
    0x43: (InputEventType.MUTE, "MUTE"),
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


@dataclass
class LibCecAdapter:
    device_name: str = "Devialet"
    adapter_path: str | None = None
    source: str = "cec"
    _cec: Any = None
    _lib: Any = None
    _connected: bool = False
    _events_queue: queue.Queue = queue.Queue()

    def __post_init__(self) -> None:
        self._events_queue = queue.Queue()
        try:
            cec_module = importlib.import_module("cec")
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise RuntimeError(
                "python libCEC bindings are not installed. Install libcec + python bindings."
            ) from exc
        self._cec = cec_module

    def _on_log(self, level, timestamp, message) -> int:
        text = str(message).rstrip()
        if text:
            LOG.debug("CEC LIB [%s] %s", timestamp, text)
        return 0

    def _on_keypress(self, key, _duration) -> int:
        try:
            code = int(key)
        except (TypeError, ValueError):
            return 0
        mapped = _KEYPRESS_CODE_MAP.get(code)
        if mapped is None:
            return 0
        kind, key_name = mapped
        self._events_queue.put(InputEvent(kind=kind, source=self.source, key=key_name))
        return 0

    def _on_command(self, cmd) -> int:
        line = str(cmd)
        LOG.debug("CEC RX: %s", line.rstrip())
        event = parse_cec_line(line, source=self.source)
        if event is not None:
            self._events_queue.put(event)
        return 0

    def _open(self) -> None:
        cec = self._cec
        cfg = cec.libcec_configuration()
        cfg.strDeviceName = self.device_name
        cfg.bActivateSource = 0
        cfg.deviceTypes.Add(cec.CEC_DEVICE_TYPE_AUDIO_SYSTEM)
        cfg.clientVersion = cec.LIBCEC_VERSION_CURRENT
        cfg.SetLogCallback(self._on_log)
        cfg.SetKeyPressCallback(self._on_keypress)
        cfg.SetCommandCallback(self._on_command)
        self._lib = cec.ICECAdapter.Create(cfg)
        adapters = self._lib.DetectAdapters()
        if not adapters:
            raise RuntimeError("No CEC adapter detected")
        selected = None
        if self.adapter_path:
            for adapter in adapters:
                if getattr(adapter, "strComName", "") == self.adapter_path:
                    selected = adapter
                    break
            if selected is None:
                raise RuntimeError(f"CEC adapter not found: {self.adapter_path}")
        else:
            selected = adapters[0]
        port = getattr(selected, "strComName", "")
        LOG.info("opening libCEC adapter: %s", port)
        if not self._lib.Open(port):
            raise RuntimeError(f"Failed to open CEC adapter: {port}")
        self._connected = True

    def events(self) -> Iterator[InputEvent]:
        self._open()
        try:
            while self._connected:
                try:
                    event = self._events_queue.get(timeout=0.2)
                except queue.Empty:
                    continue
                yield event
        finally:
            self._connected = False
            if self._lib is not None:
                try:
                    self._lib.Close()
                except Exception:  # pragma: no cover
                    LOG.debug("failed to close libCEC adapter cleanly")

    def send_tx(self, frame: str) -> bool:
        if self._lib is None or not self._connected:
            return False
        LOG.debug("CEC TX: tx %s", frame)
        command = self._lib.CommandFromString(frame.lower())
        return bool(self._lib.Transmit(command))


# Backward-compatible alias with previous adapter name.
CecClientAdapter = LibCecAdapter
