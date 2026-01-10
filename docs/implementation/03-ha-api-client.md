# Implementation Plan: Home Assistant API Client

## Overview

Implement the Home Assistant API client that provides tools for the LLM to interact with Home Assistant. This allows the LLM to discover entities, call services, and query states without using the intent system.

## Key Design Principles

1. **Minimal Initial Tools**: Start with a small set of essential tools
2. **On-Demand Tool Loading**: LLM can request more specific tools as needed
3. **Direct API Access**: Use `hass` object directly rather than REST API
4. **Token Efficiency**: Tools return only necessary information

## Files to Create/Modify

1. **Create:** `custom_components/voice_assistant/ha_client/client.py`
2. **Create:** `custom_components/voice_assistant/ha_client/tools.py`
3. **Modify:** `custom_components/voice_assistant/ha_client/__init__.py`
4. **Modify:** `custom_components/voice_assistant/conversation.py`

## Implementation Steps

### Step 1: Create Tool Definitions

Create `custom_components/voice_assistant/ha_client/tools.py`:

```python
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
```

### Step 2: Create the HA Client

Create `custom_components/voice_assistant/ha_client/client.py`:

```python
"""Home Assistant API client for LLM tool execution."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class HomeAssistantClient:
    """Client for executing Home Assistant operations."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the client."""
        self.hass = hass

    async def execute_tool(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a tool and return the result.

        Args:
            tool_name: The name of the tool to execute.
            arguments: The tool arguments.

        Returns:
            Dict with 'success' (bool) and 'result' or 'error'.
        """
        try:
            handler = getattr(self, f"_tool_{tool_name}", None)
            if handler is None:
                return {"success": False, "error": f"Unknown tool: {tool_name}"}

            result = await handler(**arguments)
            return {"success": True, "result": result}

        except Exception as err:
            _LOGGER.error("Tool execution error (%s): %s", tool_name, err)
            return {"success": False, "error": str(err)}

    async def _tool_get_entity_state(self, entity_id: str) -> dict[str, Any]:
        """Get the state of an entity."""
        state = self.hass.states.get(entity_id)
        if state is None:
            return {"error": f"Entity '{entity_id}' not found"}

        return {
            "entity_id": entity_id,
            "state": state.state,
            "attributes": dict(state.attributes),
            "last_changed": state.last_changed.isoformat(),
        }

    async def _tool_call_service(
        self,
        domain: str,
        service: str,
        entity_id: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call a Home Assistant service."""
        service_data = {"entity_id": entity_id}
        if data:
            service_data.update(data)

        await self.hass.services.async_call(
            domain,
            service,
            service_data,
            blocking=True,
        )

        return {
            "called": f"{domain}.{service}",
            "entity_id": entity_id,
            "status": "success",
        }

    async def _tool_search_entities(
        self,
        query: str,
        domain: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search for entities matching a query."""
        query_lower = query.lower()
        results = []

        for state in self.hass.states.async_all():
            # Skip if domain filter doesn't match
            if domain and not state.entity_id.startswith(f"{domain}."):
                continue

            # Check if query matches entity_id or friendly_name
            friendly_name = state.attributes.get("friendly_name", "").lower()
            entity_id_lower = state.entity_id.lower()

            if query_lower in entity_id_lower or query_lower in friendly_name:
                results.append({
                    "entity_id": state.entity_id,
                    "friendly_name": state.attributes.get("friendly_name"),
                    "state": state.state,
                    "domain": state.entity_id.split(".")[0],
                })

            if len(results) >= limit:
                break

        return results

    async def _tool_get_area_entities(
        self,
        area_name: str,
        domain: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get entities in a specific area."""
        from homeassistant.helpers import area_registry, entity_registry

        area_reg = area_registry.async_get(self.hass)
        entity_reg = entity_registry.async_get(self.hass)

        # Find area by name
        area = None
        area_name_lower = area_name.lower()
        for a in area_reg.async_list_areas():
            if a.name.lower() == area_name_lower:
                area = a
                break

        if area is None:
            return {"error": f"Area '{area_name}' not found"}

        # Get entities in area
        results = []
        for entity in entity_reg.entities.values():
            if entity.area_id != area.id:
                continue
            if domain and not entity.entity_id.startswith(f"{domain}."):
                continue

            state = self.hass.states.get(entity.entity_id)
            if state:
                results.append({
                    "entity_id": entity.entity_id,
                    "friendly_name": state.attributes.get("friendly_name"),
                    "state": state.state,
                    "domain": entity.entity_id.split(".")[0],
                })

        return results

    async def _tool_list_areas(self) -> list[dict[str, Any]]:
        """List all areas."""
        from homeassistant.helpers import area_registry

        area_reg = area_registry.async_get(self.hass)

        return [
            {"id": area.id, "name": area.name}
            for area in area_reg.async_list_areas()
        ]

    async def _tool_set_light_brightness(
        self, entity_id: str, brightness_pct: int
    ) -> dict[str, Any]:
        """Set light brightness."""
        brightness = int(brightness_pct * 255 / 100)
        await self.hass.services.async_call(
            "light",
            "turn_on",
            {"entity_id": entity_id, "brightness": brightness},
            blocking=True,
        )
        return {"entity_id": entity_id, "brightness_pct": brightness_pct}

    async def _tool_set_light_color(
        self, entity_id: str, color_name: str
    ) -> dict[str, Any]:
        """Set light color."""
        await self.hass.services.async_call(
            "light",
            "turn_on",
            {"entity_id": entity_id, "color_name": color_name},
            blocking=True,
        )
        return {"entity_id": entity_id, "color": color_name}

    async def _tool_set_temperature(
        self, entity_id: str, temperature: float
    ) -> dict[str, Any]:
        """Set thermostat temperature."""
        await self.hass.services.async_call(
            "climate",
            "set_temperature",
            {"entity_id": entity_id, "temperature": temperature},
            blocking=True,
        )
        return {"entity_id": entity_id, "temperature": temperature}

    async def _tool_set_hvac_mode(
        self, entity_id: str, hvac_mode: str
    ) -> dict[str, Any]:
        """Set HVAC mode."""
        await self.hass.services.async_call(
            "climate",
            "set_hvac_mode",
            {"entity_id": entity_id, "hvac_mode": hvac_mode},
            blocking=True,
        )
        return {"entity_id": entity_id, "hvac_mode": hvac_mode}
```

### Step 3: Update `ha_client/__init__.py`

```python
"""Home Assistant API client for LLM tool calls."""

from .client import HomeAssistantClient
from .tools import CORE_TOOLS, get_tools

__all__ = ["HomeAssistantClient", "CORE_TOOLS", "get_tools"]
```

### Step 4: Update Conversation Agent with Tool Support

Modify `conversation.py` to handle tool calls:

```python
"""Conversation agent for Voice Assistant LLM."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, Literal

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.util import ulid

from .const import (
    CONF_API_KEY,
    CONF_MAX_TOKENS,
    CONF_MODEL,
    CONF_PROVIDER,
    CONF_SYSTEM_PROMPT,
    CONF_TEMPERATURE,
    DEFAULT_MAX_TOKENS,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_TEMPERATURE,
    DOMAIN,
)
from .ha_client import HomeAssistantClient, get_tools
from .llm import create_llm_provider

if TYPE_CHECKING:
    from .llm.base import BaseLLMProvider

_LOGGER = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 5  # Prevent infinite tool loops


class VoiceAssistantConversationAgent(conversation.ConversationEntity):
    """Voice Assistant conversation agent."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the conversation agent."""
        self.hass = hass
        self.entry = entry
        self._attr_unique_id = entry.entry_id
        self._provider: BaseLLMProvider | None = None
        self._ha_client: HomeAssistantClient | None = None
        self._conversation_history: dict[str, list[dict[str, Any]]] = {}

    @property
    def provider(self) -> BaseLLMProvider:
        """Get or create the LLM provider."""
        if self._provider is None:
            self._provider = create_llm_provider(
                provider=self.entry.data[CONF_PROVIDER],
                api_key=self.entry.data[CONF_API_KEY],
                model=self.entry.data[CONF_MODEL],
                temperature=self.entry.data.get(CONF_TEMPERATURE, DEFAULT_TEMPERATURE),
                max_tokens=self.entry.data.get(CONF_MAX_TOKENS, DEFAULT_MAX_TOKENS),
            )
        return self._provider

    @property
    def ha_client(self) -> HomeAssistantClient:
        """Get or create the HA client."""
        if self._ha_client is None:
            self._ha_client = HomeAssistantClient(self.hass)
        return self._ha_client

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        """Return supported languages."""
        return "*"

    async def async_process(
        self, user_input: conversation.ConversationInput
    ) -> conversation.ConversationResult:
        """Process a user input and return a response."""
        conversation_id = user_input.conversation_id or ulid.ulid_now()

        if conversation_id not in self._conversation_history:
            self._conversation_history[conversation_id] = []

        history = self._conversation_history[conversation_id]
        messages = self._build_messages(user_input.text, history)
        tools = get_tools()

        try:
            # Process with potential tool calls
            assistant_message = await self._process_with_tools(messages, tools)

            # Update history
            history.append({"role": "user", "content": user_input.text})
            history.append({"role": "assistant", "content": assistant_message})

            if len(history) > 20:
                history = history[-20:]
                self._conversation_history[conversation_id] = history

            intent_response = intent.IntentResponse(language=user_input.language)
            intent_response.async_set_speech(assistant_message)

            return conversation.ConversationResult(
                response=intent_response,
                conversation_id=conversation_id,
            )

        except Exception as err:
            _LOGGER.error("Error processing conversation: %s", err)
            intent_response = intent.IntentResponse(language=user_input.language)
            intent_response.async_set_error(
                intent.IntentResponseErrorCode.UNKNOWN,
                f"Sorry, I encountered an error: {err}",
            )
            return conversation.ConversationResult(
                response=intent_response,
                conversation_id=conversation_id,
            )

    async def _process_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> str:
        """Process messages with tool calling support.

        Args:
            messages: Conversation messages.
            tools: Available tools.

        Returns:
            Final assistant response text.
        """
        for _ in range(MAX_TOOL_ITERATIONS):
            response = await self.provider.generate(messages, tools)

            # If no tool calls, return the content
            if "tool_calls" not in response or not response["tool_calls"]:
                return response.get("content", "")

            # Add assistant message with tool calls to history
            messages.append({
                "role": "assistant",
                "content": response.get("content"),
                "tool_calls": response["tool_calls"],
            })

            # Process each tool call
            for tool_call in response["tool_calls"]:
                tool_name = tool_call["function"]["name"]
                arguments = json.loads(tool_call["function"]["arguments"])

                _LOGGER.debug("Executing tool %s with args: %s", tool_name, arguments)

                result = await self.ha_client.execute_tool(tool_name, arguments)

                # Add tool result to messages
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(result),
                })

        # If we hit max iterations, return last content or error
        return response.get("content", "I encountered an issue processing your request.")

    def _build_messages(
        self, user_text: str, history: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Build the messages list for the LLM."""
        system_prompt = self.entry.data.get(CONF_SYSTEM_PROMPT, DEFAULT_SYSTEM_PROMPT)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ]
        messages.extend(history)
        messages.append({"role": "user", "content": user_text})

        return messages

    async def async_added_to_hass(self) -> None:
        """When entity is added to Home Assistant."""
        await super().async_added_to_hass()
        conversation.async_set_agent(self.hass, self.entry, self)

    async def async_will_remove_from_hass(self) -> None:
        """When entity is removed from Home Assistant."""
        conversation.async_unset_agent(self.hass, self.entry)
        await super().async_will_remove_from_hass()


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up conversation platform."""
    async_add_entities([VoiceAssistantConversationAgent(hass, config_entry)])
```

## Testing

After implementation:

1. Restart Home Assistant
2. Configure the voice assistant to use the Voice Assistant LLM agent
3. Test commands:
   - "What's the temperature in the living room?"
   - "Turn on the kitchen lights"
   - "List all areas in my home"
   - "Set the bedroom light to 50%"

## Expected Behavior

- LLM can query entity states
- LLM can call services to control devices
- LLM can search for entities when it doesn't know the exact ID
- Tool results are used to inform responses
- Errors are handled gracefully

## Next Steps

After completing the HA API client, proceed to:
- `04-streaming-support.md` - Implement streaming responses (optional enhancement)
