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
        return self._gateway.systems()

    def get_volume(self) -> int:
        return self._gateway.get_volume()

    def set_volume(self, volume: int) -> None:
        self._gateway.set_volume(volume)

    def volume_up(self) -> None:
        self._gateway.volume_up()

    def volume_down(self) -> None:
        self._gateway.volume_down()

    def mute_toggle(self) -> None:
        self._gateway.mute_toggle()
