# Container build recipes
#
# Build and manage container images. Runtime-agnostic (works with podman/docker).
# For running containers, see dev.just.

# Detect container runtime
[private]
runtime := if `command -v podman 2>/dev/null` != "" { "podman" } else { "docker" }

# ==============================================================================
# Compose-based Builds (for local development)
# ==============================================================================

# Build container images
# Usage: just container-build [SERVICE...]
container-build *SERVICES:
    #!/usr/bin/env bash
    set -euo pipefail

    services="{{ SERVICES }}"
    if [ -z "$services" ]; then
        services="proxy oauth"
    fi

    echo "Building container images: $services"
    {{ compose }} -f "$COMPOSE_FILE" build $services

# Rebuild container images without cache
# Usage: just container-rebuild [SERVICE...]
container-rebuild *SERVICES:
    #!/usr/bin/env bash
    set -euo pipefail

    services="{{ SERVICES }}"
    if [ -z "$services" ]; then
        services="proxy oauth"
    fi

    echo "Rebuilding container images (no cache): $services"
    {{ compose }} -f "$COMPOSE_FILE" build --no-cache $services

# Build and restart containers
# Flags: --proxy (include proxy container)
container-update *FLAGS:
    #!/usr/bin/env bash
    set -euo pipefail

    services="oauth"
    for flag in {{ FLAGS }}; do
        case $flag in
            --proxy) services="proxy $services" ;;
        esac
    done

    echo "1. Stopping containers..."
    {{ compose }} -f "$COMPOSE_FILE" down

    echo ""
    echo "2. Rebuilding images..."
    {{ compose }} -f "$COMPOSE_FILE" build --no-cache $services

    echo ""
    echo "3. Starting containers..."
    {{ compose }} -f "$COMPOSE_FILE" up -d $services

    echo ""
    echo "4. Container status:"
    {{ compose }} -f "$COMPOSE_FILE" ps
