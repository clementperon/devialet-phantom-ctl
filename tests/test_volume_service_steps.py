from devialetctl.application.service import VolumeService


def test_volume_up_uses_plus_one_with_set_volume() -> None:
    class FakeGateway:
        def __init__(self):
            self.current = 50
            self.calls = []

        async def systems_async(self):
            return {}

        async def get_volume_async(self):
            self.calls.append("get")
            return self.current

        async def set_volume_async(self, value):
            self.calls.append(("set", value))
            self.current = value

        async def volume_up_async(self):
            self.calls.append("native_up")

        async def volume_down_async(self):
            self.calls.append("native_down")

        async def mute_toggle_async(self):
            self.calls.append("mute")

    gw = FakeGateway()
    svc = VolumeService(gw)
    svc.volume_up()
    assert gw.calls == ["get", ("set", 51)]


def test_volume_down_uses_minus_one_with_set_volume() -> None:
    class FakeGateway:
        def __init__(self):
            self.current = 30
            self.calls = []

        async def systems_async(self):
            return {}

        async def get_volume_async(self):
            self.calls.append("get")
            return self.current

        async def set_volume_async(self, value):
            self.calls.append(("set", value))
            self.current = value

        async def volume_up_async(self):
            self.calls.append("native_up")

        async def volume_down_async(self):
            self.calls.append("native_down")

        async def mute_toggle_async(self):
            self.calls.append("mute")

    gw = FakeGateway()
    svc = VolumeService(gw)
    svc.volume_down()
    assert gw.calls == ["get", ("set", 29)]


def test_volume_service_falls_back_to_native_when_get_fails() -> None:
    class FakeGateway:
        async def systems_async(self):
            return {}

        async def get_volume_async(self):
            raise RuntimeError("no volume")

        async def set_volume_async(self, value):
            raise AssertionError("should not call set_volume")

        async def volume_up_async(self):
            self.used_native_up = True

        async def volume_down_async(self):
            self.used_native_down = True

        async def mute_toggle_async(self):
            return None

    gw = FakeGateway()
    gw.used_native_up = False
    gw.used_native_down = False
    svc = VolumeService(gw)
    svc.volume_up()
    svc.volume_down()
    assert gw.used_native_up is True
    assert gw.used_native_down is True
