# AGENTS.md

This file provides guidance to Claude Code when working with this repository.

## Overview

AgentLLM: LiteLLM custom provider exposing Agno agents via OpenAI-compatible API.

Architecture: `[Client] -> [LiteLLM Proxy :9501 (external) / :8890 (internal)] -> [Agno Provider] -> [Agno Agent] -> [Gemini API]`

## Common Commands

```bash
# Testing
pytest tests/                                  # Run all tests
pytest tests/test_custom_handler.py -v         # Specific test (-v auto-enables AGNO_DEBUG)
pytest tests/ -v -s                            # Verbose + show output (AGNO_DEBUG=true)

# Development (most common)
just dev                                       # Full container stack with hot reload
just dev-restart                               # Restart after code changes
just dev-logs                                  # View logs

# Code quality
just format                                    # Format code
just lint                                      # Run linting
```

## Critical Architecture Patterns

### Plugin System (NEW!)

AgentLLM now supports a **plugin-based architecture** for agents:

**AgentFactory Pattern:**
- Each agent implements an `AgentFactory` class
- Factories are registered via Python entry points in `pyproject.toml`
- Automatic discovery via `AgentRegistry.discover_agents()`

**Entry Point Registration:**
```toml
[project.entry-points."agentllm.agents"]
my-agent = "agentllm.agents.my_agent:MyAgentFactory"
```

**Benefits:**
- Agents as installable packages (separate repos possible)
- Auto-discovery at runtime (no manual imports needed)
- Metadata system for agent capabilities
- Clean separation of concerns

### Configurator Pattern (NEW!)

**AgentConfigurator** separates configuration management from agent execution:

**Responsibilities:**
- Configuration conversation (OAuth flows, token extraction)
- Toolkit management and collection
- Agent building with proper parameters
- Bound to user_id/session_id at construction

**BaseAgentWrapper** handles execution:
- Delegates to configurator for config management
- Provides run/arun interface
- Manages agent caching
- Handles streaming

**Key Classes:**
```python
from agentllm.agents.base import (
    AgentFactory,          # Factory for agent creation
    AgentRegistry,         # Plugin discovery
    AgentConfigurator,     # Configuration management
    BaseAgentWrapper,      # Execution interface
    BaseToolkitConfig,     # Toolkit configuration
)
```

### Custom Handler Path Resolution (GOTCHA!)

LiteLLM uses **file-based resolution**, not Python imports:

```
project_root/
├── proxy_config.yaml          # LiteLLM loads from here
├── custom_handler.py           # Stub that imports from src/
└── src/agentllm/
    └── custom_handler.py       # Actual implementation
```

**Why:** `custom_handler.agno_handler` in config → LiteLLM looks for `./custom_handler.py` → stub imports from `agentllm.custom_handler`

### Generic Token Storage (NEW!)

**No more modifying TokenStorage for new agents!** Use the generic token API:

```python
# Store any token type
token_storage.upsert_token(
    "my-service",
    user_id,
    api_key="key-123",
    api_secret="secret-456",
    endpoint="https://api.example.com"
)

# Retrieve any token type
token_data = token_storage.get_token("my-service", user_id)
# Returns: {"api_key": "key-123", "api_secret": "secret-456", "endpoint": "..."}

# Delete any token type
token_storage.delete_token("my-service", user_id)
```

**Adding a new token type** (just register it once, no code changes to TokenStorage):

1. Define SQLAlchemy model in `token_storage.py`:
   ```python
   class MyServiceToken(Base):
       __tablename__ = "my_service_tokens"
       id = Column(Integer, primary_key=True, autoincrement=True)
       user_id = Column(String, nullable=False, unique=True, index=True)
       api_key = Column(String, nullable=False)
       api_secret = Column(String, nullable=False)
       endpoint = Column(String, nullable=False)
       created_at = Column(DateTime, default=datetime.utcnow)
       updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
   ```

2. Register in `TokenStorage._initialize_registry()`:
   ```python
   registry.register(
       "my-service",
       TokenTypeConfig(
           model=MyServiceToken,
           encrypted_fields=["api_key", "api_secret"],  # Auto-encrypted!
       ),
   )
   ```

That's it! Now use `upsert_token("my-service", ...)` everywhere. No need for `upsert_myservice_token()` methods.

### Toolkit Configuration System

Base class: `BaseToolkitConfig` (`src/agentllm/agents/base/toolkit_config.py`)

Key methods:
- `is_configured(user_id)` - Check if toolkit is ready
- `extract_and_store_config(message, user_id)` - Parse and save credentials
- `get_config_prompt(user_id)` - Return prompt for missing config
- `get_toolkit(user_id)` - Return configured toolkit instance
- `is_required()` - Required toolkits prompt immediately, optional toolkits only when mentioned
- `check_authorization_request(message, user_id)` - Detect optional toolkit requests

#### Customizing Jira Tools Per Agent

`JiraConfig` allows each agent to specify which Jira tools to enable:

```python
# Default: all read tools enabled, write tools disabled
jira_config = JiraConfig(token_storage=self._token_storage)

# Custom: only enable specific tools your agent needs
jira_config = JiraConfig(
    token_storage=self._token_storage,
    get_fix_versions=True,       # For finding release versions
    get_issues_stats=True,        # For statistics/breakdowns
    get_issues_summary=True,      # For listing issues
    get_issues_detailed=False,    # Disable if not needed
    update_issue=True,            # Enable if agent needs to update issues
)
```

**Available Jira Tools:**
- `get_issue` - Get single issue with full details
- `get_issues_detailed` - Get issues with custom fields
- `get_issues_stats` - Get statistics breakdown (type/status/priority)
- `get_issues_summary` - Get basic issue list (key/summary/status)
- `get_fix_versions` - Get unique fix version names
- `add_comment` - Add comments to issues (write)
- `create_issue` - Create new issues (write)
- `extract_sprint_info` - Extract sprint ID/name from issue
- `get_sprint_metrics` - Get sprint metrics
- `update_issue` - Update issue fields (write)

### Streaming Format (CRITICAL!)

LiteLLM `CustomLLM` requires **GenericStreamingChunk**, NOT `ModelResponse`:

```python
{
    "text": "content",              # "text" not "content"!
    "finish_reason": "stop" or None,
    "is_finished": True or False,
    ...
}
```

### Knowledge Management System (RAG)

AgentLLM supports per-agent knowledge bases via **Retrieval-Augmented Generation (RAG)**. Each agent can have its own vector database and document collection for enhanced context.

**Quick Start**: Override `_get_knowledge_config()` in your agent configurator:

```python
def _get_knowledge_config(self) -> dict[str, Any] | None:
    return {
        "knowledge_path": "examples/my_knowledge",  # Path to MD/PDF/CSV files
        "table_name": "my_agent_knowledge"          # LanceDB table name
    }
```

That's it! Knowledge loading, indexing, and retrieval are handled automatically.

**Key Features**:
- Per-agent knowledge bases (no sharing between agent types)
- Lazy loading with persistence (fast startup, cached after first index)
- Hybrid search (vector + keyword)
- Optional (return `None` to disable)

📖 **See [docs/knowledge-management.md](../docs/knowledge-management.md) for complete documentation**

## Adding New Agents

### Modern Approach (Plugin System)

1. **Create AgentConfigurator** (`src/agentllm/agents/my_agent_configurator.py`):
   ```python
   from agentllm.agents.base import AgentConfigurator, BaseToolkitConfig

   class MyAgentConfigurator(AgentConfigurator):
       def _initialize_toolkit_configs(self) -> list[BaseToolkitConfig]:
           return []  # Add toolkit configs here

       def _build_agent_instructions(self) -> list[str]:
           return ["You are my agent.", "Your purpose is..."]

       def _get_agent_name(self) -> str:
           return "my-agent"

       def _get_agent_description(self) -> str:
           return "My agent description"

       def _get_knowledge_config(self) -> dict[str, Any] | None:
           """Override to enable RAG knowledge base (optional)."""
           return {
               "knowledge_path": "examples/my_agent_knowledge",
               "table_name": "my_agent_knowledge"
           }
           # Return None to disable knowledge for this agent
   ```

2. **Create BaseAgentWrapper** (`src/agentllm/agents/my_agent.py`):
   ```python
   from agentllm.agents.base import BaseAgentWrapper
   from .my_agent_configurator import MyAgentConfigurator

   class MyAgent(BaseAgentWrapper):
       def _create_configurator(self, user_id, session_id, shared_db, **kwargs):
           return MyAgentConfigurator(
               user_id=user_id,
               session_id=session_id,
               shared_db=shared_db,
               **kwargs
           )
   ```

3. **Create AgentFactory** (in same file):
   ```python
   from agentllm.agents.base import AgentFactory

   class MyAgentFactory(AgentFactory):
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
               "description": "My agent description",
               "mode": "chat",
               "requires_env": ["SOME_API_KEY"],
           }
   ```

4. **Register in `pyproject.toml`**:
   ```toml
   [project.entry-points."agentllm.agents"]
   my-agent = "agentllm.agents.my_agent:MyAgentFactory"
   ```

5. **Add to `proxy_config.yaml`**:
   ```yaml
   - model_name: agno/my-agent
     litellm_params:
       model: agno/my-agent
       custom_llm_provider: agno
   ```

6. **The agent will be auto-discovered** by `AgentRegistry` at runtime!

### Legacy Approach (Direct Import)

1. Create `src/agentllm/agents/my_agent.py`:
   - Follow wrapper pattern (see `demo_agent.py` for reference)
   - Use `shared_db` for session memory
   - Pass through `temperature` and `max_tokens` to model

2. Import in `src/agentllm/custom_handler.py`

3. Add to `proxy_config.yaml`:
   ```yaml
   - model_name: agno/my-agent
     litellm_params:
       model: agno/my-agent
       custom_llm_provider: agno
   ```

## Available Agents

### GitHub PR Prioritization (`agno/github-pr-prioritization`)

**Purpose**: Intelligent PR review queue management using multi-factor prioritization.

**Setup**:
1. Create GitHub personal access token:
   - Go to https://github.com/settings/tokens
   - Choose either:
     - **Fine-grained token** (recommended): Click "Generate new token (fine-grained)"
       - Select repository access and permissions
       - Token format: `github_pat_...`
     - **Classic token**: Click "Generate new token (classic)"
       - Select `repo` scope (full control of private repositories)
       - Token format: `ghp_...`
   - Copy the token
2. In chat: "My GitHub token is YOUR_TOKEN_HERE"
3. Agent validates and stores token securely

**Usage Examples**:
- "Show review queue for facebook/react"
- "What should I review next in owner/repo?"
- "Prioritize PRs in microsoft/vscode"
- "Analyze PR #12345 in owner/repo"
- "Team review velocity for the last 7 days"

**Prioritization Algorithm**:

Multi-factor scoring (0-80 scale) with weighted factors:
- **Age (25 pts)**: Older PRs get higher priority (capped at 7 days)
- **Size (20 pts)**: Smaller PRs score higher (penalized after 100 lines)
- **Activity (15 pts)**: Comments and review activity indicate importance
- **Labels (10 pts)**: urgent/hotfix/blocking/critical labels boost priority
- **Author (10 pts)**: Base score for all contributors

**Priority Tiers**:
- **CRITICAL (65-80)**: Hotfixes, urgent, blocking issues
- **HIGH (50-64)**: Aged PRs, active discussion
- **MEDIUM (35-49)**: Standard PRs ready for review
- **LOW (0-34)**: WIP, drafts

**Special Rules**:
- **Draft Exclusion**: Draft PRs are skipped unless requested
- **Label Boost**: urgent/hotfix/blocking/critical labels add 10 points
- **High Priority Labels**: high-priority/important labels add 7 points

**Output Format**:
Agent provides scored PR list with detailed breakdown, emoji indicators (🔴 Critical, 🟡 Medium, 🟢 Low), and clear recommendation for next review.

**Key Features**:
- Transparent score breakdowns showing exactly why each PR is prioritized
- Review queue filtering (exclude drafts, filter by state)
- Smart suggestions with reasoning and alternatives
- Repository velocity tracking (merged PRs, avg time to merge)
- Repository-scoped operations (can manage multiple repos)

**Implementation Details**:
- Toolkit: `GitHubToolkit` (`src/agentllm/tools/github_toolkit.py`)
- Configuration: `GitHubConfig` (`src/agentllm/agents/toolkit_configs/github_config.py`)
- Agent: `GitHubReviewAgent` (`src/agentllm/agents/github_pr_prioritization_agent.py`)
- Token storage: Database-backed via `TokenStorage.upsert_github_token()`
- Optional toolkit: Only prompts when GitHub/PRs mentioned

**Tools Available**:
- `list_prs(repo, state, limit)` - Simple markdown list of PRs with high-level info (no scoring)
- `prioritize_prs(repo, limit)` - Score and rank PRs with detailed breakdown
- `suggest_next_review(repo, reviewer)` - Smart recommendation with reasoning
- `get_repo_velocity(repo, days)` - Repository merge velocity metrics (all authors)

### Sprint Reviewer (`agno/sprint-reviewer`)

**Purpose**: AI assistant for generating sprint reviews with JIRA issue tracking and metrics.

**Setup**:

1. **Google Drive OAuth** (for team mapping document access):
   - Requires `GDRIVE_CLIENT_ID` and `GDRIVE_CLIENT_SECRET` environment variables
   - Agent will provide OAuth URL on first use
   - Visit URL, authorize, and paste back the authorization code
2. **JIRA API Token**:
   - Go to https://issues.redhat.com
   - Click profile icon → Account Settings → Security → API Tokens
   - Create and copy token
   - In chat: "My Jira token is YOUR_TOKEN_HERE"
   - Agent validates and stores token securely

**Usage Examples**:

- "Create a sprint review for the RHIDP - Plugins team"

**Workflow**:

The agent follows a structured workflow:

1. **Read team mapping**: Fetches team name to team ID mappings from Google Doc
2. **Search current sprint**: Queries JIRA for in-progress sprint issues
3. **Extract sprint info**: Gets sprint ID and name from first issue
4. **Get sprint metrics**: Retrieves structured metrics (planned, closed, stories/tasks, bugs)
5. **Search backlog**: Queries top 15 "To Do" issues from backlog
6. **Generate review**: Creates formatted markdown with metrics and issue lists

**Output Format**:

Generates structured sprint review markdown with:

- **Metrics Section**: Clickable links to sprint board, sprint report, and filtered issue lists
  - Completed vs planned issues (with breakdown by stories/tasks and bugs)
  - All metrics linked to JIRA queries with proper URL encoding
- **This Sprint Section**: Current sprint issues grouped by epic (when 2+ share same epic)
- **Next Sprint Section**: Top 15 backlog issues in "To Do" state
- **Acknowledgments Section**: Space for recognizing team contributions

**Epic Grouping Logic**:

- Groups issues when 2+ share the same Epic Link (`customfield_12311140`)
- Standalone issues listed individually if only 1 in epic
- Issues ordered by priority within groups: Blocker → Major → Normal → Minor → Undefined
- Special formatting for plugin update epics

**Key Features**:

- Automatic team ID resolution from Google Doc mapping
- JIRA metrics calculated via dedicated tool (not manual counting)
- Smart issue grouping by epic with priority ordering
- Proper URL encoding for all JIRA links
- Status indicators for current sprint issues
- Error handling for missing team names or sprint info

**Implementation Details**:

- Toolkit: `GoogleDriveTools` (for team mapping), `JiraTools` (for issue queries)
- Configuration: `GoogleDriveConfig`, `JiraConfig`
- Agent: `SprintReviewer` (`src/agentllm/agents/sprint_reviewer.py`)

**Tools Available**:

- JIRA `get_issues_detailed(jql, fields, max_results)` - Get detailed issue information with custom fields
- JIRA `get_issues_summary(jql, max_results)` - Get basic issue list (key, summary, status)
- JIRA `extract_sprint_info(issue_key)` - Extract sprint ID and name from issue
- JIRA `get_sprint_metrics(sprint_id)` - Get sprint metrics (number of planned, closed, number of bugs vs tasks and stories)
- JIRA `get_issue(issue_key)` - Get individual issue details

## Key Files

```
src/agentllm/
├── custom_handler.py              # LiteLLM CustomLLM (caching, streaming)
├── agents/
│   ├── base/                      # NEW: Plugin system base classes
│   │   ├── factory.py             #   AgentFactory ABC
│   │   ├── registry.py            #   AgentRegistry (plugin discovery)
│   │   ├── configurator.py        #   AgentConfigurator (config management)
│   │   ├── wrapper.py             #   BaseAgentWrapper (execution interface)
│   │   └── toolkit_config.py      #   BaseToolkitConfig (re-export)
│   ├── release_manager.py         # Production agent wrapper
│   ├── demo_agent.py              # Reference implementation
│   ├── github_pr_prioritization_agent.py  # GitHub PR review agent
│   └── toolkit_configs/           # Toolkit config implementations
│       └── github_config.py       # GitHub token & toolkit config
├── tools/
│   └── github_toolkit.py          # GitHub PR review tools
└── db/token_storage.py            # SQLite credential storage
```

## Environment

```bash
GEMINI_API_KEY=...                 # Required
LITELLM_MASTER_KEY=...             # Proxy auth (default: sk-agno-test-key-12345)
```

See `.env.secrets.template` for full config.

## TDD Workflow

1. Write failing test
2. Implement feature
3. `pytest tests/`
4. Refactor

Always use `uv run` for Python commands (or just use `pytest` directly).

### Debugging Tests

**Automatic AGNO_DEBUG**: Tests automatically enable `AGNO_DEBUG=true` when run with `-v` (verbose mode):

```bash
# Verbose mode - AGNO_DEBUG automatically enabled
pytest tests/test_release_manager.py -v

# Extra verbose with output capture disabled
pytest tests/test_release_manager.py -v -s

# Quiet mode - AGNO_DEBUG not set
pytest tests/test_release_manager.py
```

This is configured in `tests/conftest.py` via the `pytest_configure()` hook. When verbose mode is detected, it automatically sets:
- `AGNO_DEBUG=true` - Enables detailed Agno agent logging
- `AGNO_SHOW_TOOL_CALLS=true` - Shows tool call details

You can override these by explicitly setting them in your environment:

```bash
# Force AGNO_DEBUG even in quiet mode
AGNO_DEBUG=true pytest tests/

# Disable AGNO_DEBUG even in verbose mode
AGNO_DEBUG=false pytest tests/ -v
```
