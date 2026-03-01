"""Device models for PetUNew feeders."""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel


class DeviceStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class Device(BaseModel):
    """Represents a PetUNew feeder device."""

    device_id: str
    name: str
    status: DeviceStatus = DeviceStatus.UNKNOWN
    ip_address: str | None = None
    local_key: str | None = None
    firmware_version: str | None = None
    model: str | None = None
    wifi_signal: int | None = None

    # Tuya-specific identifiers
    tuya_device_id: str | None = None
    tuya_product_id: str | None = None

    # Capabilities detected from the device
    has_camera: bool = False
    has_speaker: bool = False
    has_microphone: bool = False
    max_portions: int = 10

    def is_online(self) -> bool:
        return self.status == DeviceStatus.ONLINE
