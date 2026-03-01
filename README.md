# PetUNew Agent

[![Lint CLAUDE.md](https://github.com/ktlyman/controller-petunew/actions/workflows/claude-md-lint.yml/badge.svg)](https://github.com/ktlyman/controller-petunew/actions/workflows/claude-md-lint.yml)

Agent-first interface for **PetUNew smart WiFi camera pet feeders**.

Instead of using the Pet-U mobile app (`cn.P2PPetCam.www.linyuan`), control your feeders programmatically — through natural language, CLI commands, or as tools in any LLM agent.

## How PetUNew Feeders Actually Work

PetUNew feeders are **NOT** Tuya-based. They use the **ThroughTek (TUTK) Kalay P2P platform** — a proprietary binary protocol over UDP with NAT-traversing P2P tunnels. The "P2P" in the app's package name (`cn.P2PPetCam`) is the tell.

Key facts discovered through research:
- **App**: "PetuNew" / "Pet-U" ([Google Play](https://play.google.com/store/apps/details?id=cn.P2PPetCam.www.linyuan), [App Store](https://apps.apple.com/us/app/petunew/id1337025891))
- **Developer**: "Jk" organization, Guangzhou, China
- **Protocol**: TUTK IOTC P2P (binary over UDP), not REST/MQTT
- **Native libs**: `libIOTCAPIs.so` + `libAVAPIs.so` in the APK
- **Related brands**: WOPET, PetFun (same P2P platform, same hardware)
- **Home Assistant**: No integration exists for this platform
- **Camera streaming**: TUTK AV API over P2P tunnel (not RTSP/HLS)
- **Device commands**: IO Control commands (`avSendIOCtrl`) with binary payloads

## Architecture

```
┌──────────────────────────────────────────────────────┐
│  Agent Layer (natural language)                      │
│  - Claude agent loop with tool_use                   │
│  - MCP server for Claude Desktop / Code              │
│  - Embeddable tools for custom agents                │
├──────────────────────────────────────────────────────┤
│  Tool Definitions (17 tools)                         │
│  - Device discovery    - Feeding control             │
│  - Schedule management - Camera/snapshot             │
│  - 2-way audio         - Motion detection            │
├──────────────────────────────────────────────────────┤
│  PetUNewClient (typed async Python API)              │
│  - feed_now()          - get_feed_schedules()        │
│  - take_snapshot()     - set_camera_quality()        │
│  - toggle_microphone() - set_night_vision()          │
├──────────────────────────────────────────────────────┤
│  TUTK Protocol Layer                                 │
│  - P2P session via device UID                        │
│  - IO Control commands (binary structs over UDP)     │
│  - AV channel for camera/audio streaming             │
│  - HTTP relay mode for agent-friendly access         │
└──────────┬───────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────┐
│  Connection Modes                                    │
│                                                      │
│  Option A: HTTP Relay (recommended)                  │
│  ┌──────────┐     ┌───────────┐     ┌──────────┐    │
│  │  Agent   │────▶│  Relay    │────▶│  Feeder  │    │
│  │ (Python) │ HTTP│ (sidecar) │ P2P │  (TUTK)  │    │
│  └──────────┘     └───────────┘     └──────────┘    │
│                                                      │
│  Option B: Native TUTK SDK                           │
│  ┌──────────┐     ┌──────────┐                       │
│  │  Agent   │────▶│  Feeder  │                       │
│  │ (ctypes) │ P2P │  (TUTK)  │                       │
│  └──────────┘     └──────────┘                       │
└──────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Install

```bash
pip install -e .
```

### 2. Find your device UID

The device UID is assigned at manufacture. Find it in:
- The Pet-U app → Device Settings → Device Info
- The label on the bottom of your feeder
- Network traffic capture during initial pairing

### 3. Configure

**Environment variables (simplest):**

```bash
# HTTP relay mode (recommended)
export PETUNEW_RELAY_URL="http://localhost:8100"
export PETUNEW_DEVICE_UID="XXXXXXXXXX"
export PETUNEW_DEVICE_NAME="Gandalf Feeder"
export PETUNEW_DEVICE_PASS="admin"  # default for most units

# OR native TUTK SDK mode
export PETUNEW_TUTK_LIB="/path/to/tutk/libs"
export PETUNEW_DEVICE_UID="XXXXXXXXXX"
```

**Or interactive setup:**

```bash
petunew configure
```

**Or config file** (`~/.config/petunew/config.json`):

```json
{
    "relay_url": "http://localhost:8100",
    "devices": [
        {
            "uid": "XXXXXXXXXX",
            "password": "admin",
            "name": "Gandalf Feeder"
        }
    ]
}
```

### 4. Use it

**CLI commands:**

```bash
# List your feeders
petunew devices

# Feed 2 portions now
petunew feed DEVICE_UID --portions 2

# View feeding schedules
petunew schedules DEVICE_UID

# Take a camera snapshot
petunew snapshot DEVICE_UID

# Get stream connection info
petunew stream DEVICE_UID
```

**Interactive agent chat:**

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
petunew chat
```

```
You: Feed Gandalf 2 portions
Agent: I've dispensed 2 portions from the Gandalf Feeder.

You: What's his feeding schedule?
Agent: Here's Gandalf's current schedule:
  - Breakfast: 8:00 AM — 2 portions
  - Lunch: 12:00 PM — 1 portion
  - Dinner: 6:00 PM — 1 portion

You: Add a 3pm snack, 1 portion
Agent: Done! Added an afternoon snack at 3:00 PM for 1 portion.

You: Check on him
Agent: Here's a snapshot from the camera: [image data, 45KB]
```

## Agent Integration

### Embed in your own agent

```python
from petunew_agent.core.auth import PetUNewAuth
from petunew_agent.core.client import PetUNewClient
from petunew_agent.tools.definitions import TOOL_DEFINITIONS
from petunew_agent.tools.handler import ToolHandler

# Get tool definitions for your agent
tools = TOOL_DEFINITIONS  # pass to Claude's tools parameter

# Handle tool calls
auth = PetUNewAuth.from_env()
client = PetUNewClient(auth)
await client.connect()

handler = ToolHandler(client)
result = await handler.handle("petunew_feed_now", {
    "device_id": "XXXXXXXXXX",
    "portions": 2,
})
```

### MCP Server (Claude Desktop / Claude Code)

Add to your MCP config:

```json
{
    "mcpServers": {
        "petunew": {
            "command": "python",
            "args": ["-m", "petunew_agent.mcp_server"],
            "env": {
                "PETUNEW_RELAY_URL": "http://localhost:8100",
                "PETUNEW_DEVICE_UID": "XXXXXXXXXX",
                "PETUNEW_DEVICE_NAME": "Gandalf Feeder"
            }
        }
    }
}
```

### Use the Python client directly

```python
from petunew_agent.core.auth import PetUNewAuth
from petunew_agent.core.client import PetUNewClient

auth = PetUNewAuth.from_env()
async with PetUNewClient(auth) as client:
    devices = await client.list_devices()
    await client.feed_now(devices[0].device_id, portions=2)
    schedules = await client.get_feed_schedules(devices[0].device_id)
    snapshot = await client.take_snapshot(devices[0].device_id)
```

## Available Tools (17)

| Tool | Description |
|------|-------------|
| `petunew_list_devices` | List all configured feeders and their status |
| `petunew_get_device_status` | Full device status |
| `petunew_feed_now` | Dispense food immediately (1-10 portions) |
| `petunew_get_feed_schedules` | View automatic feeding schedules |
| `petunew_set_feed_schedules` | Replace all schedules |
| `petunew_add_feed_schedule` | Append a new schedule |
| `petunew_remove_feed_schedule` | Remove a schedule by index |
| `petunew_get_feeding_records` | Feeding history (scheduled + manual) |
| `petunew_take_snapshot` | Capture camera photo |
| `petunew_get_stream_info` | Get stream connection info |
| `petunew_set_camera_quality` | HD / SD / Smooth |
| `petunew_toggle_camera` | Camera on/off |
| `petunew_set_speaker_volume` | Speaker volume (0-100) |
| `petunew_toggle_microphone` | 2-way audio mic on/off |
| `petunew_set_night_vision` | Off / On / Auto |
| `petunew_set_motion_detection` | Motion alerts on/off |
| `petunew_get_camera_settings` | Current camera configuration |

## TUTK P2P Protocol Details

### Dual-Channel Architecture

Research of the only fully reverse-engineered pet feeder+camera ([icex2/plaf203](https://github.com/icex2/plaf203), Petlibro PLAF203) revealed that pet feeder devices use a **dual-channel architecture**:

```
┌─────────────────────────────────┐
│  TUTK P2P Channel (CONFIRMED)  │  Standard IOTYPE commands from AVIOCTRLDEFs.h
│  - Live video streaming         │  Used by ALL TUTK-based cameras
│  - Live audio streaming         │
│  - Two-way audio (speaker)      │
│  - Motion detection config      │
│  - Stream quality control       │
│  - Device info                  │
│  - Night vision / video mode    │
└─────────────────────────────────┘

┌─────────────────────────────────┐
│  Feeding Channel (UNCONFIRMED)  │  Could be MQTT, HTTP/JSON, or vendor IOTYPE
│  - Manual feed (dispense)       │  Petlibro uses MQTT; PetUNew protocol unknown
│  - Feeding schedules            │  Must decompile cn.P2PPetCam APK to confirm
│  - Feeding history              │
│  - Device configuration         │
└─────────────────────────────────┘
```

The standard TUTK SDK defines ~60 camera IOTYPEs but **zero feeding commands**. The relay server is expected to abstract this — it handles both channels and presents a unified API.

### Camera IO Control Commands (CONFIRMED)

These use the standard TUTK IOTYPEs from `AVIOCTRLDEFs.h`, confirmed across 6+ GitHub repos:

| IOTYPE | Hex | Function | Payload |
|--------|-----|----------|---------|
| `START_VIDEO` | `0x01FF` | Start video stream | `SMsgAVIoctrlAVStream` (8 bytes) |
| `STOP_VIDEO` | `0x02FF` | Stop video stream | `SMsgAVIoctrlAVStream` |
| `START_AUDIO` | `0x0300` | Start audio receive | `SMsgAVIoctrlAVStream` |
| `STOP_AUDIO` | `0x0301` | Stop audio receive | `SMsgAVIoctrlAVStream` |
| `START_SPEAKER` | `0x0350` | Start two-way audio | `SMsgAVIoctrlAVStream` |
| `STOP_SPEAKER` | `0x0351` | Stop two-way audio | `SMsgAVIoctrlAVStream` |
| `SET_STREAMCTRL` | `0x0320` | Set stream quality | channel(4) + quality(1) + pad(3) |
| `GET_STREAMCTRL` | `0x0322` | Get stream quality | channel(4) + pad(4) |
| `SET_MOTIONDETECT` | `0x0324` | Set motion sensitivity | channel(4) + sensitivity(4) |
| `GET_MOTIONDETECT` | `0x0326` | Get motion sensitivity | channel(4) + pad(4) |
| `DEVINFO_REQ` | `0x0330` | Get device info | (empty) |
| `SET_ENVIRONMENT` | `0x0360` | Set environment mode | channel(4) + mode(4) |
| `GET_ENVIRONMENT` | `0x0362` | Get environment mode | channel(4) + pad(4) |
| `SET_VIDEOMODE` | `0x0370` | Set flip/mirror | channel(4) + mode(4) |
| `PTZ_COMMAND` | `0x1001` | Pan/tilt/zoom | 8-byte PTZ struct |

Quality levels: `MAX=1, HIGH=2, MIDDLE=3, LOW=4, MIN=5`
Environment modes: `INDOOR_50HZ=0, INDOOR_60HZ=1, OUTDOOR=2, NIGHT=3`
Video modes: `NORMAL=0, FLIP=1, MIRROR=2, FLIP_MIRROR=3`

### Feeding Commands (UNCONFIRMED — needs APK decompilation)

Feeding commands are assigned placeholder IDs (`0x7F00-0x7F03`) in the codebase. The actual mechanism will be one of:

a) **Vendor-specific TUTK IOTYPEs** (>= `0x7000`) sent via `avSendIOCtrl`
b) **MQTT messages** to a cloud broker (like Petlibro's `MANUAL_FEEDING_SERVICE`)
c) **Proprietary HTTP/JSON API** to the device or cloud

### SMsgAVIoctrlDeviceInfoResp (68 bytes)

```
Bytes 0-15:   Model name (16-char string)
Bytes 16-31:  Vendor name (16-char string)
Bytes 32-35:  Firmware version (uint32)
Bytes 36-39:  Number of channels (uint32)
Bytes 40-43:  Total storage bytes (uint32)
Bytes 44-47:  Free storage bytes (uint32)
Bytes 48-67:  Reserved
```

## HTTP Relay

Since the TUTK SDK (`libIOTCAPIs.so`, `libAVAPIs.so`) is not freely redistributable, the recommended approach for agent use is an HTTP relay that bridges REST requests to P2P commands. The relay runs as a sidecar process.

The relay must handle **both channels** — TUTK IO Control for camera functions, and whatever channel PetUNew uses for feeding.

Expected relay API:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/connect` | POST | Establish P2P session `{uid, password}` |
| `/disconnect` | POST | Close P2P session `{uid}` |
| `/io_ctrl` | POST | Send IO command `{uid, command, payload_hex}` |
| `/snapshot/{uid}` | GET | Capture camera snapshot (decode keyframe) |
| `/stream/{uid}` | GET | Proxy video stream (RTSP/HLS) |
| `/speaker_volume` | POST | Set speaker volume `{uid, volume}` |

A relay can be built from these open-source TUTK implementations:
- [kingrollsdice/p2pcam](https://github.com/kingrollsdice/p2pcam) — Python, MIT license
- [kroo/wyzecam](https://github.com/kroo/wyzecam) — Python TUTK wrapper
- [indykoning/PyPI_p2pcam](https://github.com/indykoning/PyPI_p2pcam) — Python P2P camera library

## Reverse Engineering Next Steps

Camera IOTYPEs are now confirmed. The remaining unknowns are **feeding commands** and their transport channel. To discover them:

1. **Decompile the APK** (highest priority): `jadx cn.P2PPetCam.www.linyuan.apk`
   - Search for `avSendIOCtrl` — find any vendor-specific IOTYPE constants
   - Search for MQTT client code (`MqttClient`, `paho`, `eclipse.paho`)
   - Search for HTTP API calls to cloud endpoints
   - Look under `com.tutk` and `cn.P2PPetCam` package namespaces
2. **Network capture** (validates APK findings):
   - Laptop WiFi hotspot or Raspberry Pi AP (see Eero section below)
   - `tcpdump -i <if> -s 0 -w capture.pcap 'udp and (port 10000 or port 10001 or port 32761)'`
   - Also capture TCP for MQTT (1883/8883) and HTTP (80/443)
3. **Frida hooking** (most precise, needs rooted Android):
   - Hook `avSendIOCtrl` / `avRecvIOCtrl` to log command IDs and payloads
   - Hook any MQTT publish calls to see feeding message format
4. **Compare with [icex2/plaf203](https://github.com/icex2/plaf203)**: The Petlibro feeder has complete MQTT protocol documentation

### Network Capture with Eero Router

Eero has no packet capture capability. Workarounds:

| Approach | Difficulty | Notes |
|----------|-----------|-------|
| **Laptop WiFi hotspot** | Easy | Re-provision feeder to hotspot, run Wireshark |
| **Raspberry Pi AP** | Medium | Dedicated capture AP bridged to Eero via Ethernet |
| **Managed switch** | Easy | TP-Link TL-SG108E between modem and Eero, mirror port |

The laptop hotspot approach requires no extra hardware and captures all traffic.

## Related Brands

PetUNew, WOPET, and PetFun feeders share the same P2P platform and hardware. If your feeder works with any of these apps, this agent should work with it:

| Brand | App Package | Notes |
|-------|-------------|-------|
| PetUNew | `cn.P2PPetCam.www.linyuan` | Primary target |
| PetFun | `cn.P2PPetCam.www` | Same base namespace |
| WOPET | Separate (older P2P models) | Same hardware, interchangeable |

**Note**: Some newer WOPET models have migrated to the Tuya platform. Those would use a different integration path (tinytuya / LocalTuya).
