"""High-level client for PetUNew feeder operations.

This is the primary interface for agents and applications. It wraps the
TUTK P2P protocol layer with feeder-specific logic and provides clean,
typed methods for all device operations.

PetUNew feeders communicate via the ThroughTek Kalay P2P platform using
IO Control commands over a P2P tunnel. This client abstracts that into
simple async methods.
"""

from __future__ import annotations

import json
import struct
from datetime import datetime, time

from petunew_agent.core.auth import PetUNewAuth
from petunew_agent.core.tutk import (
    NV_AUTO,
    NV_OFF,
    NV_ON,
    QUALITY_HD,
    QUALITY_SD,
    QUALITY_SMOOTH,
    TUTKProtocol,
)
from petunew_agent.models.camera import (
    CameraSettings,
    SnapshotResult,
    StreamInfo,
    StreamQuality,
)
from petunew_agent.models.device import Device, DeviceStatus
from petunew_agent.models.feeding import FeedingRecord, FeedSchedule

QUALITY_TO_INT = {"hd": QUALITY_HD, "sd": QUALITY_SD, "smooth": QUALITY_SMOOTH}
INT_TO_QUALITY = {v: k for k, v in QUALITY_TO_INT.items()}

NV_MODES = {"off": NV_OFF, "on": NV_ON, "auto": NV_AUTO}


class PetUNewClient:
    """Agent-friendly client for PetUNew smart feeders.

    Usage:
        auth = PetUNewAuth.from_env()
        client = PetUNewClient(auth)
        await client.connect()

        devices = await client.list_devices()
        await client.feed_now(devices[0].device_id, portions=2)
        schedules = await client.get_feed_schedules(devices[0].device_id)
    """

    def __init__(self, auth: PetUNewAuth):
        self.auth = auth
        self._tutk: TUTKProtocol | None = None
        self._devices: dict[str, Device] = {}

    async def connect(self) -> None:
        """Initialize the TUTK P2P subsystem and connect to all configured devices."""
        self._tutk = TUTKProtocol(
            relay_url=self.auth.relay_url,
            tutk_lib_path=self.auth.tutk_lib_path,
        )
        await self._tutk.initialize()

        # Connect to all configured devices
        for cred in self.auth.devices:
            try:
                await self._tutk.connect(cred.uid, cred.password)
                # Fetch device info to populate our device model
                info_bytes = await self._tutk.get_device_info(cred.uid)
                device = self._parse_device_info(cred.uid, cred.name, info_bytes)
                self._devices[cred.uid] = device
            except Exception as e:
                # Store device as offline if connection fails
                self._devices[cred.uid] = Device(
                    device_id=cred.uid,
                    name=cred.name or "PetUNew Feeder",
                    status=DeviceStatus.OFFLINE,
                    has_camera=True,
                    has_speaker=True,
                    has_microphone=True,
                )

    @property
    def tutk(self) -> TUTKProtocol:
        if self._tutk is None:
            raise RuntimeError("Not connected. Call connect() first.")
        return self._tutk

    @staticmethod
    def _parse_device_info(uid: str, name: str, raw: bytes) -> Device:
        """Parse GET_DEVICE_INFO response into a Device model."""
        # Response format varies; extract what we can
        fw_version = None
        model = None
        wifi_signal = None

        if len(raw) >= 4:
            # First 2 bytes: firmware major.minor
            fw_major, fw_minor = struct.unpack(">BB", raw[0:2])
            fw_version = f"{fw_major}.{fw_minor}"
        if len(raw) >= 6:
            wifi_signal = struct.unpack(">h", raw[4:6])[0]

        return Device(
            device_id=uid,
            name=name or "PetUNew Feeder",
            status=DeviceStatus.ONLINE,
            firmware_version=fw_version,
            wifi_signal=wifi_signal,
            model=model,
            has_camera=True,
            has_speaker=True,
            has_microphone=True,
            max_portions=10,
        )

    # --- Device Management ---

    async def list_devices(self) -> list[Device]:
        """Return all configured devices and their connection status."""
        # TUTK P2P doesn't have cloud device discovery — devices are
        # pre-configured via UIDs. Refresh status for connected ones.
        devices = []
        for uid, device in self._devices.items():
            session = self._tutk._sessions.get(uid) if self._tutk else None
            if session and session.is_connected:
                device.status = DeviceStatus.ONLINE
            else:
                device.status = DeviceStatus.OFFLINE
            devices.append(device)
        return devices

    async def get_device(self, device_id: str) -> Device:
        """Get info for a specific device."""
        if device_id not in self._devices:
            raise ValueError(
                f"Device {device_id} not found. Configure it in "
                "PETUNEW_DEVICES or petunew configure."
            )
        return self._devices[device_id]

    # --- Feeding ---

    async def feed_now(self, device_id: str, portions: int = 1) -> FeedingRecord:
        """Dispense food immediately.

        Args:
            device_id: Device UID.
            portions: Number of portions to dispense (1-10).

        Returns:
            FeedingRecord of the dispensed feeding.
        """
        if not 1 <= portions <= 10:
            raise ValueError("Portions must be between 1 and 10")

        await self.tutk.trigger_feed(device_id, portions)

        return FeedingRecord(
            device_id=device_id,
            timestamp=datetime.now(),
            portions=portions,
            source="agent",
            success=True,
        )

    async def get_feed_schedules(self, device_id: str) -> list[FeedSchedule]:
        """Retrieve all configured feed schedules."""
        decoded = await self.tutk.get_feed_schedule(device_id)
        labels = ["Breakfast", "Lunch", "Dinner", "Snack"]
        schedules = []
        for i, entry in enumerate(decoded):
            schedules.append(
                FeedSchedule(
                    schedule_id=f"{device_id}_sched_{i}",
                    label=labels[i] if i < len(labels) else f"Meal {i + 1}",
                    meal_time=time(hour=entry["hour"], minute=entry["minute"]),
                    portions=entry["portions"],
                    enabled=entry["enabled"],
                    repeat_days=entry["days"],
                )
            )
        return schedules

    async def set_feed_schedules(
        self, device_id: str, schedules: list[FeedSchedule]
    ) -> bool:
        """Update all feed schedules on the device."""
        entries = []
        for s in schedules:
            entries.append(
                {
                    "hour": s.meal_time.hour,
                    "minute": s.meal_time.minute,
                    "portions": s.portions,
                    "enabled": s.enabled,
                    "days": s.repeat_days,
                }
            )
        await self.tutk.set_feed_schedule(device_id, entries)
        return True

    async def add_feed_schedule(
        self,
        device_id: str,
        meal_time: time,
        portions: int = 1,
        label: str = "",
        days: list[int] | None = None,
    ) -> list[FeedSchedule]:
        """Add a new feeding schedule to the existing ones."""
        current = await self.get_feed_schedules(device_id)
        new_schedule = FeedSchedule(
            label=label or f"Meal {len(current) + 1}",
            meal_time=meal_time,
            portions=portions,
            enabled=True,
            repeat_days=days if days is not None else list(range(7)),
        )
        current.append(new_schedule)
        await self.set_feed_schedules(device_id, current)
        return current

    async def remove_feed_schedule(
        self, device_id: str, schedule_index: int
    ) -> list[FeedSchedule]:
        """Remove a feeding schedule by index."""
        current = await self.get_feed_schedules(device_id)
        if not 0 <= schedule_index < len(current):
            raise IndexError(
                f"Schedule index {schedule_index} out of range (0-{len(current) - 1})"
            )
        current.pop(schedule_index)
        await self.set_feed_schedules(device_id, current)
        return current

    async def get_feeding_records(self, device_id: str) -> list[FeedingRecord]:
        """Retrieve recent feeding history from the device."""
        raw = await self.tutk.get_feed_records(device_id)
        records = []
        # Feed records are returned as binary entries from the device.
        # Each record is typically 8 bytes:
        #   4 bytes: unix timestamp
        #   1 byte: portions
        #   1 byte: source (0=schedule, 1=manual, 2=remote)
        #   1 byte: success flag
        #   1 byte: reserved
        RECORD_SIZE = 8
        for i in range(0, len(raw), RECORD_SIZE):
            if i + RECORD_SIZE > len(raw):
                break
            ts, portions, source, success, _ = struct.unpack(
                ">IBBBB", raw[i : i + RECORD_SIZE]
            )
            source_map = {0: "schedule", 1: "manual", 2: "agent"}
            records.append(
                FeedingRecord(
                    device_id=device_id,
                    timestamp=datetime.fromtimestamp(ts),
                    portions=portions,
                    source=source_map.get(source, "unknown"),
                    success=bool(success),
                )
            )
        return records

    # --- Camera ---

    async def get_camera_settings(self, device_id: str) -> CameraSettings:
        """Get current camera configuration.

        Note: TUTK P2P doesn't have a single "get all settings" command,
        so this returns defaults. Use individual status commands for
        real-time values when the relay supports it.
        """
        return CameraSettings(
            device_id=device_id,
            quality=StreamQuality.HD,
            night_vision=True,
            motion_detection=True,
            speaker_enabled=False,
            microphone_enabled=False,
        )

    async def set_camera_quality(
        self, device_id: str, quality: StreamQuality
    ) -> bool:
        """Change camera stream quality."""
        await self.tutk.set_stream_quality(device_id, QUALITY_TO_INT[quality.value])
        return True

    async def toggle_camera(self, device_id: str, on: bool = True) -> bool:
        """Turn camera on or off."""
        await self.tutk.set_camera_power(device_id, on)
        return True

    async def take_snapshot(self, device_id: str) -> SnapshotResult:
        """Capture a photo from the feeder camera.

        The TUTK P2P protocol returns raw JPEG data in the response.
        In relay mode, the relay may save it and return a URL instead.
        """
        raw = await self.tutk.request_snapshot(device_id)
        return SnapshotResult(
            device_id=device_id,
            image_bytes=raw if raw else None,
            timestamp=datetime.now().isoformat(),
        )

    async def get_stream_info(self, device_id: str) -> StreamInfo:
        """Get stream connection info.

        TUTK P2P streams are not URL-based — they flow through the P2P
        tunnel directly. In relay mode, the relay may expose an RTSP
        or HLS endpoint that re-publishes the P2P stream.
        """
        rtsp_url = None
        if self.auth.relay_url:
            rtsp_url = f"{self.auth.relay_url}/stream/{device_id}"
        return StreamInfo(
            device_id=device_id,
            rtsp_url=rtsp_url,
            p2p_config={"uid": device_id, "protocol": "tutk_kalay"},
        )

    async def set_speaker(self, device_id: str, volume: int) -> bool:
        """Set speaker volume (0-100, 0 = muted)."""
        if not 0 <= volume <= 100:
            raise ValueError("Volume must be 0-100")
        await self.tutk.set_speaker_volume(device_id, volume)
        return True

    async def toggle_microphone(self, device_id: str, on: bool) -> bool:
        """Enable or disable the microphone for 2-way audio."""
        await self.tutk.set_microphone(device_id, on)
        return True

    async def set_night_vision(self, device_id: str, mode: str = "auto") -> bool:
        """Set night vision mode: 'off', 'on', or 'auto'."""
        if mode not in NV_MODES:
            raise ValueError(f"Mode must be one of: {list(NV_MODES.keys())}")
        await self.tutk.set_night_vision(device_id, NV_MODES[mode])
        return True

    async def set_motion_detection(self, device_id: str, enabled: bool) -> bool:
        """Enable or disable motion detection alerts."""
        await self.tutk.set_motion_detection(device_id, enabled)
        return True

    # --- Lifecycle ---

    async def disconnect(self) -> None:
        """Clean up connections."""
        if self._tutk:
            await self._tutk.close()
            self._tutk = None
        self._devices.clear()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *exc):
        await self.disconnect()
