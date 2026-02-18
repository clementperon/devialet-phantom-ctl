import asyncio
import dataclasses
import logging

from devialetctl.application.ports import Target
from devialetctl.infrastructure.devialet_gateway import DevialetHttpGateway

LOG = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class DeviceRow:
    device_id: str
    device_name: str
    model: str
    role: str
    serial: str
    address: str
    port: int


@dataclasses.dataclass(frozen=True)
class SystemRow:
    system_id: str
    system_name: str
    devices: list[DeviceRow]


@dataclasses.dataclass(frozen=True)
class GroupRow:
    group_id: str
    systems: list[SystemRow]


def _safe_fetch_json(gateway: DevialetHttpGateway, path: str) -> dict | None:
    try:
        data = asyncio.run(gateway.fetch_json_async(path))
        if isinstance(data, dict):
            return data
    except Exception as exc:
        LOG.debug("tree fetch failed path=%s host=%s err=%s", path, gateway.address, exc)
    return None


def _device_row_to_dict(dev: DeviceRow) -> dict:
    return {
        "device_id": dev.device_id,
        "device_name": dev.device_name,
        "model": dev.model,
        "role": dev.role,
        "serial": dev.serial,
        "address": dev.address,
        "port": dev.port,
    }


def build_topology_tree(targets: list[Target], gateway_factory=DevialetHttpGateway) -> dict:
    devices_by_id: dict[str, dict] = {}
    systems: dict[str, dict] = {}
    groups: dict[str, dict] = {}

    for target in targets:
        gateway = gateway_factory(target.address, target.port, target.base_path)
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
        gateway = gateway_factory(
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

    group_rows: list[GroupRow] = []
    for group_id in sorted(groups.keys()):
        group_data = groups[group_id]
        systems_rows: list[SystemRow] = []
        for system_id in sorted(group_data["systems"].keys()):
            system_data = group_data["systems"][system_id]
            devices_rows = [
                DeviceRow(
                    device_id=str(dev["device_id"]),
                    device_name=str(dev["device_name"]),
                    model=str(dev["model"]),
                    role=str(dev["role"]),
                    serial=str(dev["serial"]),
                    address=str(dev["address"]),
                    port=int(dev["port"]),
                )
                for dev in sorted(system_data["devices"], key=lambda d: d["device_name"])
            ]
            systems_rows.append(
                SystemRow(
                    system_id=str(system_id),
                    system_name=str(system_data["name"]),
                    devices=devices_rows,
                )
            )
        group_rows.append(GroupRow(group_id=str(group_id), systems=systems_rows))

    ungrouped_devices_rows = [
        DeviceRow(
            device_id=str(dev["device_id"]),
            device_name=str(dev["device_name"]),
            model=str(dev["model"]),
            role=str(dev["role"]),
            serial=str(dev["serial"]),
            address=str(dev["address"]),
            port=int(dev["port"]),
        )
        for dev in sorted(
            [d for d in devices_by_id.values() if d["system_id"] is None],
            key=lambda d: d["device_name"],
        )
    ]

    return {
        "groups": [
            {
                "group_id": group.group_id,
                "systems": [
                    {
                        "system_id": system.system_id,
                        "system_name": system.system_name,
                        "devices": [_device_row_to_dict(dev) for dev in system.devices],
                    }
                    for system in group.systems
                ],
            }
            for group in group_rows
        ],
        "ungrouped_devices": [_device_row_to_dict(dev) for dev in ungrouped_devices_rows],
        "errors": [],
    }


def render_topology_tree_lines(tree: dict) -> list[str]:
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


def pick_target_by_system_name(
    services: list[Target],
    system_name: str,
    gateway_factory=DevialetHttpGateway,
) -> Target:
    if not services:
        raise RuntimeError("No service detected via mDNS/UPnP. Check network / Wi-Fi isolation.")
    requested = system_name.strip()
    if not requested:
        raise RuntimeError("System name cannot be empty.")

    tree = build_topology_tree(services, gateway_factory=gateway_factory)
    matches: list[tuple[str, dict]] = []
    for group in tree.get("groups", []):
        group_id = str(group.get("group_id", "ungrouped"))
        for system in group.get("systems", []):
            if str(system.get("system_name", "")).casefold() == requested.casefold():
                matches.append((group_id, system))

    if not matches:
        raise RuntimeError(
            f"System '{requested}' not found. Run 'devialetctl tree' to list available systems."
        )
    if len(matches) > 1:
        groups = ", ".join(sorted({m[0] for m in matches}))
        raise RuntimeError(
            f"System name '{requested}' is ambiguous across groups: {groups}. "
            "Use --ip or rename systems."
        )

    group_id, system = matches[0]
    devices = system.get("devices", [])
    if not devices:
        raise RuntimeError(f"System '{requested}' has no reachable devices in group {group_id}.")
    selected = devices[0]
    return Target(
        address=str(selected["address"]),
        port=int(selected["port"]),
        base_path="/ipcontrol/v1",
        name=f"{requested}@{group_id}",
    )
