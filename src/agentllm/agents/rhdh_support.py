"""RHDH Support Focal agent for managing support issues and customer cases."""

import os
from typing import Any

from agno.db.sqlite import SqliteDb

from agentllm.agents.base import AgentFactory, BaseAgentWrapper
from agentllm.agents.rhdh_support_configurator import RHDHSupportConfigurator
from agentllm.db import TokenStorage

# Map GEMINI_API_KEY to GOOGLE_API_KEY if not set
if "GOOGLE_API_KEY" not in os.environ and "GEMINI_API_KEY" in os.environ:
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]


class RHDHSupport(BaseAgentWrapper):
    """RHDH Support Focal agent with toolkit configuration management.

    This class extends BaseAgentWrapper to provide a Support Focal agent
    specialized for Red Hat Developer Hub (RHDH) support issue management.

    Toolkit Configuration:
    ---------------------
    - Google Drive: OAuth-based access to process documentation (required)
    - JIRA: API token-based access to RHDHSUPP, RHDHPLAN, RHDHBUGS (READ-ONLY, optional)
    - RHCP: Offline token-based access to Red Hat Customer Portal cases (READ-ONLY, optional)
    - SystemPromptExtension: Extended instructions from Google Drive document (required if configured)

    IMPORTANT - READ-ONLY Operations:
    ---------------------------------
    This agent has READ-ONLY access to both JIRA and RHCP. It cannot:
    - Create, update, or comment on JIRA issues
    - Create, update, or modify customer cases in RHCP
    All operations are strictly query/read only for safety.

    The agent helps with:
    - Monitoring RHDHSUPP issues requiring Engineering assistance
    - Ensuring proper team assignment based on case severity and SLA
    - Tracking linked customer cases and their escalation status
    - Monitoring related RFEs (RHDHPLAN) and defects (RHDHBUGS)
    - Providing status updates for Support managers and Engineering leads
    """

    def __init__(
        self,
        shared_db: SqliteDb,
        token_storage: TokenStorage,
        user_id: str,
        session_id: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **model_kwargs,
    ):
        """Initialize the RHDH Support Focal agent with configurator pattern.

        Args:
            shared_db: Shared database instance for session management
            token_storage: Token storage instance for credentials
            user_id: User identifier (wrapper is per-user+session)
            session_id: Session identifier (optional)
            temperature: Model temperature (0.0-2.0)
            max_tokens: Maximum tokens in response
            **model_kwargs: Additional model parameters
        """
        # Store token_storage for configurator
        self._token_storage = token_storage

        # Call parent constructor (will call _create_configurator)
        super().__init__(
            shared_db=shared_db,
            user_id=user_id,
            session_id=session_id,
            temperature=temperature,
            max_tokens=max_tokens,
            **model_kwargs,
        )

    def _create_configurator(
        self,
        user_id: str,
        session_id: str | None,
        shared_db: SqliteDb,
        **kwargs: Any,
    ) -> RHDHSupportConfigurator:
        """Create RHDH Support Focal configurator instance.

        Args:
            user_id: User identifier
            session_id: Session identifier
            shared_db: Shared database
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Returns:
            RHDHSupportConfigurator instance
        """
        return RHDHSupportConfigurator(
            user_id=user_id,
            session_id=session_id,
            shared_db=shared_db,
            token_storage=self._token_storage,
            **kwargs,
        )


class RHDHSupportFactory(AgentFactory):
    """Factory for creating RHDH Support Focal instances.

    Registered via entry points in pyproject.toml for plugin system.
    """

    @staticmethod
    def create_agent(
        shared_db: Any,
        token_storage: Any,
        user_id: str,
        session_id: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> RHDHSupport:
        """Create an RHDH Support Focal instance.

        Args:
            shared_db: Shared database instance (SqliteDb)
            token_storage: Token storage instance (TokenStorage)
            user_id: User ID for this agent instance
            session_id: Optional session ID for conversation history
            temperature: Optional temperature parameter for the model
            max_tokens: Optional max tokens parameter for the model
            **kwargs: Additional keyword arguments for the agent

        Returns:
            RHDHSupport instance
        """
        return RHDHSupport(
            shared_db=shared_db,
            token_storage=token_storage,
            user_id=user_id,
            session_id=session_id,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    @staticmethod
    def get_metadata() -> dict[str, Any]:
        """Get agent metadata for proxy configuration.

        Returns:
            Dictionary with agent metadata
        """
        return {
            "name": "rhdh-support",
            "description": "Support Focal for Red Hat Developer Hub (RHDH)",
            "mode": "chat",
            "requires_env": ["GEMINI_API_KEY"],
        }
