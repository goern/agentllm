"""Nox automation for testing, integration, and running the proxy."""

import nox

# Use the current Python instead of requiring a specific version
nox.options.default_venv_backend = "none"


@nox.session(venv_backend="none")
def test(session):
    """Run unit tests with pytest."""
    session.run("uv", "run", "pytest", "tests/", "-v", "--tb=short", external=True)


@nox.session(venv_backend="none")
def integration(session):
    """Run integration tests (requires LiteLLM with provider installed)."""
    session.run(
        "uv",
        "run",
        "pytest",
        "tests/test_integration.py",
        "-v",
        "--tb=short",
        "-m",
        "integration",
        external=True,
    )


@nox.session(venv_backend="none")
def proxy(session):
    """Start LiteLLM proxy with Agno provider on port 8890."""
    session.run(
        "uv",
        "run",
        "litellm",
        "--config",
        "proxy_config.yaml",
        "--port",
        "8890",
        "--detailed_debug",
        external=True,
    )


@nox.session(venv_backend="none")
def lint(session):
    """Run linting with ruff."""
    session.run("uv", "run", "ruff", "check", "src/", "tests/", external=True)


@nox.session(venv_backend="none")
def format(session):
    """Format code with ruff."""
    session.run("uv", "run", "ruff", "format", "src/", "tests/", external=True)


@nox.session(venv_backend="none")
def hello(session):
    """Make a hello world request to the proxy (proxy must be running)."""
    import json
    import subprocess

    print("\n🚀 Testing AgentLLM Proxy...\n")

    # Check if proxy is running
    print("1️⃣  Checking if proxy is running on port 8890...")
    result = subprocess.run(["lsof", "-i:8890"], capture_output=True, text=True)

    if result.returncode != 0:
        print("❌ Proxy is not running!")
        print("\n💡 Start the proxy first:")
        print("   nox -s proxy")
        print("\nOr run in background:")
        print("   nox -s proxy &")
        return

    print("✅ Proxy is running!\n")

    # Test 1: Health check
    print("2️⃣  Testing /health endpoint...")
    result = subprocess.run(
        ["curl", "-s", "http://localhost:8890/health"], capture_output=True, text=True
    )
    print(f"   Response: {result.stdout}\n")

    # Test 2: List models
    print("3️⃣  Testing /v1/models endpoint...")
    result = subprocess.run(
        [
            "curl",
            "-s",
            "http://localhost:8890/v1/models",
            "-H",
            "Authorization: Bearer sk-agno-test-key-12345",
        ],
        capture_output=True,
        text=True,
    )
    try:
        data = json.loads(result.stdout)
        models = [m.get("id") for m in data.get("data", [])]
        print(f"   Available models: {models}\n")
    except Exception:
        print(f"   Response: {result.stdout}\n")

    # Test 3: Hello world chat completion
    print("4️⃣  Testing chat completion with agno/release-manager...")
    print("   (Note: This will fail without LLM API keys configured)\n")

    result = subprocess.run(
        [
            "curl",
            "-s",
            "http://localhost:8890/v1/chat/completions",
            "-H",
            "Authorization: Bearer sk-agno-test-key-12345",
            "-H",
            "Content-Type: application/json",
            "-d",
            json.dumps(
                {
                    "model": "agno/release-manager",
                    "messages": [{"role": "user", "content": "Hello from nox!"}],
                }
            ),
        ],
        capture_output=True,
        text=True,
    )

    print("   Request:")
    print(
        '   {"model": "agno/release-manager", '
        '"messages": [{"role": "user", "content": "Hello from nox!"}]}'
    )
    print("\n   Response:")
    try:
        data = json.loads(result.stdout)
        if "error" in data:
            print(f"   ❌ Error: {data['error']}")
            print("\n   💡 This is expected if agents don't have LLM API keys configured.")
            print("      To fix: Add API keys to .env and configure agents with models")
        elif "choices" in data:
            content = data["choices"][0]["message"]["content"]
            print(f"   ✅ Success! Agent responded: {content}")
        else:
            print(f"   {json.dumps(data, indent=2)}")
    except Exception:
        print(f"   {result.stdout}")

    print("\n✨ Test complete!\n")


# =============================================================================
# Docker Compose Development Sessions
# =============================================================================


def _check_env():
    """Check if .env file exists and has required variables."""
    import sys
    from pathlib import Path

    env_file = Path(".env")

    # Check if .env exists
    if not env_file.exists():
        print("❌ Error: .env file not found")
        print("\n💡 Create .env from template:")
        print("   cp .env.example .env")
        print("   # Then edit .env and add your GEMINI_API_KEY")
        sys.exit(1)

    # Load .env and check for required variables
    with open(env_file) as f:
        env_content = f.read()

    if "GEMINI_API_KEY" not in env_content or "AIzaSy..." in env_content:
        print("❌ Error: GEMINI_API_KEY is not set in .env")
        print("\n💡 Edit .env and add your Google Gemini API key")
        print("   Get your key from: https://aistudio.google.com/apikey")
        sys.exit(1)

    print("✅ Environment configuration validated\n")


@nox.session(venv_backend="none")
def dev(session):
    """Start local development environment with Docker Compose.

    Examples:
        nox -s dev              # Start in foreground
        nox -s dev -- --build   # Rebuild and start
        nox -s dev -- -d        # Start in background (detached)
    """
    import sys

    _check_env()

    args = ["docker", "compose", "up"]

    # Parse session arguments
    if session.posargs:
        if "--build" in session.posargs:
            args.append("--build")
        if "-d" in session.posargs or "--detach" in session.posargs:
            args.append("-d")

    print("🚀 Starting development environment...")
    print(f"   Command: {' '.join(args)}\n")

    try:
        session.run(*args, external=True)
    except KeyboardInterrupt:
        print("\n\n⏹️  Stopping containers...")
        session.run("docker", "compose", "down", external=True)
        sys.exit(0)


@nox.session(venv_backend="none")
def dev_build(session):
    """Build and start development environment (forces rebuild)."""
    _check_env()

    print("🔨 Building and starting development environment...")
    session.run("docker", "compose", "up", "--build", external=True)


@nox.session(venv_backend="none")
def dev_local_proxy(session):
    """Start only Open WebUI for local proxy development.

    This mode is for when you want to run the LiteLLM proxy locally (nox -s proxy)
    and only run Open WebUI in a container.

    Prerequisites:
        1. Ensure LITELLM_PROXY_URL is set in .env (default: http://host.docker.internal:8890/v1)
        2. Start the proxy locally: nox -s proxy

    Examples:
        # Terminal 1: Start local proxy
        nox -s proxy

        # Terminal 2: Start Open WebUI
        nox -s dev-local-proxy
    """
    import subprocess
    import sys

    _check_env()

    # Check if proxy is running locally
    print("🔍 Checking if local proxy is running on port 8890...")
    result = subprocess.run(["lsof", "-i:8890"], capture_output=True, text=True)

    if result.returncode != 0:
        print("⚠️  Warning: No service detected on port 8890")
        print("\n💡 Start the local proxy first:")
        print("   nox -s proxy")
        print("\nOr if you want both services in containers, use:")
        print("   nox -s dev_full\n")

        response = input("Continue anyway? (y/N) ")
        if response.lower() != "y":
            print("Cancelled")
            sys.exit(0)

    print("🚀 Starting Open WebUI (will connect to local proxy)...\n")

    args = ["docker", "compose", "up", "open-webui"]

    # Parse session arguments
    if session.posargs:
        if "-d" in session.posargs or "--detach" in session.posargs:
            args.append("-d")

    try:
        session.run(*args, external=True)
    except KeyboardInterrupt:
        print("\n\n⏹️  Stopping Open WebUI...")
        session.run("docker", "compose", "stop", "open-webui", external=True)
        sys.exit(0)


@nox.session(venv_backend="none")
def dev_full(session):
    """Start both LiteLLM proxy and Open WebUI in containers (production-like).

    This mode runs everything containerized, useful for testing the full stack
    or when you don't need to modify the proxy code.

    Examples:
        nox -s dev-full              # Start in foreground
        nox -s dev-full -- -d        # Start in background (detached)
    """
    import os
    import sys

    _check_env()

    # Override LITELLM_PROXY_URL to use container name
    env = os.environ.copy()
    env["LITELLM_PROXY_URL"] = "http://litellm-proxy:8890/v1"

    args = ["docker", "compose", "up"]

    # Parse session arguments
    if session.posargs:
        if "--build" in session.posargs:
            args.append("--build")
        if "-d" in session.posargs or "--detach" in session.posargs:
            args.append("-d")

    print("🚀 Starting full containerized environment...")
    print("   LiteLLM Proxy: http://litellm-proxy:8890/v1 (internal)")
    print("   Open WebUI:    http://localhost:3000\n")

    try:
        session.run(*args, external=True, env=env)
    except KeyboardInterrupt:
        print("\n\n⏹️  Stopping containers...")
        session.run("docker", "compose", "down", external=True)
        sys.exit(0)


@nox.session(venv_backend="none")
def dev_detach(session):
    """Start development environment in background."""
    import subprocess
    import time

    _check_env()

    print("🚀 Starting development environment in background...")
    session.run("docker", "compose", "up", "-d", external=True)

    print("\n⏳ Waiting for services to be healthy...")

    # Wait up to 60 seconds for litellm-proxy to be healthy
    max_wait = 60
    waited = 0
    healthy = False

    while waited < max_wait:
        result = subprocess.run(["docker", "compose", "ps"], capture_output=True, text=True)
        if "litellm-proxy" in result.stdout and "healthy" in result.stdout:
            healthy = True
            break
        time.sleep(2)
        waited += 2
        print(".", end="", flush=True)

    print("\n")

    if healthy:
        print("✅ LiteLLM Proxy is healthy\n")
    else:
        print("⚠️  Warning: LiteLLM Proxy did not become healthy within 60s")
        print("   Check logs with: nox -s dev-logs\n")

    print("🎉 Services started!\n")
    print("📍 URLs:")
    print("   Open WebUI:       http://localhost:3000")
    print("   LiteLLM Proxy:    http://localhost:8890")
    print("   Health Check:     http://localhost:8890/health")
    print("\n💡 Useful commands:")
    print("   View logs:        nox -s dev-logs")
    print("   Stop services:    nox -s dev-stop")
    print("   Clean everything: nox -s dev-clean")
    print()


@nox.session(venv_backend="none")
def dev_logs(session):
    """View logs from development containers.

    Examples:
        nox -s dev-logs                    # All services
        nox -s dev-logs -- litellm-proxy   # Specific service
    """
    args = ["docker", "compose", "logs", "-f"]

    if session.posargs:
        args.extend(session.posargs)

    print("📜 Viewing container logs (Ctrl+C to exit)...\n")
    session.run(*args, external=True)


@nox.session(venv_backend="none")
def dev_stop(session):
    """Stop development containers (preserves data)."""
    print("⏹️  Stopping development containers...")
    session.run("docker", "compose", "down", external=True)
    print("✅ Containers stopped (data preserved)")


@nox.session(venv_backend="none")
def dev_clean(session):
    """Stop containers and remove all data (including volumes).

    ⚠️  WARNING: This will delete all data including database and chat history!
    """
    import sys

    print("⚠️  WARNING: This will delete all data including database and chat history!")
    response = input("Continue? (y/N) ")

    if response.lower() != "y":
        print("Cleanup cancelled")
        sys.exit(0)

    print("\n🧹 Cleaning up containers and volumes...")
    session.run("docker", "compose", "down", "-v", external=True)
    print("✅ Cleanup complete")
