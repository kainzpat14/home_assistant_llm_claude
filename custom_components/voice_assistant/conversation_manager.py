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

Only include facts that were explicitly stated or clearly implied. If no facts were learned, return an empty object {}.

Conversation:
{conversation}

Return ONLY valid JSON, no explanation."""


@dataclass
class ConversationSession:
    """Represents an active conversation session."""

    conversation_id: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    last_activity: datetime = field(default_factory=datetime.now)

    def add_message(self, role: str, content: str) -> None:
        """Add a message to the session."""
        self.messages.append({"role": role, "content": content})
        self.last_activity = datetime.now()

    def is_expired(self, timeout_minutes: int) -> bool:
        """Check if session has expired."""
        return datetime.now() - self.last_activity > timedelta(minutes=timeout_minutes)

    def get_conversation_text(self) -> str:
        """Get conversation as text for fact extraction."""
        lines = []
        for msg in self.messages:
            role = msg["role"].capitalize()
            content = msg["content"]
            lines.append(f"{role}: {content}")
        return "\n".join(lines)


class ConversationManager:
    """Manages conversation sessions with timeout and fact learning."""

    def __init__(
        self,
        hass: HomeAssistant,
        fact_store: FactStore,
        timeout_minutes: int = 5,
    ) -> None:
        """Initialize the conversation manager."""
        self.hass = hass
        self.fact_store = fact_store
        self.timeout_minutes = timeout_minutes
        self._sessions: dict[str, ConversationSession] = {}
        self._cleanup_task: asyncio.Task | None = None
        self._llm_provider = None  # Set by conversation agent

    def set_llm_provider(self, provider) -> None:
        """Set the LLM provider for fact extraction."""
        self._llm_provider = provider

    def get_or_create_session(self, conversation_id: str) -> ConversationSession:
        """Get existing session or create new one."""
        # Check for expired session first
        if conversation_id in self._sessions:
            session = self._sessions[conversation_id]
            if session.is_expired(self.timeout_minutes):
                # Session expired - extract facts and create new
                asyncio.create_task(self._handle_session_timeout(session))
                del self._sessions[conversation_id]
            else:
                return session

        # Create new session
        session = ConversationSession(conversation_id=conversation_id)
        self._sessions[conversation_id] = session
        return session

    def get_session(self, conversation_id: str) -> ConversationSession | None:
        """Get session if exists and not expired."""
        session = self._sessions.get(conversation_id)
        if session and not session.is_expired(self.timeout_minutes):
            return session
        return None

    async def _handle_session_timeout(self, session: ConversationSession) -> None:
        """Handle session timeout - extract and save facts."""
        if not session.messages:
            return

        _LOGGER.info(
            "Session %s timed out with %d messages, extracting facts",
            session.conversation_id,
            len(session.messages),
        )

        try:
            await self._extract_and_save_facts(session)
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
        """Periodically check for and clean up expired sessions."""
        while True:
            await asyncio.sleep(60)  # Check every minute

            expired_ids = []
            for conv_id, session in self._sessions.items():
                if session.is_expired(self.timeout_minutes):
                    expired_ids.append(conv_id)

            for conv_id in expired_ids:
                session = self._sessions.pop(conv_id)
                await self._handle_session_timeout(session)
