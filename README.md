# Home Assistant Voice Assistant LLM

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub Release](https://img.shields.io/github/release/kainzpat14/home_assistant_llm_claude.svg)](https://github.com/kainzpat14/home_assistant_llm_claude/releases)

A custom Home Assistant integration that provides an LLM-powered conversation agent for voice assistants with direct API integration.

## Features

- **Direct Home Assistant API Integration**: Bypasses the traditional intent system for more flexible control
- **Token-Efficient**: Dynamically loads only required tools instead of sending complete lists with every request
- **Streaming Support**: Real-time response streaming via Home Assistant's delta function
- **Multi-LLM Support**: Extensible architecture supporting multiple LLM providers
  - Groq (initial implementation)
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

This integration is in early development. Currently implemented:
- Basic integration structure
- Configuration flow
- LLM provider abstraction layer

Coming soon:
- Groq provider implementation
- Conversation agent
- Home Assistant API client
- Streaming support

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Support

For issues and feature requests, please use the [GitHub Issues](https://github.com/kainzpat14/home_assistant_llm_claude/issues) page.
