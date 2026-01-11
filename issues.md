# Home Assistant Claude Integration - Known Issues

## 1. Debug Logging Not Visible
**Status:** ✅ Resolved
**Description:** Debug logging was not visible in Home Assistant even though it had been enabled in the integration UI and in configuration.yaml.
**Solution:** Set explicit `_LOGGER.setLevel(logging.DEBUG)` in all module initializations and added INFO/DEBUG logs to setup/unload functions. This ensures debug capability is available regardless of Home Assistant's logging configuration system.

## 2. JSON Error with Longer Conversations
**Status:** Open
**Description:** Longer conversations lead to a JSON error. Chat history is not correctly encoded.
**Error:** `Groq API error: Object of type Schema is not JSON serializable`
**Additional Context:** This error only appears in conversations that use tools, suggesting the tool schema or tool response is being included in the conversation history in a way that cannot be serialized to JSON.

## 3. Tool Calls Not Shown in Chat Log
**Status:** Open
**Description:** Tool calls are not displayed in the chat log interface.

## 4. System Prompt Override Needed
**Status:** Open
**Description:** Home Assistant provides a system prompt that is too long. We need to ignore it and provide our own system prompt instead.
