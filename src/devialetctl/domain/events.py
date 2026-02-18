from dataclasses import dataclass
from enum import Enum


class InputEventType(str, Enum):
    VOLUME_UP = "volume_up"
    VOLUME_DOWN = "volume_down"
    MUTE = "mute"
    USER_CONTROL_RELEASED = "user_control_released"
    GIVE_AUDIO_STATUS = "give_audio_status"
    SYSTEM_AUDIO_MODE_REQUEST = "system_audio_mode_request"
    GIVE_SYSTEM_AUDIO_MODE_STATUS = "give_system_audio_mode_status"
    REQUEST_ARC_INITIATION = "request_arc_initiation"
    REQUEST_ARC_TERMINATION = "request_arc_termination"
    REQUEST_SHORT_AUDIO_DESCRIPTOR = "request_short_audio_descriptor"
    GIVE_DEVICE_VENDOR_ID = "give_device_vendor_id"
    GIVE_OSD_NAME = "give_osd_name"
    SET_AUDIO_VOLUME_LEVEL = "set_audio_volume_level"
    SAMSUNG_VENDOR_COMMAND = "samsung_vendor_command"
    SAMSUNG_VENDOR_COMMAND_WITH_ID = "samsung_vendor_command_with_id"


@dataclass(frozen=True)
class InputEvent:
    kind: InputEventType
    source: str
    key: str
    value: int | None = None
    muted: bool | None = None
    vendor_subcommand: int | None = None
    vendor_mode: int | None = None
    vendor_payload: tuple[int, ...] | None = None
