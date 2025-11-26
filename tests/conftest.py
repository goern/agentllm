"""Root conftest.py for AgentLLM tests.

This module provides pytest configuration and fixtures that are available
to all test modules.
"""

import os


def pytest_configure(config):
    """Pytest configuration hook called before test collection.

    Automatically sets AGNO_DEBUG=true when running tests in verbose mode (-v).
    This provides detailed logging from Agno agents during test execution.

    Also sets up encryption key for token storage tests.

    Args:
        config: pytest Config object
    """
    # Set up encryption key for tests if not already set
    if "AGENTLLM_TOKEN_ENCRYPTION_KEY" not in os.environ:
        # Generate a test encryption key
        from cryptography.fernet import Fernet

        test_key = Fernet.generate_key().decode()
        os.environ["AGENTLLM_TOKEN_ENCRYPTION_KEY"] = test_key

    # Discover and register all toolkit token types
    # This imports all toolkit configs which auto-register their token models
    from agentllm.agents.toolkit_configs import discover_and_register_toolkits  # noqa: E402

    discover_and_register_toolkits()

    # Check if verbose mode is enabled (-v or -vv)
    verbose = config.getoption("verbose", 0)

    if verbose > 0:
        # Set AGNO_DEBUG for detailed Agno logging
        os.environ["AGNO_DEBUG"] = "true"

        # Also set show_tool_calls for better debugging
        if "AGNO_SHOW_TOOL_CALLS" not in os.environ:
            os.environ["AGNO_SHOW_TOOL_CALLS"] = "true"


def pytest_report_header(config):
    """Add custom header information to pytest output.

    Args:
        config: pytest Config object

    Returns:
        List of header lines to display
    """
    verbose = config.getoption("verbose", 0)
    headers = []

    if verbose > 0:
        headers.append(f"AGNO_DEBUG: {os.environ.get('AGNO_DEBUG', 'false')}")
        headers.append(f"AGNO_SHOW_TOOL_CALLS: {os.environ.get('AGNO_SHOW_TOOL_CALLS', 'false')}")

    return headers
