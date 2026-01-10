"""Dynamic LLM tool discovery using Home Assistant's native LLM API."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components import llm

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

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


class LLMToolManager:
    """Manager for dynamic LLM tool discovery."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the tool manager."""
        self.hass = hass
        self._llm_api: llm.APIInstance | None = None
        self._cached_tools: dict[str, Any] | None = None

    async def get_llm_api(self) -> llm.APIInstance:
        """Get or create the LLM API instance."""
        if self._llm_api is None:
            try:
                self._llm_api = await llm.async_get_api(
                    self.hass,
                    "voice_assistant",
                    llm.LLMContext(
                        platform="voice_assistant",
                        context=None,
                        user_prompt=None,
                        language=None,
                        assistant=None,
                        device_id=None,
                    ),
                )
            except Exception as err:
                _LOGGER.error("Failed to get LLM API: %s", err)
                raise
        return self._llm_api

    async def query_tools(self, domain: str | None = None) -> list[dict[str, Any]]:
        """Query available Home Assistant tools.

        Args:
            domain: Optional domain filter (e.g., 'light', 'climate').

        Returns:
            List of tool definitions in OpenAI function format.
        """
        try:
            api = await self.get_llm_api()

            # Get all available tools from HA's LLM API
            tools = await api.async_get_tools()

            # Convert HA tools to OpenAI function format
            formatted_tools = []
            for tool in tools:
                # Filter by domain if specified
                if domain and hasattr(tool, "domain") and tool.domain != domain:
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

    def _convert_tool_to_openai_format(self, tool: llm.Tool) -> dict[str, Any] | None:
        """Convert HA tool to OpenAI function format.

        Args:
            tool: Home Assistant LLM tool.

        Returns:
            Tool in OpenAI function calling format, or None if conversion fails.
        """
        try:
            # Get tool schema
            schema = tool.parameters

            return {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or f"Execute {tool.name}",
                    "parameters": schema if schema else {"type": "object", "properties": {}, "required": []},
                },
            }
        except Exception as err:
            _LOGGER.warning("Failed to convert tool %s: %s", getattr(tool, "name", "unknown"), err)
            return None

    async def execute_tool(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a Home Assistant tool.

        Args:
            tool_name: Name of the tool to execute.
            arguments: Tool arguments.

        Returns:
            Execution result.
        """
        try:
            api = await self.get_llm_api()

            # Find the tool
            tools = await api.async_get_tools()
            tool = next((t for t in tools if t.name == tool_name), None)

            if not tool:
                return {"success": False, "error": f"Tool '{tool_name}' not found"}

            # Execute the tool
            result = await tool.async_call(self.hass, arguments)

            return {"success": True, "result": result}

        except Exception as err:
            _LOGGER.error("Error executing tool %s: %s", tool_name, err)
            return {"success": False, "error": str(err)}

    def get_initial_tools(self) -> list[dict[str, Any]]:
        """Get initial tools (just query_tools meta-tool).

        Returns:
            List with only the query_tools definition.
        """
        return [QUERY_TOOLS_DEFINITION]
