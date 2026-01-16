"""Music Assistant integration for voice control."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import MAX_MUSIC_SEARCH_RESULTS, VOLUME_SCALE_FACTOR
from .music_utils import extract_room_name, fuzzy_match_room, normalize_room_name

if TYPE_CHECKING:
    from homeassistant.components.conversation import ChatLog

_LOGGER = logging.getLogger(__name__)


class MusicAssistantHandler:
    """Handler for Music Assistant operations."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the Music Assistant handler."""
        self.hass = hass
        self._player_cache: dict[str, str] = {}  # Room name -> entity_id mapping

    def is_available(self) -> bool:
        """Check if Music Assistant integration is available."""
        return self.hass.services.has_service("music_assistant", "play_media")

    async def load_and_cache_players(self) -> list[dict[str, Any]]:
        """Load all Music Assistant player entities and cache room name mappings.

        Note: This method has a side effect of populating _player_cache.
        """
        players = []

        # Get entity registry
        ent_reg = er.async_get(self.hass)

        # Find all media_player entities that start with ma_ (Music Assistant naming convention)
        for entity_id in self.hass.states.async_entity_ids("media_player"):
            state = self.hass.states.get(entity_id)
            if not state:
                continue

            # Check if it's a Music Assistant player
            # MA players typically have "mass" or "music_assistant" in integration
            entity_entry = ent_reg.async_get(entity_id)
            is_ma_player = (
                entity_entry and entity_entry.platform == "music_assistant"
            ) or entity_id.startswith("media_player.ma_")

            if is_ma_player:
                friendly_name = state.attributes.get("friendly_name", entity_id)
                players.append({
                    "entity_id": entity_id,
                    "name": friendly_name,
                    "state": state.state,
                    "media_title": state.attributes.get("media_title"),
                    "media_artist": state.attributes.get("media_artist"),
                    "media_album_name": state.attributes.get("media_album_name"),
                    "volume_level": state.attributes.get("volume_level"),
                })

                # Cache room name mapping
                room_name = extract_room_name(friendly_name, entity_id)
                self._player_cache[normalize_room_name(room_name)] = entity_id

        return players

    def resolve_player(self, player_ref: str | None) -> str | None:
        """Resolve player reference (room name or entity_id) to entity_id.

        Args:
            player_ref: Room name (e.g., 'living room') or entity_id.

        Returns:
            Entity ID or None if not found.
        """
        if not player_ref:
            return None

        # Already an entity_id
        if player_ref.startswith("media_player."):
            return player_ref

        # Use fuzzy matching utility
        return fuzzy_match_room(player_ref, self._player_cache)

    async def get_first_active_player(self) -> str | None:
        """Get the first player that is currently playing."""
        players = await self.load_and_cache_players()
        for player in players:
            if player["state"] == "playing":
                return player["entity_id"]
        # Fall back to first available player
        return players[0]["entity_id"] if players else None

    async def play_music(
        self,
        query: str,
        player: str | None = None,
        media_type: str | None = None,
        enqueue: str = "replace",
        radio_mode: bool = False,
    ) -> dict[str, Any]:
        """Play music using Music Assistant.

        Args:
            query: What to play (artist, album, track, etc.)
            player: Target player (room name or entity_id)
            media_type: Type of media (track, album, artist, playlist, radio)
            enqueue: Queue mode (play, replace, next, add)
            radio_mode: Enable radio mode

        Returns:
            Result dictionary with success status and message.
        """
        if not self.is_available():
            return {
                "success": False,
                "error": "Music Assistant is not available. Please ensure it's installed and configured.",
            }

        # Resolve player
        target_entity = self.resolve_player(player)
        if not target_entity:
            target_entity = await self.get_first_active_player()

        if not target_entity:
            return {
                "success": False,
                "error": "No Music Assistant players found. Please check your Music Assistant configuration.",
            }

        try:
            service_data = {
                "media_id": query,
                "enqueue": enqueue,
            }

            if media_type:
                service_data["media_type"] = media_type

            if radio_mode:
                service_data["radio_mode"] = True

            await self.hass.services.async_call(
                "music_assistant",
                "play_media",
                service_data,
                target={"entity_id": target_entity},
            )

            player_name = self._get_player_name(target_entity)
            return {
                "success": True,
                "message": f"Playing '{query}' on {player_name}",
                "player": target_entity,
            }

        except Exception as err:
            _LOGGER.error("Error playing music: %s", err)
            return {
                "success": False,
                "error": f"Failed to play music: {err}",
            }

    def _get_player_name(self, entity_id: str) -> str:
        """Get friendly name for a player entity."""
        state = self.hass.states.get(entity_id)
        if state:
            return state.attributes.get("friendly_name", entity_id)
        return entity_id

    async def get_now_playing(self, player: str | None = None) -> dict[str, Any]:
        """Get current playback information.

        Args:
            player: Specific player to check, or None for all active.

        Returns:
            Currently playing information.
        """
        players = await self.load_and_cache_players()

        if player:
            target_entity = self.resolve_player(player)
            players = [p for p in players if p["entity_id"] == target_entity]

        # Filter to only playing players if no specific player requested
        if not player:
            active_players = [p for p in players if p["state"] == "playing"]
            if active_players:
                players = active_players

        if not players:
            return {
                "success": True,
                "message": "Nothing is currently playing",
                "players": [],
            }

        result_players = []
        for p in players:
            info = {
                "player": p["name"],
                "state": p["state"],
            }
            if p["media_title"]:
                info["track"] = p["media_title"]
            if p["media_artist"]:
                info["artist"] = p["media_artist"]
            if p["media_album_name"]:
                info["album"] = p["media_album_name"]
            result_players.append(info)

        return {
            "success": True,
            "players": result_players,
        }

    async def control_playback(
        self,
        action: str,
        player: str | None = None,
        volume_level: int | None = None,
    ) -> dict[str, Any]:
        """Control playback on a player.

        Args:
            action: Control action (play, pause, stop, next, previous, volume_set, etc.)
            player: Target player
            volume_level: Volume level for volume_set action (0-100)

        Returns:
            Result dictionary.
        """
        target_entity = self.resolve_player(player)
        if not target_entity:
            target_entity = await self.get_first_active_player()

        if not target_entity:
            return {
                "success": False,
                "error": "No Music Assistant player found",
            }

        try:
            service_map = {
                "play": "media_play",
                "pause": "media_pause",
                "stop": "media_stop",
                "next": "media_next_track",
                "previous": "media_previous_track",
                "volume_up": "volume_up",
                "volume_down": "volume_down",
                "shuffle": "shuffle_set",
                "repeat": "repeat_set",
            }

            if action == "volume_set" and volume_level is not None:
                await self.hass.services.async_call(
                    "media_player",
                    "volume_set",
                    {"volume_level": volume_level / VOLUME_SCALE_FACTOR},
                    target={"entity_id": target_entity},
                )
            elif action in service_map:
                await self.hass.services.async_call(
                    "media_player",
                    service_map[action],
                    {},
                    target={"entity_id": target_entity},
                )
            else:
                return {
                    "success": False,
                    "error": f"Unknown action: {action}",
                }

            player_name = self._get_player_name(target_entity)
            return {
                "success": True,
                "message": f"Executed {action} on {player_name}",
            }

        except Exception as err:
            _LOGGER.error("Error controlling playback: %s", err)
            return {
                "success": False,
                "error": f"Failed to control playback: {err}",
            }

    async def search_music(
        self,
        query: str,
        media_type: str | None = None,
        limit: int = 10,
        favorites_only: bool = False,
    ) -> dict[str, Any]:
        """Search music library and providers.

        Args:
            query: Search query
            media_type: Filter by type
            limit: Max results
            favorites_only: Only search favorites

        Returns:
            Search results.
        """
        if not self.is_available():
            return {
                "success": False,
                "error": "Music Assistant is not available",
            }

        try:
            service_data = {
                "search": query,
                "limit": min(limit, MAX_MUSIC_SEARCH_RESULTS),
            }

            if media_type:
                service_data["media_type"] = media_type

            if favorites_only:
                service_data["favorite"] = True

            # Use get_library for searching
            response = await self.hass.services.async_call(
                "music_assistant",
                "get_library",
                service_data,
                blocking=True,
                return_response=True,
            )

            return {
                "success": True,
                "results": response if response else [],
                "query": query,
            }

        except Exception as err:
            _LOGGER.error("Error searching music: %s", err)
            return {
                "success": False,
                "error": f"Search failed: {err}",
            }

    async def transfer_music(
        self,
        target_player: str,
        source_player: str | None = None,
    ) -> dict[str, Any]:
        """Transfer music queue to another player.

        Args:
            target_player: Destination player
            source_player: Source player (or first active)

        Returns:
            Result dictionary.
        """
        if not self.is_available():
            return {
                "success": False,
                "error": "Music Assistant is not available",
            }

        target_entity = self.resolve_player(target_player)
        if not target_entity:
            return {
                "success": False,
                "error": f"Could not find player: {target_player}",
            }

        source_entity = None
        if source_player:
            source_entity = self.resolve_player(source_player)

        try:
            service_data = {"auto_play": True}
            if source_entity:
                service_data["source_player"] = source_entity

            await self.hass.services.async_call(
                "music_assistant",
                "transfer_queue",
                service_data,
                target={"entity_id": target_entity},
            )

            target_name = self._get_player_name(target_entity)
            return {
                "success": True,
                "message": f"Transferred music to {target_name}",
            }

        except Exception as err:
            _LOGGER.error("Error transferring music: %s", err)
            return {
                "success": False,
                "error": f"Failed to transfer: {err}",
            }
