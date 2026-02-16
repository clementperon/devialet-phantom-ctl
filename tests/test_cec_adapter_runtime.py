import asyncio
import errno

import pytest

from devialetctl.infrastructure import cec_adapter


def test_kernel_events_raises_when_open_fails(monkeypatch) -> None:
    def fake_open(*args, **kwargs):
        raise OSError("open failed")

    monkeypatch.setattr(cec_adapter.os, "open", fake_open)
    adapter = cec_adapter.CecKernelAdapter(device="/dev/cec0")
    with pytest.raises(OSError, match="open failed"):
        asyncio.run(anext(adapter.async_events()))


def test_kernel_send_tx_returns_false_when_not_open() -> None:
    adapter = cec_adapter.CecKernelAdapter(device="/dev/cec0")
    assert adapter.send_tx("50:7A:10") is False


def test_kernel_send_tx_calls_transmit_ioctl(monkeypatch) -> None:
    calls: list[int] = []

    def fake_ioctl(fd, request, arg=0, mutate_flag=True):
        calls.append(request)
        return 0

    adapter = cec_adapter.CecKernelAdapter(device="/dev/cec0")
    adapter._fd = 7
    monkeypatch.setattr(cec_adapter.fcntl, "ioctl", fake_ioctl)
    assert adapter.send_tx("50:7A:1E") is True
    assert calls == [cec_adapter.CEC_TRANSMIT]


def test_kernel_config_skips_claim_when_audio_system_already_present(monkeypatch) -> None:
    calls: list[int] = []

    def fake_ioctl(fd, request, arg=0, mutate_flag=True):
        calls.append(request)
        if request == cec_adapter.CEC_ADAP_G_LOG_ADDRS:
            arg.log_addr_mask = cec_adapter.CEC_LOG_ADDR_MASK_AUDIOSYSTEM
        return 0

    monkeypatch.setattr(cec_adapter.fcntl, "ioctl", fake_ioctl)
    adapter = cec_adapter.CecKernelAdapter()
    adapter._configure(7)
    assert cec_adapter.CEC_ADAP_S_LOG_ADDRS not in calls


def test_kernel_config_retries_on_busy_then_succeeds(monkeypatch) -> None:
    attempts = {"set": 0}

    def fake_ioctl(fd, request, arg=0, mutate_flag=True):
        if request == cec_adapter.CEC_ADAP_G_LOG_ADDRS:
            arg.log_addr_mask = 0
            return 0
        if request == cec_adapter.CEC_ADAP_S_LOG_ADDRS:
            attempts["set"] += 1
            if attempts["set"] == 1:
                raise OSError(errno.EBUSY, "busy")
            return 0
        return 0

    monkeypatch.setattr(cec_adapter.fcntl, "ioctl", fake_ioctl)
    monkeypatch.setattr(cec_adapter.time, "sleep", lambda _s: None)
    adapter = cec_adapter.CecKernelAdapter(_log_addrs_busy_retries=(0.01,))
    adapter._configure(7)
    assert attempts["set"] == 2
