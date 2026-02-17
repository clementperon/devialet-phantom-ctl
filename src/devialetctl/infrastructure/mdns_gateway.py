import time
from dataclasses import dataclass
from typing import Dict

from zeroconf import ServiceBrowser, ServiceListener, Zeroconf

from devialetctl.application.ports import DiscoveryPort, Target
from devialetctl.infrastructure.devialet_gateway import normalize_base_path
import logging

LOG = logging.getLogger(__name__)


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
        LOG.debug("mDNS add_service type=%s name=%s", service_type, name)
        info = zeroconf.get_service_info(service_type, name, timeout=2000)
        if not info or not info.addresses:
            LOG.debug("mDNS ignore service name=%s reason=no_info_or_addresses", name)
            return

        addr = None
        for a in info.addresses:
            if len(a) == 4:
                addr = ".".join(str(b) for b in a)
                break
        if addr is None:
            LOG.debug("mDNS ignore service name=%s reason=no_ipv4_address", name)
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
            LOG.debug(
                "mDNS accept service name=%s addr=%s port=%s base_path=%s txt_path=%s",
                name,
                addr,
                info.port,
                base_path,
                txt_path,
            )
            self.services.append(svc)
        else:
            LOG.debug(
                "mDNS reject service name=%s addr=%s txt_path=%s reason=not_likely_devialet",
                name,
                addr,
                txt_path,
            )

    def update_service(self, zeroconf: Zeroconf, service_type: str, name: str) -> None:
        return None

    def remove_service(self, zeroconf: Zeroconf, service_type: str, name: str) -> None:
        return None


class MdnsDiscoveryGateway(DiscoveryPort):
    def __init__(self, service_type: str = "_http._tcp.local.") -> None:
        self.service_type = service_type

    def discover(self, timeout_s: float = 3.0) -> list[Target]:
        LOG.debug(
            "mDNS discovery begin service_type=%s timeout_s=%.2f",
            self.service_type,
            timeout_s,
        )
        zc = Zeroconf()
        browser = None
        try:
            listener = _Listener()
            browser = ServiceBrowser(zc, self.service_type, listener)
            time.sleep(timeout_s)
        finally:
            if browser is not None:
                cancel = getattr(browser, "cancel", None)
                if callable(cancel):
                    cancel()
            zc.close()

        uniq: dict[tuple[str, int, str], MdnsService] = {}
        for s in listener.services:
            uniq[(s.address, s.port, s.base_path)] = s

        targets = [
            Target(address=s.address, port=s.port, base_path=s.base_path, name=s.name)
            for s in uniq.values()
        ]
        LOG.debug(
            "mDNS discovery done raw_services=%d unique_targets=%d",
            len(listener.services),
            len(targets),
        )
        return targets
