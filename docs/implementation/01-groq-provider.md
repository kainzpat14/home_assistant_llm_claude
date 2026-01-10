# Implementation Plan: Groq LLM Provider

## Overview

Implement the Groq LLM provider that extends the `BaseLLMProvider` abstract class. This provider will use the official Groq Python SDK to communicate with the Groq API.

## Prerequisites

- Groq Python SDK is already listed in `manifest.json` requirements: `groq>=0.4.0`
- Base class exists at `custom_components/voice_assistant/llm/base.py`

## File to Create

**Path:** `custom_components/voice_assistant/llm/groq.py`

## Implementation Steps

### Step 1: Create the Groq Provider Class

Create `custom_components/voice_assistant/llm/groq.py` with the following structure:

```python
"""Groq LLM provider implementation."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, AsyncIterator

from groq import AsyncGroq

from .base import BaseLLMProvider

if TYPE_CHECKING:
    from groq.types.chat import ChatCompletion, ChatCompletionChunk

_LOGGER = logging.getLogger(__name__)


class GroqProvider(BaseLLMProvider):
    """Groq API LLM provider."""

    def __init__(
        self,
        api_key: str,
        model: str = "llama-3.3-70b-versatile",
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> None:
        """Initialize the Groq provider."""
        super().__init__(
            api_key=api_key,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        self._client: AsyncGroq | None = None

    @property
    def client(self) -> AsyncGroq:
        """Get or create the Groq client."""
        if self._client is None:
            self._client = AsyncGroq(api_key=self.api_key)
        return self._client
```

### Step 2: Implement the `generate` Method

Add the non-streaming generation method:

```python
    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Generate a response from Groq.

        Args:
            messages: List of conversation messages in OpenAI format.
                      [{"role": "user", "content": "Hello"}, ...]
            tools: Optional list of tools in OpenAI function calling format.

        Returns:
            Dict with 'content' (str), 'role' (str), and optionally 'tool_calls'.
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            response: ChatCompletion = await self.client.chat.completions.create(**kwargs)
            message = response.choices[0].message

            result: dict[str, Any] = {
                "role": message.role,
                "content": message.content or "",
            }

            if message.tool_calls:
                result["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ]

            return result

        except Exception as err:
            _LOGGER.error("Groq API error: %s", err)
            raise
```

### Step 3: Implement the `generate_stream` Method

Add the streaming generation method:

```python
    async def generate_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        """Generate a streaming response from Groq.

        Args:
            messages: List of conversation messages.
            tools: Optional list of tools (note: tool calls may not stream well).

        Yields:
            Response text chunks as they are generated.
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
        }

        # Note: Streaming with tools can be complex; for now, we focus on text streaming
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            stream = await self.client.chat.completions.create(**kwargs)

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as err:
            _LOGGER.error("Groq streaming error: %s", err)
            raise
```

### Step 4: Implement the `validate_api_key` Method

Add API key validation:

```python
    async def validate_api_key(self) -> bool:
        """Validate the Groq API key by making a minimal request.

        Returns:
            True if the API key is valid, False otherwise.
        """
        try:
            # Make a minimal request to validate the key
            await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=1,
            )
            return True
        except Exception as err:
            _LOGGER.warning("Groq API key validation failed: %s", err)
            return False
```

### Step 5: Update `llm/__init__.py`

Update `custom_components/voice_assistant/llm/__init__.py` to export the provider:

```python
"""LLM provider implementations."""

from .base import BaseLLMProvider
from .groq import GroqProvider

__all__ = ["BaseLLMProvider", "GroqProvider"]
```

### Step 6: Create Provider Factory

Create `custom_components/voice_assistant/llm/factory.py` to instantiate providers:

```python
"""Factory for creating LLM provider instances."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..const import PROVIDER_GROQ

if TYPE_CHECKING:
    from .base import BaseLLMProvider


def create_llm_provider(
    provider: str,
    api_key: str,
    model: str,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    **kwargs: Any,
) -> BaseLLMProvider:
    """Create an LLM provider instance.

    Args:
        provider: Provider identifier (e.g., "groq").
        api_key: API key for the provider.
        model: Model identifier.
        temperature: Response temperature.
        max_tokens: Maximum response tokens.
        **kwargs: Additional provider-specific arguments.

    Returns:
        An initialized LLM provider instance.

    Raises:
        ValueError: If the provider is not supported.
    """
    if provider == PROVIDER_GROQ:
        from .groq import GroqProvider
        return GroqProvider(
            api_key=api_key,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    raise ValueError(f"Unsupported LLM provider: {provider}")
```

Update `llm/__init__.py` to also export the factory:

```python
"""LLM provider implementations."""

from .base import BaseLLMProvider
from .factory import create_llm_provider
from .groq import GroqProvider

__all__ = ["BaseLLMProvider", "GroqProvider", "create_llm_provider"]
```

### Step 7: Update Config Flow to Validate API Key

Modify `config_flow.py` to validate the API key during setup:

```python
# Add this import at the top
from .llm import create_llm_provider

# Update async_step_user method:
async def async_step_user(
    self, user_input: dict[str, Any] | None = None
) -> ConfigFlowResult:
    """Handle the initial step."""
    errors: dict[str, str] = {}

    if user_input is not None:
        # Validate API key
        try:
            provider = create_llm_provider(
                provider=user_input[CONF_PROVIDER],
                api_key=user_input[CONF_API_KEY],
                model=user_input[CONF_MODEL],
                temperature=user_input.get(CONF_TEMPERATURE, DEFAULT_TEMPERATURE),
                max_tokens=user_input.get(CONF_MAX_TOKENS, DEFAULT_MAX_TOKENS),
            )
            if not await provider.validate_api_key():
                errors["base"] = "invalid_api_key"
        except Exception:
            errors["base"] = "cannot_connect"

        if not errors:
            return self.async_create_entry(
                title=f"Voice Assistant ({user_input[CONF_PROVIDER]})",
                data=user_input,
            )

    return self.async_show_form(
        step_id="user",
        data_schema=vol.Schema(
            {
                vol.Required(CONF_PROVIDER, default=PROVIDER_GROQ): vol.In(
                    SUPPORTED_PROVIDERS
                ),
                vol.Required(CONF_API_KEY): str,
                vol.Required(
                    CONF_MODEL, default=DEFAULT_MODELS[PROVIDER_GROQ]
                ): str,
                vol.Optional(
                    CONF_TEMPERATURE, default=DEFAULT_TEMPERATURE
                ): vol.Coerce(float),
                vol.Optional(
                    CONF_MAX_TOKENS, default=DEFAULT_MAX_TOKENS
                ): vol.Coerce(int),
            }
        ),
        errors=errors,
    )
```

## Complete File: `llm/groq.py`

Here's the complete file for reference:

```python
"""Groq LLM provider implementation."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, AsyncIterator

from groq import AsyncGroq

from .base import BaseLLMProvider

if TYPE_CHECKING:
    from groq.types.chat import ChatCompletion

_LOGGER = logging.getLogger(__name__)


class GroqProvider(BaseLLMProvider):
    """Groq API LLM provider."""

    def __init__(
        self,
        api_key: str,
        model: str = "llama-3.3-70b-versatile",
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> None:
        """Initialize the Groq provider."""
        super().__init__(
            api_key=api_key,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        self._client: AsyncGroq | None = None

    @property
    def client(self) -> AsyncGroq:
        """Get or create the Groq client."""
        if self._client is None:
            self._client = AsyncGroq(api_key=self.api_key)
        return self._client

    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Generate a response from Groq.

        Args:
            messages: List of conversation messages in OpenAI format.
            tools: Optional list of tools in OpenAI function calling format.

        Returns:
            Dict with 'content', 'role', and optionally 'tool_calls'.
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            response: ChatCompletion = await self.client.chat.completions.create(**kwargs)
            message = response.choices[0].message

            result: dict[str, Any] = {
                "role": message.role,
                "content": message.content or "",
            }

            if message.tool_calls:
                result["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ]

            return result

        except Exception as err:
            _LOGGER.error("Groq API error: %s", err)
            raise

    async def generate_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        """Generate a streaming response from Groq.

        Args:
            messages: List of conversation messages.
            tools: Optional list of tools.

        Yields:
            Response text chunks as they are generated.
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            stream = await self.client.chat.completions.create(**kwargs)

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as err:
            _LOGGER.error("Groq streaming error: %s", err)
            raise

    async def validate_api_key(self) -> bool:
        """Validate the Groq API key.

        Returns:
            True if valid, False otherwise.
        """
        try:
            await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=1,
            )
            return True
        except Exception as err:
            _LOGGER.warning("Groq API key validation failed: %s", err)
            return False
```

## Testing

After implementation, test by:

1. Restart Home Assistant
2. Remove and re-add the integration
3. Enter a valid Groq API key (get one at https://console.groq.com/)
4. The integration should validate the key and set up successfully
5. Check Home Assistant logs for any errors

## Next Steps

After completing the Groq provider, proceed to:
- `02-conversation-agent.md` - Implement the conversation agent
