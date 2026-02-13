from dataclasses import dataclass
from typing import Any

import requests

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

    def _get(self, path: str) -> dict[str, Any]:
        r = requests.get(self.base_url + path, timeout=self.timeout_s)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, payload: dict[str, Any] | None = None) -> None:
        r = requests.post(
            self.base_url + path,
            json=(payload if payload is not None else {}),
            timeout=self.timeout_s,
        )
        r.raise_for_status()

    def systems(self) -> dict[str, Any]:
        try:
            return self._get("/systems")
        except requests.HTTPError as exc:
            response = getattr(exc, "response", None)
            if getattr(response, "status_code", None) == 404:
                return self._get("/systems/current")
            raise

    def get_volume(self) -> int:
        data = self._get("/systems/current/sources/current/soundControl/volume")
        if "volume" not in data:
            raise ValueError(f"Unexpected response: {data}")
        return int(data["volume"])

    def set_volume(self, volume: int) -> None:
        v = max(0, min(100, int(volume)))
        self._post("/systems/current/sources/current/soundControl/volume", {"volume": v})

    def volume_up(self) -> None:
        self._post("/systems/current/sources/current/soundControl/volumeUp")

    def volume_down(self) -> None:
        self._post("/systems/current/sources/current/soundControl/volumeDown")

    def mute_toggle(self) -> None:
        self._post("/systems/current/sources/current/soundControl/mute")
