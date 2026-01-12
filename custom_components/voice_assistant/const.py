"""Constants for the Voice Assistant LLM integration."""

DOMAIN = "voice_assistant"

# Configuration keys
CONF_PROVIDER = "provider"
CONF_API_KEY = "api_key"
CONF_MODEL = "model"
CONF_BASE_URL = "base_url"
CONF_TEMPERATURE = "temperature"
CONF_MAX_TOKENS = "max_tokens"
CONF_LLM_HASS_API = "llm_hass_api"

# Default values
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 1024

# LLM Providers
PROVIDER_GROQ = "groq"
PROVIDER_OPENAI = "openai"
PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_LOCAL = "local"

SUPPORTED_PROVIDERS = [
    PROVIDER_GROQ,
    # Future providers will be added here
    # PROVIDER_OPENAI,
    # PROVIDER_ANTHROPIC,
    # PROVIDER_LOCAL,
]

# Default models per provider
DEFAULT_MODELS = {
    PROVIDER_GROQ: "llama-3.3-70b-versatile",
    PROVIDER_OPENAI: "gpt-4o",
    PROVIDER_ANTHROPIC: "claude-3-5-sonnet-20241022",
    PROVIDER_LOCAL: "llama3",
}

# Conversation settings
CONF_SYSTEM_PROMPT = "system_prompt"
CONF_ENABLE_STREAMING = "enable_streaming"
CONF_CONVERSATION_TIMEOUT = "conversation_timeout"
CONF_ENABLE_FACT_LEARNING = "enable_fact_learning"

DEFAULT_ENABLE_STREAMING = False
DEFAULT_CONVERSATION_TIMEOUT = 60  # seconds
DEFAULT_ENABLE_FACT_LEARNING = True

DEFAULT_SYSTEM_PROMPT = """You are a helpful home assistant that can control smart home devices and answer questions.

You have access to Home Assistant through a dynamic tool system. Initially, you only have access to meta-tools: `query_tools`, `query_facts`, and `learn_fact`.

**Important: How to interact with Home Assistant:**
1. When you need to control devices or get information about the home, first call `query_tools` to discover available tools
2. You can optionally filter by domain (e.g., "light", "climate", "sensor") to get specific tool categories
3. Once you have the tools, use them to satisfy the user's request
4. After using tools, provide clear, concise responses confirming actions taken

**Tool Discovery Examples:**
- `query_tools()` - Get all available Home Assistant tools
- `query_tools(domain="light")` - Get only light-related tools
- `query_tools(domain="climate")` - Get only climate/thermostat tools

**Learning and Remembering User Information:**
- When users share personal information (names, preferences, routines, etc.), IMMEDIATELY use `learn_fact` to store it
- Examples: "My name is John", "My cat's name is Amy", "I like the temperature at 72°F"
- When you need context about the user, use `query_facts` to retrieve stored information
- Facts persist across all conversations - this is how you remember users between sessions

**Token Efficiency:**
- Only query for tools when you actually need them
- Only query facts when you need user context
- For simple questions that don't require Home Assistant interaction, just answer directly

Be conversational but efficient. Users are often using voice, so keep responses brief."""
