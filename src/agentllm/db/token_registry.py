"""Token type registry for generic token storage.

This module provides a registry pattern for token types, allowing new token types
to be added without modifying the TokenStorage implementation.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import DeclarativeMeta


@dataclass
class TokenTypeConfig:
    """Configuration for a token type.

    Attributes:
        model: SQLAlchemy model class for this token type
        encrypted_fields: List of field names that should be encrypted
        serializer: Optional function to serialize complex types to dict before storage
        deserializer: Optional function to deserialize dict to complex type after retrieval
    """

    model: type[DeclarativeMeta]
    encrypted_fields: list[str] = field(default_factory=list)
    serializer: Callable[[Any], dict[str, Any]] | None = None
    deserializer: Callable[[dict[str, Any]], Any] | None = None


class TokenRegistry:
    """Registry for token types.

    This registry maps token type names to their configurations, enabling
    generic token operations without type-specific methods.

    Example:
        >>> from agentllm.db.token_storage import JiraToken
        >>> registry = TokenRegistry()
        >>> config = registry.get("jira")
        >>> print(config.model)  # JiraToken
        >>> print(config.encrypted_fields)  # ["token"]
    """

    def __init__(self):
        """Initialize empty token registry."""
        self._registry: dict[str, TokenTypeConfig] = {}

    def register(self, token_type: str, config: TokenTypeConfig) -> None:
        """Register a token type configuration.

        Args:
            token_type: Token type identifier (e.g., "jira", "github")
            config: Token type configuration
        """
        self._registry[token_type] = config

    def get(self, token_type: str) -> TokenTypeConfig:
        """Get token type configuration.

        Args:
            token_type: Token type identifier

        Returns:
            Token type configuration

        Raises:
            KeyError: If token type is not registered
        """
        if token_type not in self._registry:
            available = ", ".join(self._registry.keys())
            raise KeyError(f"Unknown token type: {token_type}. Available types: {available}")
        return self._registry[token_type]

    def is_registered(self, token_type: str) -> bool:
        """Check if a token type is registered.

        Args:
            token_type: Token type identifier

        Returns:
            True if registered, False otherwise
        """
        return token_type in self._registry

    def list_types(self) -> list[str]:
        """Get list of all registered token types.

        Returns:
            List of token type identifiers
        """
        return list(self._registry.keys())
