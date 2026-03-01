"""CLI entry point for PetUNew agent.

Provides both interactive chat mode and direct command execution.

Usage:
    # Interactive chat
    petunew chat

    # Direct commands
    petunew devices
    petunew feed <device_uid> --portions 2
    petunew schedules <device_uid>
    petunew snapshot <device_uid>
    petunew configure
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from petunew_agent.core.auth import PetUNewAuth, DeviceCredentials
from petunew_agent.core.client import PetUNewClient
from petunew_agent.agent import PetUNewAgent


def main():
    parser = argparse.ArgumentParser(
        prog="petunew",
        description="Agent interface for PetUNew smart WiFi camera pet feeders",
    )
    sub = parser.add_subparsers(dest="command")

    # chat — interactive agent mode
    sub.add_parser("chat", help="Interactive chat with the PetUNew agent")

    # devices — list feeders
    sub.add_parser("devices", help="List all configured feeders")

    # feed — manual feeding
    feed_p = sub.add_parser("feed", help="Dispense food now")
    feed_p.add_argument("device_uid", help="Device UID")
    feed_p.add_argument(
        "--portions", "-p", type=int, default=1, help="Portions (1-10)"
    )

    # schedules — view/manage schedules
    sched_p = sub.add_parser("schedules", help="View feeding schedules")
    sched_p.add_argument("device_uid", help="Device UID")

    # snapshot — take a photo
    snap_p = sub.add_parser("snapshot", help="Take a camera snapshot")
    snap_p.add_argument("device_uid", help="Device UID")

    # stream — get stream info
    stream_p = sub.add_parser("stream", help="Get stream connection info")
    stream_p.add_argument("device_uid", help="Device UID")

    # configure — set up credentials
    sub.add_parser("configure", help="Set up PetUNew device credentials")

    # tools — dump tool definitions for agent integration
    sub.add_parser("tools", help="Print agent tool definitions as JSON")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    asyncio.run(_run(args))


async def _run(args: argparse.Namespace):
    if args.command == "configure":
        await _configure()
        return

    if args.command == "tools":
        from petunew_agent.tools.definitions import TOOL_DEFINITIONS
        print(json.dumps(TOOL_DEFINITIONS, indent=2))
        return

    if args.command == "chat":
        await _chat()
        return

    # All other commands need a connected client
    auth = PetUNewAuth.from_env()
    async with PetUNewClient(auth) as client:
        match args.command:
            case "devices":
                devices = await client.list_devices()
                for d in devices:
                    status = "ONLINE" if d.is_online() else "OFFLINE"
                    print(f"  {d.device_id}  {d.name}  [{status}]")
                if not devices:
                    print("  No devices configured.")

            case "feed":
                record = await client.feed_now(args.device_uid, args.portions)
                unit = "portion" if record.portions == 1 else "portions"
                print(f"  Dispensed {record.portions} {unit}")

            case "schedules":
                schedules = await client.get_feed_schedules(args.device_uid)
                for i, s in enumerate(schedules):
                    print(f"  [{i}] {s.describe()}")
                if not schedules:
                    print("  No schedules configured.")

            case "snapshot":
                snap = await client.take_snapshot(args.device_uid)
                if snap.image_bytes:
                    size = len(snap.image_bytes)
                    print(f"  Snapshot captured ({size} bytes)")
                else:
                    print("  Snapshot request sent (no data returned)")

            case "stream":
                info = await client.get_stream_info(args.device_uid)
                if info.rtsp_url:
                    print(f"  Stream: {info.rtsp_url}")
                elif info.p2p_config:
                    print(f"  P2P stream: {json.dumps(info.p2p_config)}")
                else:
                    print("  No stream info available")


async def _chat():
    """Run interactive agent chat loop."""
    agent = PetUNewAgent.from_env()
    try:
        await agent.start()
        print("PetUNew Agent ready. Type 'quit' to exit.\n")
        while True:
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if user_input.lower() in ("quit", "exit", "q"):
                break
            if not user_input:
                continue
            response = await agent.chat(user_input)
            print(f"\nAgent: {response}\n")
    finally:
        await agent.stop()


async def _configure():
    """Interactive credential setup."""
    print("PetUNew Agent Configuration\n")
    print("PetUNew feeders use the ThroughTek (TUTK) Kalay P2P platform.")
    print("Each device is identified by a UID (found in the Pet-U app).\n")

    print("Connection mode:")
    print("  1. HTTP relay (recommended — runs TUTK bridge as a sidecar)")
    print("  2. Native TUTK SDK (requires libIOTCAPIs.so / libAVAPIs.so)")

    choice = input("\nSelection [1]: ").strip() or "1"

    auth = PetUNewAuth()

    if choice == "1":
        relay = input("  Relay URL [http://localhost:8100]: ").strip()
        auth.relay_url = relay or "http://localhost:8100"
    else:
        lib_path = input("  Path to TUTK SDK libraries: ").strip()
        auth.tutk_lib_path = lib_path

    # Add devices
    print("\nAdd your feeder(s):")
    while True:
        uid = input("  Device UID (or Enter to finish): ").strip()
        if not uid:
            break
        name = input("  Device name [PetUNew Feeder]: ").strip() or "PetUNew Feeder"
        password = input("  Device password [admin]: ").strip() or "admin"
        auth.devices.append(DeviceCredentials(uid=uid, password=password, name=name))
        print(f"  Added: {name} ({uid})")

    if auth.devices:
        auth.save_config()
        print(f"\nSaved {len(auth.devices)} device(s) to ~/.config/petunew/config.json")
    else:
        print("\nNo devices added. Run 'petunew configure' again to add devices.")


if __name__ == "__main__":
    main()
