# Implementation Plan: Conversation Agent

## Overview

Implement the Home Assistant conversation agent that integrates the LLM provider with Home Assistant's voice assistant pipeline. This agent receives text input, processes it through the LLM, and returns responses.

## Prerequisites

- Groq provider implemented (see `01-groq-provider.md`)
- Understanding of Home Assistant's conversation agent API

## Files to Create/Modify

1. **Create:** `custom_components/voice_assistant/conversation.py`
2. **Modify:** `custom_components/voice_assistant/__init__.py`
3. **Modify:** `custom_components/voice_assistant/const.py`

## Implementation Steps

### Step 1: Update Constants

Add conversation-related constants to `const.py`:

```python
# Add at the end of const.py

# Conversation settings
CONF_SYSTEM_PROMPT = "system_prompt"

DEFAULT_SYSTEM_PROMPT = """You are a helpful home assistant that can control smart home devices and answer questions. You have access to Home Assistant to control devices and retrieve information.

When asked to control devices or get information about the home:
1. Use the available tools to interact with Home Assistant
2. Provide clear, concise responses
3. Confirm actions you've taken

Be conversational but efficient. Users are often using voice, so keep responses brief."""
```

### Step 2: Create the Conversation Agent

Create `custom_components/voice_assistant/conversation.py`:

```python
"""Conversation agent for Voice Assistant LLM."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Literal

from homeassistant.components import conversation
from homeassistant.components.conversation import agent
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
from .llm import create_llm_provider

if TYPE_CHECKING:
    from .llm.base import BaseLLMProvider

_LOGGER = logging.getLogger(__name__)


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
    def supported_languages(self) -> list[str] | Literal["*"]:
        """Return supported languages."""
        return "*"  # LLMs typically support multiple languages

    async def async_process(
        self, user_input: conversation.ConversationInput
    ) -> conversation.ConversationResult:
        """Process a user input and return a response."""
        conversation_id = user_input.conversation_id or ulid.ulid_now()

        # Get or initialize conversation history
        if conversation_id not in self._conversation_history:
            self._conversation_history[conversation_id] = []

        history = self._conversation_history[conversation_id]

        # Build messages for the LLM
        messages = self._build_messages(user_input.text, history)

        try:
            # Generate response
            response = await self.provider.generate(messages)

            # Extract assistant response
            assistant_message = response.get("content", "")

            # Update conversation history
            history.append({"role": "user", "content": user_input.text})
            history.append({"role": "assistant", "content": assistant_message})

            # Limit history size to prevent token overflow
            if len(history) > 20:
                history = history[-20:]
                self._conversation_history[conversation_id] = history

            # Create response
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

    def _build_messages(
        self, user_text: str, history: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Build the messages list for the LLM.

        Args:
            user_text: The current user input.
            history: Previous conversation history.

        Returns:
            List of messages in OpenAI format.
        """
        system_prompt = self.entry.data.get(CONF_SYSTEM_PROMPT, DEFAULT_SYSTEM_PROMPT)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ]

        # Add conversation history
        messages.extend(history)

        # Add current user message
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
```

### Step 3: Update `__init__.py`

Update `custom_components/voice_assistant/__init__.py` to register the conversation agent:

```python
"""Voice Assistant LLM integration for Home Assistant."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.CONVERSATION]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Voice Assistant LLM from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
```

### Step 4: Create Conversation Platform Setup

Create `custom_components/voice_assistant/conversation.py` (add platform setup at the top):

The file already contains the `VoiceAssistantConversationAgent` class. Add the platform setup function at the end:

```python
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up conversation platform."""
    async_add_entities([VoiceAssistantConversationAgent(hass, config_entry)])
```

### Complete File: `conversation.py`

```python
"""Conversation agent for Voice Assistant LLM."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Literal

from homeassistant.components import conversation
from homeassistant.components.conversation import agent
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
from .llm import create_llm_provider

if TYPE_CHECKING:
    from .llm.base import BaseLLMProvider

_LOGGER = logging.getLogger(__name__)


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

        try:
            response = await self.provider.generate(messages)
            assistant_message = response.get("content", "")

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
2. Go to Settings → Voice Assistants
3. Create or edit a voice assistant
4. Select "Voice Assistant LLM" as the conversation agent
5. Test with text input in the conversation panel or via voice

## Expected Behavior

- The agent should respond to general questions
- Conversation history is maintained within sessions
- Error messages are handled gracefully

## Next Steps

After completing the conversation agent, proceed to:
- `03-ha-api-client.md` - Implement Home Assistant API tools for the LLM
