from dataclasses import dataclass
from enum import Enum


class InputEventType(str, Enum):
    VOLUME_UP = "volume_up"
    VOLUME_DOWN = "volume_down"
    MUTE = "mute"
    GIVE_AUDIO_STATUS = "give_audio_status"


@dataclass(frozen=True)
class InputEvent:
    kind: InputEventType
    source: str
    key: str
