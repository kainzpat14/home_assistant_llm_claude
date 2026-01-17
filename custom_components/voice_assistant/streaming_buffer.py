"""Streaming buffer processor for handling CONTINUE_LISTENING markers.

This module handles the complex logic of processing streaming LLM responses
while detecting and removing CONTINUE_LISTENING markers without breaking
the stream or yielding partial markers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import AsyncIterator

_LOGGER = logging.getLogger(__name__)


@dataclass
class StreamResult:
    """Result of stream processing."""

    accumulated_content: str
    marker_found: bool
    tool_calls: list | None = None


class StreamingBufferProcessor:
    """Processes streaming chunks with marker detection and removal.

    This class handles the buffering logic needed to detect and remove
    CONTINUE_LISTENING markers from streaming responses without yielding
    partial markers to the user.
    """

    def __init__(self, marker: str) -> None:
        """Initialize the streaming buffer processor.

        Args:
            marker: The marker string to detect and remove (e.g., "[CONTINUE_LISTENING]").
        """
        self.marker = marker
        self._accumulated_content = ""
        self._chunk_buffer = ""
        self._marker_found = False
        self._tool_calls = None

    def _might_contain_partial_marker(self, buffer: str) -> bool:
        """Check if buffer ends with a partial match of the marker.

        This checks if the end of the buffer could be the beginning of the marker,
        which means we should hold the buffer until we get more chunks.

        Args:
            buffer: The current chunk buffer.

        Returns:
            True if buffer might contain a partial marker, False otherwise.
        """
        # Check if buffer ends with any prefix of the marker
        # For marker "[CONTINUE_LISTENING]", check for: "[", "[C", "[CO", "[CON", etc.
        for i in range(1, len(self.marker)):
            prefix = self.marker[:i]
            if buffer.endswith(prefix):
                _LOGGER.debug("Buffer ends with partial marker prefix: %r", prefix)
                return True

        return False

    async def process_chunks(
        self, chunk_iterator: AsyncIterator
    ) -> AsyncIterator[dict[str, str]]:
        """Process streaming chunks and yield clean content.

        This method processes chunks from the LLM, detects the CONTINUE_LISTENING
        marker, removes it, and yields clean content deltas without breaking
        the streaming experience.

        Args:
            chunk_iterator: Async iterator of StreamChunk objects.

        Yields:
            Dictionaries with "content" key containing text to display to user.
        """
        _LOGGER.debug("Starting chunk processing")

        async for chunk in chunk_iterator:
            # Process content chunks
            if chunk.content:
                self._accumulated_content += chunk.content
                self._chunk_buffer += chunk.content

                # Check if we've completed the marker in the buffer
                if self.marker in self._chunk_buffer:
                    self._marker_found = True
                    _LOGGER.info("*** FOUND COMPLETE %s MARKER in buffer! ***", self.marker)

                    # Remove marker from buffer and yield everything
                    clean_buffer = self._chunk_buffer.replace(self.marker, "")
                    if clean_buffer:
                        yield {"content": clean_buffer}

                    # Clear buffer since we've yielded it
                    self._chunk_buffer = ""

                elif self._might_contain_partial_marker(self._chunk_buffer):
                    # Buffer might contain start of marker, hold off on yielding
                    display_buffer = (
                        self._chunk_buffer[-20:]
                        if len(self._chunk_buffer) > 20
                        else self._chunk_buffer
                    )
                    _LOGGER.debug("Buffer might contain partial marker, holding: %r", display_buffer)

                else:
                    # Buffer doesn't contain marker or partial marker, safe to yield
                    if self._chunk_buffer:
                        yield {"content": self._chunk_buffer}
                    self._chunk_buffer = ""

            # Capture tool calls from final chunk
            if chunk.is_final and chunk.tool_calls:
                self._tool_calls = chunk.tool_calls
                _LOGGER.debug("Final chunk received with %d tool calls", len(self._tool_calls))

        # Yield any remaining buffer content (marker wasn't completed)
        if self._chunk_buffer and not self._marker_found:
            yield {"content": self._chunk_buffer}

        _LOGGER.debug("Finished streaming, accumulated content length: %d", len(self._accumulated_content))
        display_content = (
            self._accumulated_content[:200] + "..."
            if len(self._accumulated_content) > 200
            else self._accumulated_content
        )
        _LOGGER.debug("Full accumulated content: %r", display_content)
        _LOGGER.debug("Marker found: %s", self._marker_found)

    def get_result(self) -> StreamResult:
        """Get the final result after processing all chunks.

        Returns:
            StreamResult with accumulated content, marker status, and tool calls.
        """
        return StreamResult(
            accumulated_content=self._accumulated_content,
            marker_found=self._marker_found,
            tool_calls=self._tool_calls,
        )

    async def finalize_response(self) -> AsyncIterator[dict[str, str]]:
        """Finalize the response by adding question mark if marker was found.

        If the CONTINUE_LISTENING marker was found but the response doesn't
        end with a question mark, this adds one to trigger voice assistant
        continued listening.

        Yields:
            Dictionary with "content" containing "?" if needed.
        """
        if self._marker_found:
            # Remove marker from accumulated content for checking
            clean_content = self._accumulated_content.replace(self.marker, "").strip()
            if not clean_content.endswith("?"):
                yield {"content": "?"}
                _LOGGER.debug("Added question mark after streaming (CONTINUE_LISTENING marker present)")
