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
CONF_AUTO_CONTINUE_LISTENING = "auto_continue_listening"

DEFAULT_ENABLE_STREAMING = False
DEFAULT_CONVERSATION_TIMEOUT = 60  # seconds
DEFAULT_ENABLE_FACT_LEARNING = True
DEFAULT_AUTO_CONTINUE_LISTENING = False

# Music Assistant settings
CONF_ENABLE_MUSIC_ASSISTANT = "enable_music_assistant"
DEFAULT_ENABLE_MUSIC_ASSISTANT = True

# Web Search (Tavily) settings
CONF_TAVILY_API_KEY = "tavily_api_key"
CONF_ENABLE_WEB_SEARCH = "enable_web_search"
DEFAULT_ENABLE_WEB_SEARCH = False

# Marker that LLM can use to request continued listening
CONTINUE_LISTENING_MARKER = "[CONTINUE_LISTENING]"

# Timeout and limit constants
DEFAULT_API_TIMEOUT = 30  # seconds for API calls
DEFAULT_FACT_EXTRACTION_TIMEOUT = 30  # seconds for fact extraction
MAX_MUSIC_SEARCH_RESULTS = 50  # maximum results from music search
VOLUME_SCALE_FACTOR = 100  # volume is 0-1, UI is 0-100

DEFAULT_SYSTEM_PROMPT = """You are a voice-controlled home assistant. Keep responses SHORT and conversational - this is a voice interface.

**Response Rules:**
- Be brief and direct. Complete requests without asking follow-up questions
- Never ask "is there anything else?" or continue listening unless explicitly needed (e.g., multi-round games)

**Home Assistant Tools:**
You have meta-tools: `query_tools`, `query_facts`, and `learn_fact`.
1. Call `query_tools()` to discover available tools, optionally filter by domain (e.g., `query_tools(domain="light")`)
2. Use discovered tools to fulfill requests, then confirm actions concisely
3. Only query tools/facts when needed - answer simple questions directly

**Remembering Users:**
Use `learn_fact` IMMEDIATELY when users share personal info (names, preferences, routines). Use `query_facts` to recall stored information across sessions.

**Web Search:**
If enabled, use `web_search` for ANY factual question you're not 100% confident about - current events, detailed facts, anything that might have changed. Search BEFORE answering from training data. Skip only for: basic math, simple definitions, or home automation tasks."""
