import contextlib

from devialetctl.infrastructure import keyboard_adapter


def test_keyboard_events_line_mode(monkeypatch) -> None:
    class FakeStdin:
        def isatty(self):
            return False

    values = iter(["", "u", "play", "q"])
    monkeypatch.setattr(keyboard_adapter.sys, "stdin", FakeStdin())
    monkeypatch.setattr("builtins.input", lambda: next(values))
    adapter = keyboard_adapter.KeyboardAdapter()
    events = list(adapter.events())
    assert len(events) == 1
    assert events[0].key == "u"


def test_keyboard_events_single_key_mode(monkeypatch) -> None:
    class FakeStdin:
        def __init__(self):
            self.keys = iter([" ", "u", "x", "q"])

        def isatty(self):
            return True

        def read(self, _n):
            return next(self.keys)

    monkeypatch.setattr(keyboard_adapter.sys, "stdin", FakeStdin())
    monkeypatch.setattr(keyboard_adapter, "_stdin_cbreak", contextlib.nullcontext)
    adapter = keyboard_adapter.KeyboardAdapter()
    events = list(adapter.events())
    assert len(events) == 1
    assert events[0].key == "u"


def test_stdin_cbreak_context_calls_termios_and_tty(monkeypatch) -> None:
    called = {"tcgetattr": 0, "setcbreak": 0, "tcsetattr": 0}

    class FakeStdin:
        def fileno(self):
            return 7

    monkeypatch.setattr(keyboard_adapter.sys, "stdin", FakeStdin())
    monkeypatch.setattr(
        keyboard_adapter.termios,
        "tcgetattr",
        lambda fd: called.__setitem__("tcgetattr", fd) or ["old"],
    )
    monkeypatch.setattr(
        keyboard_adapter.tty, "setcbreak", lambda fd: called.__setitem__("setcbreak", fd)
    )
    monkeypatch.setattr(
        keyboard_adapter.termios,
        "tcsetattr",
        lambda fd, when, old: called.__setitem__("tcsetattr", (fd, when, old)),
    )

    with keyboard_adapter._stdin_cbreak():
        pass

    assert called["tcgetattr"] == 7
    assert called["setcbreak"] == 7
    assert called["tcsetattr"][0] == 7
