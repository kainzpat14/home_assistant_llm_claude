"""Dynamic LLM tool discovery using Home Assistant's native LLM API."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.helpers import llm
from homeassistant.util import ulid
from voluptuous_openapi import convert

if TYPE_CHECKING:
    from homeassistant.components.conversation import ChatLog

_LOGGER = logging.getLogger(__name__)

# The meta-tool that allows LLM to discover available tools
QUERY_TOOLS_DEFINITION = {
    "type": "function",
    "function": {
        "name": "query_tools",
        "description": "Query for available Home Assistant tools and services. Use this when you need to interact with Home Assistant devices, retrieve state information, or control smart home features. You can optionally filter by domain to get specific tool categories.",
        "parameters": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Optional: Filter tools by domain (e.g., 'light', 'climate', 'switch', 'sensor'). If not specified, returns all available tools.",
                },
            },
            "required": [],
        },
    },
}

# The meta-tool that allows LLM to query learned facts about the user
QUERY_FACTS_DEFINITION = {
    "type": "function",
    "function": {
        "name": "query_facts",
        "description": "Query learned facts about the user and their home. Use this when you need context like user names, family members, preferences, device nicknames, locations, or routines. Only call when you actually need this information - don't query if not needed.",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Optional: Filter facts by category ('user_name', 'family_members', 'preferences', 'device_nicknames', 'locations', 'routines'). If not specified, returns all learned facts.",
                },
            },
            "required": [],
        },
    },
}

# The meta-tool that allows LLM to learn and store facts about the user
LEARN_FACT_DEFINITION = {
    "type": "function",
    "function": {
        "name": "learn_fact",
        "description": "Store a fact about the user or their home for future reference. Use this when the user shares information you should remember (names, preferences, routines, pet names, etc.). The fact will be available in future conversations.",
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Category of the fact: 'user_name', 'family_members', 'preferences', 'device_nicknames', 'locations', 'routines'",
                    "enum": ["user_name", "family_members", "preferences", "device_nicknames", "locations", "routines"],
                },
                "key": {
                    "type": "string",
                    "description": "A unique key for this fact (e.g., 'cat_name', 'favorite_temperature', 'bedroom_light_nickname')",
                },
                "value": {
                    "type": "string",
                    "description": "The fact value to store",
                },
            },
            "required": ["category", "key", "value"],
        },
    },
}

# Music Assistant meta-tools
PLAY_MUSIC_DEFINITION = {
    "type": "function",
    "function": {
        "name": "play_music",
        "description": "Play music on a Music Assistant player. Use this for any music playback requests. Searches automatically if exact match not found. Supports artists, albums, tracks, playlists, and radio stations.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to play: artist name, album, track title, playlist, or combined (e.g., 'Queen', 'Bohemian Rhapsody', 'Queen - Innuendo')",
                },
                "media_type": {
                    "type": "string",
                    "description": "Type of media to search for",
                    "enum": ["track", "album", "artist", "playlist", "radio"],
                },
                "player": {
                    "type": "string",
                    "description": "Where to play: room name or player entity_id (e.g., 'living room', 'kitchen', 'media_player.ma_bedroom'). If not specified, uses default or first available player.",
                },
                "enqueue": {
                    "type": "string",
                    "description": "How to add to queue",
                    "enum": ["play", "replace", "next", "add"],
                    "default": "replace",
                },
                "radio_mode": {
                    "type": "boolean",
                    "description": "Enable radio mode to auto-generate similar tracks after selection finishes",
                    "default": False,
                },
            },
            "required": ["query"],
        },
    },
}

GET_NOW_PLAYING_DEFINITION = {
    "type": "function",
    "function": {
        "name": "get_now_playing",
        "description": "Get information about what's currently playing on Music Assistant players. Returns track name, artist, album, and playback state.",
        "parameters": {
            "type": "object",
            "properties": {
                "player": {
                    "type": "string",
                    "description": "Specific player to check (room name or entity_id). If not specified, returns info for all active players.",
                },
            },
            "required": [],
        },
    },
}

CONTROL_PLAYBACK_DEFINITION = {
    "type": "function",
    "function": {
        "name": "control_playback",
        "description": "Control music playback: play, pause, stop, skip, previous, volume. Use for playback control commands.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Playback control action",
                    "enum": ["play", "pause", "stop", "next", "previous", "volume_up", "volume_down", "volume_set", "shuffle", "repeat"],
                },
                "player": {
                    "type": "string",
                    "description": "Target player (room name or entity_id). If not specified, controls first active player.",
                },
                "volume_level": {
                    "type": "number",
                    "description": "Volume level 0-100 (only for volume_set action)",
                    "minimum": 0,
                    "maximum": 100,
                },
            },
            "required": ["action"],
        },
    },
}

SEARCH_MUSIC_DEFINITION = {
    "type": "function",
    "function": {
        "name": "search_music",
        "description": "Search the music library and streaming providers. Use when user wants to know what music is available or browse the library.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query: artist, album, track name, or genre",
                },
                "media_type": {
                    "type": "string",
                    "description": "Filter by media type",
                    "enum": ["track", "album", "artist", "playlist", "radio"],
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return",
                    "default": 10,
                    "maximum": 50,
                },
                "favorites_only": {
                    "type": "boolean",
                    "description": "Only search in favorites/library",
                    "default": False,
                },
            },
            "required": ["query"],
        },
    },
}

TRANSFER_MUSIC_DEFINITION = {
    "type": "function",
    "function": {
        "name": "transfer_music",
        "description": "Transfer music playback from one room/player to another. Use when user wants music to follow them or move to a different room.",
        "parameters": {
            "type": "object",
            "properties": {
                "target_player": {
                    "type": "string",
                    "description": "Where to move the music (room name or entity_id)",
                },
                "source_player": {
                    "type": "string",
                    "description": "Where to move music from. If not specified, uses first active player.",
                },
            },
            "required": ["target_player"],
        },
    },
}

GET_MUSIC_PLAYERS_DEFINITION = {
    "type": "function",
    "function": {
        "name": "get_music_players",
        "description": "Get list of available Music Assistant players and their current state. Use to discover which rooms/speakers are available for music playback.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}

# Web Search (Tavily) tool
WEB_SEARCH_DEFINITION = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web for current, factual information using Tavily. Use ONLY for queries requiring real-time data you don't have (news, weather, sports scores, stock prices, recent events). DO NOT use for general knowledge or home automation.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query for current factual information",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (1-10)",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 10,
                },
                "search_depth": {
                    "type": "string",
                    "description": "Search depth: 'basic' for quick results, 'advanced' for comprehensive search",
                    "enum": ["basic", "advanced"],
                    "default": "basic",
                },
            },
            "required": ["query"],
        },
    },
}


class LLMToolManager:
    """Manager for dynamic LLM tool discovery using chat_log."""

    def __init__(self, chat_log: ChatLog) -> None:
        """Initialize the tool manager with chat_log.

        Args:
            chat_log: The ChatLog instance containing the llm_api.
        """
        self.chat_log = chat_log

    @property
    def llm_api(self) -> llm.API | None:
        """Get the LLM API from the chat_log."""
        return self.chat_log.llm_api

    def query_tools(self, domain: str | None = None) -> list[dict[str, Any]]:
        """Query available Home Assistant tools from the llm_api.

        Args:
            domain: Optional domain filter (e.g., 'light', 'climate').

        Returns:
            List of tool definitions in OpenAI function format.
        """
        if self.llm_api is None:
            _LOGGER.warning("No LLM API available in chat_log")
            return []

        try:
            # Get tools from the llm_api
            tools = self.llm_api.tools

            # Convert HA tools to OpenAI function format
            formatted_tools = []
            for tool in tools:
                # Filter by domain if specified
                tool_name = getattr(tool, "name", "")
                if domain and not tool_name.startswith(f"{domain}.") and not tool_name.startswith(domain):
                    # Also check if the tool description mentions the domain
                    tool_desc = getattr(tool, "description", "").lower()
                    if domain.lower() not in tool_desc:
                        continue

                # Convert to OpenAI format
                formatted_tool = self._convert_tool_to_openai_format(tool)
                if formatted_tool:
                    formatted_tools.append(formatted_tool)

            _LOGGER.debug(
                "Queried %d tools%s",
                len(formatted_tools),
                f" for domain '{domain}'" if domain else "",
            )

            return formatted_tools

        except Exception as err:
            _LOGGER.error("Error querying tools: %s", err)
            return []

    def _convert_tool_to_openai_format(self, tool) -> dict[str, Any] | None:
        """Convert HA tool to OpenAI function format.

        Args:
            tool: Home Assistant LLM tool.

        Returns:
            Tool in OpenAI function calling format, or None if conversion fails.
        """
        try:
            # Get tool attributes
            name = getattr(tool, "name", None)
            description = getattr(tool, "description", None)
            parameters = getattr(tool, "parameters", None)

            if not name:
                return None

            # Convert parameters using voluptuous_openapi to handle Schema objects
            # This converts Home Assistant's voluptuous schemas to JSON-serializable dicts
            if parameters:
                _LOGGER.debug(
                    "Original parameters type for tool %s: %s",
                    name,
                    type(parameters).__name__,
                )
                custom_serializer = getattr(self.llm_api, "custom_serializer", None)
                converted_parameters = convert(parameters, custom_serializer=custom_serializer)

                # Post-process to add helpful descriptions for array fields
                # This helps the LLM understand when to use array syntax
                if "properties" in converted_parameters:
                    for prop_name, prop_schema in converted_parameters["properties"].items():
                        if prop_schema.get("type") == "array" and "description" not in prop_schema:
                            # Add description to array fields that don't have one
                            prop_schema["description"] = f"Array of {prop_name} values (use JSON array syntax: [{prop_name}1, {prop_name}2])"
                            _LOGGER.debug(
                                "Added array description for %s.%s",
                                name,
                                prop_name,
                            )

                _LOGGER.debug(
                    "Converted schema for tool %s: %s",
                    name,
                    converted_parameters,
                )
                parameters = converted_parameters
            else:
                parameters = {"type": "object", "properties": {}, "required": []}

            return {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description or f"Execute {name}",
                    "parameters": parameters,
                },
            }
        except Exception as err:
            _LOGGER.warning("Failed to convert tool: %s", err)
            return None

    async def execute_tool(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a Home Assistant tool via the llm_api.

        Args:
            tool_name: Name of the tool to execute.
            arguments: Tool arguments.

        Returns:
            Execution result.
        """
        if self.llm_api is None:
            return {"success": False, "error": "No LLM API available"}

        try:
            # Create tool input and execute via llm_api
            tool_input = llm.ToolInput(
                id=ulid.ulid_now(),
                tool_name=tool_name,
                tool_args=arguments,
            )
            result = await self.llm_api.async_call_tool(tool_input)

            return {"success": True, "result": result}

        except Exception as err:
            _LOGGER.error("Error executing tool %s: %s", tool_name, err)
            return {"success": False, "error": str(err)}

    @staticmethod
    def get_initial_tools(
        include_music: bool = False,
        include_web_search: bool = False,
    ) -> list[dict[str, Any]]:
        """Get initial meta-tools available to the LLM.

        Args:
            include_music: Whether to include Music Assistant tools.
            include_web_search: Whether to include web search tool.

        Returns:
            List with query_tools, query_facts, learn_fact, and optionally music/web search tools.
        """
        tools = [QUERY_TOOLS_DEFINITION, QUERY_FACTS_DEFINITION, LEARN_FACT_DEFINITION]

        if include_music:
            tools.extend([
                PLAY_MUSIC_DEFINITION,
                GET_NOW_PLAYING_DEFINITION,
                CONTROL_PLAYBACK_DEFINITION,
                SEARCH_MUSIC_DEFINITION,
                TRANSFER_MUSIC_DEFINITION,
                GET_MUSIC_PLAYERS_DEFINITION,
            ])

        if include_web_search:
            tools.append(WEB_SEARCH_DEFINITION)

        return tools
