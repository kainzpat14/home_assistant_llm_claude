"""Config flow for Voice Assistant LLM integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_KEY

from .const import (
    CONF_LLM_HASS_API,
    CONF_MAX_TOKENS,
    CONF_MODEL,
    CONF_PROVIDER,
    CONF_TEMPERATURE,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODELS,
    DEFAULT_TEMPERATURE,
    DOMAIN,
    PROVIDER_GROQ,
    SUPPORTED_PROVIDERS,
)
from .llm import create_llm_provider

_LOGGER = logging.getLogger(__name__)


class VoiceAssistantConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Voice Assistant LLM."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate API key
            try:
                provider = create_llm_provider(
                    provider=user_input[CONF_PROVIDER],
                    api_key=user_input[CONF_API_KEY],
                    model=user_input[CONF_MODEL],
                    temperature=user_input.get(CONF_TEMPERATURE, DEFAULT_TEMPERATURE),
                    max_tokens=user_input.get(CONF_MAX_TOKENS, DEFAULT_MAX_TOKENS),
                )
                if not await provider.validate_api_key():
                    errors["base"] = "invalid_api_key"
            except Exception:
                errors["base"] = "cannot_connect"

            if not errors:
                return self.async_create_entry(
                    title=f"Voice Assistant ({user_input[CONF_PROVIDER]})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PROVIDER, default=PROVIDER_GROQ): vol.In(
                        SUPPORTED_PROVIDERS
                    ),
                    vol.Required(CONF_API_KEY): str,
                    vol.Required(
                        CONF_MODEL, default=DEFAULT_MODELS[PROVIDER_GROQ]
                    ): str,
                    vol.Optional(CONF_LLM_HASS_API, default=True): bool,
                    vol.Optional(
                        CONF_TEMPERATURE, default=DEFAULT_TEMPERATURE
                    ): vol.Coerce(float),
                    vol.Optional(
                        CONF_MAX_TOKENS, default=DEFAULT_MAX_TOKENS
                    ): vol.Coerce(int),
                }
            ),
            errors=errors,
        )
