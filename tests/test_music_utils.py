"""Tests for music_utils module."""

import pytest

from custom_components.voice_assistant.music_utils import (
    extract_room_name,
    fuzzy_match_room,
    normalize_room_name,
)


class TestExtractRoomName:
    """Tests for extract_room_name function."""

    def test_extract_with_speaker_suffix(self):
        """Test extracting room name with Speaker suffix."""
        result = extract_room_name("Living Room Speaker", "media_player.ma_living_room")
        assert result == "Living Room"

    def test_extract_with_player_suffix(self):
        """Test extracting room name with Player suffix."""
        result = extract_room_name("Kitchen Player", "media_player.ma_kitchen")
        assert result == "Kitchen"

    def test_extract_with_ma_suffix(self):
        """Test extracting room name with MA suffix."""
        result = extract_room_name("Bedroom MA", "media_player.ma_bedroom")
        assert result == "Bedroom"

    def test_extract_with_music_suffix(self):
        """Test extracting room name with Music suffix."""
        result = extract_room_name("Office Music", "media_player.ma_office")
        assert result == "Office"

    def test_extract_without_suffix(self):
        """Test extracting room name without any suffix."""
        result = extract_room_name("Garage", "media_player.ma_garage")
        assert result == "Garage"

    def test_extract_fallback_to_entity_id(self):
        """Test fallback to entity_id when friendly_name is empty."""
        result = extract_room_name("", "media_player.ma_living_room")
        assert result == "living room"

    def test_extract_entity_id_without_ma_prefix(self):
        """Test parsing entity_id without ma_ prefix."""
        result = extract_room_name("", "media_player.bedroom")
        assert result == "bedroom"

    def test_extract_entity_id_with_underscores(self):
        """Test parsing entity_id with underscores."""
        result = extract_room_name("", "media_player.ma_master_bedroom")
        assert result == "master bedroom"

    def test_extract_preserves_case_from_friendly_name(self):
        """Test that case is preserved from friendly name."""
        result = extract_room_name("LOUD ROOM Speaker", "media_player.loud")
        assert result == "LOUD ROOM"

    def test_extract_multiple_suffixes_only_one_removed(self):
        """Test that only one suffix is removed (the matching one)."""
        result = extract_room_name("Player Room Player", "media_player.player_room")
        assert result == "Player Room"

    def test_extract_suffix_not_at_end(self):
        """Test that suffix in middle is not removed."""
        result = extract_room_name("Speaker Room", "media_player.speaker_room")
        assert result == "Speaker Room"  # "Speaker" not at end, so not removed


class TestNormalizeRoomName:
    """Tests for normalize_room_name function."""

    def test_normalize_uppercase(self):
        """Test normalizing uppercase room name."""
        result = normalize_room_name("LIVING ROOM")
        assert result == "living room"

    def test_normalize_mixed_case(self):
        """Test normalizing mixed case room name."""
        result = normalize_room_name("LiViNg RoOm")
        assert result == "living room"

    def test_normalize_with_leading_whitespace(self):
        """Test normalizing room name with leading whitespace."""
        result = normalize_room_name("  bedroom")
        assert result == "bedroom"

    def test_normalize_with_trailing_whitespace(self):
        """Test normalizing room name with trailing whitespace."""
        result = normalize_room_name("kitchen  ")
        assert result == "kitchen"

    def test_normalize_with_both_whitespace(self):
        """Test normalizing room name with both leading and trailing whitespace."""
        result = normalize_room_name("  office  ")
        assert result == "office"

    def test_normalize_already_normalized(self):
        """Test normalizing already normalized room name."""
        result = normalize_room_name("garage")
        assert result == "garage"

    def test_normalize_empty_string(self):
        """Test normalizing empty string."""
        result = normalize_room_name("")
        assert result == ""

    def test_normalize_whitespace_only(self):
        """Test normalizing whitespace-only string."""
        result = normalize_room_name("   ")
        assert result == ""


class TestFuzzyMatchRoom:
    """Tests for fuzzy_match_room function."""

    def test_exact_match(self):
        """Test exact match returns correct entity_id."""
        rooms = {
            "living room": "media_player.living",
            "bedroom": "media_player.bedroom",
        }
        result = fuzzy_match_room("living room", rooms)
        assert result == "media_player.living"

    def test_exact_match_case_insensitive(self):
        """Test exact match is case insensitive."""
        rooms = {"living room": "media_player.living"}
        result = fuzzy_match_room("LIVING ROOM", rooms)
        assert result == "media_player.living"

    def test_exact_match_with_whitespace(self):
        """Test exact match handles whitespace."""
        rooms = {"bedroom": "media_player.bedroom"}
        result = fuzzy_match_room("  bedroom  ", rooms)
        assert result == "media_player.bedroom"

    def test_partial_match_query_in_room(self):
        """Test partial match when query is substring of room name."""
        rooms = {"living room": "media_player.living"}
        result = fuzzy_match_room("living", rooms)
        assert result == "media_player.living"

    def test_partial_match_room_in_query(self):
        """Test partial match when room name is substring of query."""
        rooms = {"bed": "media_player.bed"}
        result = fuzzy_match_room("bedroom", rooms)
        assert result == "media_player.bed"

    def test_no_match_returns_none(self):
        """Test that no match returns None."""
        rooms = {"living room": "media_player.living"}
        result = fuzzy_match_room("kitchen", rooms)
        assert result is None

    def test_empty_query_returns_none(self):
        """Test that empty query returns None."""
        rooms = {"living room": "media_player.living"}
        result = fuzzy_match_room("", rooms)
        assert result is None

    def test_empty_rooms_returns_none(self):
        """Test that empty rooms dict returns None."""
        result = fuzzy_match_room("living room", {})
        assert result is None

    def test_multiple_rooms_returns_first_match(self):
        """Test that first matching room is returned."""
        rooms = {
            "living room": "media_player.living",
            "living area": "media_player.area",
        }
        result = fuzzy_match_room("living", rooms)
        # Should return one of them (dict iteration order)
        assert result in ["media_player.living", "media_player.area"]

    def test_fuzzy_match_with_special_characters(self):
        """Test fuzzy matching with special characters in room names."""
        rooms = {"kid's room": "media_player.kids"}
        result = fuzzy_match_room("kid", rooms)
        assert result == "media_player.kids"

    def test_fuzzy_match_partial_word(self):
        """Test fuzzy matching with partial word."""
        rooms = {"master bedroom": "media_player.master"}
        result = fuzzy_match_room("master", rooms)
        assert result == "media_player.master"

    def test_fuzzy_match_prioritizes_exact(self):
        """Test that exact matches are returned before fuzzy matches."""
        rooms = {
            "room": "media_player.room",
            "living room": "media_player.living",
        }
        result = fuzzy_match_room("room", rooms)
        assert result == "media_player.room"

    def test_no_fuzzy_match_when_no_overlap(self):
        """Test that non-overlapping strings don't match."""
        rooms = {"kitchen": "media_player.kitchen"}
        result = fuzzy_match_room("bedroom", rooms)
        assert result is None

    def test_single_character_match(self):
        """Test fuzzy matching with single character."""
        rooms = {"living room": "media_player.living"}
        result = fuzzy_match_room("l", rooms)
        assert result == "media_player.living"


class TestIntegration:
    """Integration tests combining multiple functions."""

    def test_extract_and_normalize(self):
        """Test extracting and normalizing room name."""
        room = extract_room_name("Living Room Speaker", "media_player.ma_living_room")
        normalized = normalize_room_name(room)
        assert normalized == "living room"

    def test_full_workflow(self):
        """Test full workflow: extract, normalize, and match."""
        # Simulate extracting from player data
        friendly_name = "Kitchen Player"
        entity_id = "media_player.ma_kitchen"

        # Extract room name
        room = extract_room_name(friendly_name, entity_id)
        assert room == "Kitchen"

        # Normalize for cache
        normalized = normalize_room_name(room)
        assert normalized == "kitchen"

        # Build cache
        cache = {normalized: entity_id}

        # Try to match with user query
        result = fuzzy_match_room("kitchen", cache)
        assert result == entity_id

    def test_workflow_with_fuzzy_query(self):
        """Test workflow with fuzzy user query."""
        # Setup
        room_names = [
            ("Living Room Speaker", "media_player.ma_living_room"),
            ("Bedroom Player", "media_player.ma_bedroom"),
        ]

        # Build cache
        cache = {}
        for friendly_name, entity_id in room_names:
            room = extract_room_name(friendly_name, entity_id)
            normalized = normalize_room_name(room)
            cache[normalized] = entity_id

        # Test fuzzy matching
        assert fuzzy_match_room("living", cache) == "media_player.ma_living_room"
        assert fuzzy_match_room("bed", cache) == "media_player.ma_bedroom"
        assert fuzzy_match_room("kitchen", cache) is None
