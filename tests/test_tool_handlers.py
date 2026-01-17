"""Tests for tool_handlers module."""

import json
from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.voice_assistant import tool_handlers


class TestCategorizeToolCalls:
    """Tests for categorize_tool_calls function."""

    def test_empty_list(self):
        """Test categorizing empty tool call list."""
        result = tool_handlers.categorize_tool_calls([])

        assert result == ([], [], [], [], [])

    def test_query_tools_only(self):
        """Test categorizing query_tools calls."""
        tool_calls = [
            {"function": {"name": "query_tools", "arguments": '{"domain": "light"}'}},
        ]

        query_tools, query_facts, learn_fact, music, ha = tool_handlers.categorize_tool_calls(tool_calls)

        assert len(query_tools) == 1
        assert len(query_facts) == 0
        assert len(learn_fact) == 0
        assert len(music) == 0
        assert len(ha) == 0

    def test_all_categories(self):
        """Test categorizing mixed tool calls."""
        tool_calls = [
            {"function": {"name": "query_tools", "arguments": "{}"}},
            {"function": {"name": "query_facts", "arguments": "{}"}},
            {"function": {"name": "learn_fact", "arguments": "{}"}},
            {"function": {"name": "play_music", "arguments": "{}"}},
            {"function": {"name": "light.turn_on", "arguments": "{}"}},
        ]

        query_tools, query_facts, learn_fact, music, ha = tool_handlers.categorize_tool_calls(tool_calls)

        assert len(query_tools) == 1
        assert len(query_facts) == 1
        assert len(learn_fact) == 1
        assert len(music) == 1
        assert len(ha) == 1

    def test_music_tool_names(self):
        """Test that all music tool names are categorized correctly."""
        music_tools = [
            "play_music",
            "get_now_playing",
            "control_playback",
            "search_music",
            "transfer_music",
            "get_music_players",
        ]

        for tool_name in music_tools:
            tool_calls = [{"function": {"name": tool_name, "arguments": "{}"}}]
            _, _, _, music, ha = tool_handlers.categorize_tool_calls(tool_calls)

            assert len(music) == 1, f"{tool_name} should be categorized as music tool"
            assert len(ha) == 0, f"{tool_name} should not be categorized as HA tool"

    def test_ha_tools(self):
        """Test that HA service calls are categorized correctly."""
        ha_tools = [
            "light.turn_on",
            "switch.toggle",
            "climate.set_temperature",
            "media_player.play_media",
        ]

        for tool_name in ha_tools:
            tool_calls = [{"function": {"name": tool_name, "arguments": "{}"}}]
            _, _, _, music, ha = tool_handlers.categorize_tool_calls(tool_calls)

            assert len(ha) == 1, f"{tool_name} should be categorized as HA tool"
            assert len(music) == 0, f"{tool_name} should not be categorized as music tool"


@pytest.mark.asyncio
class TestHandleQueryToolsCalls:
    """Tests for handle_query_tools_calls function."""

    async def test_empty_calls(self):
        """Test handling empty query_tools calls."""
        messages = []
        chat_log = Mock()
        handler_fn = Mock(return_value={"success": True})

        await tool_handlers.handle_query_tools_calls(
            [], [], None, messages, chat_log, handler_fn
        )

        # Should not call handler or modify messages
        handler_fn.assert_not_called()
        assert len(messages) == 0

    async def test_single_query_tools_call(self):
        """Test handling single query_tools call."""
        tool_calls = [
            {
                "id": "tool_1",
                "function": {"name": "query_tools", "arguments": '{"domain": "light"}'},
            }
        ]
        current_tools = []
        messages = []
        chat_log = Mock()
        chat_log.async_add_assistant_content_without_tools = Mock()

        handler_fn = Mock(
            return_value={
                "success": True,
                "result": {"tools": ["light.turn_on", "light.turn_off"]},
            }
        )

        await tool_handlers.handle_query_tools_calls(
            tool_calls, current_tools, None, messages, chat_log, handler_fn
        )

        # Should call handler
        handler_fn.assert_called_once()

        # Should add tool result to messages
        assert len(messages) == 1
        assert messages[0]["role"] == "tool"
        assert messages[0]["tool_call_id"] == "tool_1"

        # Should add summary to chat_log
        chat_log.async_add_assistant_content_without_tools.assert_called_once()

    async def test_multiple_query_tools_calls(self):
        """Test handling multiple query_tools calls."""
        tool_calls = [
            {
                "id": "tool_1",
                "function": {"name": "query_tools", "arguments": '{"domain": "light"}'},
            },
            {
                "id": "tool_2",
                "function": {"name": "query_tools", "arguments": '{"domain": "switch"}'},
            },
        ]
        messages = []
        chat_log = Mock()
        chat_log.async_add_assistant_content_without_tools = Mock()

        handler_fn = Mock(
            return_value={"success": True, "result": {"tools": ["test_tool"]}}
        )

        await tool_handlers.handle_query_tools_calls(
            tool_calls, [], None, messages, chat_log, handler_fn
        )

        # Should call handler twice
        assert handler_fn.call_count == 2

        # Should add two tool results
        assert len(messages) == 2


@pytest.mark.asyncio
class TestHandleQueryFactsCalls:
    """Tests for handle_query_facts_calls function."""

    async def test_empty_calls(self):
        """Test handling empty query_facts calls."""
        messages = []
        chat_log = Mock()
        handler_fn = Mock(return_value={"success": True})

        await tool_handlers.handle_query_facts_calls([], messages, chat_log, handler_fn)

        handler_fn.assert_not_called()
        assert len(messages) == 0

    async def test_successful_query(self):
        """Test handling successful query_facts call."""
        tool_calls = [
            {
                "id": "fact_1",
                "function": {"name": "query_facts", "arguments": '{"category": "user_name"}'},
            }
        ]
        messages = []
        chat_log = Mock()
        chat_log.async_add_assistant_content_without_tools = Mock()

        handler_fn = Mock(
            return_value={
                "success": True,
                "facts": {"user_name": "John", "favorite_color": "blue"},
            }
        )

        await tool_handlers.handle_query_facts_calls(
            tool_calls, messages, chat_log, handler_fn
        )

        # Should call handler
        handler_fn.assert_called_once()

        # Should add result to messages
        assert len(messages) == 1
        result = json.loads(messages[0]["content"])
        assert result["success"] is True
        assert "facts" in result


@pytest.mark.asyncio
class TestHandleLearnFactCalls:
    """Tests for handle_learn_fact_calls function."""

    async def test_empty_calls(self):
        """Test handling empty learn_fact calls."""
        messages = []
        chat_log = Mock()
        handler_fn = AsyncMock(return_value={"success": True})

        await tool_handlers.handle_learn_fact_calls([], messages, chat_log, handler_fn)

        handler_fn.assert_not_called()
        assert len(messages) == 0

    async def test_successful_learn(self):
        """Test handling successful learn_fact call."""
        tool_calls = [
            {
                "id": "learn_1",
                "function": {
                    "name": "learn_fact",
                    "arguments": '{"category": "user_name", "key": "name", "value": "John"}',
                },
            }
        ]
        messages = []
        chat_log = Mock()
        chat_log.async_add_assistant_content_without_tools = Mock()

        handler_fn = AsyncMock(return_value={"success": True})

        await tool_handlers.handle_learn_fact_calls(
            tool_calls, messages, chat_log, handler_fn
        )

        # Should call handler
        handler_fn.assert_called_once()

        # Should add result to messages
        assert len(messages) == 1
        assert messages[0]["role"] == "tool"

        # Should add summary to chat_log
        chat_log.async_add_assistant_content_without_tools.assert_called_once()


@pytest.mark.asyncio
class TestHandleMusicToolCalls:
    """Tests for handle_music_tool_calls function."""

    async def test_empty_calls(self):
        """Test handling empty music tool calls."""
        messages = []
        chat_log = Mock()
        handler_fn = AsyncMock(return_value={"success": True})

        await tool_handlers.handle_music_tool_calls([], messages, chat_log, handler_fn)

        handler_fn.assert_not_called()
        assert len(messages) == 0

    async def test_successful_play_music(self):
        """Test handling play_music call."""
        tool_calls = [
            {
                "id": "music_1",
                "function": {
                    "name": "play_music",
                    "arguments": '{"query": "Queen", "player": "living_room"}',
                },
            }
        ]
        messages = []
        chat_log = Mock()
        chat_log.async_add_assistant_content_without_tools = Mock()

        handler_fn = AsyncMock(
            return_value={"success": True, "message": "Playing Queen"}
        )

        await tool_handlers.handle_music_tool_calls(
            tool_calls, messages, chat_log, handler_fn
        )

        # Should call handler with correct tool name and arguments
        handler_fn.assert_called_once()
        call_args = handler_fn.call_args
        assert call_args[0][0] == "play_music"  # tool_name
        assert "query" in call_args[0][1]  # arguments

        # Should add result to messages
        assert len(messages) == 1

        # Should add summary to chat_log
        chat_log.async_add_assistant_content_without_tools.assert_called_once()


@pytest.mark.asyncio
class TestHandleHAToolCalls:
    """Tests for handle_ha_tool_calls function."""

    async def test_empty_calls(self):
        """Test handling empty HA tool calls."""
        messages = []
        chat_log = Mock()
        convert_fn = Mock()

        await tool_handlers.handle_ha_tool_calls(
            [], messages, chat_log, None, "", convert_fn
        )

        convert_fn.assert_not_called()
        assert len(messages) == 0

    async def test_successful_ha_tool_call(self):
        """Test handling successful HA tool call."""
        tool_calls = [
            {
                "id": "ha_1",
                "function": {
                    "name": "light.turn_on",
                    "arguments": '{"entity_id": "light.living_room"}',
                },
            }
        ]
        messages = []

        # Mock tool result
        mock_tool_result = Mock()
        mock_tool_result.tool_name = "light.turn_on"
        mock_tool_result.tool_call_id = "ha_1"
        mock_tool_result.tool_result = {"success": True}

        # Mock chat_log
        chat_log = Mock()

        async def mock_add_content(content):
            yield mock_tool_result

        chat_log.async_add_assistant_content = mock_add_content

        # Mock convert function
        convert_fn = Mock(return_value=[Mock()])

        await tool_handlers.handle_ha_tool_calls(
            tool_calls, messages, chat_log, None, "test content", convert_fn
        )

        # Should call convert function
        convert_fn.assert_called_once()

        # Should add result to messages
        assert len(messages) == 1
        assert messages[0]["role"] == "tool"
        assert messages[0]["tool_call_id"] == "ha_1"

    async def test_multiple_ha_tool_calls(self):
        """Test handling multiple HA tool calls."""
        tool_calls = [
            {
                "id": "ha_1",
                "function": {"name": "light.turn_on", "arguments": "{}"},
            },
            {
                "id": "ha_2",
                "function": {"name": "switch.turn_off", "arguments": "{}"},
            },
        ]
        messages = []

        # Mock tool results
        mock_results = [
            Mock(tool_name="light.turn_on", tool_call_id="ha_1", tool_result={}),
            Mock(tool_name="switch.turn_off", tool_call_id="ha_2", tool_result={}),
        ]

        chat_log = Mock()

        async def mock_add_content(content):
            for result in mock_results:
                yield result

        chat_log.async_add_assistant_content = mock_add_content
        convert_fn = Mock(return_value=[Mock(), Mock()])

        await tool_handlers.handle_ha_tool_calls(
            tool_calls, messages, chat_log, None, "test", convert_fn
        )

        # Should add two results to messages
        assert len(messages) == 2
