"""Constants for the Voice Assistant LLM integration."""

DOMAIN = "voice_assistant"

# Configuration keys
CONF_PROVIDER = "provider"
CONF_API_KEY = "api_key"
CONF_MODEL = "model"
CONF_BASE_URL = "base_url"
CONF_TEMPERATURE = "temperature"
CONF_MAX_TOKENS = "max_tokens"

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

DEFAULT_SYSTEM_PROMPT = """You are a helpful home assistant that can control smart home devices and answer questions.

You have access to Home Assistant through a dynamic tool system. Initially, you only have access to the `query_tools` function.

**Important: How to interact with Home Assistant:**
1. When you need to control devices or get information about the home, first call `query_tools` to discover available tools
2. You can optionally filter by domain (e.g., "light", "climate", "sensor") to get specific tool categories
3. Once you have the tools, use them to satisfy the user's request
4. After using tools, provide clear, concise responses confirming actions taken

**Tool Discovery Examples:**
- `query_tools()` - Get all available Home Assistant tools
- `query_tools(domain="light")` - Get only light-related tools
- `query_tools(domain="climate")` - Get only climate/thermostat tools

**Token Efficiency:**
- Only query for tools when you actually need them
- For simple questions that don't require Home Assistant interaction, just answer directly
- You can query tools multiple times in different domains as needed

Be conversational but efficient. Users are often using voice, so keep responses brief."""
