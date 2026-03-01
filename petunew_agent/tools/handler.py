"""Tool handler that maps agent tool calls to PetUNewClient methods.

This module bridges LLM tool_use calls to actual device operations.
An agent loop calls ToolHandler.handle() with the tool name and input,
and gets back a structured result to return to the model.
"""

from __future__ import annotations

import json
from datetime import time
from typing import Any

from petunew_agent.core.client import PetUNewClient
from petunew_agent.models.camera import StreamQuality
from petunew_agent.models.feeding import FeedSchedule


class ToolHandler:
    """Dispatches agent tool calls to PetUNewClient operations."""

    def __init__(self, client: PetUNewClient):
        self.client = client

    async def handle(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        """Execute a tool call and return the JSON result string.

        Args:
            tool_name: Name matching one of the TOOL_DEFINITIONS.
            tool_input: Parameters from the agent's tool_use block.

        Returns:
            JSON string with the operation result, suitable for
            returning as tool_result content.
        """
        try:
            result = await self._dispatch(tool_name, tool_input)
            return json.dumps(result, default=str)
        except Exception as e:
            return json.dumps({"error": str(e), "tool": tool_name})

    async def _dispatch(self, tool_name: str, params: dict) -> Any:
        match tool_name:
            case "petunew_list_devices":
                devices = await self.client.list_devices()
                return [d.model_dump() for d in devices]

            case "petunew_get_device_status":
                device = await self.client.get_device(params["device_id"])
                status = await self.client.get_device_status(params["device_id"])
                return {"device": device.model_dump(), "status": status}

            case "petunew_feed_now":
                record = await self.client.feed_now(
                    params["device_id"],
                    portions=params.get("portions", 1),
                )
                return record.model_dump()

            case "petunew_get_feed_schedules":
                schedules = await self.client.get_feed_schedules(params["device_id"])
                return [
                    {**s.model_dump(), "description": s.describe()}
                    for s in schedules
                ]

            case "petunew_set_feed_schedules":
                schedules = [
                    FeedSchedule(
                        label=s.get("label", ""),
                        meal_time=time(hour=s["hour"], minute=s["minute"]),
                        portions=s["portions"],
                        enabled=s.get("enabled", True),
                        repeat_days=s.get("days", list(range(7))),
                    )
                    for s in params["schedules"]
                ]
                await self.client.set_feed_schedules(
                    params["device_id"], schedules
                )
                return {"success": True, "schedule_count": len(schedules)}

            case "petunew_add_feed_schedule":
                updated = await self.client.add_feed_schedule(
                    device_id=params["device_id"],
                    meal_time=time(hour=params["hour"], minute=params["minute"]),
                    portions=params.get("portions", 1),
                    label=params.get("label", ""),
                    days=params.get("days"),
                )
                return [
                    {**s.model_dump(), "description": s.describe()}
                    for s in updated
                ]

            case "petunew_remove_feed_schedule":
                updated = await self.client.remove_feed_schedule(
                    params["device_id"], params["schedule_index"]
                )
                return [
                    {**s.model_dump(), "description": s.describe()}
                    for s in updated
                ]

            case "petunew_get_feeding_records":
                records = await self.client.get_feeding_records(params["device_id"])
                return [r.model_dump() for r in records]

            case "petunew_take_snapshot":
                snap = await self.client.take_snapshot(params["device_id"])
                return snap.model_dump(exclude={"image_bytes"})

            case "petunew_get_stream_info":
                info = await self.client.get_stream_info(params["device_id"])
                return info.model_dump()

            case "petunew_set_camera_quality":
                quality = StreamQuality(params["quality"])
                await self.client.set_camera_quality(params["device_id"], quality)
                return {"success": True, "quality": quality.value}

            case "petunew_toggle_camera":
                await self.client.toggle_camera(params["device_id"], params["on"])
                return {"success": True, "camera_on": params["on"]}

            case "petunew_set_speaker_volume":
                await self.client.set_speaker(params["device_id"], params["volume"])
                return {"success": True, "volume": params["volume"]}

            case "petunew_toggle_microphone":
                await self.client.toggle_microphone(params["device_id"], params["on"])
                return {"success": True, "microphone_on": params["on"]}

            case "petunew_set_night_vision":
                await self.client.set_night_vision(
                    params["device_id"], params["mode"]
                )
                return {"success": True, "mode": params["mode"]}

            case "petunew_set_motion_detection":
                await self.client.set_motion_detection(
                    params["device_id"], params["enabled"]
                )
                return {"success": True, "motion_detection": params["enabled"]}

            case "petunew_get_camera_settings":
                settings = await self.client.get_camera_settings(
                    params["device_id"]
                )
                return settings.model_dump()

            case _:
                raise ValueError(f"Unknown tool: {tool_name}")
