import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

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
    cec_device: str = "/dev/cec0"
    cec_osd_name: str = "Devialet"
    cec_vendor_compat: str = "none"
    reconnect_delay_s: float = 2.0
    log_level: str = "INFO"
    dedupe_window_s: float = 0.08
    min_interval_s: float = 0.12


def _toml_error_type():
    return getattr(tomllib, "TOMLDecodeError", ValueError)


class _TargetConfigModel(BaseModel):
    ip: str | None = None
    port: int = 80
    base_path: str = "/ipcontrol/v1"
    discover_timeout: float = 3.0
    index: int | None = None

    @field_validator("port", "discover_timeout", "index", mode="before")
    @classmethod
    def _reject_bool_numbers(cls, value):
        if isinstance(value, bool):
            raise ValueError("boolean values are not valid for numeric fields")
        return value

    @field_validator("base_path", mode="before")
    @classmethod
    def _normalize_base_path(cls, value):
        return normalize_base_path(value)


class _DaemonConfigModel(BaseModel):
    target: _TargetConfigModel = Field(default_factory=_TargetConfigModel)
    cec_device: str = "/dev/cec0"
    cec_osd_name: str = "Devialet"
    cec_vendor_compat: str = "none"
    reconnect_delay_s: float = 2.0
    log_level: str = "INFO"
    dedupe_window_s: float = 0.08
    min_interval_s: float = 0.12

    @field_validator(
        "reconnect_delay_s",
        "dedupe_window_s",
        "min_interval_s",
        mode="before",
    )
    @classmethod
    def _reject_bool_floats(cls, value):
        if isinstance(value, bool):
            raise ValueError("boolean values are not valid for numeric fields")
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def _uppercase_log_level(cls, value):
        return str(value).upper()

    @field_validator("cec_vendor_compat", mode="before")
    @classmethod
    def _normalize_vendor_compat(cls, value):
        normalized = str(value).strip().lower()
        if normalized not in {"none", "samsung"}:
            raise ValueError("cec_vendor_compat must be one of: none, samsung")
        return normalized


def _default_config_path() -> Path:
    xdg = os.getenv("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "devialetctl" / "config.toml"
    return Path.home() / ".config" / "devialetctl" / "config.toml"


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    if not path.is_file():
        raise ValueError(f"Config path is not a file: {path}")
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except OSError as exc:
        raise ValueError(f"Cannot read config file: {path}") from exc
    except _toml_error_type() as exc:
        raise ValueError(f"Invalid TOML in config file: {path}") from exc
    return data if isinstance(data, dict) else {}


def _merge_env_overrides(data: dict[str, Any]) -> dict[str, Any]:
    merged = dict(data)
    target_data = dict(merged.get("target")) if isinstance(merged.get("target"), dict) else {}

    env_ip = os.getenv("DEVIALETCTL_IP")
    env_port = os.getenv("DEVIALETCTL_PORT")
    env_base = os.getenv("DEVIALETCTL_BASE_PATH")
    env_log_level = os.getenv("DEVIALETCTL_LOG_LEVEL")
    env_cec_device = os.getenv("DEVIALETCTL_CEC_DEVICE")
    env_cec_vendor_compat = os.getenv("DEVIALETCTL_CEC_VENDOR_COMPAT")
    if env_ip is not None:
        target_data["ip"] = env_ip
    if env_port is not None:
        target_data["port"] = env_port
    if env_base is not None:
        target_data["base_path"] = env_base
    if env_log_level is not None:
        merged["log_level"] = env_log_level
    if env_cec_device is not None:
        merged["cec_device"] = env_cec_device
    if env_cec_vendor_compat is not None:
        merged["cec_vendor_compat"] = env_cec_vendor_compat

    merged["target"] = target_data
    return merged


def load_config(path: str | None = None) -> DaemonConfig:
    cfg_path = Path(path) if path else _default_config_path()
    data = _merge_env_overrides(_load_toml(cfg_path))
    try:
        parsed = _DaemonConfigModel.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"Invalid config values: {exc}") from exc

    target = RuntimeTarget(
        ip=parsed.target.ip,
        port=parsed.target.port,
        base_path=parsed.target.base_path,
        discover_timeout=parsed.target.discover_timeout,
        index=parsed.target.index,
    )
    return DaemonConfig(
        target=target,
        cec_device=parsed.cec_device,
        cec_osd_name=parsed.cec_osd_name,
        cec_vendor_compat=parsed.cec_vendor_compat,
        reconnect_delay_s=parsed.reconnect_delay_s,
        log_level=parsed.log_level,
        dedupe_window_s=parsed.dedupe_window_s,
        min_interval_s=parsed.min_interval_s,
    )
