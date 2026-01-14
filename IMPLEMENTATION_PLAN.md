# Implementation Plan for Voice Assistant Features

This document provides detailed implementation instructions for three features:
1. Streaming Response Support
2. Conversation History Management with Timeout
3. Voice Assistant Listening Control

---

## Feature 1: Streaming Response Support ✅ COMPLETED

### Overview
Enable real-time streaming of LLM responses to Home Assistant, providing immediate feedback to users instead of waiting for complete responses.

### Current State
- ✅ `GroqProvider.generate_stream_with_tools()` implemented in `llm/groq.py:136-207`
- ✅ Returns `AsyncIterator[StreamChunk]` with content and tool calls
- ✅ Fully integrated with conversation agent
- ✅ Follows Home Assistant's OpenAI integration pattern
- ✅ Uses `chat_log.async_add_delta_content_stream()` for streaming
- ✅ Tool calls handled transparently during streaming

### Implementation Steps

#### Step 1.1: Update BaseLLMProvider for Streaming with Tool Support
**File:** `custom_components/voice_assistant/llm/base.py`

The current `generate_stream()` only yields text. For tool calling support, we need a more structured approach:

```python
from dataclasses import dataclass
from typing import AsyncIterator, Any

@dataclass
class StreamChunk:
    """Represents a chunk of streaming response."""
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    is_final: bool = False

@abstractmethod
async def generate_stream_with_tools(
    self,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> AsyncIterator[StreamChunk]:
    """Generate streaming response with tool call support.

    Yields:
        StreamChunk objects containing either content deltas or accumulated tool calls.
    """
    ...
```

#### Step 1.2: Update GroqProvider Streaming
**File:** `custom_components/voice_assistant/llm/groq.py`

Implement `generate_stream_with_tools()`:

```python
async def generate_stream_with_tools(
    self,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
) -> AsyncIterator[StreamChunk]:
    """Generate streaming response with tool call accumulation."""
    kwargs = {
        "model": self.model,
        "messages": messages,
        "temperature": self.temperature,
        "max_tokens": self.max_tokens,
        "stream": True,
    }

    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    accumulated_tool_calls = []

    try:
        stream = await self.client.chat.completions.create(**kwargs)

        async for chunk in stream:
            choice = chunk.choices[0] if chunk.choices else None
            if not choice:
                continue

            delta = choice.delta

            # Yield content chunks immediately
            if delta.content:
                yield StreamChunk(content=delta.content)

            # Accumulate tool calls (they come in pieces)
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    # Tool calls are indexed - accumulate by index
                    idx = tc_delta.index
                    while len(accumulated_tool_calls) <= idx:
                        accumulated_tool_calls.append({
                            "id": "",
                            "type": "function",
                            "function": {"name": "", "arguments": ""}
                        })

                    if tc_delta.id:
                        accumulated_tool_calls[idx]["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            accumulated_tool_calls[idx]["function"]["name"] += tc_delta.function.name
                        if tc_delta.function.arguments:
                            accumulated_tool_calls[idx]["function"]["arguments"] += tc_delta.function.arguments

            # Check for finish reason
            if choice.finish_reason:
                yield StreamChunk(
                    tool_calls=accumulated_tool_calls if accumulated_tool_calls else None,
                    is_final=True
                )

    except Exception as err:
        _LOGGER.error("Groq streaming error: %s", err)
        raise
```

#### Step 1.3: Add Streaming Support to Conversation Agent
**File:** `custom_components/voice_assistant/conversation.py`

Add new method for streaming message handling:

```python
async def _async_handle_message_streaming(
    self,
    user_input: conversation.ConversationInput,
    chat_log: ChatLog,
) -> AsyncIterator[conversation.ConversationResultDelta]:
    """Handle message with streaming response.

    This method is called when streaming is enabled.

    Yields:
        ConversationResultDelta objects for real-time updates.
    """
    conversation_id = user_input.conversation_id or ulid.ulid_now()

    # Setup (same as non-streaming)
    await chat_log.async_provide_llm_data(
        user_input.as_llm_context(DOMAIN),
        self._get_config(CONF_LLM_HASS_API),
        self._get_config(CONF_SYSTEM_PROMPT, DEFAULT_SYSTEM_PROMPT),
        None,
    )

    tool_manager = LLMToolManager(chat_log)
    current_tools = LLMToolManager.get_initial_tools()
    messages = self._build_messages(
        user_input.text,
        chat_log,
        self._get_config(CONF_SYSTEM_PROMPT, DEFAULT_SYSTEM_PROMPT),
    )

    # Process with streaming
    full_response = ""
    async for chunk in self._process_with_tools_streaming(
        messages, current_tools, tool_manager, chat_log, user_input
    ):
        if chunk.content:
            full_response += chunk.content
            # Yield delta to Home Assistant
            yield conversation.ConversationResultDelta(
                response=intent.IntentResponseDelta(speech=chunk.content),
                conversation_id=conversation_id,
            )

    # Add final response to chat_log
    final_assistant_content = AssistantContent(
        agent_id=DOMAIN,
        content=full_response,
    )
    chat_log.async_add_assistant_content_without_tools(final_assistant_content)

    # Yield final result
    yield conversation.ConversationResultDelta(
        response=intent.IntentResponseDelta(speech_finished=True),
        conversation_id=conversation_id,
    )
```

#### Step 1.4: Update _process_with_tools for Streaming
**File:** `custom_components/voice_assistant/conversation.py`

```python
async def _process_with_tools_streaming(
    self,
    messages: list[dict[str, Any]],
    current_tools: list[dict[str, Any]],
    tool_manager: LLMToolManager,
    chat_log: ChatLog,
    user_input: conversation.ConversationInput,
) -> AsyncIterator[StreamChunk]:
    """Process with tools using streaming.

    Key difference from non-streaming:
    - Yields content chunks as they arrive
    - Tool calls are collected at the end of each stream
    - Only the final response (no tool calls) is streamed to user
    """
    for iteration in range(MAX_TOOL_ITERATIONS):
        _LOGGER.debug("Streaming tool iteration %d", iteration + 1)

        accumulated_content = ""
        tool_calls = None

        async for chunk in self.provider.generate_stream_with_tools(messages, current_tools):
            if chunk.content:
                accumulated_content += chunk.content
            if chunk.is_final and chunk.tool_calls:
                tool_calls = chunk.tool_calls

        # If no tool calls, stream the content
        if not tool_calls:
            # Re-stream from accumulated content (or modify to yield during accumulation)
            # For simplicity, yield the full content as one chunk here
            # In production, you'd buffer and yield during the first pass
            yield StreamChunk(content=accumulated_content, is_final=True)
            return

        # Handle tool calls (same as non-streaming)
        # ... [tool handling code - same as _process_with_tools]
        # After tool execution, continue loop for next LLM call

        # Add assistant message with tool calls to messages
        messages.append({
            "role": "assistant",
            "content": accumulated_content,
            "tool_calls": tool_calls,
        })

        # Process tools (query_tools and HA tools)
        # ... [same logic as _process_with_tools]

    # Max iterations reached
    yield StreamChunk(content="I encountered an issue processing your request.", is_final=True)
```

#### Step 1.5: Add Configuration Option
**File:** `custom_components/voice_assistant/const.py`

```python
CONF_ENABLE_STREAMING = "enable_streaming"
DEFAULT_ENABLE_STREAMING = False
```

**File:** `custom_components/voice_assistant/config_flow.py`

Add to options form:
```python
vol.Optional(
    CONF_ENABLE_STREAMING,
    default=self.config_entry.options.get(CONF_ENABLE_STREAMING, DEFAULT_ENABLE_STREAMING),
): bool,
```

#### Step 1.6: Integrate with Home Assistant Conversation API
**File:** `custom_components/voice_assistant/conversation.py`

Override the streaming method:

```python
async def async_process(
    self,
    user_input: conversation.ConversationInput,
) -> conversation.ConversationResult:
    """Process user input - entry point from HA."""
    # Check if streaming is enabled and supported
    if self._get_config(CONF_ENABLE_STREAMING, DEFAULT_ENABLE_STREAMING):
        # Use async_get_result_from_chat_log for streaming
        return await conversation.async_get_result_from_chat_log(
            self.hass,
            user_input,
            self._async_handle_message_streaming,
        )
    else:
        # Use default non-streaming path
        return await super().async_process(user_input)
```

### Testing Checklist for Streaming
- [x] Simple response without tool calls streams correctly
- [x] Response with query_tools call works (tools discovered, then response streams)
- [x] Response with HA tool calls works (lights turn on, etc.)
- [x] Multi-turn conversation maintains history
- [x] Streaming can be disabled via config option
- [x] Error handling works for streaming failures

**Status:** ✅ **COMPLETED** - Streaming support is fully implemented and tested!

---

## Feature 2: Conversation History Management with Timeout ✅ COMPLETED

### Overview
Implement external conversation history storage with configurable timeout and fact learning/persistence.

### Current State
- ✅ Global conversation session across ALL Home Assistant conversations
- ✅ Session messages provide cross-conversation memory to LLM
- ✅ Persistent fact storage using FactStore
- ✅ Timeout-based session management (seconds, not minutes)
- ✅ Automatic fact extraction on timeout
- ✅ On-demand fact learning with learn_fact meta-tool
- ✅ On-demand fact querying with query_facts meta-tool

### Architecture Decision
Create a new `ConversationManager` class that:
1. Maintains conversation history independently
2. Tracks session timeout
3. Extracts and stores facts when sessions expire
4. Injects facts into system prompts

### Implementation Steps

#### Step 2.1: Create Storage Helper
**File:** `custom_components/voice_assistant/storage.py` (new file)

```python
"""Persistent storage for conversation facts."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.facts"


class FactStore:
    """Manages persistent storage of learned facts."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the fact store."""
        self.hass = hass
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._facts: dict[str, Any] = {}

    async def async_load(self) -> None:
        """Load facts from storage."""
        data = await self._store.async_load()
        if data:
            self._facts = data
        _LOGGER.debug("Loaded %d facts from storage", len(self._facts))

    async def async_save(self) -> None:
        """Save facts to storage."""
        await self._store.async_save(self._facts)
        _LOGGER.debug("Saved %d facts to storage", len(self._facts))

    def add_fact(self, key: str, value: Any) -> None:
        """Add or update a fact."""
        self._facts[key] = value

    def get_fact(self, key: str) -> Any | None:
        """Get a fact by key."""
        return self._facts.get(key)

    def get_all_facts(self) -> dict[str, Any]:
        """Get all facts."""
        return self._facts.copy()

    def remove_fact(self, key: str) -> None:
        """Remove a fact."""
        self._facts.pop(key, None)

    def clear(self) -> None:
        """Clear all facts."""
        self._facts.clear()
```

#### Step 2.2: Create Conversation Manager
**File:** `custom_components/voice_assistant/conversation_manager.py` (new file)

```python
"""Conversation session manager with timeout and fact learning."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .storage import FactStore

_LOGGER = logging.getLogger(__name__)

FACT_EXTRACTION_PROMPT = """Analyze the following conversation and extract any personal facts that were learned about the user. Return a JSON object with facts.

Categories to look for:
- user_name: The user's name
- family_members: Names of family members mentioned
- preferences: Temperature preferences, favorite settings, routines
- device_nicknames: Custom names for devices
- locations: Room names, locations of devices
- routines: Regular patterns (wake time, bedtime, etc.)

Only include facts that were explicitly stated or clearly implied. If no facts were learned, return an empty object {}.

Conversation:
{conversation}

Return ONLY valid JSON, no explanation."""


@dataclass
class ConversationSession:
    """Represents an active conversation session."""

    conversation_id: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    last_activity: datetime = field(default_factory=datetime.now)

    def add_message(self, role: str, content: str) -> None:
        """Add a message to the session."""
        self.messages.append({"role": role, "content": content})
        self.last_activity = datetime.now()

    def is_expired(self, timeout_minutes: int) -> bool:
        """Check if session has expired."""
        return datetime.now() - self.last_activity > timedelta(minutes=timeout_minutes)

    def get_conversation_text(self) -> str:
        """Get conversation as text for fact extraction."""
        lines = []
        for msg in self.messages:
            role = msg["role"].capitalize()
            content = msg["content"]
            lines.append(f"{role}: {content}")
        return "\n".join(lines)


class ConversationManager:
    """Manages conversation sessions with timeout and fact learning."""

    def __init__(
        self,
        hass: HomeAssistant,
        fact_store: FactStore,
        timeout_minutes: int = 5,
    ) -> None:
        """Initialize the conversation manager."""
        self.hass = hass
        self.fact_store = fact_store
        self.timeout_minutes = timeout_minutes
        self._sessions: dict[str, ConversationSession] = {}
        self._cleanup_task: asyncio.Task | None = None
        self._llm_provider = None  # Set by conversation agent

    def set_llm_provider(self, provider) -> None:
        """Set the LLM provider for fact extraction."""
        self._llm_provider = provider

    def get_or_create_session(self, conversation_id: str) -> ConversationSession:
        """Get existing session or create new one."""
        # Check for expired session first
        if conversation_id in self._sessions:
            session = self._sessions[conversation_id]
            if session.is_expired(self.timeout_minutes):
                # Session expired - extract facts and create new
                asyncio.create_task(self._handle_session_timeout(session))
                del self._sessions[conversation_id]
            else:
                return session

        # Create new session
        session = ConversationSession(conversation_id=conversation_id)
        self._sessions[conversation_id] = session
        return session

    def get_session(self, conversation_id: str) -> ConversationSession | None:
        """Get session if exists and not expired."""
        session = self._sessions.get(conversation_id)
        if session and not session.is_expired(self.timeout_minutes):
            return session
        return None

    async def _handle_session_timeout(self, session: ConversationSession) -> None:
        """Handle session timeout - extract and save facts."""
        if not session.messages:
            return

        _LOGGER.info(
            "Session %s timed out with %d messages, extracting facts",
            session.conversation_id,
            len(session.messages),
        )

        try:
            await self._extract_and_save_facts(session)
        except Exception as err:
            _LOGGER.error("Error extracting facts: %s", err)

    async def _extract_and_save_facts(self, session: ConversationSession) -> None:
        """Use LLM to extract facts from conversation."""
        if not self._llm_provider:
            _LOGGER.warning("No LLM provider set, cannot extract facts")
            return

        conversation_text = session.get_conversation_text()

        messages = [
            {"role": "system", "content": "You are a fact extraction assistant. Extract facts from conversations and return them as JSON."},
            {"role": "user", "content": FACT_EXTRACTION_PROMPT.format(conversation=conversation_text)},
        ]

        try:
            response = await self._llm_provider.generate(messages, tools=None)
            content = response.get("content", "")

            # Parse JSON response
            import json
            # Find JSON in response (might have markdown code blocks)
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            facts = json.loads(content.strip())

            # Save each fact
            for key, value in facts.items():
                if value:  # Only save non-empty facts
                    self.fact_store.add_fact(key, value)
                    _LOGGER.info("Learned fact: %s = %s", key, value)

            # Persist to storage
            await self.fact_store.async_save()

        except json.JSONDecodeError as err:
            _LOGGER.warning("Failed to parse facts JSON: %s", err)
        except Exception as err:
            _LOGGER.error("Error during fact extraction: %s", err)

    def build_facts_prompt_section(self) -> str:
        """Build a prompt section containing known facts."""
        facts = self.fact_store.get_all_facts()
        if not facts:
            return ""

        lines = ["\n\n**Known information about this user:**"]
        for key, value in facts.items():
            # Format the fact nicely
            key_formatted = key.replace("_", " ").title()
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value)
            lines.append(f"- {key_formatted}: {value}")

        return "\n".join(lines)

    async def start_cleanup_task(self) -> None:
        """Start background task to clean up expired sessions."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop_cleanup_task(self) -> None:
        """Stop the cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    async def _cleanup_loop(self) -> None:
        """Periodically check for and clean up expired sessions."""
        while True:
            await asyncio.sleep(60)  # Check every minute

            expired_ids = []
            for conv_id, session in self._sessions.items():
                if session.is_expired(self.timeout_minutes):
                    expired_ids.append(conv_id)

            for conv_id in expired_ids:
                session = self._sessions.pop(conv_id)
                await self._handle_session_timeout(session)
```

#### Step 2.3: Add Configuration Constants
**File:** `custom_components/voice_assistant/const.py`

```python
# Conversation history settings
CONF_CONVERSATION_TIMEOUT = "conversation_timeout"
CONF_ENABLE_FACT_LEARNING = "enable_fact_learning"

DEFAULT_CONVERSATION_TIMEOUT = 5  # minutes
DEFAULT_ENABLE_FACT_LEARNING = True
```

#### Step 2.4: Update Config Flow
**File:** `custom_components/voice_assistant/config_flow.py`

Add to options form:
```python
vol.Optional(
    CONF_CONVERSATION_TIMEOUT,
    default=self.config_entry.options.get(
        CONF_CONVERSATION_TIMEOUT, DEFAULT_CONVERSATION_TIMEOUT
    ),
): vol.All(vol.Coerce(int), vol.Range(min=1, max=60)),

vol.Optional(
    CONF_ENABLE_FACT_LEARNING,
    default=self.config_entry.options.get(
        CONF_ENABLE_FACT_LEARNING, DEFAULT_ENABLE_FACT_LEARNING
    ),
): bool,
```

#### Step 2.5: Integrate with Conversation Agent
**File:** `custom_components/voice_assistant/conversation.py`

Update `__init__`:
```python
def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Initialize the conversation agent."""
    self.hass = hass
    self.entry = entry
    self._attr_unique_id = entry.entry_id
    self._provider: BaseLLMProvider | None = None

    # Initialize conversation manager
    self._fact_store = FactStore(hass)
    self._conversation_manager = ConversationManager(
        hass,
        self._fact_store,
        timeout_minutes=self._get_config(CONF_CONVERSATION_TIMEOUT, DEFAULT_CONVERSATION_TIMEOUT),
    )
```

Update `async_added_to_hass`:
```python
async def async_added_to_hass(self) -> None:
    """When entity is added to Home Assistant."""
    await super().async_added_to_hass()
    conversation.async_set_agent(self.hass, self.entry, self)

    # Load facts and start cleanup task
    await self._fact_store.async_load()
    self._conversation_manager.set_llm_provider(self.provider)
    await self._conversation_manager.start_cleanup_task()
```

Update `async_will_remove_from_hass`:
```python
async def async_will_remove_from_hass(self) -> None:
    """When entity is removed from Home Assistant."""
    await self._conversation_manager.stop_cleanup_task()
    conversation.async_unset_agent(self.hass, self.entry)
    await super().async_will_remove_from_hass()
```

Update `_build_messages` to include facts:
```python
def _build_messages(self, user_text: str, chat_log: ChatLog, system_prompt: str) -> list[dict[str, Any]]:
    """Build the messages list for the LLM from chat_log."""
    messages: list[dict[str, Any]] = []

    # Build system prompt with facts
    facts_section = ""
    if self._get_config(CONF_ENABLE_FACT_LEARNING, DEFAULT_ENABLE_FACT_LEARNING):
        facts_section = self._conversation_manager.build_facts_prompt_section()

    full_system_prompt = system_prompt + facts_section
    messages.append({"role": "system", "content": full_system_prompt})

    # ... rest of existing code
```

Update `_async_handle_message` to track messages in session:
```python
async def _async_handle_message(self, user_input, chat_log) -> conversation.ConversationResult:
    conversation_id = user_input.conversation_id or ulid.ulid_now()

    # Get or create session
    session = self._conversation_manager.get_or_create_session(conversation_id)

    # ... existing code to process message ...

    # After getting response, track in session
    session.add_message("user", user_input.text)
    session.add_message("assistant", assistant_message)

    # ... rest of existing code
```

#### Step 2.6: Update Integration Setup
**File:** `custom_components/voice_assistant/__init__.py`

Ensure cleanup on unload:
```python
async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # The conversation entity handles its own cleanup in async_will_remove_from_hass
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
```

### Testing Checklist for Conversation History
- [ ] Session persists within timeout period
- [ ] Session resets after timeout
- [ ] Facts are extracted when session times out
- [ ] Facts persist across HA restarts
- [ ] Facts are injected into system prompt
- [ ] Timeout is configurable via options
- [ ] Fact learning can be disabled
- [ ] Multiple concurrent conversations work independently

---

## Feature 3: Voice Assistant Listening Control ✅ COMPLETED

### Overview
Control whether the voice assistant continues listening after a response, preventing unwanted continued listening when responses end with `?`.

### Current State
- ✅ Listening control via `auto_continue_listening` configuration option
- ✅ Response processing replaces `?` with fullwidth `？` to prevent auto-listening
- ✅ LLM can use `[CONTINUE_LISTENING]` marker to explicitly request listening
- ✅ Automatic prompt instructions added when feature is enabled
- ✅ Works in both streaming and non-streaming modes

### Implementation Strategy
Use response post-processing to manipulate the final character:
1. Detect if response ends with `?`
2. Check if LLM explicitly requested continued listening
3. If not, modify response to prevent continued listening

### Implementation Steps

#### Step 3.1: Add Constants
**File:** `custom_components/voice_assistant/const.py`

```python
# Voice assistant listening control
CONF_AUTO_CONTINUE_LISTENING = "auto_continue_listening"
DEFAULT_AUTO_CONTINUE_LISTENING = False

# Marker that LLM can use to request continued listening
CONTINUE_LISTENING_MARKER = "[CONTINUE_LISTENING]"
```

#### Step 3.2: Create Response Processor
**File:** `custom_components/voice_assistant/response_processor.py` (new file)

```python
"""Response post-processing for voice assistant control."""

from __future__ import annotations

import logging
import re

from .const import CONTINUE_LISTENING_MARKER

_LOGGER = logging.getLogger(__name__)

# Unicode characters that look like ? but don't trigger listening
# Option 1: Fullwidth Question Mark
FAKE_QUESTION_MARK = "\uFF1F"  # ？ (fullwidth)

# Option 2: Zero-width space after question mark
ZERO_WIDTH_SPACE = "\u200B"


def process_response_for_listening(
    response: str,
    auto_continue_listening: bool,
) -> tuple[str, bool]:
    """Process response to control voice assistant listening behavior.

    Args:
        response: The LLM response text.
        auto_continue_listening: If True, allow normal ? behavior.

    Returns:
        Tuple of (processed_response, should_continue_listening).
    """
    # Check if LLM explicitly requested continued listening
    wants_listening = CONTINUE_LISTENING_MARKER in response

    # Remove the marker from response (user shouldn't see it)
    processed = response.replace(CONTINUE_LISTENING_MARKER, "").strip()

    # Determine if we should continue listening
    ends_with_question = processed.rstrip().endswith("?")

    if wants_listening:
        # LLM explicitly wants listening - keep the ? intact
        _LOGGER.debug("LLM requested continued listening")
        return processed, True

    if auto_continue_listening:
        # Auto mode - use default HA behavior
        return processed, ends_with_question

    # Default: prevent continued listening
    if ends_with_question:
        # Option A: Replace ? with fullwidth version
        processed = re.sub(r'\?(\s*)$', f'{FAKE_QUESTION_MARK}\\1', processed)

        # Option B (alternative): Add zero-width space after ?
        # processed = re.sub(r'\?(\s*)$', f'?{ZERO_WIDTH_SPACE}\\1', processed)

        _LOGGER.debug("Modified response to prevent continued listening")

    return processed, False


def add_listening_instructions_to_prompt(system_prompt: str) -> str:
    """Add instructions for listening control to system prompt.

    Args:
        system_prompt: The current system prompt.

    Returns:
        Updated system prompt with listening instructions.
    """
    listening_instructions = f"""

**Voice Assistant Listening Control:**
By default, I will NOT keep listening after your response, even if you ask a question.
If you want me to continue listening for the user's response (for clarifying questions or follow-ups),
include the marker {CONTINUE_LISTENING_MARKER} anywhere in your response. This marker will be removed
before the response is spoken.

Example:
- "What temperature would you like?" -> Stops listening
- "What temperature would you like? {CONTINUE_LISTENING_MARKER}" -> Continues listening

Only use the marker when you genuinely need user input to proceed."""

    return system_prompt + listening_instructions
```

#### Step 3.3: Alternative - Meta-Tool Approach
**File:** `custom_components/voice_assistant/llm_tools.py`

Add a meta-tool for listening control (optional alternative approach):

```python
SET_LISTENING_TOOL = {
    "type": "function",
    "function": {
        "name": "set_listening",
        "description": "Control whether the voice assistant should continue listening after the response. Call this BEFORE your final response if you want to ask the user a question and wait for their answer.",
        "parameters": {
            "type": "object",
            "properties": {
                "continue_listening": {
                    "type": "boolean",
                    "description": "True to keep listening for user response, False to stop"
                }
            },
            "required": ["continue_listening"]
        }
    }
}
```

#### Step 3.4: Update Config Flow
**File:** `custom_components/voice_assistant/config_flow.py`

Add to options form:
```python
vol.Optional(
    CONF_AUTO_CONTINUE_LISTENING,
    default=self.config_entry.options.get(
        CONF_AUTO_CONTINUE_LISTENING, DEFAULT_AUTO_CONTINUE_LISTENING
    ),
): bool,
```

Update strings.json for the option description:
```json
{
  "options": {
    "step": {
      "init": {
        "data": {
          "auto_continue_listening": "Auto-continue listening on questions"
        },
        "data_description": {
          "auto_continue_listening": "When enabled, voice assistant continues listening if response ends with '?'. When disabled (default), listening only continues if explicitly requested."
        }
      }
    }
  }
}
```

#### Step 3.5: Integrate with Conversation Agent
**File:** `custom_components/voice_assistant/conversation.py`

Import the response processor:
```python
from .response_processor import (
    process_response_for_listening,
    add_listening_instructions_to_prompt,
)
```

Update `_build_messages` to add listening instructions:
```python
def _build_messages(self, user_text: str, chat_log: ChatLog, system_prompt: str) -> list[dict[str, Any]]:
    """Build the messages list for the LLM from chat_log."""
    messages: list[dict[str, Any]] = []

    # Build system prompt with facts and listening instructions
    full_system_prompt = system_prompt

    # Add facts section if enabled
    if self._get_config(CONF_ENABLE_FACT_LEARNING, DEFAULT_ENABLE_FACT_LEARNING):
        facts_section = self._conversation_manager.build_facts_prompt_section()
        full_system_prompt += facts_section

    # Add listening control instructions if not auto mode
    if not self._get_config(CONF_AUTO_CONTINUE_LISTENING, DEFAULT_AUTO_CONTINUE_LISTENING):
        full_system_prompt = add_listening_instructions_to_prompt(full_system_prompt)

    messages.append({"role": "system", "content": full_system_prompt})
    # ... rest of existing code
```

Update `_async_handle_message` to process response:
```python
async def _async_handle_message(self, user_input, chat_log) -> conversation.ConversationResult:
    # ... existing code to get assistant_message ...

    # Process response for listening control
    auto_continue = self._get_config(CONF_AUTO_CONTINUE_LISTENING, DEFAULT_AUTO_CONTINUE_LISTENING)
    processed_message, _ = process_response_for_listening(
        assistant_message,
        auto_continue,
    )

    # Add the ORIGINAL response to chat_log (for conversation memory)
    # But use PROCESSED response for speech output
    final_assistant_content = AssistantContent(
        agent_id=DOMAIN,
        content=assistant_message,  # Original for history
    )
    chat_log.async_add_assistant_content_without_tools(final_assistant_content)

    intent_response = intent.IntentResponse(language=user_input.language)
    intent_response.async_set_speech(processed_message)  # Processed for speech

    return conversation.ConversationResult(
        response=intent_response,
        conversation_id=conversation_id,
    )
```

### Testing Checklist for Listening Control
- [x] Response ending with `?` does NOT continue listening (default)
- [x] Response with `[CONTINUE_LISTENING]` marker DOES continue listening
- [x] Marker is removed from spoken response (via chunk buffering)
- [x] auto_continue_listening=True allows normal `?` behavior
- [x] Configuration option works correctly
- [x] Marker removal works even when split character-by-character across chunks
- [x] Chunk buffering prevents partial marker from being spoken
- [x] Question mark automatically added when marker present without `?`

**Status:** ✅ **COMPLETED** - Voice assistant listening control is fully implemented and tested!

**Key Implementation:**
- Chunk buffering prevents marker from being spoken during streaming
- Helper method `_buffer_might_contain_partial_marker()` detects partial markers
- Buffer held when ending with `[`, `[C`, `[CO`, `[CON`, etc.
- Marker removed and clean content yielded when complete

---

## Implementation Order Recommendation

1. **Voice Assistant Listening Control** (Feature 3)
   - Simplest to implement
   - Self-contained changes
   - Immediately testable

2. **Conversation History Management** (Feature 2)
   - Medium complexity
   - Creates foundation for enhanced features
   - Requires testing timeout behavior

3. **Streaming Response Support** (Feature 1)
   - Most complex
   - Requires careful integration with HA conversation API
   - Benefits from Features 2 and 3 being stable

---

## Feature 4: Music Assistant Web API Integration

### Overview
Add support for controlling Music Assistant via its Web API, since it cannot be controlled through Home Assistant's native tools/services.

### Current State
- Home Assistant tools only expose native HA services
- Music Assistant has its own Web API that needs to be accessed separately
- No way to control Music Assistant through the voice assistant

### Requirements
- **query_tools should return Music Assistant API calls** in addition to regular HA tools
- Music Assistant API calls should be formatted as tool definitions
- LLM should be able to discover and call Music Assistant endpoints
- Support common operations: play music, control playback, search, queue management

### Implementation Strategy

#### Approach: Extend query_tools to include Music Assistant API

1. **Music Assistant API Discovery**:
   - Connect to Music Assistant Web API (typically on same host as HA)
   - Query available endpoints and capabilities
   - Convert API endpoints to tool definitions

2. **Tool Definition Format**:
   ```python
   {
       "type": "function",
       "function": {
           "name": "music_assistant_play",
           "description": "Play music on Music Assistant",
           "parameters": {
               "type": "object",
               "properties": {
                   "uri": {"type": "string", "description": "URI of media to play"},
                   "player_id": {"type": "string", "description": "ID of player to use"},
               },
               "required": ["uri", "player_id"]
           }
       }
   }
   ```

3. **API Call Execution**:
   - Intercept Music Assistant tool calls (like we do for meta-tools)
   - Make HTTP requests to Music Assistant Web API
   - Return results to LLM
   - Log execution for debugging

### Implementation Steps

#### Step 4.1: Add Music Assistant Configuration
**File:** `custom_components/voice_assistant/const.py`

```python
# Music Assistant settings
CONF_MUSIC_ASSISTANT_URL = "music_assistant_url"
CONF_ENABLE_MUSIC_ASSISTANT = "enable_music_assistant"

DEFAULT_MUSIC_ASSISTANT_URL = "http://localhost:8095"  # Default MA port
DEFAULT_ENABLE_MUSIC_ASSISTANT = True
```

#### Step 4.2: Create Music Assistant API Client
**File:** `custom_components/voice_assistant/music_assistant_client.py` (new file)

- Connect to Music Assistant Web API
- Discover available endpoints
- Generate tool definitions from API schema
- Execute API calls with proper authentication
- Handle errors and return results

#### Step 4.3: Update query_tools Handler
**File:** `custom_components/voice_assistant/conversation.py`

Modify `_handle_query_tools` to:
1. Get regular HA tools (existing functionality)
2. If Music Assistant is enabled, get MA tool definitions
3. Merge both sets of tools
4. Return combined list to LLM

#### Step 4.4: Handle Music Assistant Tool Calls
**File:** `custom_components/voice_assistant/conversation.py`

In tool processing loop:
- Detect Music Assistant tool calls (by name prefix or separate list)
- Execute via Music Assistant API client
- Return results like meta-tools (not through HA's tool system)

#### Step 4.5: Add Configuration Option
**File:** `custom_components/voice_assistant/config_flow.py`

Add to options form:
```python
vol.Optional(
    CONF_ENABLE_MUSIC_ASSISTANT,
    default=self.config_entry.options.get(
        CONF_ENABLE_MUSIC_ASSISTANT, DEFAULT_ENABLE_MUSIC_ASSISTANT
    ),
): bool,

vol.Optional(
    CONF_MUSIC_ASSISTANT_URL,
    default=self.config_entry.options.get(
        CONF_MUSIC_ASSISTANT_URL, DEFAULT_MUSIC_ASSISTANT_URL
    ),
): str,
```

### Example Tool Definitions

Music Assistant tools that should be exposed:

1. **music_assistant_play** - Play media by URI
2. **music_assistant_pause** - Pause playback
3. **music_assistant_stop** - Stop playback
4. **music_assistant_next** - Skip to next track
5. **music_assistant_previous** - Go to previous track
6. **music_assistant_search** - Search for music
7. **music_assistant_get_players** - List available players
8. **music_assistant_set_volume** - Set player volume
9. **music_assistant_queue_add** - Add item to queue

### Testing Checklist
- [ ] Music Assistant API client can connect and discover endpoints
- [ ] query_tools returns both HA tools and Music Assistant tools
- [ ] LLM can discover Music Assistant tools via query_tools
- [ ] Music Assistant tool calls execute successfully
- [ ] Errors are handled gracefully (MA offline, etc.)
- [ ] Configuration options work correctly
- [ ] Can control music playback via voice commands

### Technical Considerations

**API Authentication:**
- Music Assistant may require authentication
- Store API key/token in config if needed

**Error Handling:**
- Handle Music Assistant being offline/unreachable
- Return helpful error messages to LLM
- Don't break other tool functionality if MA fails

**Tool Namespace:**
- Prefix MA tools with `music_assistant_` to avoid conflicts
- Make it clear to LLM which tools are for Music Assistant

**Performance:**
- Cache Music Assistant tool definitions (don't query API every time)
- Only refresh when query_tools is called with domain filter or on config change

---

## Implementation Order Recommendation

1. **Voice Assistant Listening Control** (Feature 3) ✅ COMPLETED
2. **Conversation History Management** (Feature 2) ✅ COMPLETED
3. **Streaming Response Support** (Feature 1) ✅ COMPLETED
4. **Music Assistant Web API Integration** (Feature 4) - **NEXT**

---

## Files to Create/Modify Summary

### New Files
- `custom_components/voice_assistant/storage.py`
- `custom_components/voice_assistant/conversation_manager.py`
- `custom_components/voice_assistant/response_processor.py`

### Modified Files
- `custom_components/voice_assistant/const.py` - Add new constants
- `custom_components/voice_assistant/config_flow.py` - Add new options
- `custom_components/voice_assistant/conversation.py` - Integrate all features
- `custom_components/voice_assistant/llm/base.py` - Add streaming types
- `custom_components/voice_assistant/llm/groq.py` - Enhanced streaming
- `custom_components/voice_assistant/strings.json` - Add option descriptions
- `custom_components/voice_assistant/__init__.py` - Ensure cleanup

---

## Notes for Implementation

1. **Error Handling**: Each feature should fail gracefully - if fact extraction fails, conversation should continue; if streaming fails, fall back to non-streaming.

2. **Logging**: Add comprehensive debug logging for troubleshooting. Use the existing pattern of `_LOGGER.setLevel(logging.DEBUG)`.

3. **Backward Compatibility**: All new features should have configuration options that default to maintaining current behavior.

4. **Testing**: Test each feature in isolation before combining. Use Home Assistant's developer tools for quick reload testing.

5. **Documentation**: Update README.md with new configuration options after implementation.

---

## Feature 4: Music Assistant Integration

### Overview
Integrate with Music Assistant to provide intelligent voice control for music playback across the home. This feature enables natural language music commands like "play some jazz in the living room" or "what's playing in the kitchen" by leveraging Music Assistant's Home Assistant services and the existing meta-tool architecture.

### Current State
- ❌ No Music Assistant support
- ✅ Existing `query_tools` meta-tool can discover `music_assistant.*` services
- ✅ Existing architecture supports dynamic tool discovery

### Research Summary

#### Music Assistant Home Assistant Services
Based on API research ([Music Assistant Integration](https://www.home-assistant.io/integrations/music_assistant/), [Music Assistant API Docs](https://www.music-assistant.io/api/)):

| Service | Purpose | Key Parameters |
|---------|---------|----------------|
| `music_assistant.play_media` | Play/enqueue media | `media_id`, `media_type`, `artist`, `album`, `enqueue`, `radio_mode` |
| `music_assistant.search` | Search library & providers | Query string, returns matches |
| `music_assistant.get_library` | Query library with filters | `media_type`, `search`, `limit`, `order_by`, `favorite` |
| `music_assistant.get_queue` | Get queue & current item | `entity_id` → returns `current_item`, queue data |
| `music_assistant.transfer_queue` | Move queue between players | `source_player`, target entity, `auto_play` |
| `music_assistant.play_announcement` | Play announcement URL | `url`, `announce_volume`, `use_pre_announce` |

#### Media ID Formats
The `play_media` action accepts multiple formats:
- **Name**: "Queen", "Bohemian Rhapsody"
- **Combined**: "Queen - Innuendo"
- **URI**: `spotify://artist/12345`
- **Multiple items**: List format for queuing

#### Enqueue Options
- `play` - Play immediately
- `replace` - Replace queue and play
- `next` - Play next
- `replace_next` - Replace next item
- `add` - Add to end of queue

#### Radio Mode
Generates similar tracks automatically. Requires compatible provider (Spotify, Apple Music, Deezer, Tidal, YouTube Music, Subsonic).

### Architecture Decision

**Option A: Rely on Existing `query_tools`**
- Pros: No new code, Music Assistant services auto-discovered
- Cons: LLM needs to understand complex service parameters, no music-specific context

**Option B: Music-Specific Meta-Tools (RECOMMENDED)**
- Add specialized meta-tools that wrap Music Assistant services
- Provide music-specific context (available players, current playback state)
- Simplify complex operations for the LLM

### Implementation Steps

#### Step 4.1: Add Music Assistant Meta-Tool Definitions
**File:** `custom_components/voice_assistant/llm_tools.py`

Add new meta-tool definitions:

```python
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
```

#### Step 4.2: Create Music Assistant Handler
**File:** `custom_components/voice_assistant/music_assistant.py` (new file)

```python
"""Music Assistant integration for voice control."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

if TYPE_CHECKING:
    from homeassistant.components.conversation import ChatLog

_LOGGER = logging.getLogger(__name__)


class MusicAssistantHandler:
    """Handler for Music Assistant operations."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the Music Assistant handler."""
        self.hass = hass
        self._player_cache: dict[str, str] = {}  # Room name -> entity_id mapping

    def is_available(self) -> bool:
        """Check if Music Assistant integration is available."""
        return self.hass.services.has_service("music_assistant", "play_media")

    async def get_players(self) -> list[dict[str, Any]]:
        """Get all Music Assistant player entities with their state."""
        players = []

        # Get entity registry
        ent_reg = er.async_get(self.hass)

        # Find all media_player entities that start with ma_ (Music Assistant naming convention)
        for entity_id in self.hass.states.async_entity_ids("media_player"):
            state = self.hass.states.get(entity_id)
            if not state:
                continue

            # Check if it's a Music Assistant player
            # MA players typically have "mass" or "music_assistant" in integration
            entity_entry = ent_reg.async_get(entity_id)
            is_ma_player = (
                entity_entry and entity_entry.platform == "music_assistant"
            ) or entity_id.startswith("media_player.ma_")

            if is_ma_player:
                friendly_name = state.attributes.get("friendly_name", entity_id)
                players.append({
                    "entity_id": entity_id,
                    "name": friendly_name,
                    "state": state.state,
                    "media_title": state.attributes.get("media_title"),
                    "media_artist": state.attributes.get("media_artist"),
                    "media_album_name": state.attributes.get("media_album_name"),
                    "volume_level": state.attributes.get("volume_level"),
                })

                # Cache room name mapping
                room_name = self._extract_room_name(friendly_name, entity_id)
                self._player_cache[room_name.lower()] = entity_id

        return players

    def _extract_room_name(self, friendly_name: str, entity_id: str) -> str:
        """Extract room name from friendly name or entity_id."""
        # Try friendly name first
        if friendly_name:
            # Remove common suffixes
            for suffix in [" Speaker", " Player", " MA", " Music"]:
                if friendly_name.endswith(suffix):
                    return friendly_name[:-len(suffix)]
            return friendly_name

        # Fall back to entity_id parsing
        # media_player.ma_living_room -> living room
        name = entity_id.replace("media_player.", "").replace("ma_", "")
        return name.replace("_", " ")

    def resolve_player(self, player_ref: str | None) -> str | None:
        """Resolve player reference (room name or entity_id) to entity_id.

        Args:
            player_ref: Room name (e.g., 'living room') or entity_id.

        Returns:
            Entity ID or None if not found.
        """
        if not player_ref:
            return None

        # Already an entity_id
        if player_ref.startswith("media_player."):
            return player_ref

        # Look up in cache
        normalized = player_ref.lower().strip()
        if normalized in self._player_cache:
            return self._player_cache[normalized]

        # Try fuzzy matching
        for room_name, entity_id in self._player_cache.items():
            if normalized in room_name or room_name in normalized:
                return entity_id

        return None

    async def get_first_active_player(self) -> str | None:
        """Get the first player that is currently playing."""
        players = await self.get_players()
        for player in players:
            if player["state"] == "playing":
                return player["entity_id"]
        # Fall back to first available player
        return players[0]["entity_id"] if players else None

    async def play_music(
        self,
        query: str,
        player: str | None = None,
        media_type: str | None = None,
        enqueue: str = "replace",
        radio_mode: bool = False,
    ) -> dict[str, Any]:
        """Play music using Music Assistant.

        Args:
            query: What to play (artist, album, track, etc.)
            player: Target player (room name or entity_id)
            media_type: Type of media (track, album, artist, playlist, radio)
            enqueue: Queue mode (play, replace, next, add)
            radio_mode: Enable radio mode

        Returns:
            Result dictionary with success status and message.
        """
        if not self.is_available():
            return {
                "success": False,
                "error": "Music Assistant is not available. Please ensure it's installed and configured.",
            }

        # Resolve player
        target_entity = self.resolve_player(player)
        if not target_entity:
            target_entity = await self.get_first_active_player()

        if not target_entity:
            return {
                "success": False,
                "error": "No Music Assistant players found. Please check your Music Assistant configuration.",
            }

        try:
            service_data = {
                "media_id": query,
                "enqueue": enqueue,
            }

            if media_type:
                service_data["media_type"] = media_type

            if radio_mode:
                service_data["radio_mode"] = True

            await self.hass.services.async_call(
                "music_assistant",
                "play_media",
                service_data,
                target={"entity_id": target_entity},
            )

            player_name = self._get_player_name(target_entity)
            return {
                "success": True,
                "message": f"Playing '{query}' on {player_name}",
                "player": target_entity,
            }

        except Exception as err:
            _LOGGER.error("Error playing music: %s", err)
            return {
                "success": False,
                "error": f"Failed to play music: {err}",
            }

    def _get_player_name(self, entity_id: str) -> str:
        """Get friendly name for a player entity."""
        state = self.hass.states.get(entity_id)
        if state:
            return state.attributes.get("friendly_name", entity_id)
        return entity_id

    async def get_now_playing(self, player: str | None = None) -> dict[str, Any]:
        """Get current playback information.

        Args:
            player: Specific player to check, or None for all active.

        Returns:
            Currently playing information.
        """
        players = await self.get_players()

        if player:
            target_entity = self.resolve_player(player)
            players = [p for p in players if p["entity_id"] == target_entity]

        # Filter to only playing players if no specific player requested
        if not player:
            active_players = [p for p in players if p["state"] == "playing"]
            if active_players:
                players = active_players

        if not players:
            return {
                "success": True,
                "message": "Nothing is currently playing",
                "players": [],
            }

        result_players = []
        for p in players:
            info = {
                "player": p["name"],
                "state": p["state"],
            }
            if p["media_title"]:
                info["track"] = p["media_title"]
            if p["media_artist"]:
                info["artist"] = p["media_artist"]
            if p["media_album_name"]:
                info["album"] = p["media_album_name"]
            result_players.append(info)

        return {
            "success": True,
            "players": result_players,
        }

    async def control_playback(
        self,
        action: str,
        player: str | None = None,
        volume_level: int | None = None,
    ) -> dict[str, Any]:
        """Control playback on a player.

        Args:
            action: Control action (play, pause, stop, next, previous, volume_set, etc.)
            player: Target player
            volume_level: Volume level for volume_set action (0-100)

        Returns:
            Result dictionary.
        """
        target_entity = self.resolve_player(player)
        if not target_entity:
            target_entity = await self.get_first_active_player()

        if not target_entity:
            return {
                "success": False,
                "error": "No Music Assistant player found",
            }

        try:
            service_map = {
                "play": "media_play",
                "pause": "media_pause",
                "stop": "media_stop",
                "next": "media_next_track",
                "previous": "media_previous_track",
                "volume_up": "volume_up",
                "volume_down": "volume_down",
                "shuffle": "shuffle_set",
                "repeat": "repeat_set",
            }

            if action == "volume_set" and volume_level is not None:
                await self.hass.services.async_call(
                    "media_player",
                    "volume_set",
                    {"volume_level": volume_level / 100},
                    target={"entity_id": target_entity},
                )
            elif action in service_map:
                await self.hass.services.async_call(
                    "media_player",
                    service_map[action],
                    {},
                    target={"entity_id": target_entity},
                )
            else:
                return {
                    "success": False,
                    "error": f"Unknown action: {action}",
                }

            player_name = self._get_player_name(target_entity)
            return {
                "success": True,
                "message": f"Executed {action} on {player_name}",
            }

        except Exception as err:
            _LOGGER.error("Error controlling playback: %s", err)
            return {
                "success": False,
                "error": f"Failed to control playback: {err}",
            }

    async def search_music(
        self,
        query: str,
        media_type: str | None = None,
        limit: int = 10,
        favorites_only: bool = False,
    ) -> dict[str, Any]:
        """Search music library and providers.

        Args:
            query: Search query
            media_type: Filter by type
            limit: Max results
            favorites_only: Only search favorites

        Returns:
            Search results.
        """
        if not self.is_available():
            return {
                "success": False,
                "error": "Music Assistant is not available",
            }

        try:
            service_data = {
                "search": query,
                "limit": min(limit, 50),
            }

            if media_type:
                service_data["media_type"] = media_type

            if favorites_only:
                service_data["favorite"] = True

            # Use get_library for searching
            response = await self.hass.services.async_call(
                "music_assistant",
                "get_library",
                service_data,
                blocking=True,
                return_response=True,
            )

            return {
                "success": True,
                "results": response if response else [],
                "query": query,
            }

        except Exception as err:
            _LOGGER.error("Error searching music: %s", err)
            return {
                "success": False,
                "error": f"Search failed: {err}",
            }

    async def transfer_music(
        self,
        target_player: str,
        source_player: str | None = None,
    ) -> dict[str, Any]:
        """Transfer music queue to another player.

        Args:
            target_player: Destination player
            source_player: Source player (or first active)

        Returns:
            Result dictionary.
        """
        if not self.is_available():
            return {
                "success": False,
                "error": "Music Assistant is not available",
            }

        target_entity = self.resolve_player(target_player)
        if not target_entity:
            return {
                "success": False,
                "error": f"Could not find player: {target_player}",
            }

        source_entity = None
        if source_player:
            source_entity = self.resolve_player(source_player)

        try:
            service_data = {"auto_play": True}
            if source_entity:
                service_data["source_player"] = source_entity

            await self.hass.services.async_call(
                "music_assistant",
                "transfer_queue",
                service_data,
                target={"entity_id": target_entity},
            )

            target_name = self._get_player_name(target_entity)
            return {
                "success": True,
                "message": f"Transferred music to {target_name}",
            }

        except Exception as err:
            _LOGGER.error("Error transferring music: %s", err)
            return {
                "success": False,
                "error": f"Failed to transfer: {err}",
            }
```

#### Step 4.3: Update Initial Tools to Include Music
**File:** `custom_components/voice_assistant/llm_tools.py`

Modify `get_initial_tools()` to conditionally include music tools:

```python
@staticmethod
def get_initial_tools(include_music: bool = False) -> list[dict[str, Any]]:
    """Get initial meta-tools available to the LLM.

    Args:
        include_music: Whether to include Music Assistant tools.

    Returns:
        List with query_tools, query_facts, learn_fact, and optionally music tools.
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

    return tools
```

#### Step 4.4: Add Configuration Option
**File:** `custom_components/voice_assistant/const.py`

```python
# Music Assistant settings
CONF_ENABLE_MUSIC_ASSISTANT = "enable_music_assistant"
DEFAULT_ENABLE_MUSIC_ASSISTANT = True
```

**File:** `custom_components/voice_assistant/config_flow.py`

Add to options form:
```python
vol.Optional(
    CONF_ENABLE_MUSIC_ASSISTANT,
    default=self.config_entry.options.get(
        CONF_ENABLE_MUSIC_ASSISTANT, DEFAULT_ENABLE_MUSIC_ASSISTANT
    ),
): bool,
```

#### Step 4.5: Integrate with Conversation Agent
**File:** `custom_components/voice_assistant/conversation.py`

Add imports:
```python
from .music_assistant import MusicAssistantHandler
from .const import CONF_ENABLE_MUSIC_ASSISTANT, DEFAULT_ENABLE_MUSIC_ASSISTANT
```

Add to `__init__`:
```python
# Initialize Music Assistant handler
self._music_handler: MusicAssistantHandler | None = None
```

Add property:
```python
@property
def music_handler(self) -> MusicAssistantHandler:
    """Get or create the Music Assistant handler."""
    if self._music_handler is None:
        self._music_handler = MusicAssistantHandler(self.hass)
    return self._music_handler
```

Update tool initialization in `_async_handle_chat_log`:
```python
# Check if Music Assistant is enabled and available
include_music = (
    self._get_config(CONF_ENABLE_MUSIC_ASSISTANT, DEFAULT_ENABLE_MUSIC_ASSISTANT)
    and self.music_handler.is_available()
)

# Start with meta-tools (optionally including music tools)
current_tools = LLMToolManager.get_initial_tools(include_music=include_music)
```

Add music tool handlers in streaming and non-streaming paths:
```python
# Handle music meta-tools
music_tool_calls = []
for tool_call in tool_calls:
    tool_name = tool_call["function"]["name"]
    if tool_name in ["play_music", "get_now_playing", "control_playback",
                      "search_music", "transfer_music", "get_music_players"]:
        music_tool_calls.append(tool_call)

if music_tool_calls:
    music_summary = []
    for tool_call in music_tool_calls:
        tool_name = tool_call["function"]["name"]
        arguments = json.loads(tool_call["function"]["arguments"])
        _LOGGER.info("Handling music tool %s: %s", tool_name, arguments)

        result = await self._handle_music_tool(tool_name, arguments)

        messages.append({
            "role": "tool",
            "tool_call_id": tool_call["id"],
            "content": json.dumps(result),
        })

        if result.get("success"):
            music_summary.append(result.get("message", f"Executed {tool_name}"))

    if music_summary:
        summary_content = AssistantContent(
            agent_id=DOMAIN,
            content="\n".join(music_summary),
        )
        chat_log.async_add_assistant_content_without_tools(summary_content)
```

Add handler method:
```python
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
            players = await handler.get_players()
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
```

#### Step 4.6: Update System Prompt for Music
**File:** `custom_components/voice_assistant/const.py`

Add music instructions to the system prompt:
```python
DEFAULT_SYSTEM_PROMPT = """You are a helpful voice-controlled home assistant that can control smart home devices and answer questions.

**IMPORTANT: This is a VOICE interface - users are speaking to you and hearing your responses.**
Keep responses brief and conversational for voice interaction.

You have access to Home Assistant through a dynamic tool system. Initially, you only have access to meta-tools: `query_tools`, `query_facts`, and `learn_fact`.

**How to interact with Home Assistant:**
1. When you need to control devices or get information about the home, first call `query_tools` to discover available tools
2. You can optionally filter by domain (e.g., "light", "climate", "sensor") to get specific tool categories
3. Once you have the tools, use them to satisfy the user's request
4. After using tools, provide clear, concise responses confirming actions taken

**Tool Discovery Examples:**
- `query_tools()` - Get all available Home Assistant tools
- `query_tools(domain="light")` - Get only light-related tools
- `query_tools(domain="climate")` - Get only climate/thermostat tools

**Music Control (if Music Assistant is available):**
You also have access to music-specific tools for controlling Music Assistant:
- `play_music(query, player?, media_type?, enqueue?, radio_mode?)` - Play music by artist, album, track, or playlist
- `get_now_playing(player?)` - Check what's currently playing
- `control_playback(action, player?, volume_level?)` - Play, pause, skip, volume control
- `search_music(query, media_type?, limit?)` - Search the music library
- `transfer_music(target_player, source_player?)` - Move music between rooms
- `get_music_players()` - List available music players/speakers

Music command examples:
- "Play some jazz" → play_music(query="jazz", media_type="playlist")
- "What's playing?" → get_now_playing()
- "Skip this song" → control_playback(action="next")
- "Play Queen in the kitchen" → play_music(query="Queen", media_type="artist", player="kitchen")
- "Move the music to the bedroom" → transfer_music(target_player="bedroom")

**Learning and Remembering User Information:**
- When users share personal information (names, preferences, routines, etc.), IMMEDIATELY use `learn_fact` to store it
- Examples: "My name is John", "My cat's name is Amy", "I like the temperature at 72°F"
- When you need context about the user, use `query_facts` to retrieve stored information
- Facts persist across all conversations - this is how you remember users between sessions

**Token Efficiency:**
- Only query for tools when you actually need them
- Only query facts when you need user context
- For simple questions that don't require Home Assistant interaction, just answer directly"""
```

#### Step 4.7: Update Strings/Translations
**File:** `custom_components/voice_assistant/strings.json`

Add music configuration strings:
```json
{
  "options": {
    "step": {
      "init": {
        "data": {
          "enable_music_assistant": "Enable Music Assistant integration"
        },
        "data_description": {
          "enable_music_assistant": "Enable voice control for Music Assistant. Requires Music Assistant to be installed and configured."
        }
      }
    }
  }
}
```

### Testing Checklist for Music Assistant
- [ ] Music Assistant detection works when integration is present
- [ ] Music Assistant detection gracefully fails when not present
- [ ] `play_music` plays correct content on specified player
- [ ] `play_music` resolves room names to entity_ids
- [ ] `play_music` falls back to first available player when none specified
- [ ] `get_now_playing` returns correct track information
- [ ] `control_playback` executes all supported actions
- [ ] `search_music` returns relevant results
- [ ] `transfer_music` moves queue between players
- [ ] `get_music_players` lists all MA players
- [ ] Radio mode generates similar tracks
- [ ] Enqueue modes work (play, replace, next, add)
- [ ] Configuration option enables/disables music tools
- [ ] System prompt includes music instructions when enabled
- [ ] Error handling is graceful for all failure modes

### Voice Command Examples to Test

| User Says | Expected Action |
|-----------|-----------------|
| "Play some music" | `play_music(query="popular music")` |
| "Play jazz in the living room" | `play_music(query="jazz", player="living room")` |
| "Play Bohemian Rhapsody by Queen" | `play_music(query="Bohemian Rhapsody", artist="Queen", media_type="track")` |
| "What's playing?" | `get_now_playing()` |
| "What song is this?" | `get_now_playing()` |
| "Pause the music" | `control_playback(action="pause")` |
| "Skip this song" | `control_playback(action="next")` |
| "Turn up the volume" | `control_playback(action="volume_up")` |
| "Set volume to 50%" | `control_playback(action="volume_set", volume_level=50)` |
| "Move the music to the kitchen" | `transfer_music(target_player="kitchen")` |
| "Play the Beatles and add similar songs" | `play_music(query="Beatles", radio_mode=True)` |
| "Find songs by Taylor Swift" | `search_music(query="Taylor Swift", media_type="track")` |
| "What speakers are available?" | `get_music_players()` |

### Notes

1. **Graceful Degradation**: If Music Assistant is not installed, the integration should work normally without music features.

2. **Player Resolution**: The system should be flexible in accepting room names ("living room", "kitchen") or entity IDs (`media_player.ma_living_room`).

3. **Context Awareness**: The LLM should be able to infer which player to use based on conversation context (e.g., "turn it up" refers to the last mentioned player).

4. **Error Messages**: Provide helpful error messages when Music Assistant is not available or when players cannot be found.

5. **Service Availability**: Always check `is_available()` before attempting Music Assistant operations.

---

## Implementation Priority Update

With Music Assistant feature added, recommended order:

1. ✅ **Voice Assistant Listening Control** (Feature 3) - COMPLETED
2. ✅ **Conversation History Management** (Feature 2) - COMPLETED
3. ✅ **Streaming Response Support** (Feature 1) - COMPLETED
4. ⏳ **Music Assistant Integration** (Feature 4) - NEW

---

## References

- [Music Assistant Home Assistant Integration](https://www.home-assistant.io/integrations/music_assistant/)
- [Music Assistant API Documentation](https://www.music-assistant.io/api/)
- [Music Assistant play_media Action](https://www.music-assistant.io/faq/massplaymedia/)
- [Music Assistant get_queue Action](https://www.music-assistant.io/faq/get_queue/)
- [Music Assistant Python Client](https://github.com/music-assistant/client)
