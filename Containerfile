# Dockerfile for LiteLLM Proxy with Agno Custom Handler
# Works for both production and local development

FROM python:3.11-slim

# Install system dependencies including curl for healthchecks and build tools for html-to-markdown
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Layer 1: Copy dependency files and source structure (needed for uv sync)
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/

# Layer 2: Install dependencies (cached until dependencies or source structure change)
RUN uv sync --locked --no-dev

# Layer 3: Copy application configuration (changes occasionally)
COPY custom_handler.py proxy_config.yaml ./

# Layer 4: Copy agentllm package to /app/agentllm for Python imports
# The stub custom_handler.py imports from agentllm.custom_handler
COPY src/agentllm /app/agentllm

# Create directories for runtime data persistence
RUN mkdir -p /app/tmp/gdrive_workspace

# Set Python environment
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Expose LiteLLM proxy port
EXPOSE 8890

# Reset the entrypoint, don't invoke `uv`
ENTRYPOINT []

# Run LiteLLM proxy
CMD ["litellm", "--config", "/app/proxy_config.yaml", "--port", "8890", "--host", "0.0.0.0"]
