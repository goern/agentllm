# Development environment recipes
#
# Local servers and containerized development stack.
# For container builds, see container.just.

# ==============================================================================
# Local Server Management
# ==============================================================================

# Start LiteLLM proxy locally (foreground)
proxy port="9501":
    #!/usr/bin/env bash
    set -euo pipefail

    # Load environment if available
    if [ -f ".env.secrets" ]; then
        set -a
        source .env.secrets
        set +a
    fi

    echo "Starting LiteLLM proxy on :{{ port }}..."
    echo "Available models:"
    echo "  - agno/demo"
    echo "  - agno/release-manager"
    echo "  - agno/sprint-reviewer"
    echo "  - agno/github-pr-prioritization"
    echo ""

    uv run litellm \
        --config proxy_config.yaml \
        --port {{ port }} \
        --detailed_debug

# Start OAuth callback server locally
oauth-callback port="9502":
    #!/usr/bin/env bash
    set -euo pipefail

    # Load environment if available
    if [ -f ".env.secrets" ]; then
        set -a
        source .env.secrets
        set +a
    fi

    : ${AGENTLLM_DATA_DIR:=tmp}
    export AGENTLLM_DATA_DIR

    echo "Starting OAuth callback server on :{{ port }}..."
    echo "Callback URL: http://localhost:{{ port }}/agentllm/oauth/callback/{provider}"
    echo "Database: $AGENTLLM_DATA_DIR/agno_sessions.db"
    echo ""

    uv run uvicorn src.agentllm.oauth_callback.main:app \
        --host 0.0.0.0 \
        --port {{ port }} \
        --reload

# ==============================================================================
# Containerized Development Stack
# ==============================================================================

# Helper to build compose command with dev overlay
[private]
_compose_cmd:
    #!/usr/bin/env bash
    cmd="{{ compose }} -f $COMPOSE_FILE"
    if [ -f "$COMPOSE_DEV_FILE" ]; then
        cmd="$cmd -f $COMPOSE_DEV_FILE"
    fi
    echo "$cmd"

# Start containerized development stack (detached by default)
# Flags: -a/--attach (foreground), --build
# Uses compose.dev.yaml overlay to mount local source code
dev *FLAGS:
    #!/usr/bin/env bash
    set -euo pipefail

    # Build compose command with dev overlay if available
    compose_cmd=$(just _compose_cmd)
    if [ -f "$COMPOSE_DEV_FILE" ]; then
        echo "Using dev overlay (local source mounted)"
    fi

    args="up -d"  # Detached by default
    attached=false
    for flag in {{ FLAGS }}; do
        case $flag in
            -a|--attach) args="up"; attached=true ;;
            --build) args="$args --build" ;;
        esac
    done

    echo "Starting containerized development environment..."
    echo ""
    echo "Services:"
    echo "  LiteLLM Proxy:  http://localhost:9501"
    echo "  OAuth Callback: http://localhost:9502"
    echo "  Open WebUI:     http://localhost:9500"
    echo ""

    $compose_cmd $args

    # If running detached (default), show helpful info
    if [ "$attached" = false ]; then
        echo ""
        echo "=========================================="
        echo "  Services are ready!"
        echo ""
        echo "  Commands:"
        echo "    just dev-logs -f         # Follow all logs"
        echo "    just dev-logs proxy -f   # Follow proxy logs"
        echo "    just dev-restart         # Restart after code changes"
        echo "    just dev-stop            # Stop all services"
        echo "=========================================="
    fi

# Restart containers to pick up code changes
# Usage: just dev-restart [SERVICE...] [--all]
# Services: proxy, oauth, open-webui
# Default: restarts proxy only
dev-restart *ARGS:
    #!/usr/bin/env bash
    set -euo pipefail
    compose_cmd=$(just _compose_cmd)

    services=""
    all=false
    for arg in {{ ARGS }}; do
        case "$arg" in
            --all|-a) all=true ;;
            *) services="$services $arg" ;;
        esac
    done

    if [ "$all" = true ]; then
        echo "Restarting all services..."
        $compose_cmd restart
    elif [ -n "$services" ]; then
        echo "Restarting:$services"
        $compose_cmd restart $services
    else
        echo "Restarting proxy (default)..."
        echo "  Tip: use 'just dev-restart oauth' or '--all' for other services"
        echo ""
        $compose_cmd restart proxy
    fi

# Stop all containers (preserves data)
dev-stop:
    #!/usr/bin/env bash
    compose_cmd=$(just _compose_cmd)
    $compose_cmd down
    echo "Containers stopped (data preserved)"

# Show container status
dev-status:
    #!/usr/bin/env bash
    compose_cmd=$(just _compose_cmd)
    $compose_cmd ps

# Show container logs
# Usage: just dev-logs [SERVICE...] [-f]
# Services: proxy, oauth, open-webui
dev-logs *ARGS:
    #!/usr/bin/env bash
    compose_cmd=$(just _compose_cmd)
    $compose_cmd logs {{ ARGS }}

# Shell into a running container
# Services: proxy, oauth, open-webui
dev-shell SERVICE="proxy":
    #!/usr/bin/env bash
    compose_cmd=$(just _compose_cmd)
    $compose_cmd exec {{ SERVICE }} /bin/bash

# Remove all containers and volumes (full reset)
dev-reset:
    #!/usr/bin/env bash
    echo "This will remove all containers and volumes!"
    echo "This includes:"
    echo "  - Open WebUI data (accounts, settings, chat history)"
    echo "  - Agent data (sessions, credentials)"
    echo ""
    read -p "Are you sure? (y/N) " -r
    [[ ! $REPLY =~ ^[Yy]$ ]] && exit 0
    compose_cmd=$(just _compose_cmd)
    $compose_cmd down -v
    echo ""
    echo "✓ Containers and volumes removed"
    echo ""
    echo "Restart with: just dev"
