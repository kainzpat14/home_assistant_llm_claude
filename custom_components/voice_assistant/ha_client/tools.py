"""Tool definitions for Home Assistant interaction."""

from __future__ import annotations

from typing import Any

# Core tools - always available
CORE_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_entity_state",
            "description": "Get the current state of a Home Assistant entity. Use this to check if lights are on/off, get sensor readings, check door/window states, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "The entity ID (e.g., 'light.living_room', 'sensor.temperature')",
                    },
                },
                "required": ["entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "call_service",
            "description": "Call a Home Assistant service to control devices. Examples: turn on/off lights, set thermostat temperature, lock doors, play media.",
            "parameters": {
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": "The service domain (e.g., 'light', 'switch', 'climate', 'media_player')",
                    },
                    "service": {
                        "type": "string",
                        "description": "The service name (e.g., 'turn_on', 'turn_off', 'set_temperature')",
                    },
                    "entity_id": {
                        "type": "string",
                        "description": "The entity ID to target (e.g., 'light.living_room')",
                    },
                    "data": {
                        "type": "object",
                        "description": "Additional service data (e.g., {'brightness': 255, 'color_name': 'red'})",
                    },
                },
                "required": ["domain", "service", "entity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_entities",
            "description": "Search for entities by name, area, or domain. Use this to find entity IDs when you don't know the exact ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query - can be partial name, area name, or domain (e.g., 'kitchen', 'light', 'living room lamp')",
                    },
                    "domain": {
                        "type": "string",
                        "description": "Optional: filter by domain (e.g., 'light', 'switch', 'sensor')",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 10)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_area_entities",
            "description": "Get all entities in a specific area/room.",
            "parameters": {
                "type": "object",
                "properties": {
                    "area_name": {
                        "type": "string",
                        "description": "The area/room name (e.g., 'Living Room', 'Kitchen', 'Bedroom')",
                    },
                    "domain": {
                        "type": "string",
                        "description": "Optional: filter by domain (e.g., 'light', 'switch')",
                    },
                },
                "required": ["area_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_areas",
            "description": "List all areas/rooms configured in Home Assistant.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]

# Extended tools - loaded on demand for specific domains
LIGHT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "set_light_brightness",
            "description": "Set the brightness of a light (0-100%).",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "The light entity ID",
                    },
                    "brightness_pct": {
                        "type": "integer",
                        "description": "Brightness percentage (0-100)",
                    },
                },
                "required": ["entity_id", "brightness_pct"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_light_color",
            "description": "Set the color of an RGB light.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "The light entity ID",
                    },
                    "color_name": {
                        "type": "string",
                        "description": "Color name (e.g., 'red', 'blue', 'warm_white')",
                    },
                },
                "required": ["entity_id", "color_name"],
            },
        },
    },
]

CLIMATE_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "set_temperature",
            "description": "Set the target temperature for a thermostat/climate device.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "The climate entity ID",
                    },
                    "temperature": {
                        "type": "number",
                        "description": "Target temperature",
                    },
                },
                "required": ["entity_id", "temperature"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_hvac_mode",
            "description": "Set the HVAC mode (heat, cool, auto, off).",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "The climate entity ID",
                    },
                    "hvac_mode": {
                        "type": "string",
                        "description": "HVAC mode: 'heat', 'cool', 'heat_cool', 'auto', 'off'",
                    },
                },
                "required": ["entity_id", "hvac_mode"],
            },
        },
    },
]


def get_tools(include_extended: list[str] | None = None) -> list[dict[str, Any]]:
    """Get tool definitions.

    Args:
        include_extended: List of extended tool categories to include
                         (e.g., ['light', 'climate']).

    Returns:
        List of tool definitions in OpenAI format.
    """
    tools = CORE_TOOLS.copy()

    if include_extended:
        if "light" in include_extended:
            tools.extend(LIGHT_TOOLS)
        if "climate" in include_extended:
            tools.extend(CLIMATE_TOOLS)

    return tools
