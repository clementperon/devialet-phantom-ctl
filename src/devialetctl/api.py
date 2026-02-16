import asyncio
from dataclasses import dataclass
from typing import Any, Dict

from devialetctl.infrastructure.devialet_gateway import DevialetHttpGateway


@dataclass
class DevialetClient:
    address: str
    port: int = 80
    base_path: str = "/ipcontrol/v1"
    timeout_s: float = 2.5

    def __post_init__(self) -> None:
        self._gateway = DevialetHttpGateway(
            address=self.address,
            port=self.port,
            base_path=self.base_path,
            timeout_s=self.timeout_s,
        )

    # ---- IP Control endpoints (systemId "current") ----
    def systems(self) -> Dict[str, Any]:
        return asyncio.run(self._gateway.systems_async())

    def get_volume(self) -> int:
        return int(asyncio.run(self._gateway.get_volume_async()))

    def set_volume(self, volume: int) -> None:
        asyncio.run(self._gateway.set_volume_async(volume))

    def volume_up(self) -> None:
        asyncio.run(self._gateway.volume_up_async())

    def volume_down(self) -> None:
        asyncio.run(self._gateway.volume_down_async())

    def mute_toggle(self) -> None:
        asyncio.run(self._gateway.mute_toggle_async())
