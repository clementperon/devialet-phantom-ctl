import argparse
import dataclasses
import json
import logging
import os
import sys

from devialetctl.application.daemon import DaemonRunner
from devialetctl.application.ports import Target
from devialetctl.application.service import VolumeService
from devialetctl.infrastructure.config import load_config
from devialetctl.infrastructure.devialet_gateway import DevialetHttpGateway
from devialetctl.infrastructure.mdns_gateway import MdnsDiscoveryGateway
from devialetctl.infrastructure.upnp_gateway import UpnpDiscoveryGateway
from devialetctl.interfaces.topology import (
    build_topology_tree,
    pick_target_by_system_name,
    render_topology_tree_lines,
)

LOG = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class _EffectiveOptions:
    ip: str | None
    port: int
    discover_timeout: float
    system: str | None
    cec_device: str
    cec_osd_name: str
    cec_vendor_compat: str


def _effective_options(args, cfg) -> _EffectiveOptions:
    cec_device_arg = getattr(args, "cec_device", None)
    cec_osd_name_arg = getattr(args, "cec_osd_name", None)
    cec_vendor_compat_arg = getattr(args, "cec_vendor_compat", None)
    return _EffectiveOptions(
        ip=args.ip if args.ip is not None else cfg.target.ip,
        port=args.port if args.port is not None else cfg.target.port,
        discover_timeout=(
            args.discover_timeout
            if args.discover_timeout is not None
            else cfg.target.discover_timeout
        ),
        system=args.system,
        cec_device=cec_device_arg if cec_device_arg is not None else cfg.cec_device,
        cec_osd_name=cec_osd_name_arg if cec_osd_name_arg is not None else cfg.cec_osd_name,
        cec_vendor_compat=(
            cec_vendor_compat_arg
            if cec_vendor_compat_arg is not None
            else cfg.cec_vendor_compat
        ),
    )


def _pick(services: list[Target]) -> Target:
    if not services:
        raise RuntimeError(
            "No service detected via mDNS/UPnP. Check network / Wi-Fi isolation."
        )
    if len(services) == 1:
        return services[0]
    for i, s in enumerate(services):
        print(f"[{i}] {s.name} -> {s.address}:{s.port}{s.base_path}")
    raise RuntimeError(
        "Multiple services detected. Use --system <name> to pick one, or --ip to force a target."
    )


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


def _target_from_resolved(resolved: _EffectiveOptions) -> Target:
    if resolved.ip:
        return Target(address=resolved.ip, port=resolved.port, base_path="/ipcontrol/v1", name="manual")
    services = _discover_targets(timeout_s=resolved.discover_timeout)
    if resolved.system is not None:
        return pick_target_by_system_name(services, resolved.system)
    return _pick(services)


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )


def _validate_target_selection_args(parser: argparse.ArgumentParser, args) -> None:
    if args.ip and args.system:
        parser.error(
            "--ip and --system are not compatible: --ip disables discovery while --system requires discovery."
        )


def _dispatch_command(args, daemon_cfg, resolved: _EffectiveOptions) -> None:
    if args.cmd == "list":
        services = _discover_targets(timeout_s=resolved.discover_timeout)
        if not services:
            print("No service detected.")
            return
        for i, s in enumerate(services):
            print(f"[{i}] {s.name} -> {s.address}:{s.port}{s.base_path}")
        return

    if args.cmd == "tree":
        services = _discover_targets(timeout_s=resolved.discover_timeout)
        if not services:
            print("No service detected.")
            return
        tree = build_topology_tree(services)
        if args.tree_json:
            print(json.dumps(tree, indent=2, ensure_ascii=False))
            return
        for line in render_topology_tree_lines(tree):
            print(line)
        return

    target = _target_from_resolved(resolved)
    gateway = DevialetHttpGateway(target.address, target.port, target.base_path)

    if args.cmd == "daemon":
        try:
            runner = DaemonRunner(cfg=daemon_cfg, gateway=gateway)
            runner.run_forever(input_name=args.input)
            return
        except KeyboardInterrupt:
            return
        except Exception as exc:
            print(f"Daemon error: {exc}", file=sys.stderr)
            raise SystemExit(2)

    client = VolumeService(gateway)
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


def main() -> None:
    p = argparse.ArgumentParser(
        prog="devialetctl", description="Devialet Phantom IP Control (discover + commands)"
    )
    p.add_argument("--config", type=str, default=None)
    p.add_argument(
        "--log-level",
        type=str,
        default=None,
        help="Override log level (e.g. DEBUG, INFO, WARNING).",
    )
    p.add_argument("--discover-timeout", type=float, default=None)
    p.add_argument("--system", type=str, default=None, help="System name from 'tree' output.")
    p.add_argument("--ip", type=str, default=None, help="Manual IP (bypass discovery)")
    p.add_argument("--port", type=int, default=None)
    p.add_argument("--cec-device", type=str, default=None)
    p.add_argument("--cec-osd-name", type=str, default=None)
    p.add_argument(
        "--cec-vendor-compat",
        choices=["none", "samsung"],
        default=None,
    )

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

    args = p.parse_args()
    _validate_target_selection_args(p, args)
    cfg = load_config(args.config)
    resolved = _effective_options(args, cfg)
    daemon_cfg = dataclasses.replace(
        cfg,
        cec_device=resolved.cec_device,
        cec_osd_name=resolved.cec_osd_name,
        cec_vendor_compat=resolved.cec_vendor_compat,
    )
    requested_log_level = args.log_level or os.getenv("DEVIALETCTL_LOG_LEVEL")
    _configure_logging(requested_log_level if requested_log_level is not None else cfg.log_level)
    _dispatch_command(args, daemon_cfg, resolved)
