import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from devialetctl.infrastructure.devialet_gateway import normalize_base_path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


@dataclass(frozen=True)
class RuntimeTarget:
    ip: str | None = None
    port: int = 80
    base_path: str = "/ipcontrol/v1"
    discover_timeout: float = 3.0
    index: int | None = None


@dataclass(frozen=True)
class DaemonConfig:
    target: RuntimeTarget
    cec_command: str = "cec-client -d 8"
    reconnect_delay_s: float = 2.0
    log_level: str = "INFO"
    dedupe_window_s: float = 0.08
    min_interval_s: float = 0.12


def _default_config_path() -> Path:
    xdg = os.getenv("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "devialetctl" / "config.toml"
    return Path.home() / ".config" / "devialetctl" / "config.toml"


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists() or tomllib is None:
        return {}
    with path.open("rb") as f:
        data = tomllib.load(f)
    return data if isinstance(data, dict) else {}


def load_config(path: str | None = None) -> DaemonConfig:
    cfg_path = Path(path) if path else _default_config_path()
    data = _load_toml(cfg_path)
    target_data = data.get("target", {}) if isinstance(data.get("target", {}), dict) else {}

    env_ip = os.getenv("DEVIALETCTL_IP")
    env_port = os.getenv("DEVIALETCTL_PORT")
    env_base = os.getenv("DEVIALETCTL_BASE_PATH")

    target = RuntimeTarget(
        ip=env_ip if env_ip is not None else target_data.get("ip"),
        port=int(env_port) if env_port else int(target_data.get("port", 80)),
        base_path=normalize_base_path(
            env_base if env_base is not None else target_data.get("base_path", "/ipcontrol/v1")
        ),
        discover_timeout=float(target_data.get("discover_timeout", 3.0)),
        index=target_data.get("index"),
    )

    return DaemonConfig(
        target=target,
        cec_command=str(data.get("cec_command", "cec-client -d 8")),
        reconnect_delay_s=float(data.get("reconnect_delay_s", 2.0)),
        log_level=str(data.get("log_level", "INFO")).upper(),
        dedupe_window_s=float(data.get("dedupe_window_s", 0.08)),
        min_interval_s=float(data.get("min_interval_s", 0.12)),
    )
