# Session Notes

## Important Implementation Details

### Home Assistant LLM API Integration

**Key Decision:** We use Home Assistant's native LLM API for tool discovery and execution, rather than building a custom tool system.

**Why:**
- Leverages HA's built-in tool definitions for all services and entities
- Automatic schema generation and validation
- Integrated with HA's permissions and context system
- Less maintenance burden

**Implementation:**
- `llm_tools.py` wraps HA's LLM API accessed via `chat_log.llm_api`
- Tools are discovered dynamically using `query_tools` meta-tool
- Real HA tools executed via `chat_log.async_add_assistant_content()`

### Tool Schema Conversion

**Critical:** Home Assistant uses `voluptuous` schemas which must be converted to JSON-serializable format for LLM APIs.

**Solution:** Use `voluptuous-openapi` library (core HA dependency, no need to add to requirements):
```python
from voluptuous_openapi import convert
parameters = convert(tool.parameters, custom_serializer=custom_serializer)
```

**Post-processing Required:** Array fields in schemas need descriptions to guide LLMs:
```python
if prop_schema.get("type") == "array" and "description" not in prop_schema:
    prop_schema["description"] = f"Array of {prop_name} values (use JSON array syntax: [val1, val2])"
```

Without this, LLMs pass strings instead of arrays, causing validation errors.

### Conversation History Management ✅ COMPLETED

**Architecture:** Single global session across ALL Home Assistant conversations

**Key Design:**
- ONE `ConversationSession` for all conversations (not per conversation_id)
- Session messages added to LLM context, providing cross-conversation memory
- Timeout in **seconds** (1-600s range, default 60s)
- Session expires after inactivity, triggering automatic fact extraction
- `chat_log` used only for HA UI, **session is source of truth for LLM**

**Implementation Pattern:**
```python
# Single global session (not per conversation_id)
session = self._conversation_manager.get_session()
session.add_message("user", user_input.text)

# Build messages from session (not chat_log!)
def _build_messages(...):
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(session.messages)  # All messages from global session
    return messages
```

**Why This Design:**
- Cross-conversation memory: "remember my cat is Amy" → new conversation → "what's my cat's name?" works!
- Timeout in seconds for faster fact extraction (60s default vs 5 min before)
- Simpler: One session vs many per-conversation sessions
- Session messages = LLM sees full recent history across all conversations

**Fact Learning Implementation:**

Three meta-tools for fact management:
1. **query_facts**: On-demand fact retrieval (saves tokens vs. auto-injection)
2. **learn_fact**: Immediate fact storage when user shares information
3. **Automatic extraction**: Facts extracted from conversation on timeout

**Key Pattern:**
```python
LEARN_FACT_DEFINITION = {
    "function": {
        "name": "learn_fact",
        "parameters": {
            "properties": {
                "category": {"enum": ["user_name", "family_members", "preferences",
                                      "device_nicknames", "locations", "routines"]},
                "key": {"type": "string"},
                "value": {"type": "string"},
            },
            "required": ["category", "key", "value"],
        },
    },
}

async def _handle_learn_fact(self, arguments):
    self._fact_store.add_fact(key, value)
    await self._fact_store.async_save()
```

**Why This Design:**
- Facts queryable immediately, not just after timeout
- LLM decides when to learn/query facts (token efficient)
- Facts persist across conversations via FactStore
- Dual learning: explicit (learn_fact) + implicit (timeout extraction)

### System Prompt Override

Home Assistant provides its own system prompt via two mechanisms:
1. `SystemContent` in chat_log
2. `user_input.extra_system_prompt` parameter

**To use only our configured prompt:**
1. Pass `None` as 4th parameter to `async_provide_llm_data()` to ignore extra_system_prompt
2. Skip `SystemContent` when building messages from chat_log
3. Always prepend our configured system prompt to the messages list

**Note:** HA's system prompt still appears in the chat_log UI, but it doesn't affect what the LLM actually receives.

### Tool Calling Architecture

**Two Types of Tools:**
1. **query_tools (meta-tool):** Internal to our integration, handled locally, not sent to HA's tool system
2. **HA tools:** Real Home Assistant services/entities, executed via HA's tool system

**query_tools Visibility:**
- Can't be added as actual tool call to chat_log (causes "Non-external tool calls not allowed" error)
- Instead, add text summary to chat_log: `AssistantContent(content="Discovered N tools for domain")`
- This provides UI visibility without breaking HA's constraints

### ToolInput Parameters

**Important:** Home Assistant's `llm.ToolInput` only accepts 3 parameters:
```python
llm.ToolInput(
    id=tool_call["id"],
    tool_name=tool_name,
    tool_args=tool_args,
)
```

Don't try to pass: `platform`, `context`, `user_prompt`, `language`, `assistant`, or `device_id` - they will cause errors.

### Reference Integration

**ha-groq-cloud-api** (https://github.com/HunorLaczko/ha-groq-cloud-api) is an excellent reference for:
- Tool schema conversion patterns
- Import paths for HA conversation classes
- Parameter lists for HA API methods
- General integration structure

## Integration-Specific Patterns

### Logging
Set explicit log level in each module to ensure debug logging works:
```python
_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG)
```

Home Assistant's logging configuration doesn't always propagate correctly to custom integrations.

### Message Building
Always build messages in this order:
1. System prompt (ours, not HA's)
2. Previous conversation from chat_log (user + assistant messages)
3. Current user message (if not already in chat_log)

### Tool Iteration Loop
Max 5 iterations (MAX_TOOL_ITERATIONS) to prevent infinite loops.
Separate query_tools from HA tools in each iteration.
Always add tool results back to messages for next LLM call.

## Development Workflow

### Testing Pattern
1. Make changes
2. Reload integration in HA (Developer Tools → YAML → Reload Conversations)
3. Check debug logs in Settings → System → Logs
4. Test with voice pipeline or conversation UI

### Git Workflow
- Develop on branch starting with `claude/` (required by git push restrictions)
- Branch must end with session ID for push to work
- Commit frequently with clear messages
- Push before creating PR

### Common Issues Resolved
1. **Import errors:** Use `from homeassistant.components.conversation import AssistantContent` not `.models`
2. **Tool schema validation:** Add array field descriptions
3. **Memory loss:** Add final response to chat_log
4. **Logging invisible:** Set explicit log levels
5. **Non-external tool calls:** Don't add meta-tools to chat_log as tool calls

## Key Files

| File | Purpose |
|------|---------|
| `conversation.py` | Main conversation agent, handles tool loops and history |
| `llm_tools.py` | Tool discovery and schema conversion |
| `llm/groq.py` | Groq API provider implementation |
| `const.py` | Configuration constants and defaults |
| `config_flow.py` | Integration configuration UI |

## Testing Checklist

When testing conversation memory:
- Start new conversation
- Make statement with facts ("My name is X")
- Ask follow-up requiring context ("What is my name?")
- Check logs: should see "chat_log has N content items" where N > 2
- Should see previous user and assistant messages being added

## Implementation Notes

### Streaming Support ✅ COMPLETED

**Implementation Pattern (Following OpenAI Integration):**

Streaming in Home Assistant works differently than expected. Key learnings:

1. **Entity Declaration:**
   ```python
   class VoiceAssistantConversationAgent(conversation.ConversationEntity):
       _attr_supports_streaming = True
   ```

2. **Use chat_log.async_add_delta_content_stream():**
   ```python
   async for _ in chat_log.async_add_delta_content_stream(
       self.entity_id,
       self._stream_response_with_tools(messages, current_tools, ...),
   ):
       pass  # chat_log handles streaming internally
   ```

3. **Yield Dictionaries, Not Strings:**
   ```python
   async def _stream_response_with_tools(...) -> AsyncIterator[dict[str, Any]]:
       async for chunk in self.provider.generate_stream_with_tools(...):
           if chunk.content:
               yield {"content": chunk.content}  # ← MUST be dict with "content" key
   ```

4. **Don't Return Async Iterator from async_process:**
   - The default `async_process` method in ConversationEntity handles streaming automatically
   - Don't override it to return an async iterator
   - Streaming is enabled by `_attr_supports_streaming = True` + using the stream methods

5. **Tool Call Handling During Streaming:**
   - Accumulate tool calls as they arrive (they come in chunks)
   - Don't stream tool call execution to the user
   - Only stream the final text response after tools complete
   - Store accumulated content and tool_calls in the StreamChunk.is_final event

**Common Mistakes to Avoid:**
- ❌ Yielding plain strings instead of `{"content": "text"}` dicts
- ❌ Trying to override `async_process` to return AsyncIterator[ConversationResultDelta]
- ❌ Using `conversation.async_get_result_from_chat_log()` with handler parameter (it only takes 2 args)
- ❌ Streaming tool calls to users (handle them silently in the background)

**Groq Provider Streaming Implementation:**
```python
async def generate_stream_with_tools(...) -> AsyncIterator[StreamChunk]:
    accumulated_tool_calls = []
    async for chunk in stream:
        if chunk.choices[0].delta.content:
            yield StreamChunk(content=chunk.choices[0].delta.content)

        if chunk.choices[0].delta.tool_calls:
            # Accumulate tool calls by index
            for tc_delta in chunk.choices[0].delta.tool_calls:
                idx = tc_delta.index
                # Append parts to accumulated_tool_calls[idx]

        if chunk.choices[0].finish_reason:
            yield StreamChunk(
                tool_calls=accumulated_tool_calls if accumulated_tool_calls else None,
                is_final=True
            )
```

**Reference:** See OpenAI conversation integration in HA core for the official pattern.

## Completed Features Summary

### ✅ Streaming Support (Feature 1)
**Status:** Fully implemented and tested
- Real-time streaming of LLM responses using HA's pattern
- Tool call accumulation during streaming
- Proper delta format (`{"content": "..."}` dicts)
- Configuration option to enable/disable streaming

### ✅ Conversation History Management (Feature 2)
**Status:** Fully implemented and tested
- **Global session architecture**: Single session across ALL HA conversations
- **Cross-conversation memory**: Session messages provide continuous context within timeout window
- **Timeout management**: Configurable 1-600 seconds (default 60s)
- **Fact persistence**: Three-tier fact learning system
  - `learn_fact` meta-tool: Immediate fact storage when user shares info
  - `query_facts` meta-tool: On-demand fact retrieval (token efficient)
  - Automatic extraction: Background extraction when session expires

**Bugs Fixed During Implementation:**
1. **Fact extraction format error**: `{}` in prompt interpreted as format placeholder → Fixed by escaping as `{{}}`
2. **query_facts category filtering bug**: Was checking if fact keys matched category name → Fixed by returning all facts (LLM filters)

### Configuration Options
All features can be configured via integration options:
- `enable_streaming` (bool): Enable/disable streaming responses
- `conversation_timeout` (int): Session timeout in seconds (1-600, default 60)
- `enable_fact_learning` (bool): Enable/disable fact learning system
- `auto_continue_listening` (bool): Enable/disable automatic listening after `?` (default: False)

### Testing Results
✅ Streaming with tool calls works correctly
✅ Cross-conversation memory within timeout window
✅ Fact learning and retrieval works immediately
✅ Automatic fact extraction on timeout
✅ All features work together without conflicts

### ✅ Voice Assistant Listening Control (Feature 3)
**Status:** Fully implemented and tested
- **Listening control**: Prevent auto-listening after responses ending with `?`
- **Configuration option**: `auto_continue_listening` (default: False)
- **LLM marker**: `[CONTINUE_LISTENING]` for explicit listening requests
- **Chunk buffering**: Prevents marker from being spoken even when split across chunks
- **Prompt instructions**: Automatically added when feature is enabled

**How It Works:**
- Default behavior: Voice assistant stops after response, even with `?`
- LLM can include `[CONTINUE_LISTENING]` marker to request listening
- Marker is removed from spoken response via chunk buffering
- Non-streaming: Response processed to replace final `?`
- Streaming: Chunk buffer holds partial markers until complete

**Critical Implementation Detail - Chunk Buffering:**
The marker is often split character-by-character across streaming chunks:
```
' [' → 'CONT' → 'INUE' → '_LIST' → 'EN' → 'ING' → ']'
```

Solution: Buffer chunks and check for partial marker prefixes
```python
def _buffer_might_contain_partial_marker(self, buffer: str) -> bool:
    # Check if buffer ends with any prefix: "[", "[C", "[CO", "[CON", etc.
    for i in range(1, len(marker)):
        if buffer.endswith(marker[:i]):
            return True  # HOLD - don't yield yet
    return False  # Safe to yield
```

**Buffering Logic:**
1. If marker complete in buffer → Remove and yield clean content
2. If buffer ends with partial marker → HOLD (don't yield)
3. If buffer safe (no partial marker) → Yield immediately
4. At stream end → Yield remaining buffer

This ensures marker NEVER reaches chat_log, preventing it from being spoken.

**Configuration:**
- `auto_continue_listening=False` (default): Controlled listening
- `auto_continue_listening=True`: Normal HA behavior (all `?` trigger listening)

**Ready for production use!** 🎉

### Additional Providers
Pattern to follow:
1. Create `llm/provider_name.py` inheriting from `BaseLLMProvider`
2. Implement `generate()` method
3. Add to factory in `llm/__init__.py`
4. Add provider constant to `const.py`
5. Update config flow to show provider in dropdown
