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
    # Validate input
    if response is None:
        _LOGGER.warning("process_response_for_listening received None response")
        return "", False

    if not isinstance(response, str):
        _LOGGER.warning(
            "process_response_for_listening received non-string response: %s",
            type(response).__name__,
        )
        return str(response), False

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
    # Validate input
    if system_prompt is None:
        _LOGGER.warning("add_listening_instructions_to_prompt received None prompt")
        system_prompt = ""

    if not isinstance(system_prompt, str):
        _LOGGER.warning(
            "add_listening_instructions_to_prompt received non-string prompt: %s",
            type(system_prompt).__name__,
        )
        system_prompt = str(system_prompt)

    listening_instructions = f"""

**CRITICAL: Voice Assistant Listening Control**

This is a VOICE assistant. By default, I will STOP listening after your response, even if you ask a question.

**When to use {CONTINUE_LISTENING_MARKER}:**
You MUST include this marker when:
- Playing games (riddles, 20 questions, trivia, etc.)
- Asking questions that require user input to proceed
- Having multi-turn interactions or conversations
- Requesting clarifications or confirmations
- Any scenario where you're waiting for the user's response

**How it works:**
- Add {CONTINUE_LISTENING_MARKER} anywhere in your response
- The marker will be removed before speaking
- If your response doesn't end with "?", one will be added automatically

**Examples:**
✓ "Here's a riddle: What gets wetter as it dries? {CONTINUE_LISTENING_MARKER}"
✓ "Would you like me to turn on the lights? {CONTINUE_LISTENING_MARKER}"
✓ "What temperature would you like? {CONTINUE_LISTENING_MARKER}"
✗ "Here's a riddle: What gets wetter as it dries?" (I will NOT hear the answer!)

**Remember:** Without the marker, the user cannot respond to your questions!"""

    return system_prompt + listening_instructions
