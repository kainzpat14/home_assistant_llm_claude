"""Tests for LLM base provider module."""

from abc import ABC

import pytest

from custom_components.voice_assistant.llm.base import BaseLLMProvider, StreamChunk


class TestStreamChunk:
    """Test the StreamChunk dataclass."""

    def test_init_defaults(self):
        """Test StreamChunk initialization with defaults."""
        chunk = StreamChunk()

        assert chunk.content is None
        assert chunk.tool_calls is None
        assert chunk.is_final is False

    def test_init_with_content(self):
        """Test StreamChunk with content."""
        chunk = StreamChunk(content="Hello")

        assert chunk.content == "Hello"
        assert chunk.tool_calls is None
        assert chunk.is_final is False

    def test_init_with_tool_calls(self):
        """Test StreamChunk with tool calls."""
        tool_calls = [{"id": "1", "function": {"name": "test"}}]
        chunk = StreamChunk(tool_calls=tool_calls)

        assert chunk.content is None
        assert chunk.tool_calls == tool_calls
        assert chunk.is_final is False

    def test_init_final_chunk(self):
        """Test StreamChunk marked as final."""
        chunk = StreamChunk(content="Done", is_final=True)

        assert chunk.content == "Done"
        assert chunk.is_final is True

    def test_init_all_fields(self):
        """Test StreamChunk with all fields."""
        tool_calls = [{"id": "1"}]
        chunk = StreamChunk(content="Test", tool_calls=tool_calls, is_final=True)

        assert chunk.content == "Test"
        assert chunk.tool_calls == tool_calls
        assert chunk.is_final is True


class TestBaseLLMProvider:
    """Test the BaseLLMProvider abstract class."""

    def test_is_abstract(self):
        """Test that BaseLLMProvider is abstract and cannot be instantiated."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            BaseLLMProvider()

    def test_init_parameters(self):
        """Test that subclass receives init parameters correctly."""

        class ConcreteProvider(BaseLLMProvider):
            """Concrete implementation for testing."""

            async def generate(self, messages, tools=None):
                """Implement abstract method."""
                return {}

            async def generate_stream(self, messages, tools=None):
                """Implement abstract method."""
                yield "test"

            async def generate_stream_with_tools(self, messages, tools=None):
                """Implement abstract method."""
                yield StreamChunk(content="test")

            async def validate_api_key(self):
                """Implement abstract method."""
                return True

        provider = ConcreteProvider(
            api_key="test_key",
            model="test_model",
            base_url="http://test.com",
            temperature=0.5,
            max_tokens=2048,
        )

        assert provider.api_key == "test_key"
        assert provider.model == "test_model"
        assert provider.base_url == "http://test.com"
        assert provider.temperature == 0.5
        assert provider.max_tokens == 2048

    def test_init_defaults(self):
        """Test default values in initialization."""

        class ConcreteProvider(BaseLLMProvider):
            """Concrete implementation for testing."""

            async def generate(self, messages, tools=None):
                """Implement abstract method."""
                return {}

            async def generate_stream(self, messages, tools=None):
                """Implement abstract method."""
                yield "test"

            async def generate_stream_with_tools(self, messages, tools=None):
                """Implement abstract method."""
                yield StreamChunk(content="test")

            async def validate_api_key(self):
                """Implement abstract method."""
                return True

        provider = ConcreteProvider()

        assert provider.api_key is None
        assert provider.model is None
        assert provider.base_url is None
        assert provider.temperature == 0.7
        assert provider.max_tokens == 1024

    def test_abstract_methods_required(self):
        """Test that all abstract methods must be implemented."""

        class IncompleteProvider(BaseLLMProvider):
            """Provider missing some abstract methods."""

            async def generate(self, messages, tools=None):
                """Implement abstract method."""
                return {}

        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IncompleteProvider()

    async def test_generate_abstract(self):
        """Test that generate method must be implemented."""

        class TestProvider(BaseLLMProvider):
            """Test provider."""

            async def generate(self, messages, tools=None):
                """Implement abstract method."""
                return {"content": "test"}

            async def generate_stream(self, messages, tools=None):
                """Implement abstract method."""
                yield "test"

            async def generate_stream_with_tools(self, messages, tools=None):
                """Implement abstract method."""
                yield StreamChunk(content="test")

            async def validate_api_key(self):
                """Implement abstract method."""
                return True

        provider = TestProvider()
        result = await provider.generate([{"role": "user", "content": "test"}])

        assert result == {"content": "test"}

    async def test_generate_stream_abstract(self):
        """Test that generate_stream method must be implemented."""

        class TestProvider(BaseLLMProvider):
            """Test provider."""

            async def generate(self, messages, tools=None):
                """Implement abstract method."""
                return {}

            async def generate_stream(self, messages, tools=None):
                """Implement abstract method."""
                yield "chunk1"
                yield "chunk2"

            async def generate_stream_with_tools(self, messages, tools=None):
                """Implement abstract method."""
                yield StreamChunk(content="test")

            async def validate_api_key(self):
                """Implement abstract method."""
                return True

        provider = TestProvider()
        chunks = []
        async for chunk in provider.generate_stream([{"role": "user", "content": "test"}]):
            chunks.append(chunk)

        assert chunks == ["chunk1", "chunk2"]

    async def test_validate_api_key_abstract(self):
        """Test that validate_api_key method must be implemented."""

        class TestProvider(BaseLLMProvider):
            """Test provider."""

            async def generate(self, messages, tools=None):
                """Implement abstract method."""
                return {}

            async def generate_stream(self, messages, tools=None):
                """Implement abstract method."""
                yield "test"

            async def generate_stream_with_tools(self, messages, tools=None):
                """Implement abstract method."""
                yield StreamChunk(content="test")

            async def validate_api_key(self):
                """Implement abstract method."""
                return True

        provider = TestProvider()
        result = await provider.validate_api_key()

        assert result is True
