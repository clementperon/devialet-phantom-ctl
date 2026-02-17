import argparse
import asyncio
import dataclasses
import json
import logging
import os
import sys

from devialetctl.application.daemon import DaemonRunner
from devialetctl.application.ports import Target
from devialetctl.application.service import VolumeService
from devialetctl.infrastructure.config import load_config
from devialetctl.infrastructure.devialet_gateway import DevialetHttpGateway, normalize_base_path
from devialetctl.infrastructure.mdns_gateway import MdnsDiscoveryGateway
from devialetctl.infrastructure.upnp_gateway import UpnpDiscoveryGateway

LOG = logging.getLogger(__name__)


def _pick(services: list[Target], index: int | None):
    if not services:
        raise RuntimeError(
            "No service detected via mDNS/UPnP. Check network / Wi-Fi isolation."
        )
    if index is None:
        if len(services) == 1:
            return services[0]
        for i, s in enumerate(services):
            print(f"[{i}] {s.name} -> {s.address}:{s.port}{s.base_path}")
        raise RuntimeError("Multiple services detected. Run again with --index N.")
    if index < 0 or index >= len(services):
        raise RuntimeError(f"Invalid index: {index}")
    return services[index]


def _discover_targets(timeout_s: float) -> list[Target]:
    seen: set[tuple[str, int, str]] = set()
    merged: list[Target] = []
    for gateway in (MdnsDiscoveryGateway(), UpnpDiscoveryGateway()):
        for svc in gateway.discover(timeout_s=timeout_s):
            key = (svc.address, svc.port, svc.base_path)
            if key in seen:
                continue
            seen.add(key)
            merged.append(svc)
    return merged


def _safe_fetch_json(gateway: DevialetHttpGateway, path: str) -> dict | None:
    try:
        data = asyncio.run(gateway.fetch_json_async(path))
        if isinstance(data, dict):
            return data
    except Exception as exc:
        LOG.debug("tree fetch failed path=%s host=%s err=%s", path, gateway.address, exc)
    return None


def _build_topology_tree(targets: list[Target]) -> dict:
    devices_by_id: dict[str, dict] = {}
    systems: dict[str, dict] = {}
    groups: dict[str, dict] = {}

    for target in targets:
        gateway = DevialetHttpGateway(target.address, target.port, target.base_path)
        device = _safe_fetch_json(gateway, "/devices/current")
        if not device:
            continue

        device_id = str(device.get("deviceId") or f"dispatcher:{target.address}")
        system_id = str(device.get("systemId") or "") or None
        group_id = str(device.get("groupId") or "") or None
        devices_by_id[device_id] = {
            "device_id": device_id,
            "device_name": device.get("deviceName") or device.get("model") or device_id,
            "model": str(device.get("model") or ""),
            "role": str(device.get("role") or ""),
            "serial": str(device.get("serial") or ""),
            "system_id": system_id,
            "group_id": group_id,
            "address": target.address,
            "port": target.port,
        }

    if not devices_by_id:
        return {"groups": [], "ungrouped_devices": [], "errors": ["No Devialet devices detected."]}

    for dev in devices_by_id.values():
        if not dev["system_id"]:
            continue
        systems.setdefault(
            dev["system_id"],
            {"name": None, "group_id": dev["group_id"], "devices": []},
        )
        systems[dev["system_id"]]["devices"].append(dev)

    for system_id, system_data in systems.items():
        probe_device = system_data["devices"][0]
        gateway = DevialetHttpGateway(
            probe_device["address"],
            probe_device["port"],
            "/ipcontrol/v1",
        )
        sys_info = _safe_fetch_json(gateway, "/systems/current")
        if sys_info:
            system_data["name"] = str(sys_info.get("systemName") or system_id)
            sys_group_id = str(sys_info.get("groupId") or "") or None
            if sys_group_id:
                system_data["group_id"] = sys_group_id
        else:
            system_data["name"] = system_id

        group_id = system_data["group_id"] or "ungrouped"
        groups.setdefault(group_id, {"systems": {}})
        groups[group_id]["systems"][system_id] = system_data

    group_items: list[dict] = []
    for group_id in sorted(groups.keys()):
        group_data = groups[group_id]
        systems_items: list[dict] = []
        for system_id in sorted(group_data["systems"].keys()):
            system_data = group_data["systems"][system_id]
            devices_items = [
                {
                    "device_id": dev["device_id"],
                    "device_name": dev["device_name"],
                    "model": dev["model"],
                    "role": dev["role"],
                    "serial": dev["serial"],
                    "address": dev["address"],
                    "port": dev["port"],
                }
                for dev in sorted(system_data["devices"], key=lambda d: d["device_name"])
            ]
            systems_items.append(
                {
                    "system_id": system_id,
                    "system_name": system_data["name"],
                    "devices": devices_items,
                }
            )
        group_items.append(
            {
                "group_id": group_id,
                "systems": systems_items,
            }
        )

    ungrouped_devices = [
        {
            "device_id": dev["device_id"],
            "device_name": dev["device_name"],
            "model": dev["model"],
            "role": dev["role"],
            "serial": dev["serial"],
            "address": dev["address"],
            "port": dev["port"],
        }
        for dev in sorted(
            [d for d in devices_by_id.values() if d["system_id"] is None],
            key=lambda d: d["device_name"],
        )
    ]

    return {"groups": group_items, "ungrouped_devices": ungrouped_devices, "errors": []}


def _render_topology_tree_lines(tree: dict) -> list[str]:
    if tree.get("errors"):
        return tree["errors"]

    lines: list[str] = []
    for group in tree.get("groups", []):
        lines.append(f"Group {group['group_id']}")
        for system in group.get("systems", []):
            lines.append(f"  System {system['system_name']} ({system['system_id']})")
            for dev in system.get("devices", []):
                role = f" role={dev['role']}" if dev.get("role") else ""
                model = f" model={dev['model']}" if dev.get("model") else ""
                lines.append(f"    Device {dev['device_name']} @ {dev['address']}{model}{role}")

    if tree.get("ungrouped_devices"):
        lines.append("Ungrouped devices")
        for dev in tree["ungrouped_devices"]:
            model = f" model={dev['model']}" if dev.get("model") else ""
            lines.append(f"  Device {dev['device_name']} @ {dev['address']}{model}")
    return lines


def _target_from_args(args) -> Target:
    ip = args.ip
    port = args.port
    base_path = args.base_path
    discover_timeout = args.discover_timeout
    index = args.index

    if getattr(args, "cmd", None) == "daemon":
        ip = args.daemon_ip if args.daemon_ip is not None else ip
        port = args.daemon_port if args.daemon_port is not None else port
        base_path = args.daemon_base_path if args.daemon_base_path is not None else base_path
        discover_timeout = (
            args.daemon_discover_timeout
            if args.daemon_discover_timeout is not None
            else discover_timeout
        )
        index = args.daemon_index if args.daemon_index is not None else index

    if ip:
        return Target(
            address=ip, port=port, base_path=normalize_base_path(base_path), name="manual"
        )
    services = _discover_targets(timeout_s=discover_timeout)
    return _pick(services, index)


def _target_from_config(args) -> Target:
    cfg = load_config(args.config)
    if args.daemon_ip is not None:
        return Target(
            address=args.daemon_ip,
            port=args.daemon_port if args.daemon_port is not None else 80,
            base_path=normalize_base_path(
                args.daemon_base_path if args.daemon_base_path is not None else "/ipcontrol/v1"
            ),
            name="manual",
        )

    if cfg.target.ip:
        return Target(
            address=cfg.target.ip,
            port=cfg.target.port,
            base_path=cfg.target.base_path,
            name="config",
        )
    timeout = (
        args.daemon_discover_timeout
        if args.daemon_discover_timeout is not None
        else cfg.target.discover_timeout
    )
    index = args.daemon_index if args.daemon_index is not None else cfg.target.index
    services = _discover_targets(timeout_s=timeout)
    return _pick(services, index)


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )


def main() -> None:
    p = argparse.ArgumentParser(
        prog="devialetctl", description="Devialet Phantom IP Control (discover + commands)"
    )
    p.add_argument(
        "--log-level",
        type=str,
        default=None,
        help="Override log level (e.g. DEBUG, INFO, WARNING).",
    )
    p.add_argument("--discover-timeout", type=float, default=3.0)
    p.add_argument("--index", type=int, default=None)
    p.add_argument("--ip", type=str, default=None, help="Manual IP (bypass discovery)")
    p.add_argument("--port", type=int, default=80)
    p.add_argument("--base-path", type=str, default="/ipcontrol/v1")

    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    tree = sub.add_parser("tree")
    tree.add_argument("--json", action="store_true", dest="tree_json")
    sub.add_parser("systems")
    sub.add_parser("getvol")
    sub.add_parser("volup")
    sub.add_parser("voldown")
    sub.add_parser("mute")
    set_parser = sub.add_parser("setvol")
    set_parser.add_argument("value", type=int)

    daemon = sub.add_parser("daemon")
    daemon.add_argument("--input", choices=["cec", "keyboard"], default="cec")
    daemon.add_argument("--config", type=str, default=None)
    daemon.add_argument(
        "--discover-timeout", dest="daemon_discover_timeout", type=float, default=None
    )
    daemon.add_argument("--index", dest="daemon_index", type=int, default=None)
    daemon.add_argument("--ip", dest="daemon_ip", type=str, default=None)
    daemon.add_argument("--port", dest="daemon_port", type=int, default=None)
    daemon.add_argument("--base-path", dest="daemon_base_path", type=str, default=None)
    daemon.add_argument("--cec-device", dest="daemon_cec_device", type=str, default=None)
    daemon.add_argument("--cec-osd-name", dest="daemon_cec_osd_name", type=str, default=None)
    daemon.add_argument(
        "--cec-vendor-compat",
        dest="daemon_cec_vendor_compat",
        choices=["none", "samsung"],
        default=None,
    )

    args = p.parse_args()
    requested_log_level = args.log_level or os.getenv("DEVIALETCTL_LOG_LEVEL")
    if requested_log_level is not None:
        _configure_logging(requested_log_level)

    if args.cmd == "list":
        services = _discover_targets(timeout_s=args.discover_timeout)
        if not services:
            print("No service detected.")
            return
        for i, s in enumerate(services):
            print(f"[{i}] {s.name} -> {s.address}:{s.port}{s.base_path}")
        return
    if args.cmd == "tree":
        services = _discover_targets(timeout_s=args.discover_timeout)
        if not services:
            print("No service detected.")
            return
        tree = _build_topology_tree(services)
        if args.tree_json:
            print(json.dumps(tree, indent=2, ensure_ascii=False))
            return
        for line in _render_topology_tree_lines(tree):
            print(line)
        return

    if args.cmd == "daemon":
        try:
            cfg = load_config(args.config)
            cfg = dataclasses.replace(
                cfg,
                cec_device=(
                    args.daemon_cec_device if args.daemon_cec_device is not None else cfg.cec_device
                ),
                cec_osd_name=(
                    args.daemon_cec_osd_name
                    if args.daemon_cec_osd_name is not None
                    else cfg.cec_osd_name
                ),
                cec_vendor_compat=(
                    args.daemon_cec_vendor_compat
                    if args.daemon_cec_vendor_compat is not None
                    else cfg.cec_vendor_compat
                ),
            )
            if requested_log_level is None:
                _configure_logging(cfg.log_level)
            target = _target_from_config(args)
            gateway = DevialetHttpGateway(target.address, target.port, target.base_path)
            runner = DaemonRunner(cfg=cfg, gateway=gateway)
            runner.run_forever(input_name=args.input)
            return
        except KeyboardInterrupt:
            return
        except Exception as exc:
            print(f"Daemon error: {exc}", file=sys.stderr)
            raise SystemExit(2)

    target = _target_from_args(args)
    client = VolumeService(DevialetHttpGateway(target.address, target.port, target.base_path))

    try:
        if args.cmd == "systems":
            print(client.systems())
        elif args.cmd == "getvol":
            print(client.get_volume())
        elif args.cmd == "setvol":
            client.set_volume(args.value)
            print("OK")
        elif args.cmd == "volup":
            client.volume_up()
            print("OK")
        elif args.cmd == "voldown":
            client.volume_down()
            print("OK")
        elif args.cmd == "mute":
            client.mute()
            print("OK")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(2)
