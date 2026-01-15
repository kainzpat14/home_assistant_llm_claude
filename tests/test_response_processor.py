"""Tests for response_processor module."""

import pytest

from custom_components.voice_assistant.response_processor import (
    CONTINUE_LISTENING_MARKER,
    FAKE_QUESTION_MARK,
    add_listening_instructions_to_prompt,
    process_response_for_listening,
)


class TestProcessResponseForListening:
    """Test the process_response_for_listening function."""

    def test_with_marker_no_question_mark(self):
        """Test response with marker but no question mark - should add question mark."""
        response = f"Here's a riddle {CONTINUE_LISTENING_MARKER}"
        processed, should_listen = process_response_for_listening(response, False)

        assert should_listen is True
        assert CONTINUE_LISTENING_MARKER not in processed
        assert processed.endswith("?")
        assert processed == "Here's a riddle?"

    def test_with_marker_and_question_mark(self):
        """Test response with marker and question mark - should keep question mark."""
        response = f"Would you like me to turn on the lights? {CONTINUE_LISTENING_MARKER}"
        processed, should_listen = process_response_for_listening(response, False)

        assert should_listen is True
        assert CONTINUE_LISTENING_MARKER not in processed
        assert processed.endswith("?")
        assert processed == "Would you like me to turn on the lights?"

    def test_without_marker_auto_continue_enabled_with_question(self):
        """Test without marker, auto-continue enabled, with question mark."""
        response = "Do you want to continue?"
        processed, should_listen = process_response_for_listening(response, True)

        assert should_listen is True
        assert processed == "Do you want to continue?"

    def test_without_marker_auto_continue_enabled_no_question(self):
        """Test without marker, auto-continue enabled, without question mark."""
        response = "The lights are on."
        processed, should_listen = process_response_for_listening(response, True)

        assert should_listen is False
        assert processed == "The lights are on."

    def test_without_marker_auto_continue_disabled_with_question(self):
        """Test without marker, auto-continue disabled, with question mark - should replace with fake."""
        response = "Is this a question?"
        processed, should_listen = process_response_for_listening(response, False)

        assert should_listen is False
        assert not processed.endswith("?")
        assert processed.endswith(FAKE_QUESTION_MARK)
        assert processed == f"Is this a question{FAKE_QUESTION_MARK}"

    def test_without_marker_auto_continue_disabled_no_question(self):
        """Test without marker, auto-continue disabled, no question mark."""
        response = "The lights are on."
        processed, should_listen = process_response_for_listening(response, False)

        assert should_listen is False
        assert processed == "The lights are on."

    def test_marker_removal_from_middle(self):
        """Test marker is removed even when in the middle of response."""
        response = f"Here {CONTINUE_LISTENING_MARKER} is a riddle"
        processed, should_listen = process_response_for_listening(response, False)

        assert should_listen is True
        assert CONTINUE_LISTENING_MARKER not in processed
        # Note: replace() leaves space where marker was
        assert processed == "Here  is a riddle?"

    def test_question_mark_with_trailing_whitespace(self):
        """Test question mark handling with trailing whitespace."""
        response = "Is this a test?   "
        processed, should_listen = process_response_for_listening(response, False)

        assert should_listen is False
        assert FAKE_QUESTION_MARK in processed
        # rstrip() is called, so trailing whitespace is removed
        assert processed == f"Is this a test{FAKE_QUESTION_MARK}"

    def test_multiple_question_marks(self):
        """Test with multiple question marks - only last one should be replaced."""
        response = "What? Really?"
        processed, should_listen = process_response_for_listening(response, False)

        assert should_listen is False
        # Only the trailing ? should be replaced
        assert processed.startswith("What?")
        assert processed.endswith(FAKE_QUESTION_MARK)

    def test_empty_response_with_marker(self):
        """Test empty response with just marker."""
        response = CONTINUE_LISTENING_MARKER
        processed, should_listen = process_response_for_listening(response, False)

        assert should_listen is True
        assert processed == "?"

    def test_marker_with_auto_continue_enabled(self):
        """Test that marker takes precedence over auto_continue setting."""
        response = f"Test {CONTINUE_LISTENING_MARKER}"
        processed, should_listen = process_response_for_listening(response, True)

        assert should_listen is True
        assert processed == "Test?"


class TestAddListeningInstructionsToPrompt:
    """Test the add_listening_instructions_to_prompt function."""

    def test_adds_instructions_to_prompt(self):
        """Test that instructions are added to the system prompt."""
        original_prompt = "You are a helpful assistant."
        updated_prompt = add_listening_instructions_to_prompt(original_prompt)

        assert updated_prompt.startswith(original_prompt)
        assert CONTINUE_LISTENING_MARKER in updated_prompt
        assert "Voice Assistant Listening Control" in updated_prompt

    def test_instructions_contain_examples(self):
        """Test that the instructions contain usage examples."""
        updated_prompt = add_listening_instructions_to_prompt("")

        assert "Examples:" in updated_prompt
        assert "riddle" in updated_prompt.lower()
        assert "lights" in updated_prompt.lower()

    def test_instructions_explain_marker_removal(self):
        """Test that instructions explain marker will be removed."""
        updated_prompt = add_listening_instructions_to_prompt("")

        assert "marker will be removed" in updated_prompt

    def test_instructions_explain_question_mark_addition(self):
        """Test that instructions explain question mark addition."""
        updated_prompt = add_listening_instructions_to_prompt("")

        # The instructions mention "?" but not as "question mark" (uses the symbol directly)
        assert '?"' in updated_prompt or "will be added" in updated_prompt

    def test_empty_original_prompt(self):
        """Test with empty original prompt."""
        updated_prompt = add_listening_instructions_to_prompt("")

        assert len(updated_prompt) > 0
        assert CONTINUE_LISTENING_MARKER in updated_prompt
