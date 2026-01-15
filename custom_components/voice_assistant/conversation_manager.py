"""Conversation session manager with timeout and fact learning."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .storage import FactStore

_LOGGER = logging.getLogger(__name__)

FACT_EXTRACTION_PROMPT = """Analyze the following conversation and extract any personal facts that were learned about the user. Return a JSON object with facts.

Categories to look for:
- user_name: The user's name
- family_members: Names of family members mentioned
- preferences: Temperature preferences, favorite settings, routines
- device_nicknames: Custom names for devices
- locations: Room names, locations of devices
- routines: Regular patterns (wake time, bedtime, etc.)

Only include facts that were explicitly stated or clearly implied. If no facts were learned, return an empty object {{}}.

Conversation:
{conversation}

Return ONLY valid JSON, no explanation."""


@dataclass
class ConversationSession:
    """Represents a global conversation session across all HA conversations."""

    messages: list[dict[str, Any]] = field(default_factory=list)
    last_activity: datetime = field(default_factory=datetime.now)

    def add_message(self, role: str, content: str) -> None:
        """Add a message to the session."""
        self.messages.append({"role": role, "content": content})
        self.last_activity = datetime.now()

    def is_expired(self, timeout_seconds: int) -> bool:
        """Check if session has expired.

        Args:
            timeout_seconds: Timeout in seconds.

        Returns:
            True if session has expired.
        """
        return (datetime.now() - self.last_activity).total_seconds() > timeout_seconds

    def get_conversation_text(self) -> str:
        """Get conversation as text for fact extraction."""
        lines = []
        for msg in self.messages:
            role = msg["role"].capitalize()
            content = msg["content"]
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def clear(self) -> None:
        """Clear all messages from the session."""
        self.messages.clear()
        self.last_activity = datetime.now()


class ConversationManager:
    """Manages a global conversation session with timeout and fact learning."""

    def __init__(
        self,
        hass: HomeAssistant,
        fact_store: FactStore,
        timeout_seconds: int = 60,
    ) -> None:
        """Initialize the conversation manager.

        Args:
            hass: Home Assistant instance.
            fact_store: Fact storage.
            timeout_seconds: Timeout in seconds (default 60).
        """
        self.hass = hass
        self.fact_store = fact_store
        self.timeout_seconds = timeout_seconds
        self._session: ConversationSession = ConversationSession()
        self._cleanup_task: asyncio.Task | None = None
        self._llm_provider = None  # Set by conversation agent

    def set_llm_provider(self, provider) -> None:
        """Set the LLM provider for fact extraction."""
        self._llm_provider = provider

    def get_session(self) -> ConversationSession:
        """Get the global session, checking for expiration.

        Returns:
            The global conversation session.
        """
        # Check if session expired
        if self._session.is_expired(self.timeout_seconds):
            # Session expired - extract facts and clear
            _LOGGER.info("Global session expired, extracting facts and clearing")
            # Use Home Assistant's task creation to prevent garbage collection
            self.hass.async_create_task(self._handle_session_timeout())
            self._session.clear()

        return self._session

    async def _handle_session_timeout(self) -> None:
        """Handle session timeout - extract and save facts."""
        if not self._session.messages:
            return

        _LOGGER.info(
            "Session timed out with %d messages, extracting facts",
            len(self._session.messages),
        )

        try:
            await self._extract_and_save_facts(self._session)
        except Exception as err:
            _LOGGER.error("Error extracting facts: %s", err)

    async def _extract_and_save_facts(self, session: ConversationSession) -> None:
        """Use LLM to extract facts from conversation."""
        if not self._llm_provider:
            _LOGGER.warning("No LLM provider set, cannot extract facts")
            return

        conversation_text = session.get_conversation_text()

        messages = [
            {"role": "system", "content": "You are a fact extraction assistant. Extract facts from conversations and return them as JSON."},
            {"role": "user", "content": FACT_EXTRACTION_PROMPT.format(conversation=conversation_text)},
        ]

        try:
            response = await self._llm_provider.generate(messages, tools=None)
            content = response.get("content", "")

            # Parse JSON response
            # Find JSON in response (might have markdown code blocks)
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            facts = json.loads(content.strip())

            # Save each fact
            for key, value in facts.items():
                if value:  # Only save non-empty facts
                    self.fact_store.add_fact(key, value)
                    _LOGGER.info("Learned fact: %s = %s", key, value)

            # Persist to storage
            await self.fact_store.async_save()

        except json.JSONDecodeError as err:
            _LOGGER.warning("Failed to parse facts JSON: %s", err)
        except Exception as err:
            _LOGGER.error("Error during fact extraction: %s", err)

    def build_facts_prompt_section(self) -> str:
        """Build a prompt section containing known facts."""
        facts = self.fact_store.get_all_facts()
        if not facts:
            return ""

        lines = ["\n\n**Known information about this user:**"]
        for key, value in facts.items():
            # Format the fact nicely
            key_formatted = key.replace("_", " ").title()
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value)
            lines.append(f"- {key_formatted}: {value}")

        return "\n".join(lines)

    async def start_cleanup_task(self) -> None:
        """Start background task to clean up expired sessions."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop_cleanup_task(self) -> None:
        """Stop the cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    async def _cleanup_loop(self) -> None:
        """Periodically check for and clean up expired session."""
        while True:
            # Check more frequently for shorter timeouts
            check_interval = min(30, self.timeout_seconds / 2)
            await asyncio.sleep(check_interval)

            # Check if global session expired
            if self._session.is_expired(self.timeout_seconds) and self._session.messages:
                _LOGGER.info("Background cleanup: session expired, extracting facts")
                await self._handle_session_timeout()
                self._session.clear()
