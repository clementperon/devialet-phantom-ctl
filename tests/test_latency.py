import asyncio

import pytest

from devialetctl.application.latency import LatencyService, SourceLatency, select_sources
from devialetctl.infrastructure.devialet_gateway import (
    DevialetApiError,
    DevialetHttpGateway,
    raise_for_api_error,
)

LEFT = "93060b54-2ec2-5c55-a3ab-038bb5550291"
RIGHT = "dd922f2a-7291-519c-ad36-1c94dc685050"
OPT_L = "2aa09149-90eb-498b-ab38-88e5d02f5abb"
OPT_R = "6d6d4490-b621-40ae-9e20-eccbdf1c6c7f"
AIRPLAY = "959a12b3-75a1-4b92-8ddc-4bfa2bcfc756"

SOURCES = [
    {"deviceId": LEFT, "sourceId": AIRPLAY, "type": "airplay2"},
    {"deviceId": RIGHT, "sourceId": OPT_R, "type": "optical"},
    {"deviceId": LEFT, "sourceId": OPT_L, "type": "optical"},
]
MANUAL = {"default": 350, "latency": 160, "latencyControl": "manual", "max": 1000, "min": 60}


class FakeGateway:
    def __init__(self, playing=True):
        self.playing = playing
        self.latency = {
            OPT_L: dict(MANUAL),
            OPT_R: dict(MANUAL),
            AIRPLAY: {"latency": 350, "latencyControl": "auto"},
        }
        self.sets: list[tuple[str, int]] = []

    async def fetch_json_async(self, path):
        assert path == "/systems/current"
        return {
            "devices": [
                {"deviceId": LEFT, "deviceName": "TV Gauche"},
                {"deviceId": RIGHT, "deviceName": "TV Droite"},
            ]
        }

    async def get_sources_async(self):
        return SOURCES

    async def get_current_source_async(self):
        if not self.playing:
            raise DevialetApiError("NoCurrentSource")
        return SOURCES[2]

    async def get_latency_async(self, source_id):
        return dict(self.latency[source_id])

    async def set_latency_async(self, source_id, latency_ms):
        self.sets.append((source_id, latency_ms))
        self.latency[source_id]["latency"] = latency_ms


def test_raise_for_api_error() -> None:
    raise_for_api_error({"latency": 60})
    with pytest.raises(DevialetApiError, match="InvalidValue: latency not in range") as exc:
        raise_for_api_error({"error": {"code": "InvalidValue", "message": "latency not in range"}})
    assert exc.value.code == "InvalidValue"


def test_select_sources_by_type_and_id() -> None:
    assert [s["sourceId"] for s in select_sources(SOURCES, "optical")] == [OPT_R, OPT_L]
    assert [s["sourceId"] for s in select_sources(SOURCES, "OPTICAL")] == [OPT_R, OPT_L]
    assert select_sources(SOURCES, OPT_L.upper()) == [SOURCES[2]]
    with pytest.raises(ValueError, match="types: airplay2, optical"):
        select_sources(SOURCES, "hdmi")


def test_source_latency_describe() -> None:
    manual = SourceLatency(OPT_L, "optical", "TV Gauche", 60, "manual", 60, 1000, 350)
    assert manual.adjustable
    assert manual.describe() == (
        "optical         TV Gauche      60 ms (manual, 60-1000 ms, default 350 ms)"
    )
    auto = SourceLatency(AIRPLAY, "airplay2", "TV Gauche", 350, "auto")
    assert not auto.adjustable
    assert auto.describe().endswith("350 ms (auto)")


def test_latency_service_lists_all_sources_with_device_names() -> None:
    entries = LatencyService(FakeGateway()).get()
    assert [(e.source_type, e.device, e.latency, e.control) for e in entries] == [
        ("airplay2", "TV Gauche", 350, "auto"),
        ("optical", "TV Droite", 160, "manual"),
        ("optical", "TV Gauche", 160, "manual"),
    ]


def test_latency_service_current_source() -> None:
    entries = LatencyService(FakeGateway()).get("current")
    assert [(e.source_id, e.device) for e in entries] == [(OPT_L, "TV Gauche")]


def test_latency_service_current_without_playing_source_is_explained() -> None:
    with pytest.raises(ValueError, match="No source is playing"):
        LatencyService(FakeGateway(playing=False)).get("current")


def test_latency_service_sets_every_matching_source() -> None:
    gateway = FakeGateway()
    entries = LatencyService(gateway).set("optical", 60)
    assert gateway.sets == [(OPT_R, 60), (OPT_L, 60)]
    assert [e.latency for e in entries] == [60, 60]


@pytest.mark.parametrize(
    ("selector", "value", "message"),
    [
        ("optical", 59, "within 60-1000 ms"),
        ("optical", 1001, "within 60-1000 ms"),
        ("airplay2", 100, "is auto"),
    ],
)
def test_latency_service_rejects_invalid_set_before_writing(selector, value, message) -> None:
    gateway = FakeGateway()
    with pytest.raises(ValueError, match=message):
        LatencyService(gateway).set(selector, value)
    assert gateway.sets == []


def test_gateway_latency_endpoints(monkeypatch) -> None:
    gw = DevialetHttpGateway(address="10.0.0.2")
    calls = []

    async def fake_aget(path):
        calls.append(("get", path))
        if path == "/groups/current/sources":
            return {"sources": SOURCES}
        if path == "/groups/current/sources/current":
            return {"source": SOURCES[2], "playingState": "playing"}
        return dict(MANUAL)

    async def fake_apost_json(path, payload):
        calls.append(("post", path, payload))
        return {}

    monkeypatch.setattr(gw, "_aget", fake_aget)
    monkeypatch.setattr(gw, "_apost_json", fake_apost_json)

    assert asyncio.run(gw.get_sources_async()) == SOURCES
    assert asyncio.run(gw.get_current_source_async()) == SOURCES[2]
    assert asyncio.run(gw.get_latency_async(OPT_L))["latency"] == 160
    asyncio.run(gw.set_latency_async(OPT_L, 60))
    path = f"/groups/current/sources/{OPT_L}/configuration/latency"
    assert ("get", path) in calls
    assert ("post", path, {"latency": 60}) in calls


def test_gateway_latency_raises_api_errors(monkeypatch) -> None:
    gw = DevialetHttpGateway(address="10.0.0.2")

    async def fake_aget(_path):
        return {"error": {"code": "NoCurrentSource", "details": {}, "message": ""}}

    async def fake_apost_json(_path, _payload):
        return {"error": {"code": "InvalidValue", "message": "latency not in range"}}

    monkeypatch.setattr(gw, "_aget", fake_aget)
    monkeypatch.setattr(gw, "_apost_json", fake_apost_json)

    with pytest.raises(DevialetApiError, match="NoCurrentSource"):
        asyncio.run(gw.get_latency_async())
    with pytest.raises(DevialetApiError, match="NoCurrentSource"):
        asyncio.run(gw.get_current_source_async())
    with pytest.raises(DevialetApiError, match="InvalidValue"):
        asyncio.run(gw.set_latency_async(OPT_L, 5))
