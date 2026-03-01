"""Agent tool definitions for PetUNew feeder control.

These tool definitions follow the Anthropic tool_use schema and can be
passed directly to Claude or any compatible LLM agent. Each tool maps
to a PetUNewClient method.
"""

TOOL_DEFINITIONS = [
    {
        "name": "petunew_list_devices",
        "description": (
            "List all PetUNew smart feeders on the account. Returns device IDs, "
            "names, online status, and capabilities (camera, speaker, mic). "
            "Call this first to discover available feeders before performing "
            "any operations."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "petunew_get_device_status",
        "description": (
            "Get the full status of a specific PetUNew feeder, including "
            "connection state, camera settings, and current configuration."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "The device ID of the feeder to query.",
                },
            },
            "required": ["device_id"],
        },
    },
    {
        "name": "petunew_feed_now",
        "description": (
            "Dispense food from the feeder immediately. Triggers the motor "
            "to release the specified number of portions right now. Use this "
            "when the user wants to feed their pet on demand."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "The device ID of the feeder.",
                },
                "portions": {
                    "type": "integer",
                    "description": "Number of portions to dispense (1-10).",
                    "minimum": 1,
                    "maximum": 10,
                    "default": 1,
                },
            },
            "required": ["device_id"],
        },
    },
    {
        "name": "petunew_get_feed_schedules",
        "description": (
            "Retrieve all configured automatic feeding schedules for a feeder. "
            "Returns meal times, portion sizes, enabled/disabled state, and "
            "which days each schedule repeats on."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "The device ID of the feeder.",
                },
            },
            "required": ["device_id"],
        },
    },
    {
        "name": "petunew_set_feed_schedules",
        "description": (
            "Replace all feeding schedules on a feeder with a new set. "
            "Each schedule specifies a time, portion count, enabled state, "
            "and repeat days. This overwrites all existing schedules."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "The device ID of the feeder.",
                },
                "schedules": {
                    "type": "array",
                    "description": "List of feeding schedule objects.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {
                                "type": "string",
                                "description": "Name for this meal (e.g. 'Breakfast').",
                            },
                            "hour": {
                                "type": "integer",
                                "description": "Hour in 24h format (0-23).",
                                "minimum": 0,
                                "maximum": 23,
                            },
                            "minute": {
                                "type": "integer",
                                "description": "Minute (0-59).",
                                "minimum": 0,
                                "maximum": 59,
                            },
                            "portions": {
                                "type": "integer",
                                "description": "Portions to dispense (1-10).",
                                "minimum": 1,
                                "maximum": 10,
                            },
                            "enabled": {
                                "type": "boolean",
                                "description": "Whether this schedule is active.",
                                "default": True,
                            },
                            "days": {
                                "type": "array",
                                "items": {"type": "integer", "minimum": 0, "maximum": 6},
                                "description": (
                                    "Days of week to repeat (0=Mon, 6=Sun). "
                                    "Defaults to every day."
                                ),
                            },
                        },
                        "required": ["hour", "minute", "portions"],
                    },
                },
            },
            "required": ["device_id", "schedules"],
        },
    },
    {
        "name": "petunew_add_feed_schedule",
        "description": (
            "Add a single new feeding schedule without removing existing ones. "
            "The new schedule is appended to the current list."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "The device ID of the feeder.",
                },
                "hour": {
                    "type": "integer",
                    "description": "Hour in 24h format (0-23).",
                    "minimum": 0,
                    "maximum": 23,
                },
                "minute": {
                    "type": "integer",
                    "description": "Minute (0-59).",
                    "minimum": 0,
                    "maximum": 59,
                },
                "portions": {
                    "type": "integer",
                    "description": "Portions to dispense (1-10).",
                    "minimum": 1,
                    "maximum": 10,
                    "default": 1,
                },
                "label": {
                    "type": "string",
                    "description": "Name for this meal (e.g. 'Afternoon Snack').",
                },
                "days": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 0, "maximum": 6},
                    "description": "Days of week (0=Mon, 6=Sun). Defaults to every day.",
                },
            },
            "required": ["device_id", "hour", "minute"],
        },
    },
    {
        "name": "petunew_remove_feed_schedule",
        "description": (
            "Remove a feeding schedule by its index (0-based). Use "
            "petunew_get_feed_schedules first to see current schedules "
            "and their indices."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "The device ID of the feeder.",
                },
                "schedule_index": {
                    "type": "integer",
                    "description": "0-based index of the schedule to remove.",
                    "minimum": 0,
                },
            },
            "required": ["device_id", "schedule_index"],
        },
    },
    {
        "name": "petunew_get_feeding_records",
        "description": (
            "Retrieve recent feeding history — both scheduled and manual "
            "feedings. Shows timestamps, portions dispensed, and whether "
            "each feeding was successful."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "The device ID of the feeder.",
                },
            },
            "required": ["device_id"],
        },
    },
    {
        "name": "petunew_take_snapshot",
        "description": (
            "Capture a photo from the feeder's built-in camera. Returns "
            "a URL to the image. Use this to check on the pet visually."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "The device ID of the feeder.",
                },
            },
            "required": ["device_id"],
        },
    },
    {
        "name": "petunew_get_stream_info",
        "description": (
            "Get the live video stream URL for a feeder camera. Returns "
            "RTSP or HLS URLs that can be opened in a media player."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "The device ID of the feeder.",
                },
            },
            "required": ["device_id"],
        },
    },
    {
        "name": "petunew_set_camera_quality",
        "description": (
            "Change the camera stream quality. Options are 'hd' (1080p), "
            "'sd' (480p), or 'smooth' (lowest bandwidth)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "The device ID of the feeder.",
                },
                "quality": {
                    "type": "string",
                    "enum": ["hd", "sd", "smooth"],
                    "description": "Stream quality level.",
                },
            },
            "required": ["device_id", "quality"],
        },
    },
    {
        "name": "petunew_toggle_camera",
        "description": "Turn the feeder camera on or off.",
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "The device ID of the feeder.",
                },
                "on": {
                    "type": "boolean",
                    "description": "True to turn on, False to turn off.",
                },
            },
            "required": ["device_id", "on"],
        },
    },
    {
        "name": "petunew_set_speaker_volume",
        "description": (
            "Set the feeder's speaker volume. Use this before playing "
            "audio or speaking through the 2-way audio feature. "
            "0 = muted, 100 = maximum."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "The device ID of the feeder.",
                },
                "volume": {
                    "type": "integer",
                    "description": "Volume level (0-100).",
                    "minimum": 0,
                    "maximum": 100,
                },
            },
            "required": ["device_id", "volume"],
        },
    },
    {
        "name": "petunew_toggle_microphone",
        "description": (
            "Enable or disable the microphone for 2-way audio. When enabled, "
            "audio from the agent/user side can be heard through the feeder's "
            "speaker."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "The device ID of the feeder.",
                },
                "on": {
                    "type": "boolean",
                    "description": "True to enable, False to disable.",
                },
            },
            "required": ["device_id", "on"],
        },
    },
    {
        "name": "petunew_set_night_vision",
        "description": (
            "Configure night vision mode for the camera. "
            "'auto' lets the camera decide based on ambient light."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "The device ID of the feeder.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["off", "on", "auto"],
                    "description": "Night vision mode.",
                },
            },
            "required": ["device_id", "mode"],
        },
    },
    {
        "name": "petunew_set_motion_detection",
        "description": (
            "Enable or disable motion detection alerts from the camera. "
            "When enabled, the feeder can notify when it detects movement."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "The device ID of the feeder.",
                },
                "enabled": {
                    "type": "boolean",
                    "description": "True to enable, False to disable.",
                },
            },
            "required": ["device_id", "enabled"],
        },
    },
    {
        "name": "petunew_get_camera_settings",
        "description": (
            "Get current camera configuration including quality, night vision "
            "mode, motion detection, speaker, and microphone status."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "device_id": {
                    "type": "string",
                    "description": "The device ID of the feeder.",
                },
            },
            "required": ["device_id"],
        },
    },
]
