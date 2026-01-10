"""Dynamic LLM tool discovery using Home Assistant's native LLM API."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

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


class LLMToolManager:
    """Manager for dynamic LLM tool discovery using chat_log."""

    def __init__(self, chat_log: ChatLog) -> None:
        """Initialize the tool manager with chat_log.

        Args:
            chat_log: The ChatLog instance containing the llm_api.
        """
        self.chat_log = chat_log

    @property
    def llm_api(self):
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

            return {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description or f"Execute {name}",
                    "parameters": parameters if parameters else {"type": "object", "properties": {}, "required": []},
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
            from homeassistant.components.conversation.models import ToolInput

            tool_input = ToolInput(tool_name=tool_name, tool_args=arguments)
            result = await self.llm_api.async_call_tool(tool_input)

            return {"success": True, "result": result}

        except Exception as err:
            _LOGGER.error("Error executing tool %s: %s", tool_name, err)
            return {"success": False, "error": str(err)}

    @staticmethod
    def get_initial_tools() -> list[dict[str, Any]]:
        """Get initial tools (just query_tools meta-tool).

        Returns:
            List with only the query_tools definition.
        """
        return [QUERY_TOOLS_DEFINITION]
