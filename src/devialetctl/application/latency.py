"""Per-source audio latency (lip sync) of a Devialet system.

Each source of the current group has its own latency setting, in ms:
``manual`` sources (optical, Bluetooth, Spotify Connect, UPnP...) report a
``min``/``max`` range and can be changed; ``auto`` sources (AirPlay, Roon)
manage it themselves.
"""

import asyncio
import re
from dataclasses import dataclass
from typing import Any

from devialetctl.infrastructure.devialet_gateway import DevialetApiError, DevialetHttpGateway

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


@dataclass(frozen=True)
class SourceLatency:
    source_id: str
    source_type: str
    device: str
    latency: int
    control: str
    minimum: int | None = None
    maximum: int | None = None
    default: int | None = None

    @property
    def adjustable(self) -> bool:
        return self.control == "manual" and self.minimum is not None and self.maximum is not None

    def describe(self) -> str:
        text = f"{self.source_type:<15} {self.device:<14} {self.latency} ms ({self.control}"
        if self.adjustable:
            text += f", {self.minimum}-{self.maximum} ms"
            if self.default is not None:
                text += f", default {self.default} ms"
        return text + ")"


def select_sources(sources: list[dict[str, Any]], selector: str) -> list[dict[str, Any]]:
    """Pick sources by id or by type (e.g. ``optical``: one per speaker)."""
    if _UUID_RE.match(selector):
        matches = [s for s in sources if str(s.get("sourceId", "")).lower() == selector.lower()]
    else:
        matches = [s for s in sources if str(s.get("type", "")).lower() == selector.lower()]
    if not matches:
        known = ", ".join(sorted({str(s.get("type")) for s in sources}))
        raise ValueError(f"No source matches {selector!r} (types: {known})")
    return matches


class LatencyService:
    def __init__(self, gateway: DevialetHttpGateway) -> None:
        self.gateway = gateway

    @staticmethod
    def _run(coro):
        return asyncio.run(coro)

    def get(self, selector: str | None = None) -> list[SourceLatency]:
        return self._run(self._get_async(selector))

    def set(self, selector: str, latency_ms: int) -> list[SourceLatency]:
        return self._run(self._set_async(selector, latency_ms))

    async def _device_names_async(self) -> dict[str, str]:
        try:
            system = await self.gateway.fetch_json_async("/systems/current")
        except Exception:
            return {}
        return {
            str(d.get("deviceId")): str(d.get("deviceName"))
            for d in system.get("devices", [])
            if d.get("deviceId") and d.get("deviceName")
        }

    async def _resolve_async(self, selector: str | None) -> list[dict[str, Any]]:
        if selector == "current":
            try:
                return [await self.gateway.get_current_source_async()]
            except DevialetApiError as exc:
                if exc.code == "NoCurrentSource":
                    raise ValueError(
                        "No source is playing; pass --source with a type (e.g. optical) or an id"
                    ) from exc
                raise
        sources = await self.gateway.get_sources_async()
        return sources if selector is None else select_sources(sources, selector)

    async def _read_async(
        self, sources: list[dict[str, Any]], names: dict[str, str]
    ) -> list[SourceLatency]:
        result: list[SourceLatency] = []
        for source in sources:
            source_id = str(source.get("sourceId"))
            data = await self.gateway.get_latency_async(source_id)
            device_id = str(source.get("deviceId", ""))
            result.append(
                SourceLatency(
                    source_id=source_id,
                    source_type=str(source.get("type", "?")),
                    device=names.get(device_id, device_id[:8]),
                    latency=int(data["latency"]),
                    control=str(data.get("latencyControl", "?")),
                    minimum=data.get("min"),
                    maximum=data.get("max"),
                    default=data.get("default"),
                )
            )
        return result

    async def _get_async(self, selector: str | None) -> list[SourceLatency]:
        sources = await self._resolve_async(selector)
        return await self._read_async(sources, await self._device_names_async())

    async def _set_async(self, selector: str, latency_ms: int) -> list[SourceLatency]:
        sources = await self._resolve_async(selector)
        names = await self._device_names_async()
        current = await self._read_async(sources, names)
        for entry in current:
            if not entry.adjustable:
                raise ValueError(
                    f"{entry.source_type} latency is {entry.control}, it cannot be set"
                )
            if not entry.minimum <= latency_ms <= entry.maximum:
                raise ValueError(
                    f"{entry.source_type} latency must be within {entry.minimum}-{entry.maximum} ms"
                )
        for entry in current:
            await self.gateway.set_latency_async(entry.source_id, latency_ms)
        return await self._read_async(sources, names)
