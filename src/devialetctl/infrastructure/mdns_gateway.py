import logging
import time
from dataclasses import dataclass

from zeroconf import ServiceBrowser, ServiceListener, Zeroconf

from devialetctl.application.ports import DiscoveryPort, Target

LOG = logging.getLogger(__name__)
_DEFAULT_MDNS_SERVICE_TYPE = "_whatsup._tcp.local."


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

        service_type_lc = service_type.lower()
        if service_type_lc == "_whatsup._tcp.local.":
            # Devialet "_whatsup" SRV records expose an ephemeral service port.
            # We still control the speaker through HTTP on :80 /ipcontrol/v1.
            svc = MdnsService(name=name, address=addr, port=80, base_path="/ipcontrol/v1")
            LOG.debug("mDNS accept service name=%s addr=%s reason=whatsup_service", name, addr)
            self.services.append(svc)
            return

        LOG.debug(
            "mDNS reject service name=%s addr=%s reason=unsupported_service_type(%s)",
            name,
            addr,
            service_type,
        )

    def update_service(self, zeroconf: Zeroconf, service_type: str, name: str) -> None:
        return None

    def remove_service(self, zeroconf: Zeroconf, service_type: str, name: str) -> None:
        return None


class MdnsDiscoveryGateway(DiscoveryPort):
    def __init__(self, service_type: str | None = None) -> None:
        self.service_type = service_type or _DEFAULT_MDNS_SERVICE_TYPE

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
            "mDNS discovery done accepted=%d unique_targets=%d",
            len(listener.services),
            len(targets),
        )
        return targets
