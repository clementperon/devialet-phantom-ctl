from dataclasses import dataclass
from typing import List

from devialetctl.infrastructure.mdns_gateway import MdnsDiscoveryGateway


@dataclass(frozen=True)
class DevialetService:
    name: str
    address: str
    port: int
    base_path: str  # e.g. "/ipcontrol/v1"


def discover(
    timeout_s: float = 3.0, service_type: str = "_whatsup._tcp.local."
) -> List[DevialetService]:
    gateway = MdnsDiscoveryGateway(service_type=service_type)
    results = gateway.discover(timeout_s=timeout_s)
    return [
        DevialetService(name=r.name, address=r.address, port=r.port, base_path=r.base_path)
        for r in results
    ]
