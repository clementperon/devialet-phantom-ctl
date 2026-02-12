import pytest

from devialetctl.infrastructure import cec_adapter


def test_cec_events_raises_when_stdout_missing(monkeypatch) -> None:
    class FakeProc:
        stdout = None

        def poll(self):
            return None

        def terminate(self):
            return None

    monkeypatch.setattr(cec_adapter.subprocess, "Popen", lambda *args, **kwargs: FakeProc())
    adapter = cec_adapter.CecClientAdapter(command="cec-client -d 8")
    with pytest.raises(RuntimeError, match="stdout"):
        next(adapter.events())
