from devialetctl.domain.events import InputEventType
from devialetctl.infrastructure.keyboard_adapter import parse_keyboard_command


def test_parse_keyboard_up_aliases() -> None:
    ev1 = parse_keyboard_command("u")
    ev2 = parse_keyboard_command("+")
    ev3 = parse_keyboard_command("up")
    assert ev1 is not None and ev1.kind == InputEventType.VOLUME_UP
    assert ev2 is not None and ev2.kind == InputEventType.VOLUME_UP
    assert ev3 is not None and ev3.kind == InputEventType.VOLUME_UP


def test_parse_keyboard_down_aliases() -> None:
    ev1 = parse_keyboard_command("d")
    ev2 = parse_keyboard_command("-")
    ev3 = parse_keyboard_command("down")
    assert ev1 is not None and ev1.kind == InputEventType.VOLUME_DOWN
    assert ev2 is not None and ev2.kind == InputEventType.VOLUME_DOWN
    assert ev3 is not None and ev3.kind == InputEventType.VOLUME_DOWN


def test_parse_keyboard_mute_and_unknown() -> None:
    ev1 = parse_keyboard_command("m")
    ev2 = parse_keyboard_command("mute")
    assert ev1 is not None and ev1.kind == InputEventType.MUTE
    assert ev2 is not None and ev2.kind == InputEventType.MUTE
    assert parse_keyboard_command("play") is None
