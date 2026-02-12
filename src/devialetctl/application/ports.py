from dataclasses import dataclass
from typing import Any, Protocol

from devialetctl.domain.events import InputEvent


@dataclass(frozen=True)
class Target:
    address: str
    port: int
    base_path: str
    name: str = ""


class VolumeGateway(Protocol):
    def systems(self) -> dict[str, Any]:
        ...

    def get_volume(self) -> int:
        ...

    def set_volume(self, volume: int) -> None:
        ...

    def volume_up(self) -> None:
        ...

    def volume_down(self) -> None:
        ...

    def mute_toggle(self) -> None:
        ...


class EventSource(Protocol):
    def events(self):
        ...


class GatewayFactory(Protocol):
    def __call__(self, target: Target) -> VolumeGateway:
        ...


class DiscoveryPort(Protocol):
    def discover(self, timeout_s: float) -> list[Target]:
        ...


class InputAdapter(Protocol):
    def events(self):
        ...
