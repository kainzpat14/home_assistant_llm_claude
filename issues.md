# Home Assistant Claude Integration - Known Issues

## 1. Debug Logging Not Visible
**Status:** ✅ Resolved
**Description:** Debug logging was not visible in Home Assistant even though it had been enabled in the integration UI and in configuration.yaml.
**Solution:** Set explicit `_LOGGER.setLevel(logging.DEBUG)` in all module initializations and added INFO/DEBUG logs to setup/unload functions. This ensures debug capability is available regardless of Home Assistant's logging configuration system.

## 2. JSON Error with Longer Conversations
**Status:** ✅ Resolved
**Description:** Longer conversations lead to a JSON error. Chat history is not correctly encoded.
**Error:** `Groq API error: Object of type Schema is not JSON serializable`
**Root Cause:** Home Assistant's tool parameters were voluptuous Schema objects that weren't being converted to JSON-serializable dicts before being passed to the Groq API.
**Solution:** Use `voluptuous-openapi`'s `convert()` function to properly serialize tool schemas in `_convert_tool_to_openai_format()`. This follows the pattern used in the existing ha-groq-cloud-api integration. voluptuous-openapi is a core HA dependency and doesn't need to be added to requirements.

## 3. Tool Calls Not Shown in Chat Log
**Status:** 🔧 Fix Applied (Pending Testing)
**Description:** Tool calls are not displayed in the chat log interface.
**Root Cause:** The integration was processing tool calls internally but never adding them to Home Assistant's chat_log, which the UI uses to display conversations.
**Proposed Solution:**
- Convert Groq's tool call format to Home Assistant's `llm.ToolInput` format with all required fields
- Create `AssistantContent` objects with tool_calls when the LLM requests tool execution
- Use `chat_log.async_add_assistant_content()` to add tool calls and execute them
- Iterate through the async generator to get `ToolResultContent` as tools execute
- Separate handling for query_tools (meta-tool) vs real HA tools
- Added comprehensive logging for debugging
Needs testing to confirm tool calls now appear in the UI.

## 4. System Prompt Override Needed
**Status:** Open
**Description:** Home Assistant provides a system prompt that is too long. We need to ignore it and provide our own system prompt instead.

## 5. LLM Not Receiving Conversation History
**Status:** Open
**Description:** The LLM does not seem to be provided with the conversation history from previous turns, causing it to lose context between messages in a conversation.

## 6. Tool Schema Validation Error
**Status:** 🔧 Fix Applied (Pending Testing)
**Description:** Groq API returns validation error when LLM tries to call Home Assistant tools.
**Error:** `Tool call validation failed: parameters for tool HassLightSet did not match schema: errors: ['/domain': expected array, but got string]`
**Root Cause:** Home Assistant's tool schemas define some fields (like `domain`) as arrays, but without descriptions the LLM doesn't know to use array syntax. The converted schema shows `'domain': {'type': 'array', 'items': {'type': 'string'}}` but LLM passes `"domain":"light"` instead of `"domain":["light"]`.
**Solution:** Post-process converted schemas to add helpful descriptions to array fields that don't have descriptions. For example: `"Array of domain values (use JSON array syntax: [domain1, domain2])"`. This guides the LLM to use correct array syntax.
**Example from logs:**
- Failed: `{"name": "HassLightSet", "arguments": {"name":"Licht Wohnzimmer","domain":"light","brightness":0}}`
- Should be: `{"name": "HassLightSet", "arguments": {"name":"Licht Wohnzimmer","domain":["light"],"brightness":0}}`
