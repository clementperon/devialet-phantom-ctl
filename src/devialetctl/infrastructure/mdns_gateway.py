import time
from dataclasses import dataclass
from typing import Dict

from zeroconf import ServiceBrowser, ServiceListener, Zeroconf

from devialetctl.application.ports import DiscoveryPort, Target
from devialetctl.infrastructure.devialet_gateway import normalize_base_path


def _is_likely_devialet(name: str, txt_path: str | None) -> bool:
    n = name.lower()
    if "devialet" in n or "phantom" in n or "expert" in n:
        return True
    if txt_path and "ipcontrol" in txt_path.lower():
        return True
    return False


@dataclass(frozen=True)
class MdnsService:
    name: str
    address: str
    port: int
    base_path: str


class _Listener(ServiceListener):
    def __init__(self) -> None:
        self.services: list[MdnsService] = []

    def add_service(self, zeroconf: Zeroconf, service_type: str, name: str) -> None:
        info = zeroconf.get_service_info(service_type, name, timeout=2000)
        if not info or not info.addresses:
            return

        addr = None
        for a in info.addresses:
            if len(a) == 4:
                addr = ".".join(str(b) for b in a)
                break
        if addr is None:
            return

        props: Dict[str, str] = {}
        for k, v in (info.properties or {}).items():
            try:
                props[k.decode("utf-8")] = v.decode("utf-8")
            except Exception:
                pass

        txt_path = props.get("path")
        base_path = normalize_base_path(txt_path)
        svc = MdnsService(name=name, address=addr, port=info.port, base_path=base_path)
        if _is_likely_devialet(name=name, txt_path=txt_path):
            self.services.append(svc)

    def update_service(self, zeroconf: Zeroconf, service_type: str, name: str) -> None:
        return None

    def remove_service(self, zeroconf: Zeroconf, service_type: str, name: str) -> None:
        return None


class MdnsDiscoveryGateway(DiscoveryPort):
    def __init__(self, service_type: str = "_http._tcp.local.") -> None:
        self.service_type = service_type

    def discover(self, timeout_s: float = 3.0) -> list[Target]:
        zc = Zeroconf()
        try:
            listener = _Listener()
            ServiceBrowser(zc, self.service_type, listener)
            time.sleep(timeout_s)
        finally:
            zc.close()

        uniq: dict[tuple[str, int, str], MdnsService] = {}
        for s in listener.services:
            uniq[(s.address, s.port, s.base_path)] = s

        return [
            Target(address=s.address, port=s.port, base_path=s.base_path, name=s.name)
            for s in uniq.values()
        ]
