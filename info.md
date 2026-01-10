# Voice Assistant LLM

An intelligent voice assistant integration for Home Assistant powered by large language models.

## What Makes This Different?

This integration takes a unique approach to voice assistance in Home Assistant:

- **No Intents Required**: Unlike traditional integrations, this doesn't use Home Assistant's intent system. The LLM interacts directly with your Home Assistant via API calls.

- **Smart Tool Loading**: Instead of sending all available tools with every request (wasting tokens), the LLM dynamically requests only the tools it needs for each conversation.

- **Streaming Responses**: Get real-time responses as the LLM generates them, providing a more natural conversation experience.

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

This integration is in active development. Current features are foundational - we're working on implementing the core LLM and conversation agent functionality.

**Implemented:**
- Integration structure
- Configuration flow
- Provider abstraction

**In Progress:**
- Groq provider
- Conversation agent
- API tool system
- Streaming support

## Need Help?

Visit our [GitHub repository](https://github.com/kainzpat14/home_assistant_llm_claude) for documentation, issues, and discussions.
