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
    CONF_AUTO_CONTINUE_LISTENING,
    CONF_CONVERSATION_TIMEOUT,
    CONF_ENABLE_FACT_LEARNING,
    CONF_ENABLE_MUSIC_ASSISTANT,
    CONF_ENABLE_STREAMING,
    CONF_LLM_HASS_API,
    CONF_MAX_TOKENS,
    CONF_MODEL,
    CONF_PROVIDER,
    CONF_SYSTEM_PROMPT,
    CONF_TEMPERATURE,
    CONTINUE_LISTENING_MARKER,
    DEFAULT_AUTO_CONTINUE_LISTENING,
    DEFAULT_CONVERSATION_TIMEOUT,
    DEFAULT_ENABLE_FACT_LEARNING,
    DEFAULT_ENABLE_MUSIC_ASSISTANT,
    DEFAULT_ENABLE_STREAMING,
    DEFAULT_MAX_TOKENS,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_TEMPERATURE,
    DOMAIN,
)
from .conversation_manager import ConversationManager
from .llm import create_llm_provider
from .llm.base import StreamChunk
from .music_assistant import MusicAssistantHandler
from .response_processor import (
    add_listening_instructions_to_prompt,
    process_response_for_listening,
)
from .llm_tools import LLMToolManager
from .storage import FactStore
from . import tool_handlers
from .streaming_buffer import StreamingBufferProcessor

if TYPE_CHECKING:
    from homeassistant.components.conversation import ChatLog

    from .llm.base import BaseLLMProvider

_LOGGER = logging.getLogger(__name__)

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

        # Initialize conversation manager and fact store
        self._fact_store = FactStore(hass)
        self._conversation_manager = ConversationManager(
            hass,
            self._fact_store,
            timeout_seconds=self._get_config(CONF_CONVERSATION_TIMEOUT, DEFAULT_CONVERSATION_TIMEOUT),
        )

        # Initialize Music Assistant handler
        self._music_handler: MusicAssistantHandler | None = None

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
    def music_handler(self) -> MusicAssistantHandler:
        """Get or create the Music Assistant handler."""
        if self._music_handler is None:
            self._music_handler = MusicAssistantHandler(self.hass)
        return self._music_handler

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
        # Get global session for conversation tracking
        session = self._conversation_manager.get_session()

        # Add user message to global session
        session.add_message("user", user_input.text)

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
        await self._async_handle_chat_log(chat_log, user_input, session)

        return conversation.async_get_result_from_chat_log(user_input, chat_log)

    async def _async_handle_chat_log(
        self,
        chat_log: ChatLog,
        user_input: conversation.ConversationInput,
        session: Any,
    ) -> None:
        """Process the chat log with optional streaming.

        Args:
            chat_log: The chat log to process.
            user_input: The original user input.
            session: The conversation session for tracking.
        """
        # Create tool manager with access to chat_log's llm_api
        tool_manager = LLMToolManager(chat_log)

        # Check if Music Assistant is enabled and available
        include_music = (
            self._get_config(CONF_ENABLE_MUSIC_ASSISTANT, DEFAULT_ENABLE_MUSIC_ASSISTANT)
            and self.music_handler.is_available()
        )

        # Start with meta-tools (optionally including music tools)
        current_tools = LLMToolManager.get_initial_tools(include_music=include_music)

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
                messages, current_tools, tool_manager, chat_log, user_input, session
            )
        else:
            _LOGGER.debug("Streaming disabled, using non-streaming mode")
            await self._process_without_streaming(
                messages, current_tools, tool_manager, chat_log, user_input, session
            )

    async def _process_without_streaming(
        self,
        messages: list[dict[str, Any]],
        current_tools: list[dict[str, Any]],
        tool_manager: LLMToolManager,
        chat_log: ChatLog,
        user_input: conversation.ConversationInput,
        session: Any,
    ) -> None:
        """Process without streaming - original implementation.

        Args:
            messages: Conversation messages.
            current_tools: Currently available tools.
            tool_manager: The tool manager.
            chat_log: The chat log.
            user_input: The user input.
            session: The conversation session for tracking.
        """
        # Process with potential tool calls
        assistant_message = await self._process_with_tools(
            messages, current_tools, tool_manager, chat_log, user_input
        )

        # Process response for listening control
        auto_continue = self._get_config(CONF_AUTO_CONTINUE_LISTENING, DEFAULT_AUTO_CONTINUE_LISTENING)
        processed_message, _ = process_response_for_listening(assistant_message, auto_continue)

        # Add the PROCESSED response to chat_log (this is what gets spoken)
        final_assistant_content = AssistantContent(
            agent_id=DOMAIN,
            content=processed_message,
        )
        chat_log.async_add_assistant_content_without_tools(final_assistant_content)
        _LOGGER.debug("Added final assistant response to chat_log for conversation history")

        # Track ORIGINAL message in session for fact learning (preserve full context)
        session.add_message("assistant", assistant_message)

    async def _process_with_streaming(
        self,
        messages: list[dict[str, Any]],
        current_tools: list[dict[str, Any]],
        tool_manager: LLMToolManager,
        chat_log: ChatLog,
        user_input: conversation.ConversationInput,
        session: Any,
    ) -> None:
        """Process with streaming using chat_log.async_add_delta_content_stream.

        Args:
            messages: Conversation messages.
            current_tools: Currently available tools.
            tool_manager: The tool manager.
            chat_log: The chat log.
            user_input: The user input.
            session: The conversation session for tracking.
        """
        # Container to receive original content from generator
        original_content_holder = []

        # Use async_add_delta_content_stream to handle streaming
        async for content_obj in chat_log.async_add_delta_content_stream(
            self.entity_id,
            self._stream_response_with_tools(
                messages, current_tools, tool_manager, chat_log, user_input, original_content_holder
            ),
        ):
            pass  # Generator handles all streaming internally

        # Track ORIGINAL assistant message in session for fact learning (preserves marker for context)
        if original_content_holder:
            original_response = original_content_holder[0]
            session.add_message("assistant", original_response)

    async def _stream_response_with_tools(
        self,
        messages: list[dict[str, Any]],
        current_tools: list[dict[str, Any]],
        tool_manager: LLMToolManager,
        chat_log: ChatLog,
        user_input: conversation.ConversationInput,
        original_content_holder: list[str],
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
            original_content_holder: List to store original accumulated content.

        Yields:
            Delta dictionaries with "content" key.
        """
        for iteration in range(MAX_TOOL_ITERATIONS):
            _LOGGER.debug("Streaming iteration %d starting", iteration + 1)

            # Create buffer processor for this iteration
            buffer_processor = StreamingBufferProcessor(CONTINUE_LISTENING_MARKER)

            # Stream from LLM using buffer processor
            _LOGGER.debug("Starting to stream chunks from LLM provider")
            async for content_delta in buffer_processor.process_chunks(
                self.provider.generate_stream_with_tools(messages, current_tools)
            ):
                yield content_delta

            # Get the processing result
            result = buffer_processor.get_result()
            accumulated_content = result.accumulated_content
            tool_calls = result.tool_calls
            marker_found = result.marker_found

            # If no tool calls, we're done
            if not tool_calls:
                # Store original accumulated content for session tracking
                original_content_holder.append(accumulated_content)

                # If marker was present, ensure response ends with ?
                async for content_delta in buffer_processor.finalize_response():
                    yield content_delta

                _LOGGER.debug("No tool calls, streaming complete")
                return

            # Handle tool calls (not streamed to user)
            _LOGGER.info("Processing %d tool call(s) in iteration %d", len(tool_calls), iteration + 1)

            # Categorize tool calls
            (query_tools_calls, query_facts_calls, learn_fact_calls,
             music_tool_calls, ha_tool_calls) = tool_handlers.categorize_tool_calls(tool_calls)

            # Add assistant message with tool calls to history
            messages.append({
                "role": "assistant",
                "content": accumulated_content,
                "tool_calls": tool_calls,
            })

            # Handle each type of tool call using shared helper functions
            await tool_handlers.handle_query_tools_calls(
                query_tools_calls, current_tools, tool_manager, messages, chat_log,
                self._handle_query_tools
            )
            await tool_handlers.handle_query_facts_calls(
                query_facts_calls, messages, chat_log, self._handle_query_facts
            )
            await tool_handlers.handle_learn_fact_calls(
                learn_fact_calls, messages, chat_log, self._handle_learn_fact
            )
            await tool_handlers.handle_music_tool_calls(
                music_tool_calls, messages, chat_log, self._handle_music_tool
            )
            await tool_handlers.handle_ha_tool_calls(
                ha_tool_calls, messages, chat_log, user_input, accumulated_content,
                self._convert_tool_calls_to_inputs
            )

        # Max iterations reached
        # Store whatever content we accumulated for session tracking
        if accumulated_content:
            original_content_holder.append(accumulated_content)

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

            # Categorize tool calls
            (query_tools_calls, query_facts_calls, learn_fact_calls,
             music_tool_calls, ha_tool_calls) = tool_handlers.categorize_tool_calls(tool_calls)

            # Add assistant message with tool calls to history for LLM context
            messages.append({
                "role": "assistant",
                "content": response.get("content"),
                "tool_calls": tool_calls,
            })

            # Handle each type of tool call using shared helper functions
            await tool_handlers.handle_query_tools_calls(
                query_tools_calls, current_tools, tool_manager, messages, chat_log,
                self._handle_query_tools
            )
            await tool_handlers.handle_query_facts_calls(
                query_facts_calls, messages, chat_log, self._handle_query_facts
            )
            await tool_handlers.handle_learn_fact_calls(
                learn_fact_calls, messages, chat_log, self._handle_learn_fact
            )
            await tool_handlers.handle_music_tool_calls(
                music_tool_calls, messages, chat_log, self._handle_music_tool
            )
            await tool_handlers.handle_ha_tool_calls(
                ha_tool_calls, messages, chat_log, user_input, response.get("content", ""),
                self._convert_tool_calls_to_inputs
            )

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

    def _handle_query_facts(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle query_facts meta-tool call.

        Args:
            arguments: Tool arguments (may contain 'category' filter).

        Returns:
            Result with learned facts.
        """
        category = arguments.get("category")

        try:
            # Get all facts from fact store
            # Note: category parameter is optional guidance for the LLM but we don't
            # store facts with categories, so we return all facts and let the LLM filter
            facts = self._fact_store.get_all_facts()

            _LOGGER.info(
                "Queried %d facts%s",
                len(facts),
                f" (category '{category}' requested)" if category else "",
            )

            # Return facts to LLM
            return {
                "success": True,
                "facts": facts,
                "message": f"Found {len(facts)} fact(s)",
            }

        except Exception as err:
            _LOGGER.error("Error handling query_facts: %s", err)
            return {
                "success": False,
                "error": f"Failed to query facts: {err}",
            }

    async def _handle_learn_fact(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle learn_fact meta-tool call.

        Stores a fact immediately to the FactStore so it's available
        for future conversations without waiting for session timeout.

        Args:
            arguments: Tool arguments with category, key, value.

        Returns:
            Result confirming fact was stored.
        """
        category = arguments.get("category")
        key = arguments.get("key")
        value = arguments.get("value")

        if not key or not value:
            return {
                "success": False,
                "error": "Missing required parameters: key and value are required",
            }

        try:
            # Store fact immediately
            self._fact_store.add_fact(key, value)
            await self._fact_store.async_save()

            _LOGGER.info(
                "Stored fact: %s = %s (category: %s)",
                key,
                value,
                category or "unspecified",
            )

            return {
                "success": True,
                "message": f"Successfully stored {key}",
            }

        except Exception as err:
            _LOGGER.error("Error storing fact: %s", err)
            return {
                "success": False,
                "error": f"Failed to store fact: {err}",
            }

    async def _handle_music_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle music assistant meta-tool calls.

        Args:
            tool_name: Name of the music tool.
            arguments: Tool arguments.

        Returns:
            Result dictionary.
        """
        handler = self.music_handler

        try:
            if tool_name == "play_music":
                return await handler.play_music(
                    query=arguments.get("query", ""),
                    player=arguments.get("player"),
                    media_type=arguments.get("media_type"),
                    enqueue=arguments.get("enqueue", "replace"),
                    radio_mode=arguments.get("radio_mode", False),
                )
            elif tool_name == "get_now_playing":
                return await handler.get_now_playing(
                    player=arguments.get("player"),
                )
            elif tool_name == "control_playback":
                return await handler.control_playback(
                    action=arguments["action"],
                    player=arguments.get("player"),
                    volume_level=arguments.get("volume_level"),
                )
            elif tool_name == "search_music":
                return await handler.search_music(
                    query=arguments.get("query", ""),
                    media_type=arguments.get("media_type"),
                    limit=arguments.get("limit", 10),
                    favorites_only=arguments.get("favorites_only", False),
                )
            elif tool_name == "transfer_music":
                return await handler.transfer_music(
                    target_player=arguments["target_player"],
                    source_player=arguments.get("source_player"),
                )
            elif tool_name == "get_music_players":
                players = await handler.load_and_cache_players()
                return {
                    "success": True,
                    "players": players,
                    "message": f"Found {len(players)} Music Assistant player(s)",
                }
            else:
                return {
                    "success": False,
                    "error": f"Unknown music tool: {tool_name}",
                }
        except Exception as err:
            _LOGGER.error("Error handling music tool %s: %s", tool_name, err)
            return {
                "success": False,
                "error": str(err),
            }

    def _build_messages(
        self, user_text: str, chat_log: ChatLog, system_prompt: str
    ) -> list[dict[str, Any]]:
        """Build the messages list for the LLM from global session.

        Args:
            user_text: The current user message.
            chat_log: The chat log (not used - kept for compatibility).
            system_prompt: The system prompt to use (from integration config).

        Returns:
            List of messages in OpenAI format.
        """
        messages: list[dict[str, Any]] = []

        # Build system prompt with listening instructions if needed
        full_system_prompt = system_prompt
        if not self._get_config(CONF_AUTO_CONTINUE_LISTENING, DEFAULT_AUTO_CONTINUE_LISTENING):
            full_system_prompt = add_listening_instructions_to_prompt(system_prompt)
            _LOGGER.debug("Added listening control instructions to system prompt")

        # Always use our own system prompt
        messages.append({"role": "system", "content": full_system_prompt})
        _LOGGER.debug("Using integration system prompt (length: %d)", len(full_system_prompt))

        # Add global session messages (cross-conversation history)
        session = self._conversation_manager.get_session()
        if session.messages:
            _LOGGER.debug("Adding %d messages from global session", len(session.messages))
            messages.extend(session.messages)
        else:
            _LOGGER.debug("No messages in global session")

        _LOGGER.info("Built %d messages for LLM (including system prompt)", len(messages))
        return messages

    async def async_added_to_hass(self) -> None:
        """When entity is added to Home Assistant."""
        await super().async_added_to_hass()
        conversation.async_set_agent(self.hass, self.entry, self)

        # Load facts and start cleanup task
        await self._fact_store.async_load()
        self._conversation_manager.set_llm_provider(self.provider)
        await self._conversation_manager.start_cleanup_task()

    async def async_will_remove_from_hass(self) -> None:
        """When entity is removed from Home Assistant."""
        # Stop cleanup task before removing
        await self._conversation_manager.stop_cleanup_task()

        # Close LLM provider client
        if self._provider is not None and hasattr(self._provider, 'async_close'):
            await self._provider.async_close()

        conversation.async_unset_agent(self.hass, self.entry)
        await super().async_will_remove_from_hass()


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up conversation platform."""
    async_add_entities([VoiceAssistantConversationAgent(hass, config_entry)])
