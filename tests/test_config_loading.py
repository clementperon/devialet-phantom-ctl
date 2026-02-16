import pytest

from devialetctl.infrastructure.config import load_config


def test_load_config_rejects_directory_path(tmp_path) -> None:
    with pytest.raises(ValueError, match="not a file"):
        load_config(str(tmp_path))


def test_load_config_rejects_invalid_env_port(monkeypatch, tmp_path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("DEVIALETCTL_PORT", "abc")
    with pytest.raises(ValueError, match="target.port"):
        load_config(str(cfg_file))


def test_load_config_rejects_invalid_toml(tmp_path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("target = [", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid TOML"):
        load_config(str(cfg_file))


def test_load_config_coerces_integral_index_float(tmp_path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("[target]\nindex = 1.0\n", encoding="utf-8")
    cfg = load_config(str(cfg_file))
    assert cfg.target.index == 1


def test_load_config_rejects_non_integral_index_float(tmp_path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("[target]\nindex = 1.5\n", encoding="utf-8")
    with pytest.raises(ValueError, match="target.index"):
        load_config(str(cfg_file))


def test_load_config_rejects_boolean_numbers(tmp_path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("[target]\nport = true\n", encoding="utf-8")
    with pytest.raises(ValueError, match="target.port"):
        load_config(str(cfg_file))


def test_load_config_env_overrides_log_level(monkeypatch, tmp_path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('log_level = "INFO"\n', encoding="utf-8")
    monkeypatch.setenv("DEVIALETCTL_LOG_LEVEL", "debug")
    cfg = load_config(str(cfg_file))
    assert cfg.log_level == "DEBUG"


def test_load_config_uses_kernel_cec_defaults(tmp_path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("", encoding="utf-8")
    cfg = load_config(str(cfg_file))
    assert cfg.cec_device == "/dev/cec0"
    assert cfg.cec_osd_name == "Devialet"
    assert cfg.cec_vendor_id == 0x0000F0
    assert cfg.cec_announce_vendor_id is True


def test_load_config_env_overrides_cec_device(monkeypatch, tmp_path) -> None:
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("DEVIALETCTL_CEC_DEVICE", "/dev/cec1")
    cfg = load_config(str(cfg_file))
    assert cfg.cec_device == "/dev/cec1"
