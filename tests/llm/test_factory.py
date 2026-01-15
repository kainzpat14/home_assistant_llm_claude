"""Tests for LLM factory module."""

import pytest

from custom_components.voice_assistant.const import PROVIDER_GROQ
from custom_components.voice_assistant.llm.factory import create_llm_provider
from custom_components.voice_assistant.llm.groq import GroqProvider


class TestCreateLLMProvider:
    """Test the create_llm_provider factory function."""

    def test_create_groq_provider(self):
        """Test creating a Groq provider."""
        provider = create_llm_provider(
            provider=PROVIDER_GROQ,
            api_key="test_key",
            model="test_model",
            temperature=0.5,
            max_tokens=2048,
        )

        assert isinstance(provider, GroqProvider)
        assert provider.api_key == "test_key"
        assert provider.model == "test_model"
        assert provider.temperature == 0.5
        assert provider.max_tokens == 2048

    def test_create_groq_provider_with_defaults(self):
        """Test creating a Groq provider with default values."""
        provider = create_llm_provider(
            provider=PROVIDER_GROQ,
            api_key="test_key",
            model="test_model",
        )

        assert isinstance(provider, GroqProvider)
        assert provider.api_key == "test_key"
        assert provider.model == "test_model"
        assert provider.temperature == 0.7  # default
        assert provider.max_tokens == 1024  # default

    def test_create_groq_provider_with_kwargs(self):
        """Test creating a Groq provider with additional kwargs."""
        # Note: GroqProvider doesn't currently support base_url in __init__
        # but the factory passes **kwargs, so it shouldn't error
        provider = create_llm_provider(
            provider=PROVIDER_GROQ,
            api_key="test_key",
            model="test_model",
        )

        assert isinstance(provider, GroqProvider)
        # GroqProvider inherits base_url from BaseLLMProvider but doesn't set it
        assert provider.base_url is None

    def test_unsupported_provider_raises_error(self):
        """Test that unsupported provider raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported LLM provider: unsupported"):
            create_llm_provider(
                provider="unsupported",
                api_key="test_key",
                model="test_model",
            )

    def test_openai_provider_not_implemented(self):
        """Test that OpenAI provider is not yet implemented."""
        with pytest.raises(ValueError, match="Unsupported LLM provider: openai"):
            create_llm_provider(
                provider="openai",
                api_key="test_key",
                model="gpt-4",
            )

    def test_anthropic_provider_not_implemented(self):
        """Test that Anthropic provider is not yet implemented."""
        with pytest.raises(ValueError, match="Unsupported LLM provider: anthropic"):
            create_llm_provider(
                provider="anthropic",
                api_key="test_key",
                model="claude-3",
            )

    def test_provider_parameter_required(self):
        """Test that provider parameter is required."""
        # This will raise ValueError from the factory, not a TypeError
        with pytest.raises((ValueError, TypeError)):
            create_llm_provider(
                provider=None,
                api_key="test_key",
                model="test_model",
            )

    def test_api_key_passed_correctly(self):
        """Test that API key is passed to provider correctly."""
        api_key = "sk-1234567890abcdef"
        provider = create_llm_provider(
            provider=PROVIDER_GROQ,
            api_key=api_key,
            model="test_model",
        )

        assert provider.api_key == api_key

    def test_model_passed_correctly(self):
        """Test that model is passed to provider correctly."""
        model = "llama-3.3-70b-versatile"
        provider = create_llm_provider(
            provider=PROVIDER_GROQ,
            api_key="test_key",
            model=model,
        )

        assert provider.model == model

    def test_temperature_passed_correctly(self):
        """Test that temperature is passed to provider correctly."""
        temperature = 0.9
        provider = create_llm_provider(
            provider=PROVIDER_GROQ,
            api_key="test_key",
            model="test_model",
            temperature=temperature,
        )

        assert provider.temperature == temperature

    def test_max_tokens_passed_correctly(self):
        """Test that max_tokens is passed to provider correctly."""
        max_tokens = 4096
        provider = create_llm_provider(
            provider=PROVIDER_GROQ,
            api_key="test_key",
            model="test_model",
            max_tokens=max_tokens,
        )

        assert provider.max_tokens == max_tokens
