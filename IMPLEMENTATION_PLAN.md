# Implementation Plan for Voice Assistant Features

This document provides detailed implementation instructions for three features:
1. Streaming Response Support
2. Conversation History Management with Timeout
3. Voice Assistant Listening Control

---

## Feature 1: Streaming Response Support

### Overview
Enable real-time streaming of LLM responses to Home Assistant, providing immediate feedback to users instead of waiting for complete responses.

### Current State
- `GroqProvider.generate_stream()` is implemented in `llm/groq.py:99-134`
- Returns `AsyncIterator[str]` yielding content chunks
- **Not integrated** with conversation agent
- **Limitation**: Groq streaming doesn't support tool calls in chunks

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
- [ ] Simple response without tool calls streams correctly
- [ ] Response with query_tools call works (tools discovered, then response streams)
- [ ] Response with HA tool calls works (lights turn on, etc.)
- [ ] Multi-turn conversation maintains history
- [ ] Streaming can be disabled via config option
- [ ] Error handling works for streaming failures

---

## Feature 2: Conversation History Management with Timeout

### Overview
Implement external conversation history storage with configurable timeout and fact learning/persistence.

### Current State
- Conversation history is managed by Home Assistant's `chat_log`
- No persistent storage of learned facts
- No timeout-based session management

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

## Feature 3: Voice Assistant Listening Control

### Overview
Control whether the voice assistant continues listening after a response, preventing unwanted continued listening when responses end with `?`.

### Current State
- Home Assistant automatically continues listening if response ends with `?`
- No control over this behavior

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
- [ ] Response ending with `?` does NOT continue listening (default)
- [ ] Response with `[CONTINUE_LISTENING]` marker DOES continue listening
- [ ] Marker is removed from spoken response
- [ ] auto_continue_listening=True allows normal `?` behavior
- [ ] Configuration option works correctly
- [ ] Unicode replacement character sounds natural when spoken
- [ ] Original response (with `?`) is preserved in chat history

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
