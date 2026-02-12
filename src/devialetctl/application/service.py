from devialetctl.application.ports import VolumeGateway


class VolumeService:
    def __init__(self, gateway: VolumeGateway, step: int = 1) -> None:
        self.gateway = gateway
        self.step = max(1, int(step))

    def systems(self):
        return self.gateway.systems()

    def get_volume(self) -> int:
        return self.gateway.get_volume()

    def set_volume(self, value: int) -> None:
        self.gateway.set_volume(value)

    def volume_up(self) -> None:
        self._relative_step(delta=self.step, fallback=self.gateway.volume_up)

    def volume_down(self) -> None:
        self._relative_step(delta=-self.step, fallback=self.gateway.volume_down)

    def mute(self) -> None:
        self.gateway.mute_toggle()

    def _relative_step(self, delta: int, fallback) -> None:
        try:
            current = int(self.gateway.get_volume())
            target = max(0, min(100, current + delta))
            if target != current:
                self.gateway.set_volume(target)
        except Exception:
            # Keep compatibility if get/set is temporarily unavailable.
            fallback()
