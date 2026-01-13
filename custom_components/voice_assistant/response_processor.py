"""Response post-processing for voice assistant control."""

from __future__ import annotations

import logging
import re

from .const import CONTINUE_LISTENING_MARKER

_LOGGER = logging.getLogger(__name__)

# Unicode characters that look like ? but don't trigger listening
# Option 1: Fullwidth Question Mark
FAKE_QUESTION_MARK = "\uFF1F"  # ？ (fullwidth)

# Option 2: Zero-width space after question mark (alternative)
ZERO_WIDTH_SPACE = "\u200B"


def process_response_for_listening(
    response: str,
    auto_continue_listening: bool,
) -> tuple[str, bool]:
    """Process response to control voice assistant listening behavior.

    Args:
        response: The LLM response text.
        auto_continue_listening: If True, allow normal ? behavior.

    Returns:
        Tuple of (processed_response, should_continue_listening).
    """
    # Check if LLM explicitly requested continued listening
    wants_listening = CONTINUE_LISTENING_MARKER in response

    # Remove the marker from response (user shouldn't see it)
    processed = response.replace(CONTINUE_LISTENING_MARKER, "").strip()

    # Determine if we should continue listening
    ends_with_question = processed.rstrip().endswith("?")

    if wants_listening:
        # LLM explicitly wants listening
        _LOGGER.debug("LLM requested continued listening via marker")

        # If response doesn't end with ?, add one
        if not ends_with_question:
            processed = processed.rstrip() + "?"
            _LOGGER.debug("Added question mark to response with CONTINUE_LISTENING marker")

        return processed, True

    if auto_continue_listening:
        # Auto mode - use default HA behavior
        _LOGGER.debug("Auto-continue listening enabled, preserving default behavior")
        return processed, ends_with_question

    # Default: prevent continued listening
    if ends_with_question:
        # Replace ? with fullwidth version to prevent auto-listening
        processed = re.sub(r'\?(\s*)$', f'{FAKE_QUESTION_MARK}\\1', processed)
        _LOGGER.debug("Modified response to prevent continued listening (replaced ? with fullwidth)")

    return processed, False


def add_listening_instructions_to_prompt(system_prompt: str) -> str:
    """Add instructions for listening control to system prompt.

    Args:
        system_prompt: The current system prompt.

    Returns:
        Updated system prompt with listening instructions.
    """
    listening_instructions = f"""

**Voice Assistant Listening Control:**
By default, I will NOT keep listening after your response, even if you ask a question.
If you want me to continue listening for the user's response (for clarifying questions or follow-ups),
include the marker {CONTINUE_LISTENING_MARKER} anywhere in your response. The marker will be removed
before the response is spoken, and if your response doesn't end with a question mark, one will be added automatically.

Example:
- "What temperature would you like?" -> Stops listening
- "What temperature would you like {CONTINUE_LISTENING_MARKER}" -> Continues listening (? preserved)
- "I need more information {CONTINUE_LISTENING_MARKER}" -> "I need more information?" (? added, continues listening)

Only use the marker when you genuinely need user input to proceed."""

    return system_prompt + listening_instructions
