"""Voice Assistant LLM integration for Home Assistant."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)
# Set minimum log level to DEBUG to ensure debug logging capability
# Home Assistant's configuration.yaml can still override this
_LOGGER.setLevel(logging.DEBUG)

PLATFORMS: list[Platform] = [Platform.CONVERSATION]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Voice Assistant LLM from a config entry."""
    _LOGGER.info("Setting up Voice Assistant LLM integration (entry_id: %s)", entry.entry_id)
    _LOGGER.debug("Config entry data: %s", entry.data)
    _LOGGER.debug("Config entry options: %s", entry.options)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _LOGGER.info("Voice Assistant LLM integration setup completed successfully")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading Voice Assistant LLM integration (entry_id: %s)", entry.entry_id)

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        _LOGGER.info("Voice Assistant LLM integration unloaded successfully")
    else:
        _LOGGER.warning("Failed to unload Voice Assistant LLM integration")

    return unload_ok
