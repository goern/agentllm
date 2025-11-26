"""Toolkit configuration managers for agent services.

This package automatically registers all toolkit token types with the global
token registry when imported. Each config module defines its token model and
registers it on import.
"""

from loguru import logger

from .base import BaseToolkitConfig
from .gdrive_config import GoogleDriveConfig
from .gdrive_service_account_config import GDriveServiceAccountConfig
from .github_config import GitHubConfig
from .jira_config import JiraConfig
from .rhai_toolkit_config import RHAIToolkitConfig
from .rhcp_config import RHCPConfig
from .web_config import WebConfig

__all__ = [
    "BaseToolkitConfig",
    "GoogleDriveConfig",
    "GDriveServiceAccountConfig",
    "GitHubConfig",
    "JiraConfig",
    "RHCPConfig",
    "RHAIToolkitConfig",
    "WebConfig",
    "discover_and_register_toolkits",
]


def discover_and_register_toolkits() -> None:
    """Discover and register all toolkit token types.

    This function imports all toolkit config modules in this package,
    which triggers their token model registration with the global registry.

    This provides automatic discovery - adding a new toolkit config to this
    package and including it in the imports above will automatically register
    its token type.

    Example:
        >>> from agentllm.agents.toolkit_configs import discover_and_register_toolkits
        >>> discover_and_register_toolkits()
        >>> # All toolkit token types are now registered
    """
    from agentllm.db.token_registry import get_global_registry

    registry = get_global_registry()
    registered_types = registry.list_types()

    logger.info(f"Toolkit token type discovery complete. Registered {len(registered_types)} token types: {registered_types}")
