"""Shared pytest fixtures for voice assistant tests."""

from __future__ import annotations

import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

# Mock Home Assistant modules before any imports
sys.modules["homeassistant"] = MagicMock()
sys.modules["homeassistant.core"] = MagicMock()
sys.modules["homeassistant.const"] = MagicMock()
sys.modules["homeassistant.helpers"] = MagicMock()
sys.modules["homeassistant.helpers.storage"] = MagicMock()
sys.modules["homeassistant.helpers.llm"] = MagicMock()
sys.modules["homeassistant.components"] = MagicMock()
sys.modules["homeassistant.components.conversation"] = MagicMock()

# Import voluptuous for schema validation
try:
    import voluptuous as vol
except ImportError:
    # Create minimal mock if voluptuous is not available
    vol = MagicMock()
    sys.modules["voluptuous"] = vol


@pytest.fixture
def mock_hass():
    """Mock Home Assistant instance."""
    hass = MagicMock()
    hass.data = {}
    hass.states = MagicMock()
    hass.services = MagicMock()
    hass.config = MagicMock()
    hass.config.config_dir = "/config"
    return hass


@pytest.fixture
def mock_store():
    """Mock Home Assistant Store."""
    store = MagicMock()
    store.async_load = AsyncMock(return_value={})
    store.async_save = AsyncMock()
    return store


@pytest.fixture
def mock_llm_provider():
    """Mock LLM provider."""
    provider = MagicMock()
    provider.generate = AsyncMock(return_value={"content": "Test response"})
    provider.generate_stream = AsyncMock()
    provider.generate_stream_with_tools = AsyncMock()
    provider.validate_api_key = AsyncMock(return_value=True)
    provider.api_key = "test_api_key"
    provider.model = "test_model"
    provider.temperature = 0.7
    provider.max_tokens = 1024
    return provider


@pytest.fixture
def mock_config_entry():
    """Mock config entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = {
        "provider": "groq",
        "api_key": "test_key",
        "model": "test_model",
    }
    entry.options = {
        "temperature": 0.7,
        "max_tokens": 1024,
        "enable_streaming": False,
    }
    return entry
