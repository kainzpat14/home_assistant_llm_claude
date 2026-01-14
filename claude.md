# Home Assistant Voice Assistant Plugin

## Project Overview

A Home Assistant custom integration that provides an LLM entity for voice assistant functionality. This plugin takes a unique approach by bypassing Home Assistant's intent system and directly interfacing with the Home Assistant API for home management tasks.

## Key Features

### 1. LLM Entity Provider
- Provides a conversation agent entity for Home Assistant
- Integrates with Home Assistant's voice assistant pipeline

### 2. Multi-LLM Support
- **Initial Implementation**: Groq API
- **Future Expansion**: Support for additional LLM providers including:
  - OpenAI API
  - Anthropic API
  - Local LLMs (Ollama, llama.cpp, etc.)
- Architecture designed with provider abstraction layer for easy extensibility

### 3. Direct API Approach (No Intents)
Unlike traditional Home Assistant voice integrations that rely on intents:
- Does **not** use Home Assistant's intent system
- Receives input from Home Assistant and outputs responses back
- Performs all home management activities via the Home Assistant REST/WebSocket API
- The LLM queries Home Assistant API directly to:
  - Discover available entities and services
  - Execute commands (turn on lights, set thermostats, etc.)
  - Query states

### 4. Token-Efficient Tool Usage
- Does **not** send complete tool lists with every request
- LLM can dynamically inquire about available tools/entities as needed
- Reduces token consumption significantly for simple queries
- Tools are fetched on-demand based on conversation context

### 5. Streaming Response Support
- Supports streaming LLM responses via Home Assistant's delta function
- Provides real-time response feedback to users
- Improves perceived latency for voice interactions

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Home Assistant                               │
│  ┌─────────────────┐    ┌──────────────────────────────────┐   │
│  │ Voice Pipeline  │───▶│  Voice Assistant Plugin          │   │
│  │ (STT/TTS)       │◀───│  (Conversation Agent)            │   │
│  └─────────────────┘    └──────────────┬───────────────────┘   │
│                                         │                        │
│                         ┌───────────────┴───────────────┐       │
│                         ▼                               ▼       │
│              ┌──────────────────┐           ┌──────────────┐   │
│              │  LLM Provider    │           │  HA API      │   │
│              │  Abstraction     │           │  Client      │   │
│              └────────┬─────────┘           └──────────────┘   │
│                       │                                         │
└───────────────────────┼─────────────────────────────────────────┘
                        │
         ┌──────────────┼──────────────┐
         ▼              ▼              ▼
    ┌─────────┐   ┌──────────┐   ┌──────────┐
    │  Groq   │   │  OpenAI  │   │  Local   │
    │  API    │   │  API     │   │  LLM     │
    └─────────┘   └──────────┘   └──────────┘
```

## Directory Structure

```
custom_components/
└── voice_assistant/
    ├── __init__.py          # Integration setup and entry point
    ├── manifest.json        # Integration metadata
    ├── config_flow.py       # Configuration UI flow
    ├── const.py             # Constants and configuration keys
    ├── conversation.py      # Conversation agent implementation
    ├── strings.json         # UI strings
    ├── translations/        # Localization files
    │   └── en.json
    ├── llm/                  # LLM provider implementations
    │   ├── __init__.py
    │   ├── base.py          # Abstract base class for LLM providers
    │   ├── groq.py          # Groq API implementation
    │   └── ...              # Future providers
    └── ha_client/           # Home Assistant API client
        ├── __init__.py
        └── client.py        # HA API wrapper for LLM tool calls
```

## Configuration Options

| Option | Description | Required |
|--------|-------------|----------|
| `provider` | LLM provider (groq, openai, local, etc.) | Yes |
| `api_key` | API key for cloud LLM providers | Provider-dependent |
| `model` | Model identifier | Yes |
| `base_url` | API endpoint (for local LLMs) | Provider-dependent |
| `temperature` | Response creativity (0.0 - 1.0) | No (default: 0.7) |
| `max_tokens` | Maximum response length | No (default: 1024) |

## Implementation Status

### Phase 1: Foundation ✅ COMPLETE
- [x] Project structure setup
- [x] Basic integration skeleton (`__init__.py`)
- [x] Configuration flow (`config_flow.py`)
- [x] LLM provider abstraction layer (`llm/base.py`)
- [x] HACS compatibility files

### Phase 2: Core LLM Integration ✅ COMPLETE
- [x] Groq API implementation (`llm/groq.py`)
- [x] Provider factory (`llm/__init__.py`)
- [x] API key validation in config flow
- [x] Non-streaming response generation

### Phase 3: Conversation Agent ✅ COMPLETE
- [x] Conversation agent entity (`conversation.py`)
- [x] Message history management via chat_log integration
- [x] Integration with Home Assistant's conversation system
- [x] System prompt override functionality

### Phase 4: Home Assistant API Integration ✅ COMPLETE
- [x] Dynamic tool discovery using Home Assistant's native LLM API (`llm_tools.py`)
- [x] `query_tools` meta-tool for on-demand tool loading
- [x] Tool execution via chat_log.async_add_assistant_content()
- [x] Tool schema conversion with voluptuous-openapi
- [x] Array field description enhancement for better LLM comprehension
- [x] Tool calling loop in conversation agent
- [x] Chat log integration for conversation history

### Phase 5: Advanced Features ✅ COMPLETE
- [x] Dynamic tool loading (query_tools meta-tool)
- [x] Conversation context management (chat_log integration)
- [x] Streaming response support
- [x] Conversation history with timeout
- [x] Fact learning and persistence
- [x] Voice assistant listening control
- [x] Music Assistant integration

### Phase 6: Additional Providers ⏳ NOT STARTED
- [ ] OpenAI provider
- [ ] Anthropic provider
- [ ] Local LLM support (Ollama)

## Current Development Status

✅ **Core features are complete and tested.**

### Completed Features
- Streaming response support with tool call handling
- Conversation history with global session and configurable timeout
- Fact learning system (learn_fact, query_facts, automatic extraction)
- Voice assistant listening control with `[CONTINUE_LISTENING]` marker
- Music Assistant integration with voice commands
- Debug logging, tool schema conversion, chat log integration

### Important Documentation
- **[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)** - Detailed implementation instructions for all features
- **[SESSION_NOTES.md](SESSION_NOTES.md)** - Critical implementation details, patterns, and lessons learned from development

## Next Steps

### Future Enhancements
1. **Additional LLM Providers** (Phase 6)
   - OpenAI API integration
   - Anthropic Claude API integration
   - Local LLM support (Ollama, llama.cpp)
2. **Polish & Release**
   - Comprehensive testing across different setups
   - User documentation and guides
   - HACS publication preparation

## Development Notes

### Home Assistant Integration Requirements
- Minimum HA version: 2024.1.0 (for latest conversation agent API)
- Python version: 3.11+
- Uses `async`/`await` patterns throughout

### API Interaction Pattern
The LLM interacts with Home Assistant via internal API calls:
1. User speaks command → STT → Text input
2. Plugin receives text via conversation agent
3. LLM processes request, may query HA API for context
4. LLM generates response/action
5. Plugin executes HA API calls if needed
6. Response streamed back via delta function → TTS → Audio output

### Token Efficiency Strategy
Instead of including all available tools in every request:
1. Start with minimal tool set (basic HA query tools)
2. LLM can request specific tool categories as needed
3. Tools loaded dynamically based on conversation context
4. Reduces base token cost for simple queries significantly
