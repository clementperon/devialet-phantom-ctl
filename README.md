# Devialet Phantom Control (IP Control + uv)

[![Coverage](https://clementperon.github.io/devialet-phantom-ctl/badges/coverage.svg)](https://github.com/clementperon/devialet-phantom-ctl/actions/workflows/ci.yml)

Python CLI and daemon to control Devialet Phantom volume over local HTTP API.

Use cases:
- scriptable local volume control
- Raspberry Pi bridge
- TV remote volume bridge over HDMI-CEC
- foundation for IR / keyboard / Home Assistant adapters

## Features

- mDNS discovery (`_http._tcp.local`)
- volume commands: `getvol`, `setvol`, `volup`, `voldown`, `mute`
- manual target override (`--ip`, `--port`, `--base-path`)
- long-running daemon mode (`daemon --input cec`)
- keyboard test mode (`daemon --input keyboard`)
- typed config via TOML + env overrides
- packaged with `uv`

## Requirements

- Python >= 3.10
- `uv` installed: <https://docs.astral.sh/uv/getting-started/installation/>
- same LAN as Devialet Phantom
- Devialet DOS with IP control enabled

For HDMI-CEC daemon mode:
- `cec-client` available on host
- CEC-capable adapter/device path (commonly Raspberry Pi HDMI or USB-CEC adapter)

## Install

```bash
git clone <repo>
cd dvlt-volume
uv sync
```

## CLI Usage

List discovered speakers:

```bash
uv run devialetctl list
```

Read current volume:

```bash
uv run devialetctl getvol
```

Relative commands are precise:
- `volup` increases volume by `+1`
- `voldown` decreases volume by `-1`

Set volume:

```bash
uv run devialetctl setvol 35
```

Use explicit target:

```bash
uv run devialetctl --ip 192.168.1.42 --port 80 --base-path /ipcontrol/v1 getvol
```

## Daemon (CEC Input)

Run daemon with config:

```bash
uv run devialetctl daemon --input cec
```

The daemon:
- consumes CEC key events from `cec-client`
- normalizes to volume actions
- answers `GIVE_AUDIO_STATUS` (`0x71`) with `REPORT_AUDIO_STATUS` (`0x7A`)
- answers System Audio/ARC requests (`0x70`, `0x7D`, `0xC3`, `0xC4`)
- answers `REQUEST_SHORT_AUDIO_DESCRIPTOR` (`0xA4`) with `REPORT_SHORT_AUDIO_DESCRIPTOR` (`0xA3`)
- applies absolute volume from TV `SET_AUDIO_VOLUME_LEVEL` (`0x73`)
- sends updated `REPORT_AUDIO_STATUS` (`0x7A`) after handled volume/mute events
- applies dedupe/rate-limit policy
- retries with backoff if adapter/network is temporarily unavailable

Run daemon with keyboard input (no CEC hardware required):

```bash
uv run devialetctl daemon --input keyboard
```

Keyboard commands:
- `u`, `+`, `up` -> volume up
- `d`, `-`, `down` -> volume down
- `m`, `mute` -> toggle mute
- `q`, `quit`, `exit` -> stop daemon

In interactive terminal mode, single keys (`u`, `d`, `m`, `q`) work immediately without pressing Enter.

## Config File

Default config path:
- Linux/RPi: `$XDG_CONFIG_HOME/devialetctl/config.toml` or `~/.config/devialetctl/config.toml`
- macOS: `~/.config/devialetctl/config.toml`

Example `config.toml`:

```toml
log_level = "INFO"
cec_command = "cec-client -d 8 -t a -o Devialet"
reconnect_delay_s = 2.0
dedupe_window_s = 0.08
min_interval_s = 0.12

[target]
ip = "192.168.1.42"
port = 80
base_path = "/ipcontrol/v1"
discover_timeout = 3.0
index = 0
```

Use `log_level = "DEBUG"` (or `DEVIALETCTL_LOG_LEVEL=DEBUG`) to log raw HDMI-CEC frames:
- `CEC RX: ...` for received lines from `cec-client`
- `CEC TX: tx ...` for transmitted frames

Environment overrides:
- `DEVIALETCTL_IP`
- `DEVIALETCTL_PORT`
- `DEVIALETCTL_BASE_PATH`
- `DEVIALETCTL_LOG_LEVEL`

## Service Deployment

### Raspberry Pi (systemd)

Create `/etc/systemd/system/devialetctl-cec.service`:

```ini
[Unit]
Description=Devialet CEC volume bridge
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/dvlt-volume
ExecStart=/home/pi/.local/bin/uv run devialetctl daemon --input cec
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Enable it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now devialetctl-cec.service
sudo systemctl status devialetctl-cec.service
```

### macOS (LaunchAgent)

Create `~/Library/LaunchAgents/com.local.devialetctl.cec.plist` and point it to:
- your repo directory
- your `uv` binary path
- command `uv run devialetctl daemon --input cec`

Then:

```bash
launchctl unload ~/Library/LaunchAgents/com.local.devialetctl.cec.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.local.devialetctl.cec.plist
launchctl list | rg devialetctl
```

## Development

Run tests:

```bash
uv run pytest
```

## Architecture Notes

The package is organized in layers:
- `devialetctl.domain`: events and policy
- `devialetctl.application`: service, routing, daemon orchestration
- `devialetctl.infrastructure`: HTTP, mDNS, CEC adapter, config
- `devialetctl.interfaces`: CLI wiring

Legacy imports remain available:
- `devialetctl.api.DevialetClient`
- `devialetctl.discovery.discover`
