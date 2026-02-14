import logging
import time

from devialetctl.application.router import EventRouter
from devialetctl.application.service import VolumeService
from devialetctl.domain.events import InputEvent, InputEventType
from devialetctl.domain.policy import EventPolicy
from devialetctl.infrastructure.cec_adapter import CecClientAdapter
from devialetctl.infrastructure.config import DaemonConfig
from devialetctl.infrastructure.devialet_gateway import DevialetHttpGateway
from devialetctl.infrastructure.keyboard_adapter import KeyboardAdapter

LOG = logging.getLogger(__name__)
_CEC_SYSTEM_RESPONSE_MAP: dict[InputEventType, str] = {
    InputEventType.SYSTEM_AUDIO_MODE_REQUEST: "50:72:01",
    InputEventType.GIVE_SYSTEM_AUDIO_MODE_STATUS: "50:7E:01",
    InputEventType.REQUEST_ARC_INITIATION: "50:C1",
    InputEventType.REQUEST_ARC_TERMINATION: "50:C2",
}


class DaemonRunner:
    def __init__(self, cfg: DaemonConfig, gateway: DevialetHttpGateway) -> None:
        self.cfg = cfg
        self.gateway = gateway
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
                adapter = CecClientAdapter(command=self.cfg.cec_command)
                for event in adapter.events():
                    if self._handle_cec_system_request(adapter, event.kind):
                        continue
                    if event.kind == InputEventType.SET_AUDIO_VOLUME_LEVEL:
                        self._handle_set_audio_volume_level(adapter, event)
                        continue
                    if event.kind == InputEventType.GIVE_AUDIO_STATUS:
                        self._report_audio_status(adapter)
                        continue
                    handled = self.router.handle(event)
                    if handled:
                        LOG.debug("handled event=%s key=%s", event.kind.value, event.key)
                        self._report_audio_status(adapter)
                backoff_s = self.cfg.reconnect_delay_s
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                LOG.exception("daemon cycle failed, retrying: %s", exc)
                time.sleep(backoff_s)
                backoff_s = min(max_backoff_s, backoff_s * 2.0)

    def _handle_cec_system_request(self, adapter: CecClientAdapter, kind: InputEventType) -> bool:
        frame = _CEC_SYSTEM_RESPONSE_MAP.get(kind)
        if frame is None:
            return False
        if not hasattr(adapter, "send_tx"):
            return True
        sent = adapter.send_tx(frame)
        if sent:
            LOG.debug("sent CEC system/ARC response frame: %s", frame)
        else:
            LOG.debug("cannot send CEC system/ARC response frame: %s", frame)
        return True

    def _report_audio_status(self, adapter: CecClientAdapter) -> None:
        if not hasattr(adapter, "send_tx"):
            return
        try:
            volume = max(0, min(100, int(self.gateway.get_volume())))
            muted = bool(getattr(self.gateway, "get_mute_state", lambda: False)())
            status = (0x80 if muted else 0x00) | (volume & 0x7F)
            frames = [f"50:7A:{status:02X}", f"50:73:{status:02X}"]
            for frame in frames:
                sent = adapter.send_tx(frame)
                if sent:
                    LOG.debug("sent CEC audio status frame: %s", frame)
                else:
                    LOG.debug("cannot send CEC audio status; adapter not writable")
        except Exception as exc:
            LOG.debug("failed to report CEC audio status: %s", exc)

    def _handle_set_audio_volume_level(self, adapter: CecClientAdapter, event: InputEvent) -> None:
        try:
            target_volume = event.value
            if target_volume is None:
                return
            self.gateway.set_volume(max(0, min(100, int(target_volume))))

            if event.muted is not None and hasattr(self.gateway, "get_mute_state"):
                current_muted = bool(self.gateway.get_mute_state())
                if bool(event.muted) != current_muted:
                    self.gateway.mute_toggle()

            LOG.debug(
                "handled CEC set_audio_volume_level volume=%s muted=%s",
                event.value,
                event.muted,
            )
            self._report_audio_status(adapter)
        except Exception as exc:
            LOG.debug("failed to handle CEC set_audio_volume_level: %s", exc)
