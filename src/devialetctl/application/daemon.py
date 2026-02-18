import asyncio
import logging
import time
from typing import Callable

from devialetctl.application.router import EventRouter
from devialetctl.application.service import VolumeService
from devialetctl.domain.events import InputEvent, InputEventType
from devialetctl.domain.policy import EventPolicy
from devialetctl.infrastructure.cec_adapter import CecKernelAdapter
from devialetctl.infrastructure.config import DaemonConfig
from devialetctl.infrastructure.devialet_gateway import DevialetHttpGateway
from devialetctl.infrastructure.keyboard_adapter import KeyboardAdapter

LOG = logging.getLogger(__name__)
_SAMSUNG_VENDOR_92_SUPPORTED_MODES = {0x01, 0x03, 0x04, 0x05, 0x06}
_VENDOR_COMPAT_VENDOR_ID: dict[str, int] = {
    "samsung": 0x0000F0,
}


def _fixed_frame(frame: str) -> Callable[["DaemonRunner"], str]:
    return lambda _runner: frame


_CEC_SYSTEM_RESPONSE_MAP: dict[InputEventType, Callable[["DaemonRunner"], str]] = {
    InputEventType.SYSTEM_AUDIO_MODE_REQUEST: _fixed_frame("50:72:01"),
    InputEventType.GIVE_SYSTEM_AUDIO_MODE_STATUS: _fixed_frame("50:7E:01"),
    InputEventType.REQUEST_ARC_INITIATION: _fixed_frame("50:C0"),
    InputEventType.REQUEST_ARC_TERMINATION: _fixed_frame("50:C5"),
    # REPORT_SHORT_AUDIO_DESCRIPTOR with one valid LPCM SAD:
    # format=LPCM (1), channels=2, rates=32/44.1/48kHz, sizes=16/20/24bit
    InputEventType.REQUEST_SHORT_AUDIO_DESCRIPTOR: _fixed_frame("50:A3:09:07:07"),
    InputEventType.GIVE_DEVICE_VENDOR_ID: lambda runner: runner._vendor_announce_frame(),
    InputEventType.GIVE_OSD_NAME: lambda runner: runner._osd_name_frame(),
}


class DaemonRunner:
    def __init__(self, cfg: DaemonConfig, gateway: DevialetHttpGateway) -> None:
        self.cfg = cfg
        self.gateway = gateway
        self._external_watch_interval_s = 0.5
        self._external_watch_suspend_s = 0.8
        self._external_watch_suspend_until = 0.0
        self._io_lock: asyncio.Lock | None = None
        self._cached_volume: int | None = None
        self._cached_muted: bool | None = None
        self._vendor_state_byte: int = 0x14
        self.router = EventRouter(
            service=VolumeService(gateway),
            policy=EventPolicy(
                dedupe_window_s=cfg.dedupe_window_s,
                min_interval_s=cfg.min_interval_s,
            ),
        )

    def run_forever(self, input_name: str = "cec") -> None:
        if input_name == "keyboard":
            self._run_keyboard()
            return
        self._run_cec_with_backoff()

    def run_cec_forever(self) -> None:
        self._run_cec_with_backoff()

    def _run_keyboard(self) -> None:
        LOG.info("target gateway: %s", getattr(self.gateway, "base_url", "<unknown>"))
        LOG.info("keyboard input started (u/+ up, d/- down, m mute, q quit; no Enter needed)")
        adapter = KeyboardAdapter()
        for event in adapter.events():
            handled = self.router.handle(event)
            if handled:
                LOG.debug("handled keyboard event=%s key=%s", event.kind.value, event.key)

    def _run_cec_with_backoff(self) -> None:
        backoff_s = self.cfg.reconnect_delay_s
        max_backoff_s = max(self.cfg.reconnect_delay_s, 20.0)
        while True:
            try:
                adapter = CecKernelAdapter(
                    device=self.cfg.cec_device,
                    osd_name=self.cfg.cec_osd_name,
                    vendor_id=self._vendor_id_for_profile(),
                    announce_vendor_id=self._should_spoof_vendor_id(),
                    spoof_vendor_id=self._should_spoof_vendor_id(),
                )
                asyncio.run(self._run_cec_async(adapter))
                backoff_s = self.cfg.reconnect_delay_s
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                LOG.exception("daemon cycle failed, retrying: %s", exc)
                time.sleep(backoff_s)
                backoff_s = min(max_backoff_s, backoff_s * 2.0)

    async def _run_cec_async(self, adapter: CecKernelAdapter) -> None:
        self._io_lock = asyncio.Lock()
        stop_event = asyncio.Event()
        watcher = asyncio.create_task(self._watch_external_audio_state_async(adapter, stop_event))
        try:
            async for event in adapter.async_events():
                await self._handle_cec_event_async(adapter, event)
        finally:
            stop_event.set()
            await watcher
            self._io_lock = None

    async def _handle_cec_event_async(self, adapter: CecKernelAdapter, event: InputEvent) -> None:
        # Pause external Devialet polling while we process inbound CEC commands,
        # so watcher reads don't race with in-flight push/update handling.
        self._suspend_external_watch_for_push()
        async with self._require_io_lock():
            if self._handle_cec_system_request(adapter, event.kind):
                return
            if event.kind == InputEventType.SAMSUNG_VENDOR_COMMAND:
                if self._is_samsung_vendor_compat_enabled():
                    await self._handle_samsung_vendor_command_async(adapter, event)
                else:
                    LOG.debug("ignored Samsung vendor command (compat disabled)")
                return
            if event.kind == InputEventType.SAMSUNG_VENDOR_COMMAND_WITH_ID:
                if self._is_samsung_vendor_compat_enabled():
                    self._handle_samsung_vendor_command_with_id(event)
                else:
                    LOG.debug("ignored Samsung vendor command-with-id (compat disabled)")
                return
            if event.kind == InputEventType.SET_AUDIO_VOLUME_LEVEL:
                await self._handle_set_audio_volume_level_async(adapter, event)
                return
            if event.kind == InputEventType.GIVE_AUDIO_STATUS:
                await self._report_audio_status_async(adapter)
                return
            if not self.router.policy.should_emit(event):
                return
            if event.kind == InputEventType.VOLUME_UP:
                await self._relative_step_async(delta=1, fallback=self.gateway.volume_up_async)
                self._update_cache_after_relative_event(event.kind)
                LOG.debug("handled event=%s key=%s", event.kind.value, event.key)
                await self._report_audio_status_async(adapter)
                return
            if event.kind == InputEventType.VOLUME_DOWN:
                await self._relative_step_async(delta=-1, fallback=self.gateway.volume_down_async)
                self._update_cache_after_relative_event(event.kind)
                LOG.debug("handled event=%s key=%s", event.kind.value, event.key)
                await self._report_audio_status_async(adapter)
                return
            if event.kind == InputEventType.MUTE:
                await self.gateway.mute_toggle_async()
                self._update_cache_after_relative_event(event.kind)
                LOG.debug("handled event=%s key=%s", event.kind.value, event.key)
                await self._report_audio_status_async(adapter)
                return

    def _handle_cec_system_request(self, adapter: CecKernelAdapter, kind: InputEventType) -> bool:
        frame_builder = _CEC_SYSTEM_RESPONSE_MAP.get(kind)
        if frame_builder is None:
            return False
        frame = frame_builder(self)
        sent = self._send_tx(adapter, frame)
        if sent:
            LOG.debug("sent CEC system response frame: %s", frame)
        else:
            LOG.debug("cannot send CEC system response frame: %s", frame)
        return True

    async def _report_audio_status_async(self, adapter: CecKernelAdapter) -> None:
        try:
            volume, muted = await self._get_audio_state_async()
            sent = self._report_audio_status_for_state(adapter, volume, muted)
            if sent:
                LOG.debug(
                    "sent CEC audio status frame for cached state volume=%d muted=%s",
                    volume,
                    muted,
                )
            else:
                LOG.debug("cannot send CEC audio status; adapter not writable")
        except Exception as exc:
            LOG.debug("failed to report CEC audio status: %s", exc)

    async def _handle_set_audio_volume_level_async(
        self,
        adapter: CecKernelAdapter,
        event: InputEvent,
    ) -> None:
        try:
            target_volume = event.value
            if target_volume is None:
                return
            target_volume = max(0, min(100, int(target_volume)))
            await self.gateway.set_volume_async(target_volume)
            self._cached_volume = target_volume
            self._sync_vendor_state_from_volume(target_volume)

            if event.muted is not None:
                current_muted = (
                    self._cached_muted
                    if self._cached_muted is not None
                    else await self.gateway.get_mute_state_async()
                )
                if bool(event.muted) != current_muted:
                    await self.gateway.mute_toggle_async()
                self._cached_muted = bool(event.muted)

            LOG.debug(
                "handled CEC set_audio_volume_level volume=%s muted=%s",
                event.value,
                event.muted,
            )
            await self._report_audio_status_async(adapter)
        except Exception as exc:
            LOG.debug("failed to handle CEC set_audio_volume_level: %s", exc)

    async def _handle_samsung_vendor_command_async(
        self,
        adapter: CecKernelAdapter,
        event: InputEvent,
    ) -> None:
        subcommand = event.vendor_subcommand
        payload = event.vendor_payload or ()
        if subcommand is None:
            return

        if subcommand == 0x95:
            if self._cached_volume is not None:
                self._sync_vendor_state_from_volume(self._cached_volume)
            state = self._vendor_state_byte
            frame = f"50:89:95:01:{state:02X}"
            sent = self._send_tx(adapter, frame)
            if sent:
                LOG.debug("sent Samsung vendor sync response frame: %s", frame)
            else:
                LOG.debug("cannot send Samsung vendor sync response frame: %s", frame)
            return

        if subcommand == 0x92:
            mode = event.vendor_mode
            if mode in _SAMSUNG_VENDOR_92_SUPPORTED_MODES:
                LOG.debug("handled Samsung vendor 0x92 mode=0x%02X payload=%s", mode, payload)
            else:
                LOG.debug("ignored Samsung vendor 0x92 unsupported mode payload=%s", payload)
            return

        if subcommand in {0x88, 0x96}:
            LOG.debug("handled Samsung vendor subcommand=0x%02X payload=%s", subcommand, payload)
            if subcommand == 0x96 and len(payload) >= 2:
                candidate = payload[-1]
                if 0 <= candidate <= 100:
                    current = self._cached_volume
                    if current != candidate:
                        await self.gateway.set_volume_async(candidate)
                    self._vendor_state_byte = candidate
                    self._cached_volume = candidate
            return

        LOG.debug("ignored Samsung vendor subcommand=0x%02X payload=%s", subcommand, payload)

    def _handle_samsung_vendor_command_with_id(self, event: InputEvent) -> None:
        # Minimal emulation policy from reverse engineering notes:
        # unknown A0 payloads are ignored (no explicit response).
        LOG.debug("ignored Samsung vendor command-with-id payload=%s", event.vendor_payload)

    async def _get_audio_state_async(self) -> tuple[int, bool]:
        cached_volume = self._cached_volume
        cached_muted = self._cached_muted
        if cached_volume is None:
            cached_volume = max(0, min(100, int(await self.gateway.get_volume_async())))
            self._cached_volume = cached_volume
            self._sync_vendor_state_from_volume(cached_volume)
        if cached_muted is None:
            cached_muted = await self.gateway.get_mute_state_async()
            self._cached_muted = cached_muted
        return cached_volume, cached_muted

    def _update_cache_after_relative_event(self, kind: InputEventType) -> None:
        if kind == InputEventType.VOLUME_UP and self._cached_volume is not None:
            self._cached_volume = min(100, self._cached_volume + 1)
            self._sync_vendor_state_from_volume(self._cached_volume)
            return
        if kind == InputEventType.VOLUME_DOWN and self._cached_volume is not None:
            self._cached_volume = max(0, self._cached_volume - 1)
            self._sync_vendor_state_from_volume(self._cached_volume)
            return
        if kind == InputEventType.MUTE and self._cached_muted is not None:
            self._cached_muted = not self._cached_muted

    def _sync_vendor_state_from_volume(self, volume: int) -> None:
        self._vendor_state_byte = max(0, min(100, int(volume)))

    def _send_tx(self, adapter: CecKernelAdapter, frame: str) -> bool:
        if not hasattr(adapter, "send_tx"):
            return False
        return bool(adapter.send_tx(frame))

    def _report_audio_status_for_state(
        self,
        adapter: CecKernelAdapter,
        volume: int,
        muted: bool,
    ) -> bool:
        status = (0x80 if muted else 0x00) | (volume & 0x7F)
        frame = f"50:7A:{status:02X}"
        return self._send_tx(adapter, frame)

    async def _watch_external_audio_state_async(
        self,
        adapter: CecKernelAdapter,
        stop_event: asyncio.Event,
    ) -> None:
        while not stop_event.is_set():
            changed, volume, muted = await self._poll_external_audio_state_once_async()
            if changed:
                sent = self._report_audio_status_for_state(adapter, volume, muted)
                if sent:
                    LOG.debug(
                        "external audio-state changed; notified TV volume=%d muted=%s",
                        volume,
                        muted,
                    )
            await asyncio.sleep(self._external_watch_interval_s)

    async def _poll_external_audio_state_once_async(self) -> tuple[bool, int, bool]:
        async with self._require_io_lock():
            if self._is_external_watch_suspended():
                return False, 0, False
            try:
                volume = max(0, min(100, int(await self.gateway.get_volume_async())))
                muted = await self.gateway.get_mute_state_async()
            except Exception as exc:
                LOG.debug("external audio-state polling failed: %s", exc)
                return False, 0, False

            if self._cached_volume is None or self._cached_muted is None:
                self._cached_volume = volume
                self._cached_muted = muted
                self._sync_vendor_state_from_volume(volume)
                return False, volume, muted

            changed = volume != self._cached_volume or muted != self._cached_muted
            if changed:
                self._cached_volume = volume
                self._cached_muted = muted
                self._sync_vendor_state_from_volume(volume)
            return changed, volume, muted

    def _suspend_external_watch_for_push(self) -> None:
        self._external_watch_suspend_until = time.monotonic() + self._external_watch_suspend_s

    def _is_external_watch_suspended(self) -> bool:
        return time.monotonic() < self._external_watch_suspend_until

    def _require_io_lock(self) -> asyncio.Lock:
        if self._io_lock is None:
            raise RuntimeError("I/O lock is not initialized")
        return self._io_lock

    def _is_samsung_vendor_compat_enabled(self) -> bool:
        return self.cfg.cec_vendor_compat == "samsung"

    def _should_spoof_vendor_id(self) -> bool:
        # For now only Samsung vendor profile needs vendor-id spoofing.
        return self._is_samsung_vendor_compat_enabled()

    def _vendor_id_for_profile(self) -> int:
        return _VENDOR_COMPAT_VENDOR_ID.get(self.cfg.cec_vendor_compat, 0)

    def _vendor_announce_frame(self) -> str:
        vid = int(self._vendor_id_for_profile()) & 0xFFFFFF
        return f"50:87:{(vid >> 16) & 0xFF:02X}:{(vid >> 8) & 0xFF:02X}:{vid & 0xFF:02X}"

    def _osd_name_frame(self) -> str:
        encoded = self.cfg.cec_osd_name.encode("ascii", errors="ignore")[:14]
        if not encoded:
            encoded = b"Audio"
        payload = ":".join(f"{byte:02X}" for byte in encoded)
        return f"50:47:{payload}"

    async def _relative_step_async(self, delta: int, fallback) -> None:
        try:
            current = int(await self.gateway.get_volume_async())
            target = max(0, min(100, current + delta))
            if target != current:
                await self.gateway.set_volume_async(target)
        except Exception:
            await fallback()
