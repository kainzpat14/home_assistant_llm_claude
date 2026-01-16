"""Tests for conversation_manager module."""

import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.voice_assistant.conversation_manager import (
    ConversationManager,
    ConversationSession,
)


class TestConversationSession:
    """Test the ConversationSession dataclass."""

    def test_init_defaults(self):
        """Test ConversationSession initialization with defaults."""
        session = ConversationSession()

        assert session.messages == []
        assert isinstance(session.last_activity, datetime)

    def test_add_message(self):
        """Test adding a message to the session."""
        session = ConversationSession()
        initial_time = session.last_activity

        # Wait a tiny bit to ensure time changes
        session.add_message("user", "Hello")

        assert len(session.messages) == 1
        assert session.messages[0] == {"role": "user", "content": "Hello"}
        assert session.last_activity >= initial_time

    def test_add_multiple_messages(self):
        """Test adding multiple messages."""
        session = ConversationSession()

        session.add_message("user", "Hello")
        session.add_message("assistant", "Hi there")
        session.add_message("user", "How are you?")

        assert len(session.messages) == 3
        assert session.messages[0]["role"] == "user"
        assert session.messages[1]["role"] == "assistant"
        assert session.messages[2]["role"] == "user"

    def test_is_expired_not_expired(self):
        """Test session is not expired within timeout."""
        session = ConversationSession()

        assert not session.is_expired(60)

    def test_is_expired_with_old_activity(self):
        """Test session is expired after timeout."""
        session = ConversationSession()
        # Set last activity to 2 minutes ago
        session.last_activity = datetime.now() - timedelta(seconds=120)

        assert session.is_expired(60)

    def test_is_expired_at_boundary(self):
        """Test session expiration at exact timeout boundary."""
        session = ConversationSession()
        # Set last activity to exactly timeout seconds ago
        session.last_activity = datetime.now() - timedelta(seconds=60)

        # Should be expired (> timeout)
        assert session.is_expired(60)

    def test_get_conversation_text_empty(self):
        """Test getting conversation text from empty session."""
        session = ConversationSession()

        text = session.get_conversation_text()

        assert text == ""

    def test_get_conversation_text_single_message(self):
        """Test getting conversation text with single message."""
        session = ConversationSession()
        session.add_message("user", "Hello")

        text = session.get_conversation_text()

        assert text == "User: Hello"

    def test_get_conversation_text_multiple_messages(self):
        """Test getting conversation text with multiple messages."""
        session = ConversationSession()
        session.add_message("user", "Hello")
        session.add_message("assistant", "Hi there!")
        session.add_message("user", "How are you?")

        text = session.get_conversation_text()

        expected = "User: Hello\nAssistant: Hi there!\nUser: How are you?"
        assert text == expected

    def test_clear(self):
        """Test clearing the session."""
        session = ConversationSession()
        session.add_message("user", "Hello")
        session.add_message("assistant", "Hi")
        old_time = session.last_activity

        session.clear()

        assert session.messages == []
        assert session.last_activity >= old_time


class TestConversationManager:
    """Test the ConversationManager class."""

    @pytest.fixture
    def fact_store(self, mock_hass):
        """Create a mock FactStore."""
        with patch("custom_components.voice_assistant.storage.Store"):
            from custom_components.voice_assistant.storage import FactStore

            store = FactStore(mock_hass)
            store.async_save = AsyncMock()
            return store

    @pytest.fixture
    def manager(self, mock_hass, fact_store):
        """Create a ConversationManager instance."""
        return ConversationManager(mock_hass, fact_store, timeout_seconds=60)

    def test_init(self, mock_hass, fact_store):
        """Test ConversationManager initialization."""
        manager = ConversationManager(mock_hass, fact_store, timeout_seconds=120)

        assert manager.hass == mock_hass
        assert manager.fact_store == fact_store
        assert manager.timeout_seconds == 120
        assert isinstance(manager._session, ConversationSession)
        assert manager._llm_provider is None

    def test_set_llm_provider(self, manager, mock_llm_provider):
        """Test setting the LLM provider."""
        manager.set_llm_provider(mock_llm_provider)

        assert manager._llm_provider == mock_llm_provider

    def test_get_session_not_expired(self, manager):
        """Test getting session when not expired."""
        manager._session.add_message("user", "Hello")

        session = manager.get_session()

        assert len(session.messages) == 1
        assert session.messages[0]["content"] == "Hello"

    async def test_get_session_expired_clears_session(self, manager):
        """Test that expired session gets cleared."""
        manager._session.add_message("user", "Hello")
        # Set last activity to past timeout
        manager._session.last_activity = datetime.now() - timedelta(seconds=120)

        # Need to run in async context since get_session creates a task
        session = manager.get_session()

        # Wait a bit for the async task to potentially start
        await asyncio.sleep(0.1)

        # Session should be cleared
        assert len(session.messages) == 0

    async def test_handle_session_timeout_no_messages(self, manager):
        """Test handling timeout with no messages."""
        manager._session.messages = []

        await manager._handle_session_timeout()

        # Should return early without doing anything

    async def test_extract_and_save_facts_no_provider(self, manager):
        """Test fact extraction without LLM provider."""
        manager._session.add_message("user", "My name is Alice")

        await manager._extract_and_save_facts(manager._session)

        # Should log warning but not crash

    async def test_extract_and_save_facts_with_provider(self, manager, mock_llm_provider, fact_store):
        """Test fact extraction with LLM provider."""
        manager.set_llm_provider(mock_llm_provider)
        manager._session.add_message("user", "My name is Alice")
        manager._session.add_message("assistant", "Nice to meet you, Alice!")

        # Mock LLM response with facts
        mock_llm_provider.generate.return_value = {
            "content": '{"user_name": "Alice"}'
        }

        await manager._extract_and_save_facts(manager._session)

        # Check that generate was called
        mock_llm_provider.generate.assert_called_once()
        # Check that fact was saved
        assert fact_store.get_fact("user_name") == "Alice"
        fact_store.async_save.assert_called_once()

    async def test_extract_and_save_facts_with_markdown_json(self, manager, mock_llm_provider, fact_store):
        """Test fact extraction with JSON in markdown code blocks."""
        manager.set_llm_provider(mock_llm_provider)
        manager._session.add_message("user", "My cat's name is Fluffy")

        # Mock LLM response with markdown-wrapped JSON
        mock_llm_provider.generate.return_value = {
            "content": '```json\n{"pet_name": "Fluffy"}\n```'
        }

        await manager._extract_and_save_facts(manager._session)

        assert fact_store.get_fact("pet_name") == "Fluffy"

    async def test_extract_and_save_facts_empty_json(self, manager, mock_llm_provider):
        """Test fact extraction with empty JSON response."""
        manager.set_llm_provider(mock_llm_provider)
        manager._session.add_message("user", "Hello")

        mock_llm_provider.generate.return_value = {"content": "{}"}

        await manager._extract_and_save_facts(manager._session)

        # Should not crash with empty facts

    async def test_extract_and_save_facts_invalid_json(self, manager, mock_llm_provider):
        """Test fact extraction with invalid JSON."""
        manager.set_llm_provider(mock_llm_provider)
        manager._session.add_message("user", "Hello")

        mock_llm_provider.generate.return_value = {"content": "not valid json"}

        await manager._extract_and_save_facts(manager._session)

        # Should log warning but not crash

    async def test_extract_and_save_facts_skips_empty_values(self, manager, mock_llm_provider, fact_store):
        """Test that empty fact values are not saved."""
        manager.set_llm_provider(mock_llm_provider)
        manager._session.add_message("user", "Hello")

        mock_llm_provider.generate.return_value = {
            "content": '{"user_name": "Alice", "empty_field": "", "none_field": null}'
        }

        await manager._extract_and_save_facts(manager._session)

        # Only non-empty facts should be saved
        assert fact_store.get_fact("user_name") == "Alice"
        assert fact_store.get_fact("empty_field") is None
        assert fact_store.get_fact("none_field") is None

    async def test_start_cleanup_task(self, manager):
        """Test starting the cleanup task."""
        await manager.start_cleanup_task()

        assert manager._cleanup_task is not None
        assert not manager._cleanup_task.done()

        # Clean up
        await manager.stop_cleanup_task()

    async def test_stop_cleanup_task(self, manager):
        """Test stopping the cleanup task."""
        await manager.start_cleanup_task()

        await manager.stop_cleanup_task()

        assert manager._cleanup_task.cancelled() or manager._cleanup_task.done()

    async def test_stop_cleanup_task_when_not_started(self, manager):
        """Test stopping cleanup task when it was never started."""
        await manager.stop_cleanup_task()

        # Should not raise an error

    async def test_cleanup_loop_checks_expiration(self, manager, mock_llm_provider):
        """Test that cleanup loop checks for session expiration."""
        manager.set_llm_provider(mock_llm_provider)
        manager.timeout_seconds = 1  # Very short timeout for testing
        manager._session.add_message("user", "Hello")
        manager._session.last_activity = datetime.now() - timedelta(seconds=2)

        mock_llm_provider.generate.return_value = {"content": "{}"}

        # Start cleanup task
        task = asyncio.create_task(manager._cleanup_loop())

        # Wait for one cleanup cycle
        await asyncio.sleep(1.5)

        # Cancel the task
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Session should have been cleared
        assert len(manager._session.messages) == 0
