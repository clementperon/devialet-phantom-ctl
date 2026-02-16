import asyncio

from devialetctl.application.ports import VolumeGateway


class VolumeService:
    def __init__(self, gateway: VolumeGateway, step: int = 1) -> None:
        self.gateway = gateway
        self.step = max(1, int(step))

    @staticmethod
    def _run(coro):
        return asyncio.run(coro)

    def systems(self):
        return self._run(self.gateway.systems_async())

    def get_volume(self) -> int:
        return int(self._run(self.gateway.get_volume_async()))

    def set_volume(self, value: int) -> None:
        self._run(self.gateway.set_volume_async(value))

    def volume_up(self) -> None:
        self._relative_step(delta=self.step, fallback=self.gateway.volume_up_async)

    def volume_down(self) -> None:
        self._relative_step(delta=-self.step, fallback=self.gateway.volume_down_async)

    def mute(self) -> None:
        self._run(self.gateway.mute_toggle_async())

    def _relative_step(self, delta: int, fallback) -> None:
        try:
            current = int(self._run(self.gateway.get_volume_async()))
            target = max(0, min(100, current + delta))
            if target != current:
                self._run(self.gateway.set_volume_async(target))
        except Exception:
            # Keep compatibility if get/set is temporarily unavailable.
            self._run(fallback())
