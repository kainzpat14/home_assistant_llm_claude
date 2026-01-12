"""Persistent storage for conversation facts."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.facts"


class FactStore:
    """Manages persistent storage of learned facts."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the fact store."""
        self.hass = hass
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._facts: dict[str, Any] = {}

    async def async_load(self) -> None:
        """Load facts from storage."""
        data = await self._store.async_load()
        if data:
            self._facts = data
        _LOGGER.debug("Loaded %d facts from storage", len(self._facts))

    async def async_save(self) -> None:
        """Save facts to storage."""
        await self._store.async_save(self._facts)
        _LOGGER.debug("Saved %d facts to storage", len(self._facts))

    def add_fact(self, key: str, value: Any) -> None:
        """Add or update a fact."""
        self._facts[key] = value

    def get_fact(self, key: str) -> Any | None:
        """Get a fact by key."""
        return self._facts.get(key)

    def get_all_facts(self) -> dict[str, Any]:
        """Get all facts."""
        return self._facts.copy()

    def remove_fact(self, key: str) -> None:
        """Remove a fact."""
        self._facts.pop(key, None)

    def clear(self) -> None:
        """Clear all facts."""
        self._facts.clear()
