import sys

import pytest

from devialetctl.infrastructure import cec_adapter


def test_libcec_adapter_raises_when_no_adapter_detected(monkeypatch) -> None:
    class FakeCfg:
        def __init__(self):
            self.deviceTypes = self

        def Add(self, _value):
            return None

        def SetLogCallback(self, _cb):
            return None

        def SetKeyPressCallback(self, _cb):
            return None

        def SetCommandCallback(self, _cb):
            return None

    class FakeLib:
        def DetectAdapters(self):
            return []

    class FakeIcecAdapter:
        @staticmethod
        def Create(_cfg):
            return FakeLib()

    class FakeCecModule:
        CEC_DEVICE_TYPE_AUDIO_SYSTEM = 5
        LIBCEC_VERSION_CURRENT = 1
        ICECAdapter = FakeIcecAdapter

        @staticmethod
        def libcec_configuration():
            return FakeCfg()

    monkeypatch.setitem(sys.modules, "cec", FakeCecModule())
    adapter = cec_adapter.LibCecAdapter(device_name="Devialet")
    with pytest.raises(RuntimeError, match="No CEC adapter detected"):
        next(adapter.events())


def test_libcec_adapter_send_tx_returns_false_when_not_connected(monkeypatch) -> None:
    class FakeCecModule:
        CEC_DEVICE_TYPE_AUDIO_SYSTEM = 5
        LIBCEC_VERSION_CURRENT = 1

        @staticmethod
        def libcec_configuration():
            class FakeCfg:
                def __init__(self):
                    self.deviceTypes = self

                def Add(self, _value):
                    return None

                def SetLogCallback(self, _cb):
                    return None

                def SetKeyPressCallback(self, _cb):
                    return None

                def SetCommandCallback(self, _cb):
                    return None

            return FakeCfg()

    monkeypatch.setitem(sys.modules, "cec", FakeCecModule())
    adapter = cec_adapter.LibCecAdapter(device_name="Devialet")
    assert adapter.send_tx("50:7A:22") is False
