"""Tool call handlers for conversation agent.

This module contains helper functions for handling different types of tool calls:
- Meta-tools (query_tools, query_facts, learn_fact)
- Music Assistant tools
- Home Assistant service calls

Extracted from conversation.py to improve modularity and maintainability.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.conversation import (
    AssistantContent,
)

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.components import conversation
    from homeassistant.components.conversation import ChatLog

    from .llm_tools import LLMToolManager

_LOGGER = logging.getLogger(__name__)


def categorize_tool_calls(
    tool_calls: list[dict[str, Any]]
) -> tuple[list, list, list, list, list]:
    """Categorize tool calls into different types.

    Args:
        tool_calls: List of tool calls to categorize.

    Returns:
        Tuple of (query_tools_calls, query_facts_calls, learn_fact_calls,
                 music_tool_calls, ha_tool_calls).
    """
    query_tools_calls = []
    query_facts_calls = []
    learn_fact_calls = []
    music_tool_calls = []
    ha_tool_calls = []

    for tool_call in tool_calls:
        tool_name = tool_call["function"]["name"]
        if tool_name == "query_tools":
            query_tools_calls.append(tool_call)
        elif tool_name == "query_facts":
            query_facts_calls.append(tool_call)
        elif tool_name == "learn_fact":
            learn_fact_calls.append(tool_call)
        elif tool_name in ["play_music", "get_now_playing", "control_playback",
                             "search_music", "transfer_music", "get_music_players"]:
            music_tool_calls.append(tool_call)
        else:
            ha_tool_calls.append(tool_call)

    return (query_tools_calls, query_facts_calls, learn_fact_calls,
            music_tool_calls, ha_tool_calls)


async def handle_query_tools_calls(
    query_tools_calls: list[dict[str, Any]],
    current_tools: list[dict[str, Any]],
    tool_manager: LLMToolManager,
    messages: list[dict[str, Any]],
    chat_log: ChatLog,
    handle_query_tools_fn: callable,
) -> None:
    """Handle query_tools meta-tool calls.

    Args:
        query_tools_calls: List of query_tools tool calls.
        current_tools: Current list of available tools (will be modified).
        tool_manager: The tool manager.
        messages: Messages list (will be modified).
        chat_log: The chat log.
        handle_query_tools_fn: Function to handle individual query_tools call.
    """
    if not query_tools_calls:
        return

    query_tools_summary = []
    for tool_call in query_tools_calls:
        arguments = json.loads(tool_call["function"]["arguments"])
        _LOGGER.info("Handling query_tools: %s", arguments)

        result = handle_query_tools_fn(arguments, current_tools, tool_manager)

        messages.append({
            "role": "tool",
            "tool_call_id": tool_call["id"],
            "content": json.dumps(result),
        })

        domain_filter = arguments.get("domain", "all domains")
        if result.get("success"):
            tools_found = result.get("result", {}).get("tools", [])
            query_tools_summary.append(
                f"Discovered {len(tools_found)} tools for {domain_filter}"
            )

    if query_tools_summary:
        summary_content = AssistantContent(
            agent_id=DOMAIN,
            content="\n".join(query_tools_summary),
        )
        chat_log.async_add_assistant_content_without_tools(summary_content)


async def handle_query_facts_calls(
    query_facts_calls: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    chat_log: ChatLog,
    handle_query_facts_fn: callable,
) -> None:
    """Handle query_facts meta-tool calls.

    Args:
        query_facts_calls: List of query_facts tool calls.
        messages: Messages list (will be modified).
        chat_log: The chat log.
        handle_query_facts_fn: Function to handle individual query_facts call.
    """
    if not query_facts_calls:
        return

    query_facts_summary = []
    for tool_call in query_facts_calls:
        arguments = json.loads(tool_call["function"]["arguments"])
        _LOGGER.info("Handling query_facts: %s", arguments)

        result = handle_query_facts_fn(arguments)

        messages.append({
            "role": "tool",
            "tool_call_id": tool_call["id"],
            "content": json.dumps(result),
        })

        category_filter = arguments.get("category", "all categories")
        if result.get("success"):
            facts_found = result.get("facts", {})
            query_facts_summary.append(
                f"Retrieved {len(facts_found)} facts for {category_filter}"
            )

    if query_facts_summary:
        summary_content = AssistantContent(
            agent_id=DOMAIN,
            content="\n".join(query_facts_summary),
        )
        chat_log.async_add_assistant_content_without_tools(summary_content)


async def handle_learn_fact_calls(
    learn_fact_calls: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    chat_log: ChatLog,
    handle_learn_fact_fn: callable,
) -> None:
    """Handle learn_fact meta-tool calls.

    Args:
        learn_fact_calls: List of learn_fact tool calls.
        messages: Messages list (will be modified).
        chat_log: The chat log.
        handle_learn_fact_fn: Async function to handle individual learn_fact call.
    """
    if not learn_fact_calls:
        return

    learn_fact_summary = []
    for tool_call in learn_fact_calls:
        arguments = json.loads(tool_call["function"]["arguments"])
        _LOGGER.info("Handling learn_fact: %s", arguments)

        result = await handle_learn_fact_fn(arguments)

        messages.append({
            "role": "tool",
            "tool_call_id": tool_call["id"],
            "content": json.dumps(result),
        })

        if result.get("success"):
            key = arguments.get("key", "unknown")
            learn_fact_summary.append(
                f"Learned fact: {key}"
            )

    if learn_fact_summary:
        summary_content = AssistantContent(
            agent_id=DOMAIN,
            content="\n".join(learn_fact_summary),
        )
        chat_log.async_add_assistant_content_without_tools(summary_content)


async def handle_music_tool_calls(
    music_tool_calls: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    chat_log: ChatLog,
    handle_music_tool_fn: callable,
) -> None:
    """Handle music assistant meta-tool calls.

    Args:
        music_tool_calls: List of music tool calls.
        messages: Messages list (will be modified).
        chat_log: The chat log.
        handle_music_tool_fn: Async function to handle individual music tool call.
    """
    if not music_tool_calls:
        return

    music_summary = []
    for tool_call in music_tool_calls:
        tool_name = tool_call["function"]["name"]
        arguments = json.loads(tool_call["function"]["arguments"])
        _LOGGER.info("Handling music tool %s: %s", tool_name, arguments)

        result = await handle_music_tool_fn(tool_name, arguments)

        messages.append({
            "role": "tool",
            "tool_call_id": tool_call["id"],
            "content": json.dumps(result),
        })

        if result.get("success"):
            music_summary.append(result.get("message", f"Executed {tool_name}"))

    if music_summary:
        summary_content = AssistantContent(
            agent_id=DOMAIN,
            content="\n".join(music_summary),
        )
        chat_log.async_add_assistant_content_without_tools(summary_content)


async def handle_ha_tool_calls(
    ha_tool_calls: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    chat_log: ChatLog,
    user_input: conversation.ConversationInput,
    accumulated_content: str,
    convert_tool_calls_fn: callable,
) -> None:
    """Handle Home Assistant tool calls.

    Args:
        ha_tool_calls: List of HA tool calls.
        messages: Messages list (will be modified).
        chat_log: The chat log.
        user_input: The original user input.
        accumulated_content: The accumulated assistant content.
        convert_tool_calls_fn: Function to convert tool calls to ToolInput format.
    """
    if not ha_tool_calls:
        return

    _LOGGER.info("Processing %d HA tool call(s)", len(ha_tool_calls))

    tool_inputs = convert_tool_calls_fn(ha_tool_calls, user_input)

    assistant_content = AssistantContent(
        agent_id=DOMAIN,
        content=accumulated_content,
        tool_calls=tool_inputs,
    )

    async for tool_result in chat_log.async_add_assistant_content(assistant_content):
        _LOGGER.info(
            "Tool %s executed",
            tool_result.tool_name,
        )

        messages.append({
            "role": "tool",
            "tool_call_id": tool_result.tool_call_id,
            "content": json.dumps(tool_result.tool_result),
        })
