import logging
import re
import socket
import time
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlparse

import httpx  # type: ignore[reportMissingImports]

from devialetctl.application.ports import DiscoveryPort, Target

_SSDP_ADDR = ("239.255.255.250", 1900)
_SSDP_SEARCH_TARGET = "urn:schemas-upnp-org:device:MediaRenderer:2"
_DEFAULT_BASE_PATH = "/ipcontrol/v1"
_DEFAULT_PORT = 80
LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class UpnpService:
    name: str
    address: str
    port: int
    base_path: str


def _parse_ssdp_headers(payload: bytes) -> dict[str, str]:
    text = payload.decode("utf-8", errors="ignore")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    return headers


def _iter_ssdp_responses(timeout_s: float) -> Iterable[dict[str, str]]:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as sock:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.settimeout(max(0.2, min(timeout_s, 1.0)))
        msg = "\r\n".join(
            [
                "M-SEARCH * HTTP/1.1",
                "HOST: 239.255.255.250:1900",
                'MAN: "ssdp:discover"',
                "MX: 1",
                f"ST: {_SSDP_SEARCH_TARGET}",
                "",
                "",
            ]
        ).encode("ascii")
        LOG.debug("UPnP SSDP M-SEARCH start st=%s timeout_s=%.2f", _SSDP_SEARCH_TARGET, timeout_s)
        sock.sendto(msg, _SSDP_ADDR)

        deadline = time.monotonic() + max(0.1, timeout_s)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                LOG.debug("UPnP SSDP M-SEARCH finished (timeout reached)")
                return
            sock.settimeout(max(0.05, min(remaining, 0.5)))
            try:
                payload, _ = sock.recvfrom(8192)
            except TimeoutError:
                continue
            except OSError:
                LOG.debug("UPnP SSDP receive aborted due to socket error")
                return
            headers = _parse_ssdp_headers(payload)
            if headers:
                LOG.debug(
                    "UPnP SSDP response location=%s st=%s usn=%s",
                    headers.get("location", ""),
                    headers.get("st", ""),
                    headers.get("usn", ""),
                )
                yield headers


def _is_devialet_manufacturer(location: str, timeout_s: float) -> bool:
    timeout = max(0.3, min(timeout_s, 1.5))
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(location)
        response.raise_for_status()
        xml_text = response.text
    except Exception as exc:
        LOG.debug("UPnP XML fetch failed location=%s err=%s", location, exc)
        return False

    if not re.search(
        r"<manufacturer>\s*Devialet\s*</manufacturer>",
        xml_text,
        flags=re.IGNORECASE,
    ):
        LOG.debug("UPnP XML rejected location=%s manufacturer_tag_not_found", location)
        return False

    LOG.debug("UPnP XML accepted location=%s manufacturer=Devialet", location)
    return True


class UpnpDiscoveryGateway(DiscoveryPort):
    def discover(self, timeout_s: float = 3.0) -> list[Target]:
        uniq: dict[str, UpnpService] = {}
        LOG.debug(
            "UPnP discovery begin timeout_s=%.2f target=%s",
            timeout_s,
            _SSDP_SEARCH_TARGET,
        )
        for headers in _iter_ssdp_responses(timeout_s):
            location = headers.get("location", "")
            if not _is_devialet_manufacturer(location=location, timeout_s=timeout_s):
                continue
            parsed = urlparse(location)
            host = parsed.hostname
            if not host:
                LOG.debug("UPnP response ignored (missing host in location): %s", location)
                continue
            if host in uniq:
                continue

            uniq[host] = UpnpService(
                name=f"UPnP:{host}",
                address=host,
                port=_DEFAULT_PORT,
                base_path=_DEFAULT_BASE_PATH,
            )
            LOG.debug("UPnP device accepted host=%s base_path=%s", host, _DEFAULT_BASE_PATH)

        targets = [
            Target(address=s.address, port=s.port, base_path=s.base_path, name=s.name)
            for s in uniq.values()
        ]
        LOG.debug("UPnP discovery done found=%d", len(targets))
        return targets
