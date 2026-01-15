"""Tests for storage module."""

from unittest.mock import AsyncMock, patch

import pytest

from custom_components.voice_assistant.storage import FactStore


class TestFactStore:
    """Test the FactStore class."""

    @pytest.fixture
    def fact_store(self, mock_hass):
        """Create a FactStore instance."""
        with patch("custom_components.voice_assistant.storage.Store") as mock_store_class:
            store_instance = AsyncMock()
            store_instance.async_load = AsyncMock(return_value=None)
            store_instance.async_save = AsyncMock()
            mock_store_class.return_value = store_instance

            fact_store = FactStore(mock_hass)
            fact_store._store = store_instance
            return fact_store

    async def test_init(self, mock_hass):
        """Test FactStore initialization."""
        with patch("custom_components.voice_assistant.storage.Store") as mock_store_class:
            fact_store = FactStore(mock_hass)

            assert fact_store.hass == mock_hass
            assert fact_store._facts == {}
            mock_store_class.assert_called_once()

    async def test_async_load_empty(self, fact_store):
        """Test loading when storage is empty."""
        fact_store._store.async_load = AsyncMock(return_value=None)

        await fact_store.async_load()

        assert fact_store._facts == {}
        fact_store._store.async_load.assert_called_once()

    async def test_async_load_with_data(self, fact_store):
        """Test loading existing facts from storage."""
        test_facts = {
            "user_name": "John",
            "favorite_color": "blue",
        }
        fact_store._store.async_load = AsyncMock(return_value=test_facts)

        await fact_store.async_load()

        assert fact_store._facts == test_facts
        fact_store._store.async_load.assert_called_once()

    async def test_async_save(self, fact_store):
        """Test saving facts to storage."""
        fact_store._facts = {"user_name": "John"}

        await fact_store.async_save()

        fact_store._store.async_save.assert_called_once_with({"user_name": "John"})

    def test_add_fact(self, fact_store):
        """Test adding a fact."""
        fact_store.add_fact("user_name", "Alice")

        assert fact_store._facts["user_name"] == "Alice"

    def test_add_fact_overwrites_existing(self, fact_store):
        """Test that adding a fact with existing key overwrites it."""
        fact_store.add_fact("user_name", "Alice")
        fact_store.add_fact("user_name", "Bob")

        assert fact_store._facts["user_name"] == "Bob"

    def test_get_fact_existing(self, fact_store):
        """Test getting an existing fact."""
        fact_store._facts = {"user_name": "Alice"}

        result = fact_store.get_fact("user_name")

        assert result == "Alice"

    def test_get_fact_nonexistent(self, fact_store):
        """Test getting a non-existent fact returns None."""
        result = fact_store.get_fact("nonexistent")

        assert result is None

    def test_get_all_facts(self, fact_store):
        """Test getting all facts."""
        test_facts = {
            "user_name": "Alice",
            "favorite_color": "blue",
            "pet_name": "Fluffy",
        }
        fact_store._facts = test_facts

        result = fact_store.get_all_facts()

        assert result == test_facts
        # Ensure it returns a copy, not the original
        assert result is not fact_store._facts

    def test_get_all_facts_empty(self, fact_store):
        """Test getting all facts when empty."""
        result = fact_store.get_all_facts()

        assert result == {}

    def test_remove_fact_existing(self, fact_store):
        """Test removing an existing fact."""
        fact_store._facts = {
            "user_name": "Alice",
            "favorite_color": "blue",
        }

        fact_store.remove_fact("user_name")

        assert "user_name" not in fact_store._facts
        assert "favorite_color" in fact_store._facts

    def test_remove_fact_nonexistent(self, fact_store):
        """Test removing a non-existent fact does not raise error."""
        fact_store._facts = {"user_name": "Alice"}

        # Should not raise an error
        fact_store.remove_fact("nonexistent")

        assert fact_store._facts == {"user_name": "Alice"}

    def test_clear(self, fact_store):
        """Test clearing all facts."""
        fact_store._facts = {
            "user_name": "Alice",
            "favorite_color": "blue",
            "pet_name": "Fluffy",
        }

        fact_store.clear()

        assert fact_store._facts == {}

    def test_clear_empty(self, fact_store):
        """Test clearing when already empty."""
        fact_store.clear()

        assert fact_store._facts == {}

    async def test_full_workflow(self, fact_store):
        """Test a complete workflow: load, add, save."""
        # Start with existing data
        fact_store._store.async_load = AsyncMock(return_value={"user_name": "Alice"})
        await fact_store.async_load()

        # Add new facts
        fact_store.add_fact("favorite_color", "blue")
        fact_store.add_fact("pet_name", "Fluffy")

        # Save
        await fact_store.async_save()

        expected_facts = {
            "user_name": "Alice",
            "favorite_color": "blue",
            "pet_name": "Fluffy",
        }
        fact_store._store.async_save.assert_called_once_with(expected_facts)

    def test_add_fact_with_complex_value(self, fact_store):
        """Test adding facts with complex data types."""
        fact_store.add_fact("family_members", ["Alice", "Bob", "Charlie"])
        fact_store.add_fact("preferences", {"temp": 72, "unit": "F"})

        assert fact_store.get_fact("family_members") == ["Alice", "Bob", "Charlie"]
        assert fact_store.get_fact("preferences") == {"temp": 72, "unit": "F"}
