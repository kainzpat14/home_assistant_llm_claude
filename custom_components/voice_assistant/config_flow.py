"""Config flow for Voice Assistant LLM integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_API_KEY
from homeassistant.core import callback
from homeassistant.helpers import llm, selector

from .const import (
    CONF_ENABLE_STREAMING,
    CONF_LLM_HASS_API,
    CONF_MAX_TOKENS,
    CONF_MODEL,
    CONF_PROVIDER,
    CONF_TEMPERATURE,
    DEFAULT_ENABLE_STREAMING,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODELS,
    DEFAULT_TEMPERATURE,
    DOMAIN,
    PROVIDER_GROQ,
    SUPPORTED_PROVIDERS,
)
from .llm import create_llm_provider

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG)

DEFAULT_OPTIONS = {
    CONF_PROVIDER: PROVIDER_GROQ,
    CONF_MODEL: DEFAULT_MODELS[PROVIDER_GROQ],
    CONF_TEMPERATURE: DEFAULT_TEMPERATURE,
    CONF_MAX_TOKENS: DEFAULT_MAX_TOKENS,
}


class VoiceAssistantConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Voice Assistant LLM."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return VoiceAssistantOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step - API key validation only."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate API key with default provider
            try:
                provider = create_llm_provider(
                    provider=PROVIDER_GROQ,
                    api_key=user_input[CONF_API_KEY],
                    model=DEFAULT_MODELS[PROVIDER_GROQ],
                    temperature=DEFAULT_TEMPERATURE,
                    max_tokens=DEFAULT_MAX_TOKENS,
                )
                if not await provider.validate_api_key():
                    errors["base"] = "invalid_api_key"
            except Exception:
                errors["base"] = "cannot_connect"

            if not errors:
                # Store only API key in data, everything else in options
                return self.async_create_entry(
                    title="Voice Assistant LLM",
                    data={CONF_API_KEY: user_input[CONF_API_KEY]},
                    options=DEFAULT_OPTIONS,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): str,
                }
            ),
            errors=errors,
            description_placeholders={
                "docs_url": "https://console.groq.com/keys",
            },
        )


class VoiceAssistantOptionsFlow(OptionsFlow):
    """Handle options flow for Voice Assistant LLM."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Remove llm_hass_api if not selected
            if not user_input.get(CONF_LLM_HASS_API):
                user_input.pop(CONF_LLM_HASS_API, None)

            # Validate the provider/model combination if changed
            try:
                provider = create_llm_provider(
                    provider=user_input[CONF_PROVIDER],
                    api_key=self.config_entry.data[CONF_API_KEY],
                    model=user_input[CONF_MODEL],
                    temperature=user_input.get(CONF_TEMPERATURE, DEFAULT_TEMPERATURE),
                    max_tokens=user_input.get(CONF_MAX_TOKENS, DEFAULT_MAX_TOKENS),
                )
                if not await provider.validate_api_key():
                    errors["base"] = "invalid_api_key"
            except Exception:
                errors["base"] = "cannot_connect"

            if not errors:
                return self.async_create_entry(title="", data=user_input)

        # Get current options or use defaults
        current_provider = self.config_entry.options.get(
            CONF_PROVIDER, DEFAULT_OPTIONS[CONF_PROVIDER]
        )

        # Build list of available LLM APIs
        hass_apis: list[selector.SelectOptionDict] = [
            selector.SelectOptionDict(label=api.name, value=api.id)
            for api in llm.async_get_apis(self.hass)
        ]

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_PROVIDER,
                        default=current_provider,
                    ): vol.In(SUPPORTED_PROVIDERS),
                    vol.Required(
                        CONF_MODEL,
                        default=self.config_entry.options.get(
                            CONF_MODEL, DEFAULT_MODELS[current_provider]
                        ),
                    ): str,
                    vol.Optional(
                        CONF_LLM_HASS_API,
                        description={"suggested_value": self.config_entry.options.get(CONF_LLM_HASS_API)},
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=hass_apis)
                    ),
                    vol.Optional(
                        CONF_TEMPERATURE,
                        default=self.config_entry.options.get(
                            CONF_TEMPERATURE, DEFAULT_OPTIONS[CONF_TEMPERATURE]
                        ),
                    ): vol.Coerce(float),
                    vol.Optional(
                        CONF_MAX_TOKENS,
                        default=self.config_entry.options.get(
                            CONF_MAX_TOKENS, DEFAULT_OPTIONS[CONF_MAX_TOKENS]
                        ),
                    ): vol.Coerce(int),
                    vol.Optional(
                        CONF_ENABLE_STREAMING,
                        default=self.config_entry.options.get(
                            CONF_ENABLE_STREAMING, DEFAULT_ENABLE_STREAMING
                        ),
                    ): bool,
                }
            ),
            errors=errors,
        )
