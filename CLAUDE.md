# CLAUDE.md

This file provides guidance to Claude Code when working on the PetUNew Agent codebase.

## Project Overview

PetUNew Agent is a Python library and CLI for controlling PetUNew smart WiFi camera pet feeders through natural language, CLI commands, or as tools in any LLM agent. It communicates over the ThroughTek (TUTK) Kalay P2P protocol — not Tuya, not REST/MQTT.

## Architecture

```
petunew_agent/
├── agent.py          # Claude agent loop (tool_use based)
├── cli.py            # CLI entry point (petunew command)
├── mcp_server.py     # MCP server for Claude Desktop / Code
├── core/
│   ├── auth.py       # Device credentials and config management
│   ├── client.py     # PetUNewClient — high-level async API
│   └── tutk.py       # TUTK P2P protocol layer (binary over UDP)
├── models/
│   ├── device.py     # Device model
│   ├── feeding.py    # FeedSchedule, FeedingRecord
│   └── camera.py     # CameraSettings, StreamInfo
└── tools/
    ├── definitions.py  # 17 agent tool definitions (Anthropic format)
    └── handler.py      # Tool call dispatcher → PetUNewClient
```

### Connection Modes

- **HTTP Relay (recommended)**: Agent → HTTP relay (localhost:8100) → Feeder via P2P. Relay runs as a sidecar process and bridges REST to TUTK.
- **Native TUTK SDK**: Agent loads `libIOTCAPIs.so` + `libAVAPIs.so` via ctypes. Not freely redistributable.

## Build and Run

```bash
# Install (editable)
pip install -e .

# Install with agent support (anthropic SDK)
pip install -e ".[agent]"

# Install with dev dependencies
pip install -e ".[dev]"

# Run CLI
petunew devices
petunew feed <UID> --portions 2
petunew chat

# Run tests
pytest
```

## Key Commands

| Command | Description |
|---------|-------------|
| `petunew chat` | Interactive agent conversation |
| `petunew devices` | List configured feeders |
| `petunew feed <UID>` | Dispense food (--portions N) |
| `petunew schedules <UID>` | View feeding schedules |
| `petunew snapshot <UID>` | Take camera photo |
| `petunew stream <UID>` | Get stream connection info |
| `petunew configure` | Interactive credential setup |
| `petunew tools` | Dump tool definitions as JSON |

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `ANTHROPIC_API_KEY` | Claude API key (agent/chat mode) |
| `PETUNEW_RELAY_URL` | HTTP relay address (e.g. `http://localhost:8100`) |
| `PETUNEW_DEVICE_UID` | Device identifier |
| `PETUNEW_DEVICE_PASS` | Device password (default: `admin`) |
| `PETUNEW_DEVICE_NAME` | Display name for the device |
| `PETUNEW_TUTK_LIB` | Path to TUTK SDK libraries (native mode) |

## Code Conventions

- Python 3.10+ with `from __future__ import annotations`
- Async/await throughout (`PetUNewClient` is fully async)
- Pydantic v2 models for data validation
- `match` statements for CLI command dispatch
- Agent loop uses `claude-sonnet-4-20250514` model
- Tool definitions follow Anthropic's tool_use format

## Protocol Notes

- Camera commands use standard TUTK IOTYPEs from `AVIOCTRLDEFs.h` — these are confirmed and stable.
- Feeding commands (`0x7F00`-`0x7F03`) are placeholder IDs. The actual transport mechanism (vendor IOTYPEs, MQTT, or HTTP) is unconfirmed and requires APK decompilation of `cn.P2PPetCam.www.linyuan` to verify.
- Related brands (WOPET, PetFun) share the same P2P platform and hardware.

## Testing

```bash
pytest                    # Run all tests
pytest -x                 # Stop on first failure
pytest -v                 # Verbose output
pytest tests/test_foo.py  # Specific test file
```

## CI

GitHub Actions runs `claude-md-lint` on push and PR to lint CLAUDE.md and related documentation. The lint must score 95+ to pass.
