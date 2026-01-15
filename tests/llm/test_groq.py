"""Tests for Groq LLM provider module."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.voice_assistant.llm.base import StreamChunk
from custom_components.voice_assistant.llm.groq import GroqProvider


class TestGroqProvider:
    """Test the GroqProvider class."""

    @pytest.fixture
    def provider(self):
        """Create a GroqProvider instance."""
        return GroqProvider(
            api_key="test_key",
            model="test_model",
            temperature=0.5,
            max_tokens=2048,
        )

    def test_init(self):
        """Test GroqProvider initialization."""
        provider = GroqProvider(
            api_key="test_key",
            model="test_model",
            temperature=0.5,
            max_tokens=2048,
        )

        assert provider.api_key == "test_key"
        assert provider.model == "test_model"
        assert provider.temperature == 0.5
        assert provider.max_tokens == 2048
        assert provider._client is None

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        provider = GroqProvider(api_key="test_key")

        assert provider.api_key == "test_key"
        assert provider.model == "llama-3.3-70b-versatile"
        assert provider.temperature == 0.7
        assert provider.max_tokens == 1024

    def test_client_property_lazy_initialization(self, provider):
        """Test that client is lazily initialized."""
        with patch("custom_components.voice_assistant.llm.groq.AsyncGroq") as mock_groq:
            mock_client = MagicMock()
            mock_groq.return_value = mock_client

            # First access should create client
            client1 = provider.client
            assert client1 == mock_client
            mock_groq.assert_called_once_with(api_key="test_key")

            # Second access should return same client
            client2 = provider.client
            assert client2 == mock_client
            # Should still only be called once
            mock_groq.assert_called_once()

    async def test_generate_simple_response(self, provider):
        """Test generating a simple text response."""
        with patch.object(provider, "_client") as mock_client:
            provider._client = mock_client
            # Mock response
            mock_message = MagicMock()
            mock_message.role = "assistant"
            mock_message.content = "Hello, how can I help you?"
            mock_message.tool_calls = None

            mock_choice = MagicMock()
            mock_choice.message = mock_message

            mock_response = MagicMock()
            mock_response.choices = [mock_choice]

            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

            messages = [{"role": "user", "content": "Hello"}]
            result = await provider.generate(messages)

            assert result["role"] == "assistant"
            assert result["content"] == "Hello, how can I help you?"
            assert "tool_calls" not in result

            mock_client.chat.completions.create.assert_called_once()
            call_kwargs = mock_client.chat.completions.create.call_args[1]
            assert call_kwargs["model"] == "test_model"
            assert call_kwargs["messages"] == messages
            assert call_kwargs["temperature"] == 0.5
            assert call_kwargs["max_tokens"] == 2048

    async def test_generate_with_tools(self, provider):
        """Test generating with tool calls."""
        mock_client = MagicMock()
        provider._client = mock_client
        with patch.object(provider, "_client", mock_client):
            # Mock tool call
            mock_tool_call = MagicMock()
            mock_tool_call.id = "call_123"
            mock_tool_call.type = "function"
            mock_tool_call.function.name = "get_weather"
            mock_tool_call.function.arguments = '{"location": "Paris"}'

            mock_message = MagicMock()
            mock_message.role = "assistant"
            mock_message.content = ""
            mock_message.tool_calls = [mock_tool_call]

            mock_choice = MagicMock()
            mock_choice.message = mock_message

            mock_response = MagicMock()
            mock_response.choices = [mock_choice]

            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

            messages = [{"role": "user", "content": "What's the weather in Paris?"}]
            tools = [{"type": "function", "function": {"name": "get_weather"}}]
            result = await provider.generate(messages, tools=tools)

            assert result["role"] == "assistant"
            assert len(result["tool_calls"]) == 1
            assert result["tool_calls"][0]["id"] == "call_123"
            assert result["tool_calls"][0]["function"]["name"] == "get_weather"

            call_kwargs = mock_client.chat.completions.create.call_args[1]
            assert call_kwargs["tools"] == tools
            assert call_kwargs["tool_choice"] == "auto"

    async def test_generate_with_none_content(self, provider):
        """Test generating when content is None."""
        mock_client = MagicMock()
        provider._client = mock_client
        with patch.object(provider, "_client", mock_client):
            mock_message = MagicMock()
            mock_message.role = "assistant"
            mock_message.content = None
            mock_message.tool_calls = None

            mock_choice = MagicMock()
            mock_choice.message = mock_message

            mock_response = MagicMock()
            mock_response.choices = [mock_choice]

            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

            result = await provider.generate([{"role": "user", "content": "Hello"}])

            # Should default to empty string
            assert result["content"] == ""

    async def test_generate_error_handling(self, provider):
        """Test error handling during generation."""
        mock_client = MagicMock()
        provider._client = mock_client
        with patch.object(provider, "_client", mock_client):
            mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API Error"))

            with pytest.raises(Exception, match="API Error"):
                await provider.generate([{"role": "user", "content": "Hello"}])

    async def test_generate_stream(self, provider):
        """Test streaming text generation."""
        mock_client = MagicMock()
        provider._client = mock_client
        with patch.object(provider, "_client", mock_client):
            # Mock streaming chunks
            mock_chunks = []
            for text in ["Hello", " ", "world", "!"]:
                chunk = MagicMock()
                delta = MagicMock()
                delta.content = text
                choice = MagicMock()
                choice.delta = delta
                chunk.choices = [choice]
                mock_chunks.append(chunk)

            async def mock_stream():
                for chunk in mock_chunks:
                    yield chunk

            mock_client.chat.completions.create = AsyncMock(return_value=mock_stream())

            messages = [{"role": "user", "content": "Say hello"}]
            chunks = []
            async for chunk in provider.generate_stream(messages):
                chunks.append(chunk)

            assert chunks == ["Hello", " ", "world", "!"]

            call_kwargs = mock_client.chat.completions.create.call_args[1]
            assert call_kwargs["stream"] is True

    async def test_generate_stream_with_none_content(self, provider):
        """Test streaming skips chunks with None content."""
        mock_client = MagicMock()
        provider._client = mock_client
        with patch.object(provider, "_client", mock_client):
            mock_chunks = []
            # First chunk with None content
            chunk1 = MagicMock()
            delta1 = MagicMock()
            delta1.content = None
            choice1 = MagicMock()
            choice1.delta = delta1
            chunk1.choices = [choice1]
            mock_chunks.append(chunk1)

            # Second chunk with content
            chunk2 = MagicMock()
            delta2 = MagicMock()
            delta2.content = "Hello"
            choice2 = MagicMock()
            choice2.delta = delta2
            chunk2.choices = [choice2]
            mock_chunks.append(chunk2)

            async def mock_stream():
                for chunk in mock_chunks:
                    yield chunk

            mock_client.chat.completions.create = AsyncMock(return_value=mock_stream())

            chunks = []
            async for chunk in provider.generate_stream([{"role": "user", "content": "test"}]):
                chunks.append(chunk)

            # Should only yield the non-None chunk
            assert chunks == ["Hello"]

    async def test_generate_stream_with_tools_content_only(self, provider):
        """Test streaming with tools but only content chunks."""
        mock_client = MagicMock()
        provider._client = mock_client
        with patch.object(provider, "_client", mock_client):
            mock_chunks = []
            for text in ["Hello", " world"]:
                chunk = MagicMock()
                delta = MagicMock()
                delta.content = text
                delta.tool_calls = None
                choice = MagicMock()
                choice.delta = delta
                choice.finish_reason = None
                chunk.choices = [choice]
                mock_chunks.append(chunk)

            # Final chunk with finish reason
            final_chunk = MagicMock()
            final_delta = MagicMock()
            final_delta.content = None
            final_delta.tool_calls = None
            final_choice = MagicMock()
            final_choice.delta = final_delta
            final_choice.finish_reason = "stop"
            final_chunk.choices = [final_choice]
            mock_chunks.append(final_chunk)

            async def mock_stream():
                for chunk in mock_chunks:
                    yield chunk

            mock_client.chat.completions.create = AsyncMock(return_value=mock_stream())

            chunks = []
            async for chunk in provider.generate_stream_with_tools([{"role": "user", "content": "test"}]):
                chunks.append(chunk)

            # Should have content chunks and final chunk
            assert len(chunks) == 3
            assert chunks[0].content == "Hello"
            assert chunks[1].content == " world"
            assert chunks[2].is_final is True

    async def test_generate_stream_with_tools_tool_calls(self, provider):
        """Test streaming with tool call accumulation."""
        mock_client = MagicMock()
        provider._client = mock_client
        with patch.object(provider, "_client", mock_client):
            mock_chunks = []

            # First tool call chunk
            chunk1 = MagicMock()
            delta1 = MagicMock()
            delta1.content = None
            tc_delta1 = MagicMock()
            tc_delta1.index = 0
            tc_delta1.id = "call_123"
            tc_delta1.function.name = "get_weather"
            tc_delta1.function.arguments = '{"location"'
            delta1.tool_calls = [tc_delta1]
            choice1 = MagicMock()
            choice1.delta = delta1
            choice1.finish_reason = None
            chunk1.choices = [choice1]
            mock_chunks.append(chunk1)

            # Second tool call chunk (continuation)
            chunk2 = MagicMock()
            delta2 = MagicMock()
            delta2.content = None
            tc_delta2 = MagicMock()
            tc_delta2.index = 0
            tc_delta2.id = None
            tc_delta2.function.name = ""
            tc_delta2.function.arguments = ': "Paris"}'
            delta2.tool_calls = [tc_delta2]
            choice2 = MagicMock()
            choice2.delta = delta2
            choice2.finish_reason = None
            chunk2.choices = [choice2]
            mock_chunks.append(chunk2)

            # Final chunk
            final_chunk = MagicMock()
            final_delta = MagicMock()
            final_delta.content = None
            final_delta.tool_calls = None
            final_choice = MagicMock()
            final_choice.delta = final_delta
            final_choice.finish_reason = "tool_calls"
            final_chunk.choices = [final_choice]
            mock_chunks.append(final_chunk)

            async def mock_stream():
                for chunk in mock_chunks:
                    yield chunk

            mock_client.chat.completions.create = AsyncMock(return_value=mock_stream())

            chunks = []
            async for chunk in provider.generate_stream_with_tools([{"role": "user", "content": "test"}]):
                chunks.append(chunk)

            # Should have final chunk with accumulated tool calls
            assert len(chunks) == 1
            assert chunks[0].is_final is True
            assert chunks[0].tool_calls is not None
            assert len(chunks[0].tool_calls) == 1
            assert chunks[0].tool_calls[0]["id"] == "call_123"
            assert chunks[0].tool_calls[0]["function"]["name"] == "get_weather"
            assert chunks[0].tool_calls[0]["function"]["arguments"] == '{"location": "Paris"}'

    async def test_validate_api_key_success(self, provider):
        """Test successful API key validation."""
        mock_client = MagicMock()
        provider._client = mock_client
        with patch.object(provider, "_client", mock_client):
            mock_client.chat.completions.create = AsyncMock(return_value=MagicMock())

            result = await provider.validate_api_key()

            assert result is True
            mock_client.chat.completions.create.assert_called_once()

    async def test_validate_api_key_failure(self, provider):
        """Test failed API key validation."""
        mock_client = MagicMock()
        provider._client = mock_client
        with patch.object(provider, "_client", mock_client):
            mock_client.chat.completions.create = AsyncMock(side_effect=Exception("Invalid API key"))

            result = await provider.validate_api_key()

            assert result is False
