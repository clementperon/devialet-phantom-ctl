from dataclasses import dataclass
from enum import Enum


class InputEventType(str, Enum):
    VOLUME_UP = "volume_up"
    VOLUME_DOWN = "volume_down"
    MUTE = "mute"
    GIVE_AUDIO_STATUS = "give_audio_status"
    SYSTEM_AUDIO_MODE_REQUEST = "system_audio_mode_request"
    GIVE_SYSTEM_AUDIO_MODE_STATUS = "give_system_audio_mode_status"
    REQUEST_ARC_INITIATION = "request_arc_initiation"
    REQUEST_ARC_TERMINATION = "request_arc_termination"


@dataclass(frozen=True)
class InputEvent:
    kind: InputEventType
    source: str
    key: str
