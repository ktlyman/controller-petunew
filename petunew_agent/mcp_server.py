"""MCP (Model Context Protocol) server for PetUNew feeders.

Exposes PetUNew feeder tools as an MCP server, so any MCP-compatible
agent (Claude Desktop, Claude Code, etc.) can control feeders directly.

Usage:
    python -m petunew_agent.mcp_server

Configure in Claude Desktop's claude_desktop_config.json:
    {
        "mcpServers": {
            "petunew": {
                "command": "python",
                "args": ["-m", "petunew_agent.mcp_server"],
                "env": {
                    "PETUNEW_RELAY_URL": "http://localhost:8100",
                    "PETUNEW_DEVICE_UID": "XXXXXXXXXX",
                    "PETUNEW_DEVICE_NAME": "My Feeder"
                }
            }
        }
    }
"""

from __future__ import annotations

import asyncio
import json
import sys

from petunew_agent.core.auth import PetUNewAuth
from petunew_agent.core.client import PetUNewClient
from petunew_agent.tools.definitions import TOOL_DEFINITIONS
from petunew_agent.tools.handler import ToolHandler

# MCP protocol uses JSON-RPC 2.0 over stdio
_client: PetUNewClient | None = None
_handler: ToolHandler | None = None


async def _ensure_client() -> ToolHandler:
    global _client, _handler
    if _handler is None:
        auth = PetUNewAuth.from_env()
        _client = PetUNewClient(auth)
        await _client.connect()
        _handler = ToolHandler(_client)
    return _handler


def _make_response(id: int | str, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": id, "result": result}


def _make_error(id: int | str | None, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}


async def _handle_request(request: dict) -> dict:
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params", {})

    match method:
        case "initialize":
            return _make_response(req_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {
                    "name": "petunew",
                    "version": "0.1.0",
                },
            })

        case "notifications/initialized":
            return None  # No response for notifications

        case "tools/list":
            tools = []
            for t in TOOL_DEFINITIONS:
                tools.append({
                    "name": t["name"],
                    "description": t["description"],
                    "inputSchema": t["input_schema"],
                })
            return _make_response(req_id, {"tools": tools})

        case "tools/call":
            handler = await _ensure_client()
            tool_name = params.get("name", "")
            tool_input = params.get("arguments", {})
            result_str = await handler.handle(tool_name, tool_input)
            return _make_response(req_id, {
                "content": [{"type": "text", "text": result_str}],
            })

        case _:
            return _make_error(req_id, -32601, f"Method not found: {method}")


async def _run_server():
    """Run the MCP server over stdio."""
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)

    write_transport, write_protocol = await asyncio.get_event_loop().connect_write_pipe(
        asyncio.streams.FlowControlMixin, sys.stdout
    )
    writer = asyncio.StreamWriter(write_transport, write_protocol, reader, asyncio.get_event_loop())

    while True:
        line = await reader.readline()
        if not line:
            break

        try:
            request = json.loads(line.decode().strip())
        except json.JSONDecodeError:
            continue

        response = await _handle_request(request)
        if response is not None:
            response_bytes = (json.dumps(response) + "\n").encode()
            writer.write(response_bytes)
            await writer.drain()


def main():
    try:
        asyncio.run(_run_server())
    except KeyboardInterrupt:
        pass
    finally:
        if _client:
            asyncio.run(_client.disconnect())


if __name__ == "__main__":
    main()
