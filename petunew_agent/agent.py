"""Agent loop for PetUNew feeder control.

This module implements a complete agent loop that uses Claude (or any
compatible LLM) to interpret natural language commands and translate
them into feeder operations via tool calls.

Usage:
    agent = PetUNewAgent.from_env()
    await agent.start()
    response = await agent.chat("Feed Gandalf 2 portions")
"""

from __future__ import annotations

import json
import os
from typing import Any

from petunew_agent.core.auth import PetUNewAuth
from petunew_agent.core.client import PetUNewClient
from petunew_agent.tools.definitions import TOOL_DEFINITIONS
from petunew_agent.tools.handler import ToolHandler

SYSTEM_PROMPT = """\
You are a pet care assistant that controls PetUNew smart WiFi camera pet feeders.
You help users manage their pets' feeding schedules, dispense food on demand,
and monitor their pets through the feeder's built-in camera.

Key behaviors:
- Always list devices first if you don't know the device_id yet.
- Confirm before dispensing food (unless the user explicitly says to feed now).
- When showing schedules, format times in a readable way (e.g., "8:00 AM").
- When a user asks to "check on" their pet, take a camera snapshot.
- Be concise but warm — these are people's pets.

Available capabilities:
- Dispense food immediately (1-10 portions)
- View and modify automatic feeding schedules
- View feeding history
- Take camera snapshots to check on the pet
- Get live stream URLs for real-time viewing
- Adjust camera settings (quality, night vision, motion detection)
- Control 2-way audio (speaker volume, microphone)
"""


class PetUNewAgent:
    """Conversational agent for PetUNew feeder control."""

    def __init__(self, client: PetUNewClient, anthropic_client: Any = None):
        self.client = client
        self.handler = ToolHandler(client)
        self._anthropic = anthropic_client
        self._messages: list[dict] = []

    @classmethod
    def from_env(cls) -> PetUNewAgent:
        """Create agent from environment variables.

        Required env vars:
            ANTHROPIC_API_KEY - for the Claude API
            PETUNEW_RELAY_URL or PETUNEW_TUTK_LIB - connection mode
            PETUNEW_DEVICE_UID - device UID (or PETUNEW_DEVICES for JSON)
        """
        auth = PetUNewAuth.from_env()
        client = PetUNewClient(auth)

        anthropic_client = None
        if os.environ.get("ANTHROPIC_API_KEY"):
            try:
                import anthropic
                anthropic_client = anthropic.Anthropic()
            except ImportError:
                pass

        return cls(client, anthropic_client)

    async def start(self) -> None:
        """Connect to PetUNew services."""
        await self.client.connect()

    async def stop(self) -> None:
        """Disconnect and clean up."""
        await self.client.disconnect()

    async def chat(self, user_message: str) -> str:
        """Process a user message and return the agent's response.

        This runs a full agent loop: sends the message to Claude with
        the PetUNew tools, executes any tool calls, and returns the
        final text response.
        """
        if not self._anthropic:
            raise RuntimeError(
                "Anthropic client not configured. Set ANTHROPIC_API_KEY "
                "or pass an anthropic client to the constructor."
            )

        self._messages.append({"role": "user", "content": user_message})

        while True:
            response = self._anthropic.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOL_DEFINITIONS,
                messages=self._messages,
            )

            # Collect the assistant response
            self._messages.append({"role": "assistant", "content": response.content})

            # Check if we need to handle tool calls
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:
                # No tool calls — extract text response
                text_parts = [b.text for b in response.content if b.type == "text"]
                return "\n".join(text_parts)

            # Execute tool calls and collect results
            tool_results = []
            for tool_use in tool_uses:
                result_str = await self.handler.handle(
                    tool_use.name, tool_use.input
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": result_str,
                    }
                )

            self._messages.append({"role": "user", "content": tool_results})

    def get_tools(self) -> list[dict]:
        """Return tool definitions for external agent integration.

        Use this when embedding PetUNew tools in a larger agent system.
        Pair with handle_tool_call() for execution.
        """
        return TOOL_DEFINITIONS

    async def handle_tool_call(self, tool_name: str, tool_input: dict) -> str:
        """Execute a tool call from an external agent.

        Args:
            tool_name: Tool name from a tool_use block.
            tool_input: Input parameters from the tool_use block.

        Returns:
            JSON string result for the tool_result content.
        """
        return await self.handler.handle(tool_name, tool_input)
