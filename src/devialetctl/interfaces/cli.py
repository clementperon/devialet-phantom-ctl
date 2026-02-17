import argparse
import dataclasses
import logging
import os
import sys

from devialetctl.application.daemon import DaemonRunner
from devialetctl.application.ports import Target
from devialetctl.application.service import VolumeService
from devialetctl.infrastructure.config import load_config
from devialetctl.infrastructure.devialet_gateway import DevialetHttpGateway, normalize_base_path
from devialetctl.infrastructure.mdns_gateway import MdnsDiscoveryGateway


def _pick(services: list[Target], index: int | None):
    if not services:
        raise RuntimeError(
            "No service detected via mDNS (Bonjour). Check network / Wi-Fi isolation."
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
    services = MdnsDiscoveryGateway().discover(timeout_s=discover_timeout)
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
    services = MdnsDiscoveryGateway().discover(timeout_s=timeout)
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
        services = MdnsDiscoveryGateway().discover(timeout_s=args.discover_timeout)
        if not services:
            print("No service detected.")
            return
        for i, s in enumerate(services):
            print(f"[{i}] {s.name} -> {s.address}:{s.port}{s.base_path}")
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
