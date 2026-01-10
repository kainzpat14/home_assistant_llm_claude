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
