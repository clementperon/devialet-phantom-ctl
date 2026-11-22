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


def test_format_phys_addr() -> None:
    assert cec_adapter.format_phys_addr(0x3000) == "3.0.0.0"
    assert cec_adapter.format_phys_addr(0x12AB) == "1.2.a.b"
    assert cec_adapter.format_phys_addr(cec_adapter.CEC_PHYS_ADDR_INVALID) == "f.f.f.f (none)"


def test_kernel_config_without_physical_address_logs_error_and_continues(
    monkeypatch, caplog
) -> None:
    calls: list[int] = []

    def fake_ioctl(fd, request, arg=0, mutate_flag=True):
        calls.append(request)
        if request == cec_adapter.CEC_ADAP_G_PHYS_ADDR:
            arg.value = cec_adapter.CEC_PHYS_ADDR_INVALID
        if request == cec_adapter.CEC_ADAP_G_LOG_ADDRS:
            arg.log_addr_mask = 0
        return 0

    monkeypatch.setattr(cec_adapter.fcntl, "ioctl", fake_ioctl)
    adapter = cec_adapter.CecKernelAdapter(device="/dev/cec1")
    with caplog.at_level("ERROR"):
        adapter._configure(7)
    assert "/dev/cec1 has no HDMI physical address" in caplog.text
    # The kernel claims the logical address by itself once the address appears.
    assert cec_adapter.CEC_ADAP_S_LOG_ADDRS in calls
    assert adapter._has_phys_addr() is False


def test_kernel_poll_phys_addr_tracks_hotplug_and_reannounces_vendor(monkeypatch, caplog) -> None:
    values = iter([0x3000, cec_adapter.CEC_PHYS_ADDR_INVALID, 0x3000])
    sent: list[str] = []

    def fake_ioctl(fd, request, arg=0, mutate_flag=True):
        if request == cec_adapter.CEC_ADAP_G_PHYS_ADDR:
            arg.value = next(values)
        return 0

    monkeypatch.setattr(cec_adapter.fcntl, "ioctl", fake_ioctl)
    adapter = cec_adapter.CecKernelAdapter(
        device="/dev/cec0",
        announce_vendor_id=True,
        spoof_vendor_id=True,
        _phys_addr_poll_interval_s=0.0,
    )
    adapter._phys_addr = cec_adapter.CEC_PHYS_ADDR_INVALID
    monkeypatch.setattr(adapter, "send_tx", lambda frame: sent.append(frame) or True)

    with caplog.at_level("INFO"):
        adapter._poll_phys_addr(7)  # appears -> announce vendor id
        adapter._poll_phys_addr(7)  # lost
        adapter._poll_phys_addr(7)  # back -> announce again

    assert sent == ["5F:87:00:00:F0", "5F:87:00:00:F0"]
    assert "HDMI physical address is now 3.0.0.0" in caplog.text
    assert "lost its HDMI physical address" in caplog.text


def test_kernel_poll_phys_addr_is_rate_limited(monkeypatch) -> None:
    reads: list[int] = []

    def fake_ioctl(fd, request, arg=0, mutate_flag=True):
        if request == cec_adapter.CEC_ADAP_G_PHYS_ADDR:
            reads.append(request)
            arg.value = 0x1000
        return 0

    monkeypatch.setattr(cec_adapter.fcntl, "ioctl", fake_ioctl)
    adapter = cec_adapter.CecKernelAdapter(_phys_addr_poll_interval_s=60.0)
    adapter._phys_addr = 0x1000
    adapter._phys_addr_checked_at = cec_adapter.time.monotonic()
    adapter._poll_phys_addr(7)
    assert reads == []


def test_kernel_poll_phys_addr_ignores_read_errors(monkeypatch) -> None:
    def fake_ioctl(fd, request, arg=0, mutate_flag=True):
        raise OSError(errno.EIO, "io error")

    monkeypatch.setattr(cec_adapter.fcntl, "ioctl", fake_ioctl)
    adapter = cec_adapter.CecKernelAdapter(_phys_addr_poll_interval_s=0.0)
    adapter._phys_addr = 0x1000
    adapter._poll_phys_addr(7)
    assert adapter._phys_addr == 0x1000
