"""Base class for LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, AsyncIterator

if TYPE_CHECKING:
    from typing import Any


@dataclass
class StreamChunk:
    """Represents a chunk of streaming response."""

    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    is_final: bool = False


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> None:
        """Initialize the LLM provider."""
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.temperature = temperature
        self.max_tokens = max_tokens

    @abstractmethod
    async def generate(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Generate a response from the LLM.

        Args:
            messages: List of conversation messages.
            tools: Optional list of available tools/functions.

        Returns:
            The LLM response including any tool calls.
        """

    @abstractmethod
    async def generate_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        """Generate a streaming response from the LLM.

        Args:
            messages: List of conversation messages.
            tools: Optional list of available tools/functions.

        Yields:
            Response text chunks as they are generated.
        """

    @abstractmethod
    async def generate_stream_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Generate streaming response with tool call support.

        Args:
            messages: List of conversation messages.
            tools: Optional list of available tools/functions.

        Yields:
            StreamChunk objects containing either content deltas or accumulated tool calls.
        """

    @abstractmethod
    async def validate_api_key(self) -> bool:
        """Validate that the API key is valid.

        Returns:
            True if the API key is valid, False otherwise.
        """
