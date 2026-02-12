from devialetctl.application.service import VolumeService
from devialetctl.domain.events import InputEvent, InputEventType
from devialetctl.domain.policy import EventPolicy


class EventRouter:
    def __init__(self, service: VolumeService, policy: EventPolicy | None = None) -> None:
        self.service = service
        self.policy = policy or EventPolicy()

    def handle(self, event: InputEvent) -> bool:
        if not self.policy.should_emit(event):
            return False

        if event.kind == InputEventType.VOLUME_UP:
            self.service.volume_up()
            return True
        if event.kind == InputEventType.VOLUME_DOWN:
            self.service.volume_down()
            return True
        if event.kind == InputEventType.MUTE:
            self.service.mute()
            return True
        return False
