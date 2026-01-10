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
)
from .llm import create_llm_provider
from .llm_tools import LLMToolManager

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
        self._tool_manager: LLMToolManager | None = None
        self._conversation_history: dict[str, list[dict[str, Any]]] = {}
        self._current_tools: list[dict[str, Any]] = []  # Currently available tools

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
    def tool_manager(self) -> LLMToolManager:
        """Get or create the tool manager."""
        if self._tool_manager is None:
            self._tool_manager = LLMToolManager(self.hass)
        return self._tool_manager

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

        # Start with only query_tools - LLM will request more if needed
        self._current_tools = self.tool_manager.get_initial_tools()

        try:
            # Process with potential tool calls
            assistant_message = await self._process_with_tools(messages)

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
    ) -> str:
        """Process messages with dynamic tool discovery.

        Args:
            messages: Conversation messages.

        Returns:
            Final assistant response text.
        """
        for iteration in range(MAX_TOOL_ITERATIONS):
            # Generate with currently available tools
            response = await self.provider.generate(messages, self._current_tools)

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

                _LOGGER.debug(
                    "Iteration %d: Executing tool %s with args: %s",
                    iteration + 1,
                    tool_name,
                    arguments,
                )

                # Handle query_tools specially
                if tool_name == "query_tools":
                    result = await self._handle_query_tools(arguments)
                else:
                    # Execute HA tool via tool manager
                    result = await self.tool_manager.execute_tool(tool_name, arguments)

                # Add tool result to messages
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(result),
                })

        # If we hit max iterations, return last content or error
        return response.get("content", "I encountered an issue processing your request.")

    async def _handle_query_tools(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Handle query_tools meta-tool call.

        Args:
            arguments: Tool arguments (may contain 'domain' filter).

        Returns:
            Result with list of available tools.
        """
        domain = arguments.get("domain")

        try:
            # Query Home Assistant for available tools
            ha_tools = await self.tool_manager.query_tools(domain)

            # Add queried tools to current available tools (excluding duplicates)
            existing_names = {t["function"]["name"] for t in self._current_tools}
            for tool in ha_tools:
                if tool["function"]["name"] not in existing_names:
                    self._current_tools.append(tool)

            _LOGGER.info(
                "Queried %d tools%s, now have %d total tools available",
                len(ha_tools),
                f" for domain '{domain}'" if domain else "",
                len(self._current_tools),
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
