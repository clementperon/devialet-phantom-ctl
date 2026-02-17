from dataclasses import dataclass
from typing import List

from devialetctl.infrastructure.mdns_gateway import MdnsDiscoveryGateway
from devialetctl.infrastructure.upnp_gateway import UpnpDiscoveryGateway


@dataclass(frozen=True)
class DevialetService:
    name: str
    address: str
    port: int
    base_path: str  # e.g. "/ipcontrol/v1"


def discover(
    timeout_s: float = 3.0, service_type: str = "_whatsup._tcp.local."
) -> List[DevialetService]:
    results = []
    seen: set[tuple[str, int, str]] = set()
    for gateway in (MdnsDiscoveryGateway(service_type=service_type), UpnpDiscoveryGateway()):
        for svc in gateway.discover(timeout_s=timeout_s):
            key = (svc.address, svc.port, svc.base_path)
            if key in seen:
                continue
            seen.add(key)
            results.append(svc)
    return [
        DevialetService(name=r.name, address=r.address, port=r.port, base_path=r.base_path)
        for r in results
    ]
