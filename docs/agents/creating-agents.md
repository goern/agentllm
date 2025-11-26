# Creating Custom Agents

This guide walks you through creating custom Agno agents for AgentLLM, from simple agents to complex ones with tools and configuration.

## Table of Contents

- [Overview](#overview)
- [Simple Agent (No Tools)](#simple-agent-no-tools)
- [Agent with Tools](#agent-with-tools)
- [Agent with Configuration](#agent-with-configuration)
- [Testing Your Agent](#testing-your-agent)
- [Best Practices](#best-practices)

## Overview

Creating a custom agent involves five main steps:

1. **Create the agent configurator** - Extend `AgentConfigurator` and implement configuration logic
2. **Create the agent wrapper** - Extend `BaseAgentWrapper` and reference the configurator
3. **Create the agent factory** - Implement `AgentFactory` for plugin system registration
4. **Register via entry points** - Add entry point in `pyproject.toml` for auto-discovery
5. **Add to proxy config** - Register model in `proxy_config.yaml`
6. **Test the agent** - Verify via curl or OpenWebUI (agent will be auto-discovered!)

### Architecture Pattern

AgentLLM agents follow a **configurator + wrapper + factory pattern** with plugin-based discovery:

**1. AgentConfigurator** - Manages configuration and agent building:

```python
from agentllm.agents.base import AgentConfigurator, BaseToolkitConfig

class MyAgentConfigurator(AgentConfigurator):
    """Configuration management for MyAgent."""

    def _initialize_toolkit_configs(self) -> list[BaseToolkitConfig]:
        """Return list of toolkit configurations."""
        return []  # No toolkits, or [MyToolkitConfig(), ...]

    def _build_agent_instructions(self) -> list[str]:
        """Return agent instructions/system prompt."""
        return [
            "You are my custom agent.",
            "Your purpose is to...",
        ]

    def _get_agent_name(self) -> str:
        """Return agent identifier (e.g., 'my-agent')."""
        return "my-agent"

    def _get_agent_description(self) -> str:
        """Return agent description for users."""
        return "My custom agent for ..."
```

**2. BaseAgentWrapper** - Handles execution:

```python
from agentllm.agents.base import BaseAgentWrapper
from .my_agent_configurator import MyAgentConfigurator

class MyAgent(BaseAgentWrapper):
    """My custom agent implementation."""

    def _create_configurator(self, user_id, session_id, shared_db, **kwargs):
        """Create configurator instance for this agent."""
        return MyAgentConfigurator(
            user_id=user_id,
            session_id=session_id,
            shared_db=shared_db,
            **kwargs
        )
```

**3. AgentFactory** - Enables plugin system:

```python
from agentllm.agents.base import AgentFactory

class MyAgentFactory(AgentFactory):
    """Factory for creating MyAgent instances."""

    @staticmethod
    def create_agent(shared_db, token_storage, user_id, session_id=None,
                    temperature=None, max_tokens=None, **kwargs):
        return MyAgent(
            shared_db=shared_db,
            user_id=user_id,
            session_id=session_id,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )

    @staticmethod
    def get_metadata():
        return {
            "name": "my-agent",
            "description": "My custom agent",
            "mode": "chat",
            "requires_env": [],  # e.g., ["MY_API_KEY"]
        }
```

**Why this pattern?**
- **Separation of concerns**: Configurator handles config, wrapper handles execution
- **Plugin architecture**: Auto-discovery via entry points, no manual imports
- **Per-user isolation**: Each wrapper instance is tied to a specific user+session
- **Dependency injection**: Database and token storage passed explicitly (testable)
- **Reusable logic**: All agents share common functionality from base classes
- **Type safety**: Abstract methods enforce implementation contract
- **Installable agents**: Agents can be distributed as separate packages

## Simple Agent (No Tools)

Let's create a simple creative writing agent with no external tools or configuration requirements.

### Step 1: Create Agent Configurator

Create `src/agentllm/agents/writer_agent_configurator.py`:

```python
"""Creative writing agent configurator."""

from agentllm.agents.base import AgentConfigurator, BaseToolkitConfig


class WriterAgentConfigurator(AgentConfigurator):
    """Configuration management for Writer Agent."""

    def _initialize_toolkit_configs(self) -> list[BaseToolkitConfig]:
        """No toolkits needed for this simple agent."""
        return []

    def _build_agent_instructions(self) -> list[str]:
        """Return agent instructions."""
        return [
            "You are a creative writing assistant.",
            "Help users craft engaging stories, articles, and creative content.",
            "Provide constructive feedback on writing.",
            "Suggest plot ideas, character development, and narrative structures.",
            "Adapt your tone and style to match the user's needs.",
        ]

    def _get_agent_name(self) -> str:
        """Return agent name."""
        return "writer-agent"

    def _get_agent_description(self) -> str:
        """Return agent description."""
        return "Creative writing assistant for stories, articles, and content"
```

### Step 2: Create Agent Wrapper and Factory

Create `src/agentllm/agents/writer_agent.py`:

```python
"""Creative writing agent wrapper and factory."""

from agentllm.agents.base import BaseAgentWrapper, AgentFactory
from .writer_agent_configurator import WriterAgentConfigurator


class WriterAgent(BaseAgentWrapper):
    """Creative writing agent with no tools or required configuration."""

    def _create_configurator(self, user_id, session_id, shared_db, **kwargs):
        """Create Writer Agent configurator instance."""
        return WriterAgentConfigurator(
            user_id=user_id,
            session_id=session_id,
            shared_db=shared_db,
            **kwargs
        )


class WriterAgentFactory(AgentFactory):
    """Factory for creating Writer Agent instances."""

    @staticmethod
    def create_agent(shared_db, token_storage, user_id, session_id=None,
                    temperature=None, max_tokens=None, **kwargs):
        """Create a Writer Agent instance."""
        return WriterAgent(
            shared_db=shared_db,
            user_id=user_id,
            session_id=session_id,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )

    @staticmethod
    def get_metadata():
        """Get agent metadata."""
        return {
            "name": "writer-agent",
            "description": "Creative writing assistant",
            "mode": "chat",
            "requires_env": [],
        }
```

**Key Points:**
- Configurator handles all agent configuration logic
- Wrapper just delegates to configurator via `_create_configurator()`
- Factory enables plugin system with metadata
- No toolkits needed (empty list from configurator)
- All parameter handling is done by base classes

### Step 3: Register via Entry Points

Edit `pyproject.toml` to register the agent for auto-discovery:

```toml
[project.entry-points."agentllm.agents"]
# ... existing agents ...
writer-agent = "agentllm.agents.writer_agent:WriterAgentFactory"
```

**Key Points:**
- Entry point name (`writer-agent`) should match the agent name returned by `_get_agent_name()`
- Points to the factory class, not the wrapper
- No imports needed in `custom_handler.py` - automatic discovery!
- The factory is loaded and registered at runtime by `AgentRegistry`

### Step 4: Add to Proxy Config

Edit `proxy_config.yaml` and add model entry:

```yaml
model_list:
  # Existing models...

  # Creative Writing Agent
  - model_name: agno/writer-agent
    litellm_params:
      model: agno/writer-agent
      custom_llm_provider: agno
```

### Step 5: Test the Agent

```bash
# Restart proxy
nox -s dev_stop
nox -s dev_build

# Test with curl
curl -X POST http://localhost:9501/v1/chat/completions \
  -H "Authorization: Bearer sk-agno-test-key-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agno/writer-agent",
    "messages": [
      {"role": "user", "content": "Help me write a short story about a robot learning to paint"}
    ]
  }'
```

Or test via Open WebUI:
1. Open http://localhost:3000
2. Select `agno/writer-agent`
3. Start chatting!

## Agent with Tools

Now let's add tools to give agents capabilities. Tools in AgentLLM are organized into `Toolkit` classes.

### Example: Weather Agent with API Tool

**Step 1: Create the Toolkit**

Create `src/agentllm/tools/weather_toolkit.py`:

```python
"""Weather tools for fetching weather data."""

from agno.toolkit import Toolkit
from agno.tools import tool


class WeatherTools(Toolkit):
    """Tools for weather information."""

    def __init__(self, api_key: str):
        """Initialize weather tools.

        Args:
            api_key: OpenWeatherMap API key
        """
        super().__init__(name="weather_tools")
        self.api_key = api_key
        self.register(self.get_current_weather)
        self.register(self.get_forecast)

    @tool
    def get_current_weather(self, city: str) -> str:
        """Get current weather for a city.

        Args:
            city: Name of the city

        Returns:
            Current weather description
        """
        import requests

        url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={self.api_key}&units=metric"

        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()

            temp = data["main"]["temp"]
            description = data["weather"][0]["description"]

            return f"Current weather in {city}: {description}, {temp}°C"
        except Exception as e:
            return f"Error fetching weather: {str(e)}"

    @tool
    def get_forecast(self, city: str, days: int = 3) -> str:
        """Get weather forecast for a city.

        Args:
            city: Name of the city
            days: Number of days to forecast (1-5)

        Returns:
            Weather forecast
        """
        import requests

        url = f"https://api.openweathermap.org/data/2.5/forecast?q={city}&appid={self.api_key}&units=metric"

        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()

            # Process forecast data (simplified)
            forecasts = data["list"][:days * 8]  # 8 forecasts per day

            result = f"Weather forecast for {city}:\n"
            for forecast in forecasts[::8]:  # One per day
                date = forecast["dt_txt"].split()[0]
                temp = forecast["main"]["temp"]
                desc = forecast["weather"][0]["description"]
                result += f"- {date}: {desc}, {temp}°C\n"

            return result
        except Exception as e:
            return f"Error fetching forecast: {str(e)}"
```

**Step 2: Create Configurator with Tools**

Create `src/agentllm/agents/weather_agent_configurator.py`:

```python
"""Weather agent configurator with tools."""

import os
from agentllm.agents.base import AgentConfigurator, BaseToolkitConfig
from agentllm.tools.weather_toolkit import WeatherTools


class WeatherAgentConfigurator(AgentConfigurator):
    """Configuration management for Weather Agent."""

    def __init__(self, *args, **kwargs):
        """Initialize Weather Agent configurator."""
        # Get API key from environment
        self.api_key = os.getenv("OPENWEATHER_API_KEY")
        if not self.api_key:
            raise ValueError("OPENWEATHER_API_KEY environment variable not set")

        super().__init__(*args, **kwargs)

    def _initialize_toolkit_configs(self) -> list[BaseToolkitConfig]:
        """No user configuration needed - using shared API key."""
        return []

    def _build_agent_instructions(self) -> list[str]:
        """Return agent instructions."""
        return [
            "You are a weather assistant.",
            "Use the weather tools to provide current weather and forecasts.",
            "Always specify the city clearly when using tools.",
            "Provide helpful context and recommendations based on weather.",
        ]

    def _get_agent_name(self) -> str:
        """Return agent name."""
        return "weather-agent"

    def _get_agent_description(self) -> str:
        """Return agent description."""
        return "Weather assistant with real-time weather data"

    def _collect_toolkits(self) -> list:
        """Return tools for this agent (shared API key, no per-user config)."""
        # Override to provide toolkits directly (not from toolkit configs)
        return [WeatherTools(api_key=self.api_key)]
```

**Step 3: Create Agent Wrapper and Factory**

Create `src/agentllm/agents/weather_agent.py`:

```python
"""Weather agent wrapper and factory."""

from agentllm.agents.base import BaseAgentWrapper, AgentFactory
from .weather_agent_configurator import WeatherAgentConfigurator


class WeatherAgent(BaseAgentWrapper):
    """Weather agent with API tools."""

    def _create_configurator(self, user_id, session_id, shared_db, **kwargs):
        """Create Weather Agent configurator instance."""
        return WeatherAgentConfigurator(
            user_id=user_id,
            session_id=session_id,
            shared_db=shared_db,
            **kwargs
        )


class WeatherAgentFactory(AgentFactory):
    """Factory for creating Weather Agent instances."""

    @staticmethod
    def create_agent(shared_db, token_storage, user_id, session_id=None,
                    temperature=None, max_tokens=None, **kwargs):
        """Create a Weather Agent instance."""
        return WeatherAgent(
            shared_db=shared_db,
            user_id=user_id,
            session_id=session_id,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )

    @staticmethod
    def get_metadata():
        """Get agent metadata."""
        return {
            "name": "weather-agent",
            "description": "Weather assistant with real-time data",
            "mode": "chat",
            "requires_env": ["OPENWEATHER_API_KEY"],
        }
```

**Step 4: Configure Environment**

Add to `.env.secrets`:
```bash
OPENWEATHER_API_KEY=your_api_key_here
```

**Step 5: Register via Entry Points**

Edit `pyproject.toml`:
```toml
[project.entry-points."agentllm.agents"]
weather-agent = "agentllm.agents.weather_agent:WeatherAgentFactory"
```

**Step 6: Add to Proxy Config and Test**

Add to `proxy_config.yaml`, then test via curl or OpenWebUI.

**Key Points:**
- Configurator can override `_collect_toolkits()` to provide tools directly
- For shared services (no per-user credentials): Override `_collect_toolkits()` in configurator
- For per-user credentials (OAuth, API tokens): Use toolkit configs (see next section)
- Tools are instantiated once in configurator `__init__()` and reused

## Agent with Configuration

For agents that need user-specific configuration (OAuth tokens, API keys), use **toolkit configurations**. Toolkit configs handle extracting, storing, and retrieving per-user credentials.

### Architecture

Toolkit configurations enable agents to:
1. Prompt users for credentials when needed
2. Extract credentials from natural language messages
3. Store credentials securely per user
4. Provide configured toolkits to the agent

### Example: DemoAgent with Required Configuration

The **Demo Agent** (`src/agentllm/agents/demo_agent.py`) is the reference implementation. It demonstrates:

- **Required configuration**: `FavoriteColorConfig` (user must configure before using agent)
- **Simple toolkit**: `ColorTools` (no external APIs)
- **Configuration extraction**: Recognizes patterns like "my favorite color is blue"
- **Per-user isolation**: Each user has their own configuration

**Key Code Patterns:**

**Configurator** (handles configuration):
```python
class DemoAgentConfigurator(AgentConfigurator):
    """Configuration management for Demo Agent."""

    def __init__(self, user_id, session_id, shared_db, token_storage, ...):
        # Store token_storage for use in toolkit configs
        self._token_storage = token_storage
        super().__init__(user_id, session_id, shared_db, ...)

    def _initialize_toolkit_configs(self) -> list[BaseToolkitConfig]:
        """Register toolkit configurations."""
        return [
            FavoriteColorConfig(token_storage=self._token_storage),  # Required config
        ]

    # ... other abstract methods ...
```

**Wrapper** (handles execution):
```python
class DemoAgent(BaseAgentWrapper):
    """Demo agent with required configuration."""

    def __init__(self, shared_db, token_storage, user_id, session_id=None, ...):
        # Store token_storage to pass to configurator
        self._token_storage = token_storage
        super().__init__(shared_db, user_id, session_id, ...)

    def _create_configurator(self, user_id, session_id, shared_db, **kwargs):
        """Create configurator with token_storage."""
        return DemoAgentConfigurator(
            user_id=user_id,
            session_id=session_id,
            shared_db=shared_db,
            token_storage=self._token_storage,  # Pass token_storage
            **kwargs
        )
```

**How Configuration Works:**

1. **First message**: Configurator's `handle_configuration()` checks if `FavoriteColorConfig.is_configured(user_id)` returns True
2. **If not configured**: Configurator returns prompt from `get_config_prompt()`
3. **User sends config**: "My favorite color is blue"
4. **Extraction**: Configurator's `handle_configuration()` calls `extract_and_store_config()`, which extracts "blue" and stores it
5. **Toolkit creation**: Configurator's `build_agent()` calls `get_toolkit(user_id)` to get `ColorTools` configured with "blue"
6. **Agent continues**: Now that config is complete, wrapper executes the agent

**Key Benefit:** Configuration logic is cleanly separated in the configurator - the wrapper just delegates!

### Creating Your Own Toolkit Config

See these reference implementations:

- **Simple example**: `src/agentllm/agents/toolkit_configs/favorite_color_config.py` - In-memory configuration
- **OAuth example**: `src/agentllm/agents/toolkit_configs/gdrive_config.py` - Google Drive OAuth flow
- **API token example**: `src/agentllm/agents/toolkit_configs/jira_config.py` - Jira API token storage
- **Base class**: `src/agentllm/agents/toolkit_configs/base.py` - Abstract methods you must implement

Required methods to implement:
- `is_configured(user_id)` - Check if user has provided credentials
- `extract_and_store_config(message, user_id)` - Extract and save credentials from message
- `get_config_prompt()` - Return prompt requesting credentials
- `get_toolkit(user_id)` - Return configured toolkit instance
- `check_authorization_request(message)` - Detect if user is attempting to authorize

## Testing Your Agent

### Unit Tests

Create `tests/test_my_agent.py`:

```python
"""Tests for My Agent."""

import pytest
from agentllm.agents import my_agent


def test_agent_creation():
    """Test basic agent instantiation."""
    agent = my_agent.create_my_agent()
    assert agent.name == "my-agent"
    assert agent.description is not None


def test_agent_with_temperature():
    """Test temperature parameter."""
    agent = my_agent.create_my_agent(temperature=0.7)
    assert agent.model.temperature == 0.7


@pytest.mark.skipif(
    not os.getenv("GEMINI_API_KEY"),
    reason="Requires GEMINI_API_KEY"
)
def test_agent_execution():
    """Test actual agent execution."""
    agent = my_agent.create_my_agent()
    response = agent.run("Hello!")
    assert response.content is not None
```

Run tests:
```bash
nox -s test
```

### Integration Tests

Test via proxy:

```python
def test_agent_via_proxy():
    """Test agent through LiteLLM proxy."""
    import requests

    response = requests.post(
        "http://localhost:9501/v1/chat/completions",
        headers={
            "Authorization": "Bearer sk-agno-test-key-12345",
            "Content-Type": "application/json"
        },
        json={
            "model": "agno/my-agent",
            "messages": [{"role": "user", "content": "Test message"}]
        }
    )

    assert response.status_code == 200
    data = response.json()
    assert "choices" in data
```

### Manual Testing

```bash
# Start proxy
nox -s proxy

# Test with curl
curl -X POST http://localhost:9501/v1/chat/completions \
  -H "Authorization: Bearer sk-agno-test-key-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agno/my-agent",
    "messages": [{"role": "user", "content": "Hello!"}],
    "temperature": 0.7,
    "max_tokens": 500
  }'
```

## Best Practices

### Agent Design

1. **Clear purpose**: Each agent should have a well-defined role
2. **Focused tools**: Only include tools relevant to the agent's purpose
3. **Good instructions**: Be specific about behavior and capabilities
4. **Conversation memory**: Use `add_history_to_context=True` for coherent conversations

### Instructions

Good instructions are:
- **Specific**: "Provide code examples" not "be helpful"
- **Actionable**: "Always validate input" not "be careful"
- **Concise**: 3-5 clear directives

Example:
```python
instructions=[
    "You are a Python code review assistant.",
    "Identify bugs, security issues, and code smells.",
    "Suggest specific improvements with code examples.",
    "Explain the reasoning behind each recommendation.",
    "Focus on clarity, efficiency, and maintainability.",
]
```

### Parameter Handling

Parameters flow from API request → wrapper → configurator → Agno Agent:

1. Passed to your agent wrapper's `__init__()`
2. Wrapper passes them to configurator via `_create_configurator()`
3. Configurator stores and applies them when building the agent

**Your responsibility:** Just pass them through:

```python
class MyAgent(BaseAgentWrapper):
    def _create_configurator(self, user_id, session_id, shared_db, **kwargs):
        # kwargs includes temperature, max_tokens, model_kwargs
        return MyAgentConfigurator(
            user_id=user_id,
            session_id=session_id,
            shared_db=shared_db,
            **kwargs  # Passes temperature, max_tokens, etc.
        )
```

The configurator automatically applies these parameters when creating the Agno Agent instance.

**API usage example:**
```bash
curl -d '{
  "model": "agno/my-agent",
  "temperature": 0.3,     # Precise responses
  "max_tokens": 1000,     # Longer responses
  ...
}'
```

### Database and Sessions

`BaseAgentWrapper` requires `shared_db` via dependency injection:

```python
class MyAgent(BaseAgentWrapper):
    def __init__(self, shared_db: SqliteDb, ...):
        super().__init__(shared_db=shared_db, ...)
```

The `shared_db` is created and passed by `custom_handler.py`:
```python
# In custom_handler.py
DB_PATH = Path("tmp/agent-data/agno_sessions.db")
shared_db = SqliteDb(db_file=str(DB_PATH))

agent = MyAgent(shared_db=shared_db, ...)  # Injected here
```

**Benefits of this pattern:**
- No need to manage database in your agent code
- Testable (can pass mock database)
- Persistent conversation history across sessions
- Multi-turn conversations work correctly
- Sessions survive proxy restarts

### Security

1. **Validate environment variables:**
   ```python
   api_key = os.getenv("MY_API_KEY")
   if not api_key:
       raise ValueError("MY_API_KEY not set")
   ```

2. **Never log sensitive data:**
   ```python
   # Bad
   print(f"Using API key: {api_key}")

   # Good
   print("API key configured")
   ```

3. **Use per-user credentials** when possible (see toolkit config pattern)

### Performance

1. **Cache expensive resources:**
   ```python
   class MyAgent:
       def __init__(self):
           self._agents = {}  # Cache agents per user
   ```

2. **Lazy initialization:**
   ```python
   @property
   def expensive_resource(self):
       if not hasattr(self, "_resource"):
           self._resource = create_expensive_thing()
       return self._resource
   ```

## Example Agents

Study these reference implementations:

- **Simple agent**: See `writer-agent` example above
- **Agent with tools + config**: `src/agentllm/agents/demo_agent.py` and `src/agentllm/agents/demo_agent_configurator.py`
- **Production agent**: `src/agentllm/agents/release_manager.py` and `src/agentllm/agents/release_manager_configurator.py`
- **Toolkit config**: `src/agentllm/agents/toolkit_configs/favorite_color_config.py`
- **Base classes**: `src/agentllm/agents/base/` directory

## Troubleshooting

### Agent Not Found

**Error:** `Unknown agent model: agno/my-agent`

**Solution:**
1. Verify entry point registration in `pyproject.toml`
2. Check that factory class exists and is correctly named
3. Ensure factory implements `AgentFactory` interface
4. Restart proxy: `nox -s dev_stop && nox -s proxy`
5. Check logs for plugin discovery errors

### Tools Not Working

**Issue:** Agent doesn't use tools

**Checklist:**
1. Tools properly registered: `toolkit.register(self.my_tool)`
2. Tools added to agent: `Agent(tools=[my_toolkit], ...)`
3. Tool has `@tool` decorator
4. Tool has proper docstring (agent uses this to understand when to call it)

### Import Errors

**Error:** `ModuleNotFoundError: No module named 'agentllm'`

**Solution:**
```bash
uv pip install -e .
```

## Next Steps

- **[Demo Agent Source](../../src/agentllm/agents/demo_agent.py)** - Complete reference implementation with extensive comments
- **[Demo Agent Configurator](../../src/agentllm/agents/demo_agent_configurator.py)** - Example configurator implementation
- **[AGENTS.md](../../AGENTS.md)** - Architecture patterns, plugin system, and developer guide
- **[Base Classes](../../src/agentllm/agents/base/)** - Plugin system base classes
- **[.env.secrets.template](../../.env.secrets.template)** - All available configuration options

Happy agent building! 🤖
