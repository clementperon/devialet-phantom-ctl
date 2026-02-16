from dataclasses import dataclass
from typing import Any

import httpx

from devialetctl.application.ports import VolumeGateway


def normalize_base_path(value: str | None) -> str:
    raw = (value or "").strip()
    if raw in {"", "/"}:
        return "/ipcontrol/v1"
    if not raw.startswith("/"):
        raw = f"/{raw}"
    return raw.rstrip("/") or "/ipcontrol/v1"


@dataclass
class DevialetHttpGateway(VolumeGateway):
    address: str
    port: int = 80
    base_path: str = "/ipcontrol/v1"
    timeout_s: float = 2.5

    def __post_init__(self) -> None:
        self.base_path = normalize_base_path(self.base_path)
        self.base_url = f"http://{self.address}:{self.port}{self.base_path}"

    async def _aget(self, path: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            r = await client.get(self.base_url + path)
        r.raise_for_status()
        return r.json()

    async def _apost(self, path: str, payload: dict[str, Any] | None = None) -> None:
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            r = await client.post(
                self.base_url + path,
                json=(payload if payload is not None else {}),
            )
        r.raise_for_status()

    async def systems_async(self) -> dict[str, Any]:
        try:
            return await self._aget("/systems")
        except httpx.HTTPStatusError as exc:
            response = getattr(exc, "response", None)
            if getattr(response, "status_code", None) == 404:
                return await self._aget("/systems/current")
            raise

    async def get_volume_async(self) -> int:
        data = await self._aget("/systems/current/sources/current/soundControl/volume")
        if "volume" not in data:
            raise ValueError(f"Unexpected response: {data}")
        return int(data["volume"])

    async def set_volume_async(self, volume: int) -> None:
        v = max(0, min(100, int(volume)))
        await self._apost("/systems/current/sources/current/soundControl/volume", {"volume": v})

    async def get_mute_state_async(self) -> bool:
        state = await self._aget("/groups/current/sources/current")
        mute_state = str(state.get("muteState", "")).lower()
        return mute_state == "muted"

    async def volume_up_async(self) -> None:
        await self._apost("/systems/current/sources/current/soundControl/volumeUp")

    async def volume_down_async(self) -> None:
        await self._apost("/systems/current/sources/current/soundControl/volumeDown")

    async def mute_toggle_async(self) -> None:
        if await self.get_mute_state_async():
            await self._apost("/groups/current/sources/current/playback/unmute")
        else:
            await self._apost("/groups/current/sources/current/playback/mute")
