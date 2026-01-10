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

## Implementation Phases

### Phase 1: Foundation (Completed)
- [x] Project structure setup
- [x] Basic integration skeleton (`__init__.py`)
- [x] Configuration flow (`config_flow.py`)
- [x] LLM provider abstraction layer (`llm/base.py`)
- [x] HACS compatibility files

### Phase 2: Core LLM Integration (In Progress)
**See:** `docs/implementation/01-groq-provider.md`
- [ ] Groq API implementation (`llm/groq.py`)
- [ ] Provider factory (`llm/factory.py`)
- [ ] API key validation in config flow

### Phase 3: Conversation Agent
**See:** `docs/implementation/02-conversation-agent.md`
- [ ] Conversation agent entity (`conversation.py`)
- [ ] Message history management
- [ ] Integration with voice pipeline

### Phase 4: Home Assistant API Integration
**See:** `docs/implementation/03-ha-api-client.md`
- [ ] HA API client wrapper (`ha_client/client.py`)
- [ ] Tool definitions (`ha_client/tools.py`)
- [ ] Entity discovery tools
- [ ] Service execution tools
- [ ] State query tools
- [ ] Tool calling loop in conversation agent

### Phase 5: Advanced Features
- [ ] Streaming response support
- [ ] Dynamic tool loading
- [ ] Conversation context management

### Phase 6: Additional Providers
- [ ] OpenAI provider
- [ ] Anthropic provider
- [ ] Local LLM support (Ollama)

## Implementation Plans

Detailed implementation plans are available in `docs/implementation/`:

| Order | File | Description |
|-------|------|-------------|
| 1 | `01-groq-provider.md` | Groq LLM provider with streaming support |
| 2 | `02-conversation-agent.md` | Home Assistant conversation agent |
| 3 | `03-ha-api-client.md` | HA API client and tool definitions |

**Instructions for Sonnet:** Follow the implementation plans in order. Each plan contains:
- Complete code for each file
- Step-by-step implementation instructions
- Testing guidance
- Dependencies on previous steps

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
