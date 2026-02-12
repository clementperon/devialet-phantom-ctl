from devialetctl.application.service import VolumeService


def test_volume_up_uses_plus_one_with_set_volume() -> None:
    class FakeGateway:
        def __init__(self):
            self.current = 50
            self.calls = []

        def systems(self):
            return {}

        def get_volume(self):
            self.calls.append("get")
            return self.current

        def set_volume(self, value):
            self.calls.append(("set", value))
            self.current = value

        def volume_up(self):
            self.calls.append("native_up")

        def volume_down(self):
            self.calls.append("native_down")

        def mute_toggle(self):
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

        def systems(self):
            return {}

        def get_volume(self):
            self.calls.append("get")
            return self.current

        def set_volume(self, value):
            self.calls.append(("set", value))
            self.current = value

        def volume_up(self):
            self.calls.append("native_up")

        def volume_down(self):
            self.calls.append("native_down")

        def mute_toggle(self):
            self.calls.append("mute")

    gw = FakeGateway()
    svc = VolumeService(gw)
    svc.volume_down()
    assert gw.calls == ["get", ("set", 29)]


def test_volume_service_falls_back_to_native_when_get_fails() -> None:
    class FakeGateway:
        def systems(self):
            return {}

        def get_volume(self):
            raise RuntimeError("no volume")

        def set_volume(self, value):
            raise AssertionError("should not call set_volume")

        def volume_up(self):
            self.used_native_up = True

        def volume_down(self):
            self.used_native_down = True

        def mute_toggle(self):
            return None

    gw = FakeGateway()
    gw.used_native_up = False
    gw.used_native_down = False
    svc = VolumeService(gw)
    svc.volume_up()
    svc.volume_down()
    assert gw.used_native_up is True
    assert gw.used_native_down is True
