from dataclasses import dataclass
from enum import Enum


class InputEventType(str, Enum):
    VOLUME_UP = "volume_up"
    VOLUME_DOWN = "volume_down"
    MUTE = "mute"


@dataclass(frozen=True)
class InputEvent:
    kind: InputEventType
    source: str
    key: str
