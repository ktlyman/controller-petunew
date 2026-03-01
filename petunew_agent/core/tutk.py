"""ThroughTek (TUTK) Kalay P2P protocol layer for PetUNew feeders.

PetUNew feeders use the ThroughTek Kalay P2P platform — NOT Tuya.
The Android app package `cn.P2PPetCam.www.linyuan` and native libraries
`libIOTCAPIs.so` / `libAVAPIs.so` confirm this.

This module wraps the TUTK IOTC and AV APIs for:
- P2P session establishment via device UID
- IO Control commands for camera/audio/device control
- AV channel management for camera streaming

Architecture note (critical):
  Research of the Petlibro PLAF203 (the only fully RE'd pet feeder+camera
  on GitHub: github.com/icex2/plaf203) reveals a DUAL-CHANNEL architecture:

    TUTK P2P channel:   Camera streaming, audio, motion detection, PTZ
    Separate channel:    Feeding commands, schedules, device configuration
                         (typically MQTT or proprietary HTTP/JSON)

  The standard TUTK AVIOCTRLDEFs.h defines ~60 camera IOTYPEs but ZERO
  feeding commands. PetUNew likely follows the same pattern — the app
  probably has an MQTT client or HTTP API for feeder motor control that
  is completely separate from the TUTK AV session.

  Until the cn.P2PPetCam APK is decompiled, feeding commands are marked
  UNCONFIRMED. Camera IOTYPEs use the confirmed standard values from the
  TUTK SDK (AVIOCTRLDEFs.h).

Standard IOTYPE sources:
  - github.com/cnping/TUTK (SDK headers, AVIOCTRLDEFs.h)
  - github.com/miguelangel-nubla/videoP2Proxy (extended defs)
  - github.com/leejansq/p2p (extended defs)
  - github.com/lr-m/Yihaw (Yi IoT camera RE)
  - github.com/icex2/plaf203 (Petlibro feeder RE — MQTT feeding)

Related open-source TUTK implementations:
  - github.com/kingrollsdice/p2pcam (Python, MIT)
  - github.com/kroo/wyzecam (Python TUTK wrapper)
"""

from __future__ import annotations

import asyncio
import ctypes
import ctypes.util
import logging
import struct
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# =========================================================================
# IO Control Command IDs — Standard TUTK AVIOCTRLDEFs.h (CONFIRMED)
# =========================================================================
# These are defined in the official TUTK SDK and used across all
# TUTK-based IP cameras. Confirmed via multiple GitHub sources.

class AVIOCtrl(IntEnum):
    """Standard TUTK IOTYPE commands from AVIOCTRLDEFs.h."""

    # Video stream
    START_VIDEO = 0x01FF
    STOP_VIDEO = 0x02FF

    # Audio stream
    START_AUDIO = 0x0300
    STOP_AUDIO = 0x0301

    # Two-way audio (speaker)
    START_SPEAKER = 0x0350
    STOP_SPEAKER = 0x0351

    # Recording
    SET_RECORD_REQ = 0x0310
    SET_RECORD_RESP = 0x0311
    GET_RECORD_REQ = 0x0312
    GET_RECORD_RESP = 0x0313
    LIST_EVENT_REQ = 0x0318
    LIST_EVENT_RESP = 0x0319
    PLAY_RECORD = 0x031A
    PLAY_RECORD_RESP = 0x031B

    # Stream quality
    SET_STREAMCTRL_REQ = 0x0320
    SET_STREAMCTRL_RESP = 0x0321
    GET_STREAMCTRL_REQ = 0x0322
    GET_STREAMCTRL_RESP = 0x0323

    # Motion detection
    SET_MOTIONDETECT_REQ = 0x0324
    SET_MOTIONDETECT_RESP = 0x0325
    GET_MOTIONDETECT_REQ = 0x0326
    GET_MOTIONDETECT_RESP = 0x0327

    # Device info
    DEVINFO_REQ = 0x0330
    DEVINFO_RESP = 0x0331

    # Password
    SET_PASSWORD_REQ = 0x0332
    SET_PASSWORD_RESP = 0x0333

    # WiFi
    LIST_WIFI_REQ = 0x0340
    LIST_WIFI_RESP = 0x0341
    SET_WIFI_REQ = 0x0342
    SET_WIFI_RESP = 0x0343
    GET_WIFI_REQ = 0x0344
    GET_WIFI_RESP = 0x0345

    # Environment (indoor/outdoor/night)
    SET_ENVIRONMENT_REQ = 0x0360
    SET_ENVIRONMENT_RESP = 0x0361
    GET_ENVIRONMENT_REQ = 0x0362
    GET_ENVIRONMENT_RESP = 0x0363

    # Video mode (flip/mirror)
    SET_VIDEOMODE_REQ = 0x0370
    SET_VIDEOMODE_RESP = 0x0371
    GET_VIDEOMODE_REQ = 0x0372
    GET_VIDEOMODE_RESP = 0x0373

    # Storage
    FORMAT_STORAGE_REQ = 0x0380
    FORMAT_STORAGE_RESP = 0x0381

    # Timezone
    GET_TIMEZONE_REQ = 0x03A0
    GET_TIMEZONE_RESP = 0x03A1
    SET_TIMEZONE_REQ = 0x03B0
    SET_TIMEZONE_RESP = 0x03B1

    # PTZ
    PTZ_COMMAND = 0x1001

    # Events
    EVENT_REPORT = 0x1FFF


# =========================================================================
# Feeding Commands — UNCONFIRMED (need APK decompilation to verify)
# =========================================================================
# These are PLACEHOLDER IDs based on the Petlibro PLAF203 architecture.
# The PLAF203 uses MQTT for feeding, not TUTK IO Control. PetUNew may:
#   a) Use vendor-specific IOTYPE extensions (>= 0x7000)
#   b) Use an MQTT channel (like Petlibro)
#   c) Use a proprietary HTTP/JSON API
#
# The relay server should abstract this — it accepts our "feed" commands
# and translates them to whatever the device actually uses.

class FeedCmd(IntEnum):
    """Feeding command IDs — UNCONFIRMED, may use a separate channel."""

    MANUAL_FEED = 0x7F00
    SET_FEED_SCHEDULE = 0x7F01
    GET_FEED_SCHEDULE = 0x7F02
    GET_FEED_RECORDS = 0x7F03


# =========================================================================
# Standard TUTK constants and enums
# =========================================================================

# Quality levels (ENUM_QUALITY_LEVEL from AVIOCTRLDEFs.h)
QUALITY_MAX = 0x01
QUALITY_HIGH = 0x02
QUALITY_MIDDLE = 0x03
QUALITY_LOW = 0x04
QUALITY_MIN = 0x05

# For client-facing API
QUALITY_HD = QUALITY_HIGH
QUALITY_SD = QUALITY_LOW
QUALITY_SMOOTH = QUALITY_MIN

# Environment modes (ENUM_ENVIRONMENT from AVIOCTRLDEFs.h)
ENV_INDOOR_50HZ = 0x00
ENV_INDOOR_60HZ = 0x01
ENV_OUTDOOR = 0x02
ENV_NIGHT = 0x03

# Night vision (mapped to environment modes)
NV_OFF = ENV_OUTDOOR
NV_ON = ENV_NIGHT
NV_AUTO = ENV_INDOOR_50HZ  # Device auto-switches

# Video modes (ENUM_VIDEO_MODE from AVIOCTRLDEFs.h)
VIDEOMODE_NORMAL = 0x00
VIDEOMODE_FLIP = 0x01
VIDEOMODE_MIRROR = 0x02
VIDEOMODE_FLIP_MIRROR = 0x03

# Motion detection sensitivity range: 0-100

# Codec IDs (ENUM_CODECID)
CODEC_H264 = 0x4E
CODEC_H265 = 0x4F
CODEC_MJPEG = 0x50

# Frame flags (ENUM_FRAMEFLAG)
FRAME_PB = 0x00  # P/B frame
FRAME_I = 0x01  # Key frame
FRAME_MD = 0x02  # Motion detection
FRAME_IO = 0x03  # IO alarm

# --- Payload struct formats ---

# SMsgAVIoctrlAVStream (8 bytes): channel(4) + reserved(4)
AV_STREAM_STRUCT = struct.Struct("<I4s")

# SMsgAVIoctrlDeviceInfoResp (68 bytes)
DEVINFO_RESP_STRUCT = struct.Struct("<16s16sIIII8s")

# Motion detection: channel(4) + sensitivity(4)
MOTION_DETECT_STRUCT = struct.Struct("<II")

# Stream quality: channel(4) + quality(1) + reserved(3)
STREAM_CTRL_STRUCT = struct.Struct("<IB3s")

# Environment: channel(4) + mode(4)
ENVIRONMENT_STRUCT = struct.Struct("<II")

# Video mode: channel(4) + mode(4)
VIDEOMODE_STRUCT = struct.Struct("<II")

# Feed schedule entry (5 bytes) — UNCONFIRMED format
SCHEDULE_ENTRY_SIZE = 5
SCHEDULE_STRUCT = struct.Struct(">BBBBB")

# Manual feed payload: 1 byte for portion count — UNCONFIRMED
FEED_STRUCT = struct.Struct(">B")


@dataclass
class TUTKSession:
    """Represents an active P2P session with a PetUNew feeder."""

    device_uid: str
    session_id: int = -1
    av_channel: int = -1
    is_connected: bool = False


@dataclass
class TUTKProtocol:
    """TUTK Kalay P2P protocol interface for PetUNew feeders.

    This protocol layer can operate in two modes:

    1. Native mode (production): Loads libIOTCAPIs.so and libAVAPIs.so
       from the TUTK SDK and calls them via ctypes. Requires the TUTK
       SDK libraries to be installed.

    2. HTTP relay mode (development/agent use): Connects through a
       local HTTP relay that bridges to the P2P protocol. This allows
       the agent to operate without native TUTK libraries by running
       a companion relay process.

    The relay approach is recommended for agent use since the TUTK SDK
    is not freely redistributable. A relay can be built from the
    open-source p2pcam or wyzecam projects.

    IMPORTANT: Feeding commands may not travel over the TUTK AV channel.
    The relay server is expected to handle routing — accepting our feed
    commands via HTTP and translating them to the correct channel
    (whether that's TUTK IO Control, MQTT, or proprietary HTTP).
    """

    relay_url: str | None = None
    tutk_lib_path: str | None = None
    _sessions: dict[str, TUTKSession] = field(default_factory=dict, repr=False)
    _iotc_lib: Any = field(default=None, repr=False)
    _av_lib: Any = field(default=None, repr=False)
    _initialized: bool = False

    async def initialize(self) -> None:
        """Initialize the TUTK IOTC subsystem."""
        if self._initialized:
            return

        if self.relay_url:
            import httpx
            async with httpx.AsyncClient(timeout=5) as http:
                resp = await http.get(f"{self.relay_url}/health")
                resp.raise_for_status()
            self._initialized = True
            logger.info("TUTK relay mode: connected to %s", self.relay_url)
            return

        # Native mode — load TUTK shared libraries
        lib_dir = Path(self.tutk_lib_path) if self.tutk_lib_path else None
        iotc_path = self._find_library("IOTCAPIs", lib_dir)
        av_path = self._find_library("AVAPIs", lib_dir)

        if not iotc_path or not av_path:
            raise FileNotFoundError(
                "TUTK SDK libraries not found (libIOTCAPIs.so, libAVAPIs.so). "
                "Either install the TUTK SDK, set tutk_lib_path, or use "
                "relay_url for HTTP relay mode. See README for details."
            )

        self._iotc_lib = ctypes.CDLL(iotc_path)
        self._av_lib = ctypes.CDLL(av_path)

        ret = self._iotc_lib.IOTC_Initialize2(0)
        if ret < 0:
            raise RuntimeError(f"IOTC_Initialize2 failed: error {ret}")

        ret = self._av_lib.avInitialize(32)
        if ret < 0:
            raise RuntimeError(f"avInitialize failed: error {ret}")

        self._initialized = True
        logger.info("TUTK native mode: initialized")

    @staticmethod
    def _find_library(name: str, lib_dir: Path | None = None) -> str | None:
        if lib_dir:
            for suffix in (".so", ".dylib", ".dll"):
                path = lib_dir / f"lib{name}{suffix}"
                if path.exists():
                    return str(path)
        return ctypes.util.find_library(name)

    async def connect(self, device_uid: str, password: str = "admin") -> TUTKSession:
        """Establish a P2P session with a PetUNew feeder."""
        if not self._initialized:
            await self.initialize()

        if device_uid in self._sessions:
            session = self._sessions[device_uid]
            if session.is_connected:
                return session

        if self.relay_url:
            session = await self._connect_relay(device_uid, password)
        else:
            session = await self._connect_native(device_uid, password)

        self._sessions[device_uid] = session
        return session

    async def _connect_relay(self, uid: str, password: str) -> TUTKSession:
        import httpx
        async with httpx.AsyncClient(timeout=30) as http:
            resp = await http.post(
                f"{self.relay_url}/connect",
                json={"uid": uid, "password": password},
            )
            resp.raise_for_status()
            data = resp.json()

        return TUTKSession(
            device_uid=uid,
            session_id=data.get("session_id", 0),
            av_channel=data.get("av_channel", 0),
            is_connected=True,
        )

    async def _connect_native(self, uid: str, password: str) -> TUTKSession:
        loop = asyncio.get_event_loop()

        def _do_connect():
            sid = self._iotc_lib.IOTC_Connect_ByUID(uid.encode())
            if sid < 0:
                raise ConnectionError(
                    f"IOTC_Connect_ByUID failed for {uid}: error {sid}"
                )

            svc_type = ctypes.c_uint(0)
            av_chan = self._av_lib.avClientStart(
                sid,
                password.encode(),
                password.encode(),
                20,
                ctypes.pointer(svc_type),
                0,
                None,
            )
            if av_chan < 0:
                self._iotc_lib.IOTC_Session_Close(sid)
                raise ConnectionError(
                    f"avClientStart failed for {uid}: error {av_chan}"
                )

            return TUTKSession(
                device_uid=uid,
                session_id=sid,
                av_channel=av_chan,
                is_connected=True,
            )

        return await loop.run_in_executor(None, _do_connect)

    async def send_io_command(
        self, device_uid: str, cmd: int, payload: bytes = b""
    ) -> bytes:
        """Send an IO Control command and receive the response.

        Accepts both AVIOCtrl (confirmed camera) and FeedCmd (unconfirmed
        feeding) command IDs.
        """
        session = self._sessions.get(device_uid)
        if not session or not session.is_connected:
            raise RuntimeError(f"No active session for {device_uid}")

        if self.relay_url:
            return await self._send_relay(session, cmd, payload)
        else:
            return await self._send_native(session, cmd, payload)

    async def _send_relay(
        self, session: TUTKSession, cmd: int, payload: bytes
    ) -> bytes:
        import httpx
        async with httpx.AsyncClient(timeout=15) as http:
            resp = await http.post(
                f"{self.relay_url}/io_ctrl",
                json={
                    "uid": session.device_uid,
                    "session_id": session.session_id,
                    "av_channel": session.av_channel,
                    "command": int(cmd),
                    "payload": payload.hex(),
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return bytes.fromhex(data.get("response", ""))

    async def _send_native(
        self, session: TUTKSession, cmd: int, payload: bytes
    ) -> bytes:
        loop = asyncio.get_event_loop()

        def _do_send():
            buf = ctypes.create_string_buffer(payload)
            ret = self._av_lib.avSendIOCtrl(
                session.av_channel, int(cmd), buf, len(payload)
            )
            if ret < 0:
                raise RuntimeError(
                    f"avSendIOCtrl failed: cmd=0x{cmd:04x} error={ret}"
                )

            resp_buf = ctypes.create_string_buffer(4096)
            resp_cmd = ctypes.c_uint(0)
            resp_len = self._av_lib.avRecvIOCtrl(
                session.av_channel,
                ctypes.pointer(resp_cmd),
                resp_buf,
                4096,
                1000,
            )
            if resp_len < 0:
                return b""
            return resp_buf.raw[:resp_len]

        return await loop.run_in_executor(None, _do_send)

    # --- Camera helpers (CONFIRMED standard TUTK IOTYPEs) ---

    async def start_video(self, device_uid: str, channel: int = 0) -> bytes:
        payload = AV_STREAM_STRUCT.pack(channel, b"\x00" * 4)
        return await self.send_io_command(device_uid, AVIOCtrl.START_VIDEO, payload)

    async def stop_video(self, device_uid: str, channel: int = 0) -> bytes:
        payload = AV_STREAM_STRUCT.pack(channel, b"\x00" * 4)
        return await self.send_io_command(device_uid, AVIOCtrl.STOP_VIDEO, payload)

    async def start_audio(self, device_uid: str, channel: int = 0) -> bytes:
        payload = AV_STREAM_STRUCT.pack(channel, b"\x00" * 4)
        return await self.send_io_command(device_uid, AVIOCtrl.START_AUDIO, payload)

    async def stop_audio(self, device_uid: str, channel: int = 0) -> bytes:
        payload = AV_STREAM_STRUCT.pack(channel, b"\x00" * 4)
        return await self.send_io_command(device_uid, AVIOCtrl.STOP_AUDIO, payload)

    async def start_speaker(self, device_uid: str, channel: int = 0) -> bytes:
        payload = AV_STREAM_STRUCT.pack(channel, b"\x00" * 4)
        return await self.send_io_command(device_uid, AVIOCtrl.START_SPEAKER, payload)

    async def stop_speaker(self, device_uid: str, channel: int = 0) -> bytes:
        payload = AV_STREAM_STRUCT.pack(channel, b"\x00" * 4)
        return await self.send_io_command(device_uid, AVIOCtrl.STOP_SPEAKER, payload)

    async def set_stream_quality(self, device_uid: str, quality: int) -> bytes:
        payload = STREAM_CTRL_STRUCT.pack(0, quality, b"\x00" * 3)
        return await self.send_io_command(
            device_uid, AVIOCtrl.SET_STREAMCTRL_REQ, payload
        )

    async def get_stream_quality(self, device_uid: str) -> bytes:
        payload = STREAM_CTRL_STRUCT.pack(0, 0, b"\x00" * 3)
        return await self.send_io_command(
            device_uid, AVIOCtrl.GET_STREAMCTRL_REQ, payload
        )

    async def set_motion_detection(self, device_uid: str, sensitivity: int) -> bytes:
        """Set motion detection sensitivity (0=off, 1-100)."""
        payload = MOTION_DETECT_STRUCT.pack(0, sensitivity)
        return await self.send_io_command(
            device_uid, AVIOCtrl.SET_MOTIONDETECT_REQ, payload
        )

    async def get_motion_detection(self, device_uid: str) -> bytes:
        payload = MOTION_DETECT_STRUCT.pack(0, 0)
        return await self.send_io_command(
            device_uid, AVIOCtrl.GET_MOTIONDETECT_REQ, payload
        )

    async def get_device_info(self, device_uid: str) -> bytes:
        return await self.send_io_command(
            device_uid, AVIOCtrl.DEVINFO_REQ, b""
        )

    async def set_environment(self, device_uid: str, mode: int) -> bytes:
        """Set environment mode (indoor 50Hz/60Hz, outdoor, night)."""
        payload = ENVIRONMENT_STRUCT.pack(0, mode)
        return await self.send_io_command(
            device_uid, AVIOCtrl.SET_ENVIRONMENT_REQ, payload
        )

    async def get_environment(self, device_uid: str) -> bytes:
        payload = ENVIRONMENT_STRUCT.pack(0, 0)
        return await self.send_io_command(
            device_uid, AVIOCtrl.GET_ENVIRONMENT_REQ, payload
        )

    async def set_video_mode(self, device_uid: str, mode: int) -> bytes:
        """Set video flip/mirror mode."""
        payload = VIDEOMODE_STRUCT.pack(0, mode)
        return await self.send_io_command(
            device_uid, AVIOCtrl.SET_VIDEOMODE_REQ, payload
        )

    # --- Feeding helpers (UNCONFIRMED — may use separate channel) ---

    async def trigger_feed(self, device_uid: str, portions: int) -> bytes:
        """Dispense food. WARNING: Command ID is unconfirmed.

        If the relay is in use, the relay handles routing this to the
        correct channel (TUTK IO, MQTT, or HTTP). In native mode, this
        attempts to send via avSendIOCtrl which may not work if the
        feeder uses a separate feeding channel.
        """
        payload = FEED_STRUCT.pack(portions)
        return await self.send_io_command(device_uid, FeedCmd.MANUAL_FEED, payload)

    async def get_feed_schedule(self, device_uid: str) -> list[dict]:
        resp = await self.send_io_command(
            device_uid, FeedCmd.GET_FEED_SCHEDULE, b""
        )
        return self.decode_schedule(resp)

    async def set_feed_schedule(
        self, device_uid: str, schedules: list[dict]
    ) -> bytes:
        payload = self.encode_schedule(schedules)
        return await self.send_io_command(
            device_uid, FeedCmd.SET_FEED_SCHEDULE, payload
        )

    async def get_feed_records(self, device_uid: str) -> bytes:
        return await self.send_io_command(
            device_uid, FeedCmd.GET_FEED_RECORDS, b""
        )

    # --- Night vision (via environment mode) ---

    async def set_night_vision(self, device_uid: str, mode: int) -> bytes:
        """Set night vision: NV_OFF, NV_ON, or NV_AUTO."""
        return await self.set_environment(device_uid, mode)

    # --- Speaker volume ---

    async def set_speaker_volume(self, device_uid: str, volume: int) -> bytes:
        """Speaker volume is not a standard TUTK IOTYPE.

        In relay mode, the relay handles this. In native mode, the
        volume may be controlled via the audio codec or a vendor-specific
        IOTYPE.
        """
        if self.relay_url:
            import httpx
            async with httpx.AsyncClient(timeout=15) as http:
                resp = await http.post(
                    f"{self.relay_url}/speaker_volume",
                    json={"uid": device_uid, "volume": volume},
                )
                resp.raise_for_status()
                return bytes.fromhex(resp.json().get("response", ""))
        return b""

    async def set_microphone(self, device_uid: str, on: bool) -> bytes:
        """Toggle microphone for 2-way audio."""
        if on:
            return await self.start_speaker(device_uid)
        else:
            return await self.stop_speaker(device_uid)

    async def set_camera_power(self, device_uid: str, on: bool) -> bytes:
        """Start or stop the video stream (no standard power-off IOTYPE)."""
        if on:
            return await self.start_video(device_uid)
        else:
            return await self.stop_video(device_uid)

    async def request_snapshot(self, device_uid: str) -> bytes:
        """Request a snapshot via the relay.

        TUTK doesn't have a standard snapshot IOTYPE — snapshots are
        typically taken by decoding a keyframe from the video stream.
        The relay is expected to handle this.
        """
        if self.relay_url:
            import httpx
            async with httpx.AsyncClient(timeout=15) as http:
                resp = await http.get(
                    f"{self.relay_url}/snapshot/{device_uid}",
                )
                resp.raise_for_status()
                return resp.content
        return b""

    async def get_wifi_signal(self, device_uid: str) -> bytes:
        """WiFi signal info is part of the device info response."""
        return await self.get_device_info(device_uid)

    # --- Schedule encoding (UNCONFIRMED format) ---

    @staticmethod
    def encode_schedule(schedules: list[dict]) -> bytes:
        """Encode feed schedules into binary format.

        WARNING: This encoding is speculative. The actual format must
        be confirmed by decompiling the cn.P2PPetCam APK or capturing
        network traffic.

        Each entry: {hour, minute, portions, enabled, days}
        """
        parts = []
        for s in schedules:
            day_mask = 0
            for day in s.get("days", range(7)):
                day_mask |= 1 << day
            flags = 0x80 if s.get("enabled", True) else 0x00
            parts.append(
                SCHEDULE_STRUCT.pack(
                    s["hour"],
                    s["minute"],
                    s.get("portions", 1),
                    day_mask,
                    flags,
                )
            )
        return b"".join(parts)

    @staticmethod
    def decode_schedule(data: bytes) -> list[dict]:
        """Decode the binary blob into schedule entries."""
        schedules = []
        for i in range(0, len(data), SCHEDULE_ENTRY_SIZE):
            if i + SCHEDULE_ENTRY_SIZE > len(data):
                break
            hour, minute, portions, day_mask, flags = SCHEDULE_STRUCT.unpack(
                data[i : i + SCHEDULE_ENTRY_SIZE]
            )
            enabled = bool(flags & 0x80)
            days = [d for d in range(7) if day_mask & (1 << d)]
            schedules.append(
                {
                    "hour": hour,
                    "minute": minute,
                    "portions": portions,
                    "enabled": enabled,
                    "days": days,
                }
            )
        return schedules

    # --- Lifecycle ---

    async def disconnect(self, device_uid: str) -> None:
        session = self._sessions.pop(device_uid, None)
        if not session or not session.is_connected:
            return

        if self.relay_url:
            import httpx
            async with httpx.AsyncClient(timeout=5) as http:
                await http.post(
                    f"{self.relay_url}/disconnect",
                    json={"uid": device_uid, "session_id": session.session_id},
                )
        elif self._av_lib and self._iotc_lib:
            self._av_lib.avClientStop(session.av_channel)
            self._iotc_lib.IOTC_Session_Close(session.session_id)

        session.is_connected = False

    async def disconnect_all(self) -> None:
        for uid in list(self._sessions.keys()):
            await self.disconnect(uid)

        if self._iotc_lib and not self.relay_url:
            self._av_lib.avDeInitialize()
            self._iotc_lib.IOTC_DeInitialize()
            self._initialized = False

    async def close(self) -> None:
        await self.disconnect_all()
