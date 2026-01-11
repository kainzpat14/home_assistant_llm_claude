"""Groq LLM provider implementation."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, AsyncIterator

from groq import AsyncGroq

from .base import BaseLLMProvider

if TYPE_CHECKING:
    from groq.types.chat import ChatCompletion

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG)


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
