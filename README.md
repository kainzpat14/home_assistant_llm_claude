# Home Assistant Voice Assistant LLM

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub Release](https://img.shields.io/github/release/kainzpat14/home_assistant_llm_claude.svg)](https://github.com/kainzpat14/home_assistant_llm_claude/releases)

A custom Home Assistant integration that provides an LLM-powered conversation agent for voice assistants with direct API integration.

## Features

- **Direct Home Assistant API Integration**: Bypasses the traditional intent system for more flexible control
- **Token-Efficient**: Dynamically loads only required tools instead of sending complete lists with every request
- **Streaming Support**: Real-time response streaming via Home Assistant's delta function
- **Conversation Memory**: Global session with configurable timeout and cross-conversation context
- **Fact Learning**: Persistent fact storage - the assistant remembers user preferences, names, and routines
- **Voice Assistant Listening Control**: Control when the assistant continues listening after responses
- **Music Assistant Integration**: Voice control for Music Assistant - play music, control playback, transfer between rooms
- **Multi-LLM Support**: Extensible architecture supporting multiple LLM providers
  - Groq (implemented)
  - OpenAI (planned)
  - Anthropic (planned)
  - Local LLMs (planned)

## Why This Integration?

Unlike traditional Home Assistant voice integrations that rely on the intent system, this integration:
- Allows the LLM to query Home Assistant API directly for entity discovery
- Reduces token usage by fetching tools on-demand based on conversation context
- Provides more natural language understanding without predefined intents
- Supports streaming responses for better user experience

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant instance
2. Click on "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL: `https://github.com/kainzpat14/home_assistant_llm_claude`
6. Select category: "Integration"
7. Click "Add"
8. Find "Voice Assistant LLM" in the integration list and install it
9. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/voice_assistant` directory to your Home Assistant's `custom_components` directory
2. Restart Home Assistant

## Configuration

1. Go to Settings → Devices & Services
2. Click "+ ADD INTEGRATION"
3. Search for "Voice Assistant LLM"
4. Follow the configuration steps:
   - Select your LLM provider (currently Groq)
   - Enter your API key
   - Select the model
   - Configure temperature and max tokens (optional)

## Usage

After configuration, the integration will register as a conversation agent. You can:
1. Set it as the default conversation agent in your voice assistant pipeline
2. Use it in automations with the `conversation.process` service
3. Interact with it through the Home Assistant UI

## Requirements

- Home Assistant 2024.1.0 or newer
- API key for your chosen LLM provider

## Current Status

This integration has all core features implemented and tested:

### ✅ Completed Features
- **Core Integration**: Full integration structure, configuration flow, LLM provider abstraction
- **Groq Provider**: Complete implementation with tool calling and streaming support
- **Conversation Agent**: Full conversation handling with Home Assistant integration
- **Streaming Responses**: Real-time streaming via Home Assistant's delta function
- **Conversation History**: Global session with configurable timeout (1-600 seconds)
- **Fact Learning**: Three-tier fact system (learn_fact, query_facts, automatic extraction)
- **Voice Listening Control**: Configurable listening behavior after responses
- **Music Assistant**: Voice control for Music Assistant playback and queue management

### 🔧 Configuration Options
- `enable_streaming`: Enable/disable streaming responses
- `conversation_timeout`: Session timeout in seconds (default: 60)
- `enable_fact_learning`: Enable/disable fact learning system
- `auto_continue_listening`: Control listening behavior after questions
- `enable_music_assistant`: Enable/disable Music Assistant integration

### ⏳ Planned
- Additional LLM providers (OpenAI, Anthropic, local LLMs)

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Support

For issues and feature requests, please use the [GitHub Issues](https://github.com/kainzpat14/home_assistant_llm_claude/issues) page.
