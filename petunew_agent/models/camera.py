"""Camera models for PetUNew feeders."""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel


class StreamQuality(str, Enum):
    HD = "hd"
    SD = "sd"
    SMOOTH = "smooth"


class CameraSettings(BaseModel):
    """Current camera configuration."""

    device_id: str
    quality: StreamQuality = StreamQuality.HD
    night_vision: bool = True
    motion_detection: bool = True
    speaker_enabled: bool = False
    microphone_enabled: bool = False


class SnapshotResult(BaseModel):
    """Result of a camera snapshot request."""

    device_id: str
    image_url: str | None = None
    image_bytes: bytes | None = None
    timestamp: str = ""
    quality: StreamQuality = StreamQuality.HD

    model_config = {"arbitrary_types_allowed": True}


class StreamInfo(BaseModel):
    """Information needed to connect to a live stream."""

    device_id: str
    rtsp_url: str | None = None
    hls_url: str | None = None
    p2p_config: dict | None = None
    quality: StreamQuality = StreamQuality.HD
