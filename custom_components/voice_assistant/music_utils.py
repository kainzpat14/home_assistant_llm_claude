"""Utility functions for music assistant integration.

This module contains pure utility functions that can be tested independently
of Home Assistant runtime.
"""

from __future__ import annotations

import re


def extract_room_name(friendly_name: str, entity_id: str) -> str:
    """Extract room name from friendly name or entity_id.

    This function removes common suffixes from friendly names and can fall back
    to parsing the entity_id if needed.

    Args:
        friendly_name: The friendly name of the player (e.g., "Living Room Speaker").
        entity_id: The entity ID (e.g., "media_player.ma_living_room").

    Returns:
        The extracted room name (e.g., "Living Room" or "living room").

    Examples:
        >>> extract_room_name("Living Room Speaker", "media_player.ma_living_room")
        'Living Room'
        >>> extract_room_name("", "media_player.ma_bedroom")
        'bedroom'
    """
    # Try friendly name first
    if friendly_name:
        # Remove common suffixes
        for suffix in [" Speaker", " Player", " MA", " Music"]:
            if friendly_name.endswith(suffix):
                return friendly_name[: -len(suffix)]
        return friendly_name

    # Fall back to entity_id parsing
    # media_player.ma_living_room -> living room
    name = entity_id.replace("media_player.", "").replace("ma_", "")
    return name.replace("_", " ")


def normalize_room_name(room_name: str) -> str:
    """Normalize room name for fuzzy matching.

    Args:
        room_name: The room name to normalize.

    Returns:
        Normalized room name (lowercase, stripped).

    Examples:
        >>> normalize_room_name("  Living Room  ")
        'living room'
        >>> normalize_room_name("BEDROOM")
        'bedroom'
    """
    return room_name.lower().strip()


def fuzzy_match_room(
    query: str, available_rooms: dict[str, str]
) -> str | None:
    """Fuzzy match a room query against available room names.

    Uses a tiered matching strategy:
    1. Exact match (highest priority)
    2. Word boundary match (e.g., "living" matches "living room" but not "reliving")
    3. Substring match (fallback for partial words like "liv" -> "living room")

    Args:
        query: The room name query (e.g., "living").
        available_rooms: Dict mapping normalized room names to entity IDs.

    Returns:
        The entity ID of the matched room, or None if no match found.

    Examples:
        >>> rooms = {"living room": "media_player.living", "bedroom": "media_player.bed"}
        >>> fuzzy_match_room("living", rooms)
        'media_player.living'
        >>> fuzzy_match_room("room", rooms)  # Word boundary: matches first occurrence
        'media_player.living'
        >>> fuzzy_match_room("bed", rooms)
        'media_player.bed'
        >>> fuzzy_match_room("kitchen", rooms)
        None
    """
    normalized_query = normalize_room_name(query)

    # Empty query returns None
    if not normalized_query:
        return None

    # Exact match first
    if normalized_query in available_rooms:
        return available_rooms[normalized_query]

    # Try word boundary matching first (more precise)
    # Match query as a complete word in the room name
    escaped_query = re.escape(normalized_query)
    for room_name, entity_id in available_rooms.items():
        # Check if query is a complete word in room_name
        if re.search(rf'\b{escaped_query}\b', room_name):
            return entity_id

    # Fall back to substring matching if no word boundary match
    # This handles cases like "liv" matching "living room"
    for room_name, entity_id in available_rooms.items():
        if normalized_query in room_name or room_name in normalized_query:
            return entity_id

    return None
