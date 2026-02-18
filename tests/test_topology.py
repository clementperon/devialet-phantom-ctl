import pytest

from devialetctl.application.ports import Target
from devialetctl.interfaces.topology import (
    build_topology_tree,
    pick_target_by_system_name,
    render_topology_tree_lines,
)


def _svc(name: str, address: str) -> Target:
    return Target(name=name, address=address, port=80, base_path="/ipcontrol/v1")


def test_build_topology_tree_returns_error_when_no_device_payload() -> None:
    class FakeGateway:
        def __init__(self, address, port, base_path):
            self.address = address

        async def fetch_json_async(self, path):
            return None

    tree = build_topology_tree([_svc("d1", "10.0.0.2")], gateway_factory=FakeGateway)
    assert tree["groups"] == []
    assert tree["ungrouped_devices"] == []
    assert tree["errors"] == ["No Devialet devices detected."]


def test_render_topology_tree_lines_handles_errors_and_ungrouped() -> None:
    lines = render_topology_tree_lines({"errors": ["boom"], "groups": [], "ungrouped_devices": []})
    assert lines == ["boom"]

    tree = {
        "errors": [],
        "groups": [],
        "ungrouped_devices": [
            {
                "device_name": "Kitchen",
                "address": "10.0.0.42",
                "model": "Phantom II",
            }
        ],
    }
    lines = render_topology_tree_lines(tree)
    assert "Ungrouped devices" in lines
    assert "  Device Kitchen @ 10.0.0.42 model=Phantom II" in lines


def test_pick_target_by_system_name_validation_and_ambiguity(monkeypatch) -> None:
    with pytest.raises(RuntimeError, match="No service"):
        pick_target_by_system_name([], "TV")

    with pytest.raises(RuntimeError, match="cannot be empty"):
        pick_target_by_system_name([_svc("d1", "10.0.0.2")], "   ")

    monkeypatch.setattr(
        "devialetctl.interfaces.topology.build_topology_tree",
        lambda services, gateway_factory=None: {
            "errors": [],
            "groups": [
                {
                    "group_id": "g1",
                    "systems": [
                        {
                            "system_name": "TV",
                            "devices": [{"address": "10.0.0.2", "port": 80}],
                        }
                    ],
                },
                {
                    "group_id": "g2",
                    "systems": [
                        {
                            "system_name": "TV",
                            "devices": [{"address": "10.0.0.3", "port": 80}],
                        }
                    ],
                },
            ],
            "ungrouped_devices": [],
        },
    )
    with pytest.raises(RuntimeError, match="ambiguous across groups"):
        pick_target_by_system_name([_svc("d1", "10.0.0.2")], "TV")


def test_pick_target_by_system_name_raises_when_system_has_no_devices(monkeypatch) -> None:
    monkeypatch.setattr(
        "devialetctl.interfaces.topology.build_topology_tree",
        lambda services, gateway_factory=None: {
            "errors": [],
            "groups": [{"group_id": "grp-tv", "systems": [{"system_name": "TV", "devices": []}]}],
            "ungrouped_devices": [],
        },
    )

    with pytest.raises(RuntimeError, match="has no reachable devices"):
        pick_target_by_system_name([_svc("d1", "10.0.0.2")], "TV")
