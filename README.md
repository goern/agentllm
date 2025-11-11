# AgentLLM - Agno Provider for LiteLLM

A custom LiteLLM provider that exposes [Agno](https://github.com/agno-agi/agno) agents through an OpenAI-compatible API, enabling seamless integration with Open WebUI and other OpenAI-compatible clients.

> **Note:** This project uses LiteLLM's official `CustomLLM` extension mechanism with dynamic registration via `custom_provider_map`. No forking or monkey patching required!

## Quick Start

Get the full stack running in under 5 minutes:

**Prerequisites:** Python 3.11+, [uv](https://docs.astral.sh/uv/getting-started/installation/), [nox](https://nox.thea.codes/), [Podman](https://podman.io/), and a [Gemini API key](https://aistudio.google.com/apikey)

```bash
# 0. Install uv and nox (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh  # Install uv
uv tool install nox                               # Install nox

# 1. Clone and navigate
git clone https://github.com/durandom/agentllm
cd agentllm

# 2. Install dependencies
uv sync

# 3. Configure environment
cp .env.secrets.template .env.secrets
# Edit .env.secrets and add your GEMINI_API_KEY (get from https://aistudio.google.com/apikey)

# 4. Start everything (containerized)
nox -s dev_build  # First time: builds containers
# nox -s dev      # Subsequent starts: reuses existing images
```

**Access Open WebUI:** <http://localhost:3000>

**Available Agents:**
- `agno/release-manager` - RHDH release management assistant
- `agno/demo-agent` - Example agent with color tools

## Architecture

```mermaid
flowchart LR;
    Client-->LiteLLM_Proxy;
    LiteLLM_Proxy-->Agno_Provider;
    Agno_Provider-->Agno_Agent;
    Agno_Agent-->LLM_APIs;
```

**Components:**
- **LiteLLM Proxy**: OpenAI-compatible API gateway with authentication
- **Agno Provider**: Custom LiteLLM handler (`litellm.CustomLLM`) for Agno agents
- **Agno Agents**: Intelligent agents with tools (Google Drive, Jira, etc.)
- **Gemini API**: Underlying LLM (Google Gemini 2.5 Flash)

The provider uses LiteLLM's official `custom_provider_map` for dynamic registration:

```yaml
litellm_settings:
  custom_provider_map:
    - provider: "agno"
      custom_handler: custom_handler.agno_handler
```

See [CLAUDE.md](CLAUDE.md) for detailed architecture documentation.

## Development

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager ([install](https://docs.astral.sh/uv/getting-started/installation/): `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- [nox](https://nox.thea.codes/) task automation ([install](https://nox.thea.codes/en/stable/tutorial.html#installation): `uv tool install nox`)
- [Podman](https://podman.io/) ([install](https://podman.io/getting-started/installation))
- Google Gemini API key ([get here](https://aistudio.google.com/apikey))

### Development Modes

**Choose based on your workflow:**

| Mode | Command | Use When | Proxy | OpenWebUI |
|------|---------|----------|-------|-----------|
| **Full Container** | `nox -s dev` or `nox -s dev_build` | Just testing agents | Container | Container |
| **Development** | Terminal 1: `nox -s proxy`<br>Terminal 2: `nox -s dev_local_proxy` | Modifying agent code | Local (hot reload) | Container |

**Note:** Use `nox -s dev` for quick starts (reuses existing images), or `nox -s dev_build` when you need to rebuild (after code changes).

**Port reference:**
- Open WebUI: <http://localhost:3000> (external) → container port 8080 (internal)
- LiteLLM Proxy: <http://localhost:8890>

### Common Commands

```bash
# Testing
nox -s test                                    # Run unit tests
nox -s integration                             # Run integration tests (requires running proxy)
uv run pytest tests/test_custom_handler.py -v  # Run specific test

# Development
nox -s proxy                                   # Start LiteLLM proxy locally
nox -s dev                                     # Start full containerized stack (no rebuild)
nox -s dev_build                               # Build and start (forces rebuild)
nox -s dev_logs                                # View container logs
nox -s dev_stop                                # Stop containers (preserve data)
nox -s dev_clean                               # Clean everything (including volumes)

# Code quality
nox -s format                                  # Format code
make lint                                      # Run linting
```

### Testing the Proxy

```bash
# Start proxy
nox -s proxy

# Make a request
curl -X POST http://localhost:8890/v1/chat/completions \
  -H "Authorization: Bearer sk-agno-test-key-12345" \
  -H "Content-Type: application/json" \
  -H "X-OpenWebUI-User-Id: test-user" \
  -d '{
    "model": "agno/demo-agent",
    "messages": [{"role": "user", "content": "Hey"}]
  }'
```

## Available Models

**Agno Agents** (powered by Gemini 2.5 Flash):
- `agno/release-manager` - RHDH release management assistant (Google Drive, Jira integration)
- `agno/demo-agent` - Example agent with color tools (educational reference)

**Direct Gemini Models:**
- `gemini-2.5-pro` - Most capable model
- `gemini-2.5-flash` - Fast and efficient (used by Agno agents)

List models from running proxy:
```bash
curl -X GET http://localhost:8890/v1/models \
  -H "Authorization: Bearer sk-agno-test-key-12345"
```

> **Note:** All models require `GEMINI_API_KEY` in your `.env.secrets` file.

## Adding New Agents

See [docs/agents/creating-agents.md](docs/agents/creating-agents.md) for a complete guide. Quick overview:

1. **Create agent file** in `src/agentllm/agents/my_agent.py`:

```python
from agno.agent import Agent
from agno.models.google import Gemini
from agentllm.agents.release_manager import shared_db

def create_my_agent(temperature=None, max_tokens=None, **kwargs):
    model_params = {"id": "gemini-2.5-flash"}
    if temperature is not None:
        model_params["temperature"] = temperature
    if max_tokens is not None:
        model_params["max_tokens"] = max_tokens

    return Agent(
        name="my-agent",
        model=Gemini(**model_params),
        description="My custom agent",
        instructions=["Your instructions here"],
        markdown=True,
        db=shared_db,                    # Shared session database
        add_history_to_context=True,     # Enable conversation memory
        num_history_runs=10,
        read_chat_history=True,
    )

def get_agent(agent_name="my-agent", temperature=None, max_tokens=None, **kwargs):
    if agent_name != "my-agent":
        raise KeyError(f"Agent '{agent_name}' not found.")
    return create_my_agent(temperature, max_tokens, **kwargs)
```

2. **Register agent** in `src/agentllm/custom_handler.py` (import your module)

3. **Add to proxy config** in `proxy_config.yaml`:

```yaml
- model_name: agno/my-agent
  litellm_params:
    model: agno/my-agent
    custom_llm_provider: agno
```

4. **Restart proxy**: `nox -s proxy`

## Configuration

### Environment Variables

Required:
- `GEMINI_API_KEY` - Google Gemini API key ([get here](https://aistudio.google.com/apikey))
- `LITELLM_MASTER_KEY` - Proxy API key (default: `sk-agno-test-key-12345`)

Optional:
- `OPENAI_API_BASE_URL` - LiteLLM proxy URL for Open WebUI
  - Development: `http://host.docker.internal:8890/v1` (default)
  - Production: `http://litellm-proxy:8890/v1`
- `GDRIVE_CLIENT_ID`, `GDRIVE_CLIENT_SECRET` - For Google Drive integration
- `RELEASE_MANAGER_SYSTEM_PROMPT_GDRIVE_URL` - Extended system prompt URL

See `.env.secrets.template` for all available configuration options.

### Proxy Configuration

Edit `proxy_config.yaml` to:
- Add/remove models (Agno agents, Gemini, or other LLM providers)
- Configure authentication
- Adjust logging and server settings

## Key Features

### LiteLLM Custom Provider

The Agno provider extends `litellm.CustomLLM` and implements:

- `completion()` - Synchronous completions with full agent execution
- `streaming()` - Synchronous streaming (GenericStreamingChunk format)
- `acompletion()` - Async completions using `agent.arun()`
- `astreaming()` - True real-time streaming with `agent.arun(stream=True)` ⚡

**Key Benefits:**
- No LiteLLM modifications required
- Parameter pass-through (`temperature`, `max_tokens` → agent model)
- Conversation context preserved in agent sessions
- Per-user agent isolation

### Agent Wrapper Pattern

Agents use a wrapper pattern (see `ReleaseManager` in `src/agentllm/agents/release_manager.py`):

- **Toolkit Configuration**: OAuth flows for Google Drive, API tokens for Jira
- **Per-user Isolation**: Separate agents and credentials per user
- **Configuration Management**: Extract credentials from messages, prompt when missing
- **Session Memory**: SQLite-backed conversation history

### Streaming Support

LiteLLM's `CustomLLM` requires **GenericStreamingChunk format**:

```python
{
    "text": "content here",           # Use "text", not "content"
    "finish_reason": "stop" or None,
    "index": 0,
    "is_finished": True or False,
    "tool_use": None,
    "usage": {...}
}
```

**Async streaming** provides true real-time token-by-token streaming using Agno's native `async for` with `agent.arun(stream=True)`.

## Project Structure

```
agentllm/
├── src/agentllm/
│   ├── custom_handler.py              # LiteLLM CustomLLM implementation
│   ├── proxy_config.yaml              # LiteLLM proxy configuration
│   ├── agents/
│   │   ├── release_manager.py         # ReleaseManager wrapper class
│   │   ├── demo_agent.py              # Demo agent (example)
│   │   └── toolkit_configs/
│   │       ├── base.py                # Abstract toolkit config base
│   │       ├── gdrive_config.py       # Google Drive OAuth
│   │       └── jira_config.py         # Jira API token
│   ├── tools/
│   │   ├── gdrive_toolkit.py          # Google Drive tools
│   │   ├── jira_toolkit.py            # Jira tools
│   │   └── color_toolkit.py           # Demo color tools
│   └── db/
│       └── token_storage.py           # SQLite credential storage
├── tests/
│   ├── test_custom_handler.py         # Provider tests
│   ├── test_release_manager.py        # ReleaseManager tests
│   └── test_demo_agent.py             # Demo agent tests
├── docs/
│   ├── agents/
│   │   └── creating-agents.md         # Complete agent creation guide
│   └── templates/                     # Documentation templates
├── noxfile.py                         # Task automation
├── proxy_config.yaml                  # Proxy config (symlink to src/)
└── CLAUDE.md                          # Architecture & developer guide
```

## Documentation

- **[Creating Agents](docs/agents/creating-agents.md)** - Complete guide to building custom agents with tools and configuration
- **[CLAUDE.md](CLAUDE.md)** - Complete architecture and development reference for contributors

## Troubleshooting

### Tests Fail with "No module named 'agentllm'"

```bash
uv pip install -e .
```

### Agent Fails to Initialize

Ensure `GEMINI_API_KEY` is set in `.env.secrets`. Get your key from [Google AI Studio](https://aistudio.google.com/apikey).

### Proxy Won't Start

Check that port 8890 is available:

```bash
lsof -i :8890
```

### Can't Access Open WebUI

- Verify container is running: `podman ps`
- Check port mapping: Should see `0.0.0.0:3000->8080/tcp`
- Try http://localhost:3000 (external port, not 8080)
- Check container logs: `nox -s dev_logs`

## Contributing

1. Write tests for new features (TDD workflow)
2. Run tests: `nox -s test`
3. Format code: `nox -s format`
4. Run linting: `make lint`
5. Update documentation

## License

GPL-3.0-only

## References

- [Agno Framework](https://github.com/agno-agi/agno)
- [LiteLLM](https://github.com/BerriAI/litellm)
- [LiteLLM CustomLLM Docs](https://docs.litellm.ai/docs/providers/custom_llm_server)
- [Open WebUI](https://github.com/open-webui/open-webui)
