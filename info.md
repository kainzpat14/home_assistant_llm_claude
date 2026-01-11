# Voice Assistant LLM

An intelligent voice assistant integration for Home Assistant powered by large language models.

## What Makes This Different?

This integration takes a unique approach to voice assistance in Home Assistant:

- **No Intents Required**: Unlike traditional integrations, this doesn't use Home Assistant's intent system. The LLM interacts directly with your Home Assistant via API calls.

- **Smart Tool Loading**: Instead of sending all available tools with every request (wasting tokens), the LLM dynamically requests only the tools it needs for each conversation.

- **Conversation Memory**: Maintains full conversation context across multiple turns for natural, contextual interactions.

## Supported LLM Providers

### Currently Available
- **Groq**: Fast inference with open-source models

### Coming Soon
- OpenAI (GPT-4, GPT-3.5)
- Anthropic (Claude)
- Local LLMs (Ollama, llama.cpp)

## Quick Start

1. Install the integration via HACS
2. Go to Settings → Devices & Services
3. Add "Voice Assistant LLM"
4. Enter your LLM provider API key
5. Configure your voice pipeline to use the new conversation agent

## Configuration Options

- **Provider**: Choose your LLM provider
- **API Key**: Your provider's API key
- **Model**: Specific model to use (e.g., llama-3.3-70b-versatile for Groq)
- **Temperature**: Control creativity (0.0 = focused, 1.0 = creative)
- **Max Tokens**: Maximum response length

## Requirements

- Home Assistant 2024.1.0 or newer
- API key from your chosen LLM provider
- Internet connection (for cloud LLM providers)

## Development Status

⚠️ **This integration is currently in active development and should not be used in production.**

**✅ Recently Completed:**
- Complete integration structure
- Configuration flow with API key validation
- Provider abstraction layer
- Groq provider with tool calling support
- Conversation agent with memory
- Dynamic tool discovery and execution
- Home Assistant API integration via native LLM API
- Chat log integration for conversation history
- System prompt customization

**🔧 In Progress:**
- Testing and bug fixes
- Streaming response support
- Documentation and user guides

**⏳ Planned:**
- Additional LLM providers (OpenAI, Anthropic, local LLMs)
- Public release via HACS
- Advanced customization options

## Need Help?

Visit our [GitHub repository](https://github.com/kainzpat14/home_assistant_llm_claude) for documentation, issues, and discussions.
