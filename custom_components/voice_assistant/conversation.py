"""Conversation agent for Voice Assistant LLM."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any, AsyncIterator, Literal

from homeassistant.components import conversation
from homeassistant.components.conversation import (
    AssistantContent,
    ToolResultContent,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent, llm
from homeassistant.util import ulid

from .const import (
    CONF_API_KEY,
    CONF_ENABLE_STREAMING,
    CONF_LLM_HASS_API,
    CONF_MAX_TOKENS,
    CONF_MODEL,
    CONF_PROVIDER,
    CONF_SYSTEM_PROMPT,
    CONF_TEMPERATURE,
    DEFAULT_ENABLE_STREAMING,
    DEFAULT_MAX_TOKENS,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_TEMPERATURE,
    DOMAIN,
)
from .llm import create_llm_provider
from .llm.base import StreamChunk
from .llm_tools import LLMToolManager

if TYPE_CHECKING:
    from homeassistant.components.conversation import ChatLog

    from .llm.base import BaseLLMProvider

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG)

MAX_TOOL_ITERATIONS = 5  # Prevent infinite tool loops


class VoiceAssistantConversationAgent(conversation.ConversationEntity):
    """Voice Assistant conversation agent."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supports_streaming = True

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

    def _get_config(self, key: str, default: Any = None) -> Any:
        """Get config value from options (preferred) or data (fallback).

        Args:
            key: Configuration key.
            default: Default value if not found.

        Returns:
            Configuration value.
        """
        return self.entry.options.get(key, self.entry.data.get(key, default))

    @property
    def provider(self) -> BaseLLMProvider:
        """Get or create the LLM provider."""
        if self._provider is None:
            self._provider = create_llm_provider(
                provider=self._get_config(CONF_PROVIDER),
                api_key=self.entry.data[CONF_API_KEY],  # API key is always in data
                model=self._get_config(CONF_MODEL),
                temperature=self._get_config(CONF_TEMPERATURE, DEFAULT_TEMPERATURE),
                max_tokens=self._get_config(CONF_MAX_TOKENS, DEFAULT_MAX_TOKENS),
            )
        return self._provider

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        """Return supported languages."""
        return "*"

    @property
    def supported_features(self) -> conversation.ConversationEntityFeature:
        """Return supported features."""
        features = conversation.ConversationEntityFeature(0)
        if self._get_config(CONF_LLM_HASS_API):
            features |= conversation.ConversationEntityFeature.CONTROL
        return features


    async def _async_handle_message(
        self,
        user_input: conversation.ConversationInput,
        chat_log: ChatLog,
    ) -> conversation.ConversationResult:
        """Handle a message from the user.

        Args:
            user_input: The user's input.
            chat_log: The chat log containing llm_api and conversation history.

        Returns:
            The conversation result.
        """
        # Provide LLM data to chat_log to set up llm_api
        try:
            await chat_log.async_provide_llm_data(
                user_input.as_llm_context(DOMAIN),
                self._get_config(CONF_LLM_HASS_API),
                self._get_config(CONF_SYSTEM_PROMPT, DEFAULT_SYSTEM_PROMPT),
                None,  # Ignore HA's extra_system_prompt - use only our configured prompt
            )
            _LOGGER.debug("Provided LLM data with our system prompt, ignoring HA's extra prompt")
        except conversation.ConverseError as err:
            _LOGGER.error("Error providing LLM data: %s", err)
            return err.as_conversation_result()

        # Handle the chat log with streaming support
        await self._async_handle_chat_log(chat_log, user_input)

        return conversation.async_get_result_from_chat_log(user_input, chat_log)

    async def _async_handle_chat_log(
        self,
        chat_log: ChatLog,
        user_input: conversation.ConversationInput,
    ) -> None:
        """Process the chat log with optional streaming.

        Args:
            chat_log: The chat log to process.
            user_input: The original user input.
        """
        # Create tool manager with access to chat_log's llm_api
        tool_manager = LLMToolManager(chat_log)

        # Start with only query_tools - LLM will request more if needed
        current_tools = LLMToolManager.get_initial_tools()

        # Build messages from chat_log content and add system prompt
        messages = self._build_messages(
            user_input.text,
            chat_log,
            self._get_config(CONF_SYSTEM_PROMPT, DEFAULT_SYSTEM_PROMPT),
        )

        # Check if streaming is enabled
        streaming_enabled = self._get_config(CONF_ENABLE_STREAMING, DEFAULT_ENABLE_STREAMING)

        if streaming_enabled:
            _LOGGER.debug("Streaming enabled, using streaming mode")
            await self._process_with_streaming(
                messages, current_tools, tool_manager, chat_log, user_input
            )
        else:
            _LOGGER.debug("Streaming disabled, using non-streaming mode")
            await self._process_without_streaming(
                messages, current_tools, tool_manager, chat_log, user_input
            )

    async def _process_without_streaming(
        self,
        messages: list[dict[str, Any]],
        current_tools: list[dict[str, Any]],
        tool_manager: LLMToolManager,
        chat_log: ChatLog,
        user_input: conversation.ConversationInput,
    ) -> None:
        """Process without streaming - original implementation.

        Args:
            messages: Conversation messages.
            current_tools: Currently available tools.
            tool_manager: The tool manager.
            chat_log: The chat log.
            user_input: The user input.
        """
        # Process with potential tool calls
        assistant_message = await self._process_with_tools(
            messages, current_tools, tool_manager, chat_log, user_input
        )

        # Add the final assistant response to chat_log
        final_assistant_content = AssistantContent(
            agent_id=DOMAIN,
            content=assistant_message,
        )
        chat_log.async_add_assistant_content_without_tools(final_assistant_content)
        _LOGGER.debug("Added final assistant response to chat_log for conversation history")

    async def _process_with_streaming(
        self,
        messages: list[dict[str, Any]],
        current_tools: list[dict[str, Any]],
        tool_manager: LLMToolManager,
        chat_log: ChatLog,
        user_input: conversation.ConversationInput,
    ) -> None:
        """Process with streaming using chat_log.async_add_delta_content_stream.

        Args:
            messages: Conversation messages.
            current_tools: Currently available tools.
            tool_manager: The tool manager.
            chat_log: The chat log.
            user_input: The user input.
        """
        # Use async_add_delta_content_stream to handle streaming
        async for _ in chat_log.async_add_delta_content_stream(
            self.entity_id,
            self._stream_response_with_tools(
                messages, current_tools, tool_manager, chat_log, user_input
            ),
        ):
            pass  # The chat_log handles adding content internally

    async def _stream_response_with_tools(
        self,
        messages: list[dict[str, Any]],
        current_tools: list[dict[str, Any]],
        tool_manager: LLMToolManager,
        chat_log: ChatLog,
        user_input: conversation.ConversationInput,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream LLM response with tool call handling.

        This generator yields content deltas for streaming. Tool calls are handled
        without yielding, and only the final text response is streamed.

        Args:
            messages: Conversation messages.
            current_tools: Currently available tools.
            tool_manager: The tool manager.
            chat_log: The chat log.
            user_input: The user input.

        Yields:
            Delta dictionaries with "content" key.
        """
        for iteration in range(MAX_TOOL_ITERATIONS):
            _LOGGER.debug("Streaming iteration %d starting", iteration + 1)

            accumulated_content = ""
            tool_calls = None

            # Stream from LLM and accumulate
            async for chunk in self.provider.generate_stream_with_tools(messages, current_tools):
                if chunk.content:
                    accumulated_content += chunk.content
                    # Yield content delta immediately for streaming
                    yield {"content": chunk.content}
                if chunk.is_final and chunk.tool_calls:
                    tool_calls = chunk.tool_calls

            # If no tool calls, we're done (content already streamed)
            if not tool_calls:
                _LOGGER.debug("No tool calls, streaming complete")
                return

            # Handle tool calls (not streamed to user)
            _LOGGER.info("Processing %d tool call(s) in iteration %d", len(tool_calls), iteration + 1)

            # Separate query_tools from HA tools
            query_tools_calls = []
            ha_tool_calls = []

            for tool_call in tool_calls:
                tool_name = tool_call["function"]["name"]
                if tool_name == "query_tools":
                    query_tools_calls.append(tool_call)
                else:
                    ha_tool_calls.append(tool_call)

            # Add assistant message with tool calls to history
            messages.append({
                "role": "assistant",
                "content": accumulated_content,
                "tool_calls": tool_calls,
            })

            # Handle query_tools
            if query_tools_calls:
                query_tools_summary = []
                for tool_call in query_tools_calls:
                    arguments = json.loads(tool_call["function"]["arguments"])
                    _LOGGER.info("Handling query_tools: %s", arguments)

                    result = self._handle_query_tools(arguments, current_tools, tool_manager)

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": json.dumps(result),
                    })

                    domain_filter = arguments.get("domain", "all domains")
                    if result.get("success"):
                        tools_found = result.get("result", {}).get("tools", [])
                        query_tools_summary.append(
                            f"Discovered {len(tools_found)} tools for {domain_filter}"
                        )

                if query_tools_summary:
                    summary_content = AssistantContent(
                        agent_id=DOMAIN,
                        content="\n".join(query_tools_summary),
                    )
                    chat_log.async_add_assistant_content_without_tools(summary_content)

            # Handle HA tools
            if ha_tool_calls:
                _LOGGER.info("Processing %d HA tool call(s)", len(ha_tool_calls))

                tool_inputs = self._convert_tool_calls_to_inputs(ha_tool_calls, user_input)

                assistant_content = AssistantContent(
                    agent_id=DOMAIN,
                    content=accumulated_content,
                    tool_calls=tool_inputs,
                )

                async for tool_result in chat_log.async_add_assistant_content(assistant_content):
                    _LOGGER.info(
                        "Tool %s executed",
                        tool_result.tool_name,
                    )

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_result.tool_call_id,
                        "content": json.dumps(tool_result.tool_result),
                    })

        # Max iterations reached
        _LOGGER.warning("Hit max streaming iterations (%d)", MAX_TOOL_ITERATIONS)
        yield {"content": "I encountered an issue processing your request."}

    def _convert_tool_calls_to_inputs(
        self,
        tool_calls: list[dict[str, Any]],
        user_input: conversation.ConversationInput,
    ) -> list[llm.ToolInput]:
        """Convert Groq tool calls to Home Assistant ToolInput format.

        Args:
            tool_calls: Tool calls from Groq API.
            user_input: The original user input for context.

        Returns:
            List of ToolInput objects for Home Assistant.
        """
        tool_inputs = []
        for tool_call in tool_calls:
            tool_name = tool_call["function"]["name"]
            # Parse arguments from JSON string to dict
            try:
                tool_args = json.loads(tool_call["function"]["arguments"])
            except json.JSONDecodeError:
                _LOGGER.warning(
                    "Failed to parse tool arguments for %s: %s",
                    tool_name,
                    tool_call["function"]["arguments"],
                )
                tool_args = {}

            tool_input = llm.ToolInput(
                id=tool_call["id"],
                tool_name=tool_name,
                tool_args=tool_args,
            )
            tool_inputs.append(tool_input)
            _LOGGER.debug(
                "Converted tool call: %s with args: %s (id: %s)",
                tool_name,
                tool_args,
                tool_call["id"],
            )

        return tool_inputs

    async def _process_with_tools(
        self,
        messages: list[dict[str, Any]],
        current_tools: list[dict[str, Any]],
        tool_manager: LLMToolManager,
        chat_log: ChatLog,
        user_input: conversation.ConversationInput,
    ) -> str:
        """Process messages with dynamic tool discovery.

        Args:
            messages: Conversation messages.
            current_tools: Currently available tools.
            tool_manager: The tool manager for discovering and executing tools.
            chat_log: The chat log for storing conversation content.
            user_input: The original user input for context.

        Returns:
            Final assistant response text.
        """
        for iteration in range(MAX_TOOL_ITERATIONS):
            _LOGGER.debug("Tool iteration %d starting", iteration + 1)

            # Generate with currently available tools
            response = await self.provider.generate(messages, current_tools)

            # If no tool calls, return the content
            if "tool_calls" not in response or not response["tool_calls"]:
                _LOGGER.debug("No tool calls in response, returning content")
                return response.get("content", "")

            tool_calls = response["tool_calls"]
            _LOGGER.info("Received %d tool call(s) in iteration %d", len(tool_calls), iteration + 1)

            # Separate query_tools from real HA tools
            query_tools_calls = []
            ha_tool_calls = []

            for tool_call in tool_calls:
                tool_name = tool_call["function"]["name"]
                if tool_name == "query_tools":
                    query_tools_calls.append(tool_call)
                else:
                    ha_tool_calls.append(tool_call)

            # Add assistant message with tool calls to history for LLM context
            messages.append({
                "role": "assistant",
                "content": response.get("content"),
                "tool_calls": tool_calls,
            })

            # Handle query_tools locally (not in chat_log - it's an internal meta-tool)
            if query_tools_calls:
                query_tools_summary = []
                for tool_call in query_tools_calls:
                    arguments = json.loads(tool_call["function"]["arguments"])
                    _LOGGER.info("Handling query_tools with args: %s", arguments)

                    result = self._handle_query_tools(arguments, current_tools, tool_manager)

                    # Add result to messages for LLM
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": json.dumps(result),
                    })

                    # Build summary for chat_log
                    domain_filter = arguments.get("domain", "all domains")
                    if result.get("success"):
                        tools_found = result.get("result", {}).get("tools", [])
                        query_tools_summary.append(
                            f"Discovered {len(tools_found)} tools for {domain_filter}"
                        )

                # Add a message to chat_log describing what query_tools did
                if query_tools_summary:
                    summary_content = AssistantContent(
                        agent_id=DOMAIN,
                        content="\n".join(query_tools_summary),
                    )
                    chat_log.async_add_assistant_content_without_tools(summary_content)
                    _LOGGER.debug("Added query_tools summary to chat_log")

            # Handle real HA tools through chat_log
            if ha_tool_calls:
                _LOGGER.info("Processing %d Home Assistant tool call(s)", len(ha_tool_calls))

                # Convert to ToolInput objects
                tool_inputs = self._convert_tool_calls_to_inputs(ha_tool_calls, user_input)

                # Create AssistantContent with tool calls
                assistant_content = AssistantContent(
                    agent_id=DOMAIN,
                    content=response.get("content"),
                    tool_calls=tool_inputs,
                )

                _LOGGER.debug(
                    "Adding assistant content to chat_log with %d tool call(s)",
                    len(tool_inputs),
                )

                # Add to chat_log and execute tools
                # This returns an async generator of ToolResultContent
                async for tool_result in chat_log.async_add_assistant_content(assistant_content):
                    _LOGGER.info(
                        "Tool %s executed with result (success: %s)",
                        tool_result.tool_name,
                        "data" in tool_result.tool_result if isinstance(tool_result.tool_result, dict) else "unknown",
                    )

                    # Add tool result to messages for next LLM iteration
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_result.tool_call_id,
                        "content": json.dumps(tool_result.tool_result),
                    })

        # If we hit max iterations, return last content or error
        _LOGGER.warning("Hit max tool iterations (%d)", MAX_TOOL_ITERATIONS)
        return response.get("content", "I encountered an issue processing your request.")

    def _handle_query_tools(
        self,
        arguments: dict[str, Any],
        current_tools: list[dict[str, Any]],
        tool_manager: LLMToolManager,
    ) -> dict[str, Any]:
        """Handle query_tools meta-tool call.

        Args:
            arguments: Tool arguments (may contain 'domain' filter).
            current_tools: List to update with discovered tools.
            tool_manager: The tool manager.

        Returns:
            Result with list of available tools.
        """
        domain = arguments.get("domain")

        try:
            # Query Home Assistant for available tools
            ha_tools = tool_manager.query_tools(domain)

            # Add queried tools to current available tools (excluding duplicates)
            existing_names = {t["function"]["name"] for t in current_tools}
            for tool in ha_tools:
                if tool["function"]["name"] not in existing_names:
                    current_tools.append(tool)

            _LOGGER.info(
                "Queried %d tools%s, now have %d total tools available",
                len(ha_tools),
                f" for domain '{domain}'" if domain else "",
                len(current_tools),
            )

            # Return summary to LLM
            tool_names = [t["function"]["name"] for t in ha_tools]
            return {
                "success": True,
                "result": {
                    "message": f"Found {len(ha_tools)} tools" + (f" for domain '{domain}'" if domain else ""),
                    "tools": tool_names,
                    "note": "These tools are now available for you to use. You can call them directly.",
                },
            }

        except Exception as err:
            _LOGGER.error("Error handling query_tools: %s", err)
            return {
                "success": False,
                "error": f"Failed to query tools: {err}",
            }

    def _build_messages(
        self, user_text: str, chat_log: ChatLog, system_prompt: str
    ) -> list[dict[str, Any]]:
        """Build the messages list for the LLM from chat_log.

        Args:
            user_text: The current user message.
            chat_log: The chat log with conversation history.
            system_prompt: The system prompt to use (from integration config).

        Returns:
            List of messages in OpenAI format.
        """
        messages: list[dict[str, Any]] = []

        # Always use our own system prompt, ignore Home Assistant's
        messages.append({"role": "system", "content": system_prompt})
        _LOGGER.debug("Using integration system prompt (length: %d)", len(system_prompt))

        # Convert chat_log content to OpenAI message format
        # Skip SystemContent - we use our own system prompt above
        if hasattr(chat_log, "content") and chat_log.content:
            _LOGGER.debug("chat_log has %d content items", len(chat_log.content))
            for content in chat_log.content:
                content_type = type(content).__name__
                if content_type == "SystemContent":
                    # Skip - we use our own system prompt
                    _LOGGER.debug("Skipping Home Assistant system prompt")
                    continue
                elif content_type == "UserContent":
                    messages.append({"role": "user", "content": content.content})
                    _LOGGER.debug("Added user message from chat_log: %s", content.content[:50])
                elif content_type == "AssistantContent":
                    messages.append({"role": "assistant", "content": content.content})
                    _LOGGER.debug("Added assistant message from chat_log: %s", str(content.content)[:50] if content.content else "None")
        else:
            _LOGGER.debug("chat_log has no content or content attribute")

        # Add current user message if not already in chat_log
        if not messages or messages[-1].get("content") != user_text:
            messages.append({"role": "user", "content": user_text})
            _LOGGER.debug("Added current user message (not in chat_log)")
        else:
            _LOGGER.debug("Current user message already in chat_log")

        _LOGGER.info("Built %d messages for LLM (including system prompt)", len(messages))
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
