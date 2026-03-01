"""Authentication and device credentials for PetUNew feeders.

PetUNew feeders use the ThroughTek (TUTK) Kalay P2P platform. Each
device is identified by a UID string and authenticated with a password.
The UID is assigned at manufacture and can be found:
  - In the Pet-U app under device settings
  - Printed on the device label (sometimes)
  - Captured from network traffic during pairing

Two operating modes:
  1. Direct P2P: Provide device UIDs and the TUTK SDK libraries
  2. HTTP relay: Point to a relay server that bridges P2P connections

The relay approach is recommended for agent use — it decouples the
TUTK native SDK from the Python agent and can be run as a sidecar.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DeviceCredentials:
    """Credentials for a single PetUNew feeder."""

    uid: str
    password: str = "admin"
    name: str = ""


@dataclass
class PetUNewAuth:
    """Manages PetUNew device credentials and connection settings."""

    # Device credentials (uid -> DeviceCredentials)
    devices: list[DeviceCredentials] = field(default_factory=list)

    # Connection mode
    relay_url: str | None = None  # HTTP relay URL (recommended for agents)
    tutk_lib_path: str | None = None  # Path to TUTK SDK libs (native mode)

    @classmethod
    def from_env(cls) -> PetUNewAuth:
        """Load configuration from environment variables.

        Env vars:
            PETUNEW_RELAY_URL    - HTTP relay URL (e.g. http://localhost:8100)
            PETUNEW_TUTK_LIB     - Path to TUTK SDK library directory
            PETUNEW_DEVICES      - JSON array of {uid, password, name} objects
            PETUNEW_DEVICE_UID   - Single device UID (shortcut for one device)
            PETUNEW_DEVICE_PASS  - Password for single device (default: admin)
            PETUNEW_DEVICE_NAME  - Name for single device
        """
        auth = cls(
            relay_url=os.environ.get("PETUNEW_RELAY_URL"),
            tutk_lib_path=os.environ.get("PETUNEW_TUTK_LIB"),
        )

        # Multi-device config via JSON
        devices_json = os.environ.get("PETUNEW_DEVICES")
        if devices_json:
            for d in json.loads(devices_json):
                auth.devices.append(DeviceCredentials(**d))

        # Single device shortcut
        uid = os.environ.get("PETUNEW_DEVICE_UID")
        if uid and not any(d.uid == uid for d in auth.devices):
            auth.devices.append(
                DeviceCredentials(
                    uid=uid,
                    password=os.environ.get("PETUNEW_DEVICE_PASS", "admin"),
                    name=os.environ.get("PETUNEW_DEVICE_NAME", "PetUNew Feeder"),
                )
            )

        return auth

    @classmethod
    def from_config(cls, path: str | Path | None = None) -> PetUNewAuth:
        """Load from config file."""
        config_path = (
            Path(path) if path else Path.home() / ".config" / "petunew" / "config.json"
        )
        if not config_path.exists():
            raise FileNotFoundError(
                f"Config not found at {config_path}. "
                "Run 'petunew configure' or set environment variables."
            )
        with open(config_path) as f:
            data = json.load(f)

        auth = cls(
            relay_url=data.get("relay_url"),
            tutk_lib_path=data.get("tutk_lib_path"),
        )
        for d in data.get("devices", []):
            auth.devices.append(DeviceCredentials(**d))
        return auth

    def save_config(self, path: str | Path | None = None):
        """Persist configuration to file."""
        config_path = (
            Path(path) if path else Path.home() / ".config" / "petunew" / "config.json"
        )
        config_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "relay_url": self.relay_url,
            "tutk_lib_path": self.tutk_lib_path,
            "devices": [
                {"uid": d.uid, "password": d.password, "name": d.name}
                for d in self.devices
            ],
        }
        with open(config_path, "w") as f:
            json.dump(data, f, indent=2)

    def get_device(self, uid: str) -> DeviceCredentials:
        for d in self.devices:
            if d.uid == uid:
                return d
        raise ValueError(f"No credentials for device {uid}")

    @property
    def has_devices(self) -> bool:
        return len(self.devices) > 0

    @property
    def connection_mode(self) -> str:
        if self.relay_url:
            return "relay"
        if self.tutk_lib_path:
            return "native"
        return "unconfigured"
