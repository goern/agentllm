# AgentLLM - Agno Provider for LiteLLM

A custom LiteLLM provider that exposes [Agno](https://github.com/agno-agi/agno) agents through an OpenAI-compatible API, enabling seamless integration with Open WebUI and other OpenAI-compatible clients.

> **Note:** This project uses LiteLLM's official `CustomLLM` extension mechanism with dynamic registration via `custom_provider_map`. No forking or monkey patching required!

## Overview

This project implements a LiteLLM custom provider for Agno agents, allowing you to:

- Expose Agno agents as OpenAI-compatible chat models
- Use Agno agents with Open WebUI or any OpenAI-compatible client
- Run agents behind a LiteLLM proxy with authentication
- Switch between different agents using model names

## Architecture

```
[Client] -> [LiteLLM Proxy :8890] -> [Agno Provider] -> [Agno Agent] -> [LLM APIs]
```

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- Google Gemini API key (get from [Google AI Studio](https://aistudio.google.com/apikey))

## Installation

1. Clone this repository:
```bash
git clone <repo-url>
cd agentllm
```

2. Install dependencies with uv:
```bash
uv sync
```

3. Configure environment variables:
```bash
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY
```

## Project Structure

```
agentllm/
├── src/agentllm/
│   ├── provider/
│   │   └── transformation.py    # LiteLLM provider implementation
│   ├── agents/
│   │   └── release_manager.py   # Release manager Agno agent
│   └── proxy_config.yaml        # LiteLLM proxy configuration
├── tests/
│   └── test_provider.py         # TDD unit tests
├── noxfile.py                   # Task automation
└── pyproject.toml               # Project configuration
```

## Usage

### Running Tests

```bash
# Run unit tests
nox -s test

# Run integration tests
nox -s integration

# Run specific test
uv run pytest tests/test_custom_handler.py::TestAgnoCustomLLM -v
```

### Starting the Proxy

```bash
# Start LiteLLM proxy with Agno provider
nox -s proxy

# Or manually:
uv run litellm --config src/agentllm/proxy_config.yaml --port 8890
```

### Making Requests

Once the proxy is running, you can make OpenAI-compatible requests:

```bash
curl -X POST http://localhost:8890/v1/chat/completions \
  -H "Authorization: Bearer sk-agno-test-key-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agno/release-manager",
    "messages": [
      {"role": "user", "content": "Help me plan a release"}
    ]
  }'
```

### Available Models

**Agno Agents** (powered by Gemini 2.5 Flash):
- `agno/release-manager` - Release management assistant for software releases, changelogs, and version planning

**Direct Gemini 2.5 Models:**
- `gemini-2.5-pro` - Most capable model
- `gemini-2.5-flash` - Fast and efficient (used by Agno agents)

> **Note:** All models require a single `GEMINI_API_KEY` in your `.env` file. Get your API key from [Google AI Studio](https://aistudio.google.com/apikey).

## How It Works

This project uses LiteLLM's **official CustomLLM extension mechanism** - no forking or monkey patching required!

### Dynamic Registration

The Agno provider is registered via `custom_provider_map` in `proxy_config.yaml`:

```yaml
litellm_settings:
  custom_provider_map:
    - provider: "agno"
      custom_handler: custom_handler.agno_handler
```

This is the **recommended approach** from LiteLLM for adding custom providers without modifying the LiteLLM codebase.

### Implementation

The provider extends `litellm.CustomLLM` base class and implements:
- `completion()` - Synchronous completions
- `streaming()` - Streaming responses
- `acompletion()` - Async completions (future enhancement)

See [LiteLLM CustomLLM Docs](https://docs.litellm.ai/docs/providers/custom_llm_server) for details.

## Development Workflow

This project follows Test-Driven Development (TDD):

1. Write a failing test
2. Implement the feature
3. Run tests: `nox -s test`
4. Refactor if needed

### Adding New Agents

1. Create a new file in `src/agentllm/agents/` (e.g., `my_agent.py`):

```python
from pathlib import Path
from typing import Optional
from agno.agent import Agent
from agno.models.google import Gemini
from agno.db.sqlite import SqliteDb

# Use shared database
DB_PATH = Path("tmp/agno_sessions.db")
DB_PATH.parent.mkdir(exist_ok=True)
shared_db = SqliteDb(db_file=str(DB_PATH))

def create_my_agent(
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    **model_kwargs
) -> Agent:
    model_params = {"id": "gemini-2.5-flash"}
    if temperature is not None:
        model_params["temperature"] = temperature
    if max_tokens is not None:
        model_params["max_tokens"] = max_tokens
    model_params.update(model_kwargs)

    return Agent(
        name="my-agent",
        model=Gemini(**model_params),
        description="My custom agent",
        instructions=["Your instructions here"],
        markdown=True,
        db=shared_db,
        add_history_to_context=True,
        num_history_runs=10,
        read_chat_history=True,
    )

def get_agent(
    agent_name: str = "my-agent",
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    **model_kwargs
) -> Agent:
    if agent_name != "my-agent":
        raise KeyError(f"Agent '{agent_name}' not found.")
    return create_my_agent(temperature, max_tokens, **model_kwargs)
```

2. Update imports in `src/agentllm/custom_handler.py` to use your new agent module

3. Add to `proxy_config.yaml`:

```yaml
  - model_name: agno/my-agent
    litellm_params:
      model: agno/my-agent
      api_base: http://localhost/agno
      custom_llm_provider: agno
```

4. Restart the proxy

## Running with Open WebUI

The project supports two development modes to accommodate different workflows.

### Development Mode (Recommended)

**Use case:** Fast iteration on proxy/agent code with live debugging

Run the LiteLLM proxy locally and Open WebUI in a container:

```bash
# Terminal 1: Start local proxy with hot reload
nox -s proxy

# Terminal 2: Start Open WebUI (connects to local proxy)
nox -s dev_local_proxy
```

**How it works:**
- Proxy runs locally with instant code reloading
- Open WebUI runs in Docker and connects to proxy via `http://host.docker.internal:8890/v1`
- Works on all platforms (Mac, Linux, Windows)
- Configuration in `.env`: `LITELLM_PROXY_URL=http://host.docker.internal:8890/v1`

**Advantages:**
- ✨ Instant code reloading for proxy changes
- 🐛 Easy debugging with local debuggers
- 📊 Direct log access in terminal
- 💨 Lower resource usage

### Production Mode (Full Container Stack)

**Use case:** Testing the complete containerized setup

Run both services in containers:

```bash
# Start both services (foreground)
nox -s dev_full

# Or in background
nox -s dev_full -- -d
```

**How it works:**
- Both LiteLLM proxy and Open WebUI run in Docker
- Services communicate via internal Docker network
- Matches production deployment architecture

**Advantages:**
- 🏭 Production-like environment
- 🐳 Tests full Docker setup
- 👥 Easier for non-Python developers

### Quick Start

1. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env and add your GEMINI_API_KEY
   ```

2. **Choose your mode and start**:

   For development mode:
   ```bash
   # Terminal 1
   nox -s proxy
   # Terminal 2
   nox -s dev_local_proxy
   ```

   For production mode:
   ```bash
   nox -s dev_full
   ```

3. **Access Open WebUI**:
   - Open your browser to http://localhost:3000
   - Create an account (first user becomes admin)
   - The Agno models will be automatically available!

4. **Select an Agno agent**:
   - Click on the model selector
   - Choose `agno/release-manager`
   - Start chatting with your Agno agent!

### Useful Commands

```bash
# View logs from containers
nox -s dev_logs                    # All services
nox -s dev_logs -- litellm-proxy   # Specific service

# Stop containers (preserves data)
nox -s dev_stop

# Clean everything (including volumes)
nox -s dev_clean
```

### Configuration Details

The connection between Open WebUI and LiteLLM proxy is controlled by `LITELLM_PROXY_URL` in `.env`:

```bash
# Development mode (default)
LITELLM_PROXY_URL=http://host.docker.internal:8890/v1

# Production mode (set automatically by nox -s dev_full)
LITELLM_PROXY_URL=http://litellm-proxy:8890/v1
```

**No manual .env editing needed** - just use the appropriate `nox` command!

## Configuration

### Environment Variables

See `.env.example` for all configuration options. Key variables include:

- **GEMINI_API_KEY** - Required for all models (Agno agents and direct Gemini models). Get from [Google AI Studio](https://aistudio.google.com/apikey)
- **LITELLM_MASTER_KEY** - API key for accessing the LiteLLM proxy (default: `sk-agno-test-key-12345`)

### Proxy Configuration

Edit `src/agentllm/proxy_config.yaml` to:
- Add/remove agent models (Agno agents, Gemini, or other LLM providers)
- Change authentication settings
- Configure logging
- Adjust server settings

The proxy already includes configurations for:
- **Agno agents** (custom agents with specialized behaviors)
- **Google Gemini 2.5 models** (gemini-2.5-pro, gemini-2.5-flash)

## Provider Implementation

The Agno provider extends `litellm.CustomLLM` and implements:

- `completion()` - Synchronous completions with full agent execution
- `streaming()` - Synchronous streaming returning GenericStreamingChunk format
- `acompletion()` - Async completions using `agent.arun()`
- `astreaming()` - **True real-time streaming** using `agent.arun(stream=True)` ⚡
- Dynamic registration via `custom_provider_map` in config
- Parameter pass-through - `temperature` and `max_tokens` are passed to agent's model
- Conversation context - Previous messages are preserved in agent's session

### Streaming Support

LiteLLM's `CustomLLM` requires streaming methods to return `GenericStreamingChunk` dictionaries, **not** `ModelResponse` objects. The key format requirements:

**GenericStreamingChunk Format:**
```python
{
    "text": "content here",           # Use "text", not "content" or "delta"
    "finish_reason": "stop" or None,
    "index": 0,
    "is_finished": True or False,
    "tool_use": None,
    "usage": {"completion_tokens": 0, "prompt_tokens": 0, "total_tokens": 0}
}
```

**Sync streaming** (`streaming()`): Gets the complete response from `completion()` and returns it as a single GenericStreamingChunk.

**Async streaming** (`astreaming()`): Uses Agno's native `async for` streaming with `agent.arun(stream=True)` for true real-time token-by-token streaming, yielding each chunk in GenericStreamingChunk format.

**Common Pitfall:** Do NOT return `ModelResponse` objects from streaming methods - LiteLLM's streaming handler expects the `GenericStreamingChunk` dictionary format with a `text` field. Returning `ModelResponse` will cause `AttributeError: 'ModelResponse' object has no attribute 'text'`.

This approach requires **no modifications to LiteLLM** - it's a pure plugin using official extension APIs.

## Troubleshooting

### Tests Fail with "No module named 'agentllm'"

```bash
uv pip install -e .
```

### Agent Fails to Initialize

Ensure you have set `GEMINI_API_KEY` in your `.env` file. Get your key from [Google AI Studio](https://aistudio.google.com/apikey).

### Proxy Won't Start

Check that port 8890 is available:
```bash
lsof -i :8890
```

## Contributing

1. Write tests for new features
2. Follow TDD workflow
3. Run `nox -s lint` and `nox -s format`
4. Update documentation

## License

[Your License Here]

## References

- [Agno Framework](https://github.com/agno-agi/agno)
- [LiteLLM](https://github.com/BerriAI/litellm)
- [LiteLLM Provider Registration](https://docs.litellm.ai/docs/provider_registration/)
- [Open WebUI](https://github.com/open-webui/open-webui)
