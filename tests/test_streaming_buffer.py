"""Tests for streaming_buffer module."""

import pytest

from custom_components.voice_assistant.streaming_buffer import (
    StreamingBufferProcessor,
    StreamResult,
)


# Mock StreamChunk class for testing
class MockStreamChunk:
    """Mock StreamChunk for testing."""

    def __init__(self, content=None, is_final=False, tool_calls=None):
        """Initialize mock chunk."""
        self.content = content
        self.is_final = is_final
        self.tool_calls = tool_calls


async def collect_deltas(processor, chunks):
    """Helper to collect all yielded deltas."""
    async def chunk_generator():
        for chunk in chunks:
            yield chunk

    deltas = []
    async for delta in processor.process_chunks(chunk_generator()):
        deltas.append(delta)
    return deltas


@pytest.mark.asyncio
class TestStreamingBufferProcessor:
    """Tests for StreamingBufferProcessor."""

    async def test_basic_chunk_processing(self):
        """Test basic chunk processing without markers."""
        processor = StreamingBufferProcessor("[TEST_MARKER]")
        chunks = [
            MockStreamChunk(content="Hello "),
            MockStreamChunk(content="world"),
            MockStreamChunk(content="!", is_final=True),
        ]

        deltas = await collect_deltas(processor, chunks)

        # Should yield all content
        assert len(deltas) == 3
        assert deltas[0] == {"content": "Hello "}
        assert deltas[1] == {"content": "world"}
        assert deltas[2] == {"content": "!"}

        # Check result
        result = processor.get_result()
        assert result.accumulated_content == "Hello world!"
        assert result.marker_found is False
        assert result.tool_calls is None

    async def test_marker_detection_and_removal(self):
        """Test that marker is detected and removed from output."""
        processor = StreamingBufferProcessor("[CONTINUE_LISTENING]")
        chunks = [
            MockStreamChunk(content="Do you want to continue"),
            MockStreamChunk(content="? [CONTINUE_LISTENING]"),
            MockStreamChunk(content="", is_final=True),
        ]

        deltas = await collect_deltas(processor, chunks)

        # Should yield content without marker
        assert len(deltas) == 2
        assert deltas[0] == {"content": "Do you want to continue"}
        assert deltas[1] == {"content": "? "}  # Marker removed

        # Check result
        result = processor.get_result()
        assert result.accumulated_content == "Do you want to continue? [CONTINUE_LISTENING]"
        assert result.marker_found is True

    async def test_partial_marker_buffering(self):
        """Test that partial markers are buffered correctly."""
        processor = StreamingBufferProcessor("[CONTINUE_LISTENING]")
        chunks = [
            MockStreamChunk(content="Hello"),
            MockStreamChunk(content=" [CON"),  # Partial marker
            MockStreamChunk(content="TINUE_LISTENING]"),  # Completes marker
            MockStreamChunk(content="", is_final=True),
        ]

        deltas = await collect_deltas(processor, chunks)

        # First chunk yields immediately
        # Second chunk is buffered (partial marker)
        # Third chunk completes marker and yields clean content
        assert len(deltas) == 2
        assert deltas[0] == {"content": "Hello"}
        assert deltas[1] == {"content": " "}  # Marker removed

        # Check result
        result = processor.get_result()
        assert result.accumulated_content == "Hello [CONTINUE_LISTENING]"
        assert result.marker_found is True

    async def test_false_start_marker(self):
        """Test handling of text that starts like a marker but isn't."""
        processor = StreamingBufferProcessor("[CONTINUE_LISTENING]")
        chunks = [
            MockStreamChunk(content="Hello [C"),  # Looks like marker start
            MockStreamChunk(content="OOL]"),  # But it's not
            MockStreamChunk(content="", is_final=True),
        ]

        deltas = await collect_deltas(processor, chunks)

        # First chunk buffered, second completes non-marker and yields
        assert len(deltas) == 1
        assert deltas[0] == {"content": "Hello [COOL]"}

        # Check result
        result = processor.get_result()
        assert result.accumulated_content == "Hello [COOL]"
        assert result.marker_found is False

    async def test_tool_calls_captured(self):
        """Test that tool calls are captured from final chunk."""
        processor = StreamingBufferProcessor("[TEST_MARKER]")
        mock_tool_calls = [{"id": "1", "function": {"name": "test"}}]
        chunks = [
            MockStreamChunk(content="Hello"),
            MockStreamChunk(content=" world", is_final=True, tool_calls=mock_tool_calls),
        ]

        deltas = await collect_deltas(processor, chunks)

        # Check tool calls captured
        result = processor.get_result()
        assert result.tool_calls == mock_tool_calls

    async def test_finalize_adds_question_mark(self):
        """Test that finalize adds ? when marker found and no ? at end."""
        processor = StreamingBufferProcessor("[CONTINUE_LISTENING]")
        chunks = [
            MockStreamChunk(content="Do you want to play[CONTINUE_LISTENING]"),
            MockStreamChunk(content="", is_final=True),
        ]

        # Process chunks
        await collect_deltas(processor, chunks)

        # Finalize should add question mark
        finalize_deltas = []
        async for delta in processor.finalize_response():
            finalize_deltas.append(delta)

        assert len(finalize_deltas) == 1
        assert finalize_deltas[0] == {"content": "?"}

    async def test_finalize_no_question_mark_when_present(self):
        """Test that finalize doesn't add ? when already present."""
        processor = StreamingBufferProcessor("[CONTINUE_LISTENING]")
        chunks = [
            MockStreamChunk(content="Do you want to play?[CONTINUE_LISTENING]"),
            MockStreamChunk(content="", is_final=True),
        ]

        # Process chunks
        await collect_deltas(processor, chunks)

        # Finalize should NOT add question mark
        finalize_deltas = []
        async for delta in processor.finalize_response():
            finalize_deltas.append(delta)

        assert len(finalize_deltas) == 0

    async def test_finalize_no_question_mark_without_marker(self):
        """Test that finalize doesn't add ? when marker not found."""
        processor = StreamingBufferProcessor("[CONTINUE_LISTENING]")
        chunks = [
            MockStreamChunk(content="This is a statement"),
            MockStreamChunk(content="", is_final=True),
        ]

        # Process chunks
        await collect_deltas(processor, chunks)

        # Finalize should NOT add question mark (no marker)
        finalize_deltas = []
        async for delta in processor.finalize_response():
            finalize_deltas.append(delta)

        assert len(finalize_deltas) == 0

    async def test_empty_chunks_ignored(self):
        """Test that empty chunks are handled gracefully."""
        processor = StreamingBufferProcessor("[TEST_MARKER]")
        chunks = [
            MockStreamChunk(content=""),
            MockStreamChunk(content="Hello"),
            MockStreamChunk(content=""),
            MockStreamChunk(content="", is_final=True),
        ]

        deltas = await collect_deltas(processor, chunks)

        # Only non-empty content yields
        assert len(deltas) == 1
        assert deltas[0] == {"content": "Hello"}

        result = processor.get_result()
        assert result.accumulated_content == "Hello"

    async def test_marker_at_chunk_boundary(self):
        """Test marker split across multiple chunks."""
        processor = StreamingBufferProcessor("[MARKER]")
        chunks = [
            MockStreamChunk(content="Text ["),
            MockStreamChunk(content="MAR"),
            MockStreamChunk(content="KER]"),
            MockStreamChunk(content="", is_final=True),
        ]

        deltas = await collect_deltas(processor, chunks)

        # Should yield text without marker
        assert len(deltas) == 1
        assert deltas[0] == {"content": "Text "}

        result = processor.get_result()
        assert result.accumulated_content == "Text [MARKER]"
        assert result.marker_found is True

    async def test_multiple_markers_in_stream(self):
        """Test handling of multiple markers (all markers removed)."""
        processor = StreamingBufferProcessor("[MARKER]")
        chunks = [
            MockStreamChunk(content="First [MARKER]"),
            MockStreamChunk(content=" Second [MARKER]"),
            MockStreamChunk(content="", is_final=True),
        ]

        deltas = await collect_deltas(processor, chunks)

        # All markers are removed from output
        assert len(deltas) == 2
        assert deltas[0] == {"content": "First "}
        assert deltas[1] == {"content": " Second "}

        result = processor.get_result()
        assert result.marker_found is True

    async def test_result_immutability(self):
        """Test that StreamResult is immutable via dataclass."""
        result = StreamResult(
            accumulated_content="test",
            marker_found=True,
            tool_calls=None
        )

        assert result.accumulated_content == "test"
        assert result.marker_found is True
        assert result.tool_calls is None

    async def test_marker_in_middle_of_content(self):
        """Test marker appearing in the middle of content."""
        processor = StreamingBufferProcessor("[MARKER]")
        chunks = [
            MockStreamChunk(content="Before "),
            MockStreamChunk(content="[MARKER]"),
            MockStreamChunk(content=" After"),
            MockStreamChunk(content="", is_final=True),
        ]

        deltas = await collect_deltas(processor, chunks)

        # Should yield before and after without marker (no empty content yielded)
        assert len(deltas) == 2
        assert deltas[0] == {"content": "Before "}
        assert deltas[1] == {"content": " After"}

        result = processor.get_result()
        assert result.accumulated_content == "Before [MARKER] After"
        assert result.marker_found is True
