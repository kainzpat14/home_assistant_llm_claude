# Home Assistant Claude Integration - Known Issues

## 1. Debug Logging Not Visible
**Status:** Open
**Description:** Debug logging is not visible in Home Assistant even though it has been enabled in the integration UI and in configuration.yaml.

## 2. JSON Error with Longer Conversations
**Status:** Open
**Description:** Longer conversations lead to a JSON error. Chat history is not correctly encoded.

## 3. Tool Calls Not Shown in Chat Log
**Status:** Open
**Description:** Tool calls are not displayed in the chat log interface.

## 4. System Prompt Override Needed
**Status:** Open
**Description:** Home Assistant provides a system prompt that is too long. We need to ignore it and provide our own system prompt instead.
