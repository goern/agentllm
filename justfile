# AgentLLM Task Runner
# https://github.com/casey/just
#
# Install: brew install just
# Completion: just --completions zsh > ~/.zfunc/_just
#
# Usage:
#   just              # Show all available commands
#   just <recipe>     # Run a recipe
#   just --list       # List all recipes with descriptions

set dotenv-load := true
set shell := ["bash", "-euo", "pipefail", "-c"]

# Import modules
import? 'just/dev.just'
import? 'just/container.just'

# Project paths
export REPO_ROOT := justfile_directory()
export COMPOSE_FILE := REPO_ROOT / "compose.yaml"
export COMPOSE_DEV_FILE := REPO_ROOT / "compose.dev.yaml"

# Container runtime (podman/docker)
compose := "podman compose"

# Default recipe - show available commands
default:
    @just --list --unsorted

# List all users and their tokens from the session database
tokens:
    uv run python scripts/tokens.py list

# List only user IDs (useful for scripts)
users:
    uv run python scripts/tokens.py users

# Get the first configured user ID (useful for test fixtures)
first-user:
    uv run python scripts/tokens.py first-user

# Show detailed token information for a specific user
token-details USER_ID:
    uv run python scripts/tokens.py details {{ USER_ID }}

# Delete all tokens for a specific user (use with caution!)
delete-user-tokens USER_ID:
    uv run python scripts/tokens.py delete {{ USER_ID }}

# Clean up all test database files
clean-test-dbs:
    #!/usr/bin/env bash
    set -euo pipefail

    echo "🧹 Cleaning up test databases..."

    find tmp -name "test_*.db" -type f -delete 2>/dev/null || true

    echo "✅ Test databases cleaned"

# ==============================================================================
# Project Management
# ==============================================================================

# Sync workspace dependencies
sync:
    uv sync

# Show project info
info:
    @echo "AgentLLM"
    @echo "========"
    @echo "Root: {{ REPO_ROOT }}"
    @echo ""
    @echo "Services:"
    @echo "  Proxy:    http://localhost:9501"
    @echo "  OAuth:    http://localhost:9502"
    @echo "  WebUI:    http://localhost:9500"

# Clean build artifacts
clean:
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name ".nox" -exec rm -rf {} + 2>/dev/null || true

# Run unit tests with pytest
test *ARGS:
    uv run pytest tests/ -v --tb=short {{ ARGS }}

# Run integration tests (requires proxy)
test-integration *ARGS:
    uv run pytest tests/test_integration.py -v --tb=short -m integration {{ ARGS }}

# Run accuracy evaluations (requires ANTHROPIC_API_KEY)
test-eval *ARGS:
    #!/usr/bin/env bash
    set -euo pipefail

    # Check for ANTHROPIC_API_KEY
    if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
        echo "❌ Error: ANTHROPIC_API_KEY environment variable not set"
        echo ""
        echo "💡 Set your Anthropic API key:"
        echo "   export ANTHROPIC_API_KEY=sk-ant-..."
        echo "   Or add to .env file"
        echo ""
        echo "Get your key from: https://console.anthropic.com/settings/keys"
        exit 1
    fi

    echo "✅ ANTHROPIC_API_KEY configured"
    echo "🧪 Running accuracy evaluations..."
    echo ""

    uv run pytest tests/test_rhai_roadmap_accuracy.py -v --tb=short -m integration {{ ARGS }}

# Format code with ruff
format:
    uv run ruff format src/ tests/

# Lint code
lint:
    make lint

# ==============================================================================
# Testing and Validation
# ==============================================================================

# Test the running proxy with a series of requests
hello:
    #!/usr/bin/env bash
    set -euo pipefail

    echo ""
    echo "🚀 Testing AgentLLM Proxy..."
    echo ""

    # Check if proxy is running
    echo "1️⃣  Checking if proxy is running on port 9501..."
    if ! lsof -i:9501 > /dev/null 2>&1; then
        echo "❌ Proxy is not running!"
        echo ""
        echo "💡 Start the proxy first:"
        echo "   just proxy"
        echo ""
        echo "Or run in containerized mode:"
        echo "   just dev"
        exit 1
    fi

    echo "✅ Proxy is running!"
    echo ""

    # Test 1: Health check
    echo "2️⃣  Testing /health/readiness endpoint..."
    response=$(curl -s http://localhost:9501/health/readiness)
    if echo "$response" | grep -q '"status":"healthy"'; then
        echo "   ✅ Proxy is healthy and ready"
    else
        echo "   Response: $response"
    fi
    echo ""

    # Test 2: List models
    echo "3️⃣  Testing /v1/models endpoint..."
    response=$(curl -s http://localhost:9501/v1/models \
        -H "Authorization: Bearer ${LITELLM_MASTER_KEY:-sk-agno-test-key-12345}")
    models=$(echo "$response" | jq -r '.data[].id' 2>/dev/null | tr '\n' ', ' | sed 's/,$//')
    echo "   Available models: $models"
    echo ""

    # Test 3: Chat completion
    echo "4️⃣  Testing chat completion with agno/demo-agent..."
    echo "   (Note: This will fail without LLM API keys configured)"
    echo ""

    response=$(curl -s http://localhost:9501/v1/chat/completions \
        -H "Authorization: Bearer ${LITELLM_MASTER_KEY:-sk-agno-test-key-12345}" \
        -H "Content-Type: application/json" \
        -d '{
            "model": "agno/demo-agent",
            "messages": [{"role": "user", "content": "Hello! What is your favorite color?"}],
            "metadata": {"user_id": "test-user-from-just", "session_id": "test-session-123"}
        }')

    echo "   Request:"
    echo '   {"model": "agno/demo-agent", "messages": [...], "metadata": {"user_id": "test-user-from-just", ...}}'
    echo ""
    echo "   Response:"

    if echo "$response" | jq -e '.error' > /dev/null 2>&1; then
        error_msg=$(echo "$response" | jq -r '.error.message' 2>/dev/null)
        echo "   ❌ Error: $error_msg"
        echo ""
        echo "   💡 Common issues:"
        echo "      - Missing GEMINI_API_KEY in environment"
        echo "      - Agent not configured properly"
        echo "      - Database not initialized"
    elif echo "$response" | jq -e '.choices' > /dev/null 2>&1; then
        content=$(echo "$response" | jq -r '.choices[0].message.content' 2>/dev/null)
        echo "   ✅ Success! Agent responded:"
        echo ""
        echo "      $content"
        echo ""
    else
        echo "   Raw response: $response"
    fi

    echo ""
    echo "✨ Test complete!"
    echo ""

# ==============================================================================
# Examples
# ==============================================================================

# Run RHAI releases example
example-rhai-releases USER_ID:
    #!/usr/bin/env bash
    set -euo pipefail

    echo ""
    echo "================================================================================"
    echo "🎯 RHAI RELEASES EXAMPLE"
    echo "================================================================================"
    echo ""

    # Check required environment variables
    if [ -z "${AGENTLLM_RHAI_ROADMAP_PUBLISHER_RELEASE_SHEET:-}" ]; then
        echo "❌ Missing required environment variable:"
        echo "   AGENTLLM_RHAI_ROADMAP_PUBLISHER_RELEASE_SHEET: RHAI Release Sheet URL"
        echo ""
        echo "💡 Set this variable in your .env or .envrc file"
        echo "   See CLAUDE.md for setup instructions"
        echo ""
        exit 1
    fi

    echo "✅ All required environment variables are set"
    echo "👤 User ID: {{ USER_ID }}"
    echo ""

    # Check if token database exists
    data_dir="${AGENTLLM_DATA_DIR:-tmp/}"
    token_db_path="$data_dir/agno_sessions.db"

    if [ ! -f "$token_db_path" ]; then
        echo "❌ Token database not found: $token_db_path"
        echo ""
        echo "   You need to authorize Google Drive through the agent first."
        echo "   Start the agent and interact with it to trigger authorization:"
        echo ""
        echo "   1. just proxy"
        echo "   2. Use Open WebUI to interact with agno/release-manager"
        echo ""
        exit 1
    fi

    echo "💾 Token database found: $token_db_path"
    echo "🚀 Starting example..."
    echo ""
    echo "================================================================================"
    echo ""

    # Run the example script with user_id
    uv run python examples/rhai_releases_example.py {{ USER_ID }}
