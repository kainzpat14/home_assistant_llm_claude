# Additional Requirements

## Conversation History Management

### External History Storage
**Requirement:** Keep conversation history outside of Home Assistant's internal system.

**Details:**
- Conversation should persist independently of Home Assistant's chat_log
- Continue conversation across multiple interactions until a timeout occurs
- Timeout should be configurable (e.g., 5 minutes of inactivity)

### Fact Learning and Persistence
**Requirement:** When a conversation times out, extract and permanently save learned facts for future reference.

**Implementation Considerations:**
- Extract facts from conversation (e.g., user preferences, names, habits)
- Store facts in persistent storage (file, database, or Home Assistant storage helper)
- Retrieve and inject relevant facts into system prompt for future conversations
- Facts should survive integration reloads and Home Assistant restarts

**Example Facts to Store:**
- User's name and family members
- Preferences (favorite temperature, usual wake time, etc.)
- Device nicknames and locations
- Routine patterns

## Voice Assistant Listening Control

### Problem
Home Assistant's voice assistant keeps listening if the LLM response ends with a question mark (`?`), which may not always be desired.

### Requirement
Control whether the voice assistant continues listening by manipulating the response text sent to Home Assistant.

**Default Behavior:** Never keep listening unless explicitly requested by the LLM.

### Implementation Strategy
**Fake the Last Character:**
- Detect if LLM response ends with `?`
- Check if LLM explicitly wants to keep listening (via special marker, tool call, or metadata)
- If LLM does NOT want listening to continue:
  - Modify the response text before returning to Home Assistant
  - Add invisible/hidden character after `?`, or replace `?` with similar Unicode character
  - This prevents Home Assistant from triggering continued listening
- If LLM explicitly wants listening to continue:
  - Keep the `?` unchanged

**Possible Approaches:**
1. **System Prompt Instruction:** Instruct LLM to use a special marker like `[CONTINUE_LISTENING]` when it wants to keep the mic open
2. **Tool Call:** Create a meta-tool `set_listening(continue: bool)` that LLM can call
3. **Post-processing:** Strip trailing `?` by default, or add zero-width space after it

### Configuration
Add option in integration config:
- `auto_continue_listening`: Boolean (default: False)
- When False, always prevent continued listening
- When True, allow continued listening on `?`
