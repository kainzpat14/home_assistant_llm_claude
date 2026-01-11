# Home Assistant Claude Integration - Known Issues

## 1. Debug Logging Not Visible
**Status:** ✅ Resolved
**Description:** Debug logging was not visible in Home Assistant even though it had been enabled in the integration UI and in configuration.yaml.
**Solution:** Set explicit `_LOGGER.setLevel(logging.DEBUG)` in all module initializations and added INFO/DEBUG logs to setup/unload functions. This ensures debug capability is available regardless of Home Assistant's logging configuration system.

## 2. JSON Error with Longer Conversations
**Status:** 🔧 Fix Applied (Pending Testing)
**Description:** Longer conversations lead to a JSON error. Chat history is not correctly encoded.
**Error:** `Groq API error: Object of type Schema is not JSON serializable`
**Root Cause:** Home Assistant's tool parameters were voluptuous Schema objects that weren't being converted to JSON-serializable dicts before being passed to the Groq API.
**Proposed Solution:** Added `voluptuous-openapi` dependency and use its `convert()` function to properly serialize tool schemas in `_convert_tool_to_openai_format()`. This follows the pattern used in the existing ha-groq-cloud-api integration. Needs testing to confirm.

## 3. Tool Calls Not Shown in Chat Log
**Status:** Open
**Description:** Tool calls are not displayed in the chat log interface.

## 4. System Prompt Override Needed
**Status:** Open
**Description:** Home Assistant provides a system prompt that is too long. We need to ignore it and provide our own system prompt instead.
