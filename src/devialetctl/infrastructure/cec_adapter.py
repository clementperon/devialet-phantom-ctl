import asyncio
import ctypes
import errno
import fcntl
import logging
import os
import time
from dataclasses import dataclass
from typing import AsyncIterator

from devialetctl.domain.events import InputEvent, InputEventType

LOG = logging.getLogger(__name__)

# Linux CEC UAPI constants (include/uapi/linux/cec.h)
CEC_MAX_MSG_SIZE = 16
CEC_MAX_LOG_ADDRS = 4
CEC_LOG_ADDR_TYPE_AUDIOSYSTEM = 4
CEC_OP_CEC_VERSION_1_4 = 5
CEC_OP_PRIM_DEVTYPE_AUDIOSYSTEM = 5
CEC_OP_ALL_DEVTYPE_AUDIOSYSTEM = 0x08

CEC_MODE_INITIATOR = 0x1
CEC_MODE_FOLLOWER = 0x10
CEC_LOG_ADDR_MASK_AUDIOSYSTEM = 1 << 5
_LOGICAL_ADDRESS_NAMES: dict[int, str] = {
    0x0: "TV",
    0x1: "Recorder 1",
    0x2: "Recorder 2",
    0x3: "Tuner 1",
    0x4: "Playback 1",
    0x5: "Audio System",
    0x6: "Tuner 2",
    0x7: "Tuner 3",
    0x8: "Playback 2",
    0x9: "Recorder 3",
    0xA: "Tuner 4",
    0xB: "Playback 3",
    0xC: "Reserved 1",
    0xD: "Reserved 2",
    0xE: "Free Use",
    0xF: "Broadcast",
}

_CEC_OPCODE_NAMES: dict[str, str] = {
    "00": "FEATURE_ABORT",
    "36": "STANDBY",
    "44": "USER_CONTROL_PRESSED",
    "45": "USER_CONTROL_RELEASED",
    "46": "GIVE_OSD_NAME",
    "47": "SET_OSD_NAME",
    "70": "SYSTEM_AUDIO_MODE_REQUEST",
    "71": "GIVE_AUDIO_STATUS",
    "72": "SET_SYSTEM_AUDIO_MODE",
    "73": "SET_AUDIO_VOLUME_LEVEL",
    "7A": "REPORT_AUDIO_STATUS",
    "7D": "GIVE_SYSTEM_AUDIO_MODE_STATUS",
    "7E": "SYSTEM_AUDIO_MODE_STATUS",
    "80": "ROUTING_CHANGE",
    "86": "SET_STREAM_PATH",
    "84": "REPORT_PHYSICAL_ADDRESS",
    "87": "DEVICE_VENDOR_ID",
    "8C": "GIVE_DEVICE_VENDOR_ID",
    "8F": "GIVE_DEVICE_POWER_STATUS",
    "90": "REPORT_POWER_STATUS",
    "A3": "REPORT_SHORT_AUDIO_DESCRIPTOR",
    "A4": "REQUEST_SHORT_AUDIO_DESCRIPTOR",
    "C0": "INITIATE_ARC",
    "C1": "REPORT_ARC_INITIATED",
    "C2": "REPORT_ARC_TERMINATED",
    "C3": "REQUEST_ARC_INITIATION",
    "C4": "REQUEST_ARC_TERMINATION",
    "C5": "TERMINATE_ARC",
}

_SAMSUNG_VENDOR_SUBCOMMAND_NAMES: dict[int, str] = {
    0x88: "MODEL_NAME",
    0x92: "Q_SYMPHONY_MODE_CONFIG_UPDATE",
    0x95: "SYNC_TV_VOLUME_REQUEST",
    0x96: "SYNC_TV_VOLUME",
    0xA2: "VENDOR_0xA2",
}

_USER_CONTROL_KEYCODE_MAP: dict[str, tuple[InputEventType, str]] = {
    "41": (InputEventType.VOLUME_UP, "VOLUME_UP"),
    "42": (InputEventType.VOLUME_DOWN, "VOLUME_DOWN"),
    "43": (InputEventType.MUTE, "MUTE"),
}

_SYSTEM_REQUEST_OPCODE_MAP: dict[str, tuple[InputEventType, str]] = {
    "46": (InputEventType.GIVE_OSD_NAME, "GIVE_OSD_NAME"),
    "70": (InputEventType.SYSTEM_AUDIO_MODE_REQUEST, "SYSTEM_AUDIO_MODE_REQUEST"),
    "7D": (InputEventType.GIVE_SYSTEM_AUDIO_MODE_STATUS, "GIVE_SYSTEM_AUDIO_MODE_STATUS"),
    "C3": (InputEventType.REQUEST_ARC_INITIATION, "REQUEST_ARC_INITIATION"),
    "C4": (InputEventType.REQUEST_ARC_TERMINATION, "REQUEST_ARC_TERMINATION"),
    "A4": (
        InputEventType.REQUEST_SHORT_AUDIO_DESCRIPTOR,
        "REQUEST_SHORT_AUDIO_DESCRIPTOR",
    ),
    "8C": (InputEventType.GIVE_DEVICE_VENDOR_ID, "GIVE_DEVICE_VENDOR_ID"),
    "8F": (InputEventType.GIVE_DEVICE_POWER_STATUS, "GIVE_DEVICE_POWER_STATUS"),
}


class CecMsg(ctypes.Structure):
    _fields_ = [
        ("tx_ts", ctypes.c_uint64),
        ("rx_ts", ctypes.c_uint64),
        ("len", ctypes.c_uint32),
        ("timeout", ctypes.c_uint32),
        ("sequence", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("msg", ctypes.c_uint8 * CEC_MAX_MSG_SIZE),
        ("reply", ctypes.c_uint8),
        ("rx_status", ctypes.c_uint8),
        ("tx_status", ctypes.c_uint8),
        ("tx_arb_lost_cnt", ctypes.c_uint8),
        ("tx_nack_cnt", ctypes.c_uint8),
        ("tx_low_drive_cnt", ctypes.c_uint8),
        ("tx_error_cnt", ctypes.c_uint8),
    ]


class CecLogAddrs(ctypes.Structure):
    _fields_ = [
        ("log_addr", ctypes.c_uint8 * CEC_MAX_LOG_ADDRS),
        ("log_addr_mask", ctypes.c_uint16),
        ("cec_version", ctypes.c_uint8),
        ("num_log_addrs", ctypes.c_uint8),
        ("vendor_id", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("osd_name", ctypes.c_char * 15),
        ("primary_device_type", ctypes.c_uint8 * CEC_MAX_LOG_ADDRS),
        ("log_addr_type", ctypes.c_uint8 * CEC_MAX_LOG_ADDRS),
        ("all_device_types", ctypes.c_uint8 * CEC_MAX_LOG_ADDRS),
        ("features", (ctypes.c_uint8 * 12) * CEC_MAX_LOG_ADDRS),
    ]


def _IOC(direction: int, ioc_type: str, nr: int, size: int) -> int:
    return ((direction & 0x3) << 30) | ((size & 0x3FFF) << 16) | (ord(ioc_type) << 8) | nr


def _IOR(ioc_type: str, nr: int, struct_type: type[ctypes.Structure]) -> int:
    return _IOC(2, ioc_type, nr, ctypes.sizeof(struct_type))


def _IOW(ioc_type: str, nr: int, struct_type: type[ctypes.Structure]) -> int:
    return _IOC(1, ioc_type, nr, ctypes.sizeof(struct_type))


def _IOWR(ioc_type: str, nr: int, struct_type: type[ctypes.Structure]) -> int:
    return _IOC(3, ioc_type, nr, ctypes.sizeof(struct_type))


class U32(ctypes.Structure):
    _fields_ = [("value", ctypes.c_uint32)]


CEC_ADAP_S_LOG_ADDRS = _IOWR("a", 4, CecLogAddrs)
CEC_ADAP_G_LOG_ADDRS = _IOR("a", 3, CecLogAddrs)
CEC_TRANSMIT = _IOWR("a", 5, CecMsg)
CEC_RECEIVE = _IOWR("a", 6, CecMsg)
CEC_S_MODE = _IOW("a", 9, U32)


def _parse_frame_parts(frame: str) -> list[str]:
    return [p.upper() for p in frame.split(":") if p]


def parse_cec_frame(frame: str, source: str = "cec") -> InputEvent | None:
    parts = _parse_frame_parts(frame)
    if not parts:
        return None
    # CEC GIVE_AUDIO_STATUS frame: <srcdst>:71
    if len(parts) >= 2 and parts[1] == "71":
        return InputEvent(
            kind=InputEventType.GIVE_AUDIO_STATUS,
            source=source,
            key="GIVE_AUDIO_STATUS",
        )
    # CEC USER_CONTROL_PRESSED frame: <srcdst>:44:<keycode>
    if len(parts) >= 3 and parts[1] == "44":
        mapped = _USER_CONTROL_KEYCODE_MAP.get(parts[2])
        if mapped is not None:
            event, key = mapped
            return InputEvent(kind=event, source=source, key=key)
    # CEC USER_CONTROL_RELEASED frame: <srcdst>:45
    if len(parts) >= 2 and parts[1] == "45":
        return InputEvent(
            kind=InputEventType.USER_CONTROL_RELEASED,
            source=source,
            key="USER_CONTROL_RELEASED",
        )
    # CEC SET_AUDIO_VOLUME_LEVEL frame: <srcdst>:73:<status-byte>
    if len(parts) >= 3 and parts[1] == "73":
        status = int(parts[2], 16)
        return InputEvent(
            kind=InputEventType.SET_AUDIO_VOLUME_LEVEL,
            source=source,
            key="SET_AUDIO_VOLUME_LEVEL",
            value=status & 0x7F,
            muted=bool(status & 0x80),
        )
    # Samsung vendor command: <srcdst>:89:<subcommand>:...
    if len(parts) >= 3 and parts[1] == "89":
        payload = tuple(int(p, 16) for p in parts[2:])
        subcommand = payload[0]
        mode = payload[1] if subcommand == 0x92 and len(payload) >= 2 else None
        return InputEvent(
            kind=InputEventType.SAMSUNG_VENDOR_COMMAND,
            source=source,
            key="SAMSUNG_VENDOR_COMMAND",
            vendor_subcommand=subcommand,
            vendor_mode=mode,
            vendor_payload=payload,
        )
    # Samsung vendor command with ID: <srcdst>:A0:...
    if len(parts) >= 3 and parts[1] == "A0":
        payload = tuple(int(p, 16) for p in parts[2:])
        return InputEvent(
            kind=InputEventType.SAMSUNG_VENDOR_COMMAND_WITH_ID,
            source=source,
            key="SAMSUNG_VENDOR_COMMAND_WITH_ID",
            vendor_payload=payload,
        )
    # CEC system-audio / ARC requests.
    if len(parts) >= 2:
        mapped = _SYSTEM_REQUEST_OPCODE_MAP.get(parts[1])
        if mapped is not None:
            event, key = mapped
            return InputEvent(kind=event, source=source, key=key)
    return None


def format_cec_frame_human(frame: str) -> str:
    parts = [p.upper() for p in frame.split(":")]
    if len(parts) < 2 or len(parts[0]) != 2:
        return frame

    try:
        header = int(parts[0], 16)
    except ValueError:
        return frame

    initiator = (header >> 4) & 0x0F
    destination = header & 0x0F
    opcode = parts[1]
    initiator_name = _LOGICAL_ADDRESS_NAMES.get(initiator, f"LA{initiator:X}")
    destination_name = _LOGICAL_ADDRESS_NAMES.get(destination, f"LA{destination:X}")
    if opcode == "89":
        opcode_name = "SAMSUNG_VENDOR_COMMAND"
        if len(parts) > 2:
            try:
                subcommand = int(parts[2], 16)
            except ValueError:
                subcommand = None
            if subcommand is not None:
                sub_name = _SAMSUNG_VENDOR_SUBCOMMAND_NAMES.get(
                    subcommand,
                    f"VENDOR_SUBCOMMAND_0x{subcommand:02X}",
                )
                opcode_name = f"{opcode_name} ({sub_name})"
    else:
        opcode_name = _CEC_OPCODE_NAMES.get(opcode, f"OPCODE_0x{opcode}")
    payload = ""
    if len(parts) > 2:
        payload = f" payload={':'.join(parts[2:])}"
    return f"{initiator_name} -> {destination_name} : {opcode_name}{payload}"


@dataclass
class CecKernelAdapter:
    device: str = "/dev/cec0"
    osd_name: str = "Devialet"
    vendor_id: int = 0x0000F0
    announce_vendor_id: bool = False
    spoof_vendor_id: bool = False
    source: str = "cec"
    _fd: int | None = None
    _effective_vendor_id: int | None = None
    _log_addrs_busy_retries: tuple[float, ...] = (0.1, 0.25, 0.5)
    _async_poll_interval_s: float = 0.05

    def _vendor_broadcast_announce_frame(self) -> str:
        vid = int(self.vendor_id) & 0xFFFFFF
        return f"5F:87:{(vid >> 16) & 0xFF:02X}:{(vid >> 8) & 0xFF:02X}:{vid & 0xFF:02X}"

    @staticmethod
    def _has_audio_system_claim(addrs: CecLogAddrs) -> bool:
        return bool(addrs.log_addr_mask & CEC_LOG_ADDR_MASK_AUDIOSYSTEM)

    def _configure(self, fd: int) -> None:
        mode = U32(value=CEC_MODE_INITIATOR | CEC_MODE_FOLLOWER)
        fcntl.ioctl(fd, CEC_S_MODE, mode)

        current = CecLogAddrs()
        fcntl.ioctl(fd, CEC_ADAP_G_LOG_ADDRS, current)
        self._effective_vendor_id = int(current.vendor_id) & 0xFFFFFF
        if self._has_audio_system_claim(current):
            LOG.info(
                "kernel cec adapter already configured as Audio System "
                "(mask=0x%04X), skipping logical-address claim",
                int(current.log_addr_mask),
            )
            return

        addrs = CecLogAddrs()
        addrs.num_log_addrs = 1
        addrs.cec_version = CEC_OP_CEC_VERSION_1_4
        if self.spoof_vendor_id:
            addrs.vendor_id = int(self.vendor_id) & 0xFFFFFF
            self._effective_vendor_id = int(addrs.vendor_id) & 0xFFFFFF
        else:
            # Preserve current adapter vendor identity unless explicitly spoofing.
            addrs.vendor_id = int(current.vendor_id) & 0xFFFFFF
            self._effective_vendor_id = int(current.vendor_id) & 0xFFFFFF
        encoded_name = self.osd_name.encode("ascii", errors="ignore")[:14]
        addrs.osd_name = encoded_name
        addrs.primary_device_type[0] = CEC_OP_PRIM_DEVTYPE_AUDIOSYSTEM
        addrs.log_addr_type[0] = CEC_LOG_ADDR_TYPE_AUDIOSYSTEM
        addrs.all_device_types[0] = CEC_OP_ALL_DEVTYPE_AUDIOSYSTEM
        retry_delays = (0.0,) + self._log_addrs_busy_retries
        for idx, delay_s in enumerate(retry_delays):
            if delay_s > 0:
                time.sleep(delay_s)
            try:
                fcntl.ioctl(fd, CEC_ADAP_S_LOG_ADDRS, addrs)
                LOG.info("kernel cec adapter claimed logical address as Audio System")
                return
            except OSError as exc:
                if exc.errno != errno.EBUSY:
                    raise
                if idx >= len(retry_delays) - 1:
                    raise OSError(
                        errno.EBUSY,
                        "CEC logical address claim is busy; another CEC owner "
                        "or stale adapter state is active",
                    ) from exc
                LOG.warning(
                    "CEC logical address claim busy (attempt %d/%d), retrying in %.2fs",
                    idx + 1,
                    len(retry_delays),
                    retry_delays[idx + 1],
                )

    def get_effective_vendor_id(self) -> int:
        if self._effective_vendor_id is not None:
            return int(self._effective_vendor_id) & 0xFFFFFF
        return int(self.vendor_id) & 0xFFFFFF

    @staticmethod
    def _msg_from_frame(frame: str) -> CecMsg:
        parts = _parse_frame_parts(frame)
        if not parts:
            raise ValueError("empty CEC frame")
        if len(parts) > CEC_MAX_MSG_SIZE:
            raise ValueError(f"CEC frame too long ({len(parts)} bytes)")
        msg = CecMsg()
        msg.len = len(parts)
        for idx, part in enumerate(parts):
            msg.msg[idx] = int(part, 16)
        return msg

    @staticmethod
    def _frame_from_msg(msg: CecMsg) -> str:
        size = int(msg.len)
        if size <= 0 or size > CEC_MAX_MSG_SIZE:
            return ""
        return ":".join(f"{int(msg.msg[i]):02X}" for i in range(size))

    def _receive_one_frame(self, fd: int) -> str:
        msg = CecMsg()
        msg.timeout = 0
        fcntl.ioctl(fd, CEC_RECEIVE, msg)
        # Ignore internal TX status notifications.
        if msg.sequence and msg.tx_status and not msg.rx_status:
            return ""
        return self._frame_from_msg(msg)

    async def async_events(self) -> AsyncIterator[InputEvent]:
        LOG.info("starting kernel cec adapter (async): %s", self.device)
        fd = os.open(self.device, os.O_RDWR | os.O_NONBLOCK)
        self._fd = fd

        try:
            self._configure(fd)
            if self.announce_vendor_id and self.spoof_vendor_id:
                self.send_tx(self._vendor_broadcast_announce_frame())

            while True:
                try:
                    frame = self._receive_one_frame(fd)
                except OSError as exc:
                    if exc.errno in {errno.EAGAIN, errno.EWOULDBLOCK, errno.EINTR}:
                        await asyncio.sleep(self._async_poll_interval_s)
                        continue
                    raise
                if not frame:
                    await asyncio.sleep(self._async_poll_interval_s)
                    continue
                LOG.info("CEC RX frame: %s", frame)
                LOG.info("CEC RX decoded: %s -> %s", frame, format_cec_frame_human(frame))
                event = parse_cec_frame(frame, source=self.source)
                if event is not None:
                    yield event
                await asyncio.sleep(0)
        finally:
            self._fd = None
            try:
                os.close(fd)
            except OSError:
                pass

    def send_tx(self, frame: str) -> bool:
        fd = self._fd
        if fd is None:
            return False
        upper_frame = frame.upper()
        LOG.info("CEC TX frame: %s", upper_frame)
        LOG.info("CEC TX decoded: %s -> %s", upper_frame, format_cec_frame_human(upper_frame))
        try:
            msg = self._msg_from_frame(upper_frame)
            fcntl.ioctl(fd, CEC_TRANSMIT, msg)
            return True
        except (ValueError, OSError) as exc:
            LOG.warning("failed to transmit CEC frame %s: %s", upper_frame, exc)
            return False
