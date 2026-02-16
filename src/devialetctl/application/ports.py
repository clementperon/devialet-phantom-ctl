from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class Target:
    address: str
    port: int
    base_path: str
    name: str = ""


class VolumeGateway(Protocol):
    async def systems_async(self) -> dict[str, Any]: ...

    async def get_volume_async(self) -> int: ...

    async def set_volume_async(self, volume: int) -> None: ...

    async def volume_up_async(self) -> None: ...

    async def volume_down_async(self) -> None: ...

    async def mute_toggle_async(self) -> None: ...


class DiscoveryPort(Protocol):
    def discover(self, timeout_s: float) -> list[Target]: ...
