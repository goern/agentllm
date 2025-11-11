"""Release Manager agent for managing software releases and changelogs."""

import os

from agno.db.sqlite import SqliteDb
from loguru import logger

from agentllm.agents.base_agent import BaseAgentWrapper
from agentllm.agents.toolkit_configs import GoogleDriveConfig
from agentllm.agents.toolkit_configs.base import BaseToolkitConfig
from agentllm.agents.toolkit_configs.jira_config import JiraConfig
from agentllm.agents.toolkit_configs.system_prompt_extension_config import (
    SystemPromptExtensionConfig,
)
from agentllm.db import TokenStorage

# Map GEMINI_API_KEY to GOOGLE_API_KEY if not set
if "GOOGLE_API_KEY" not in os.environ and "GEMINI_API_KEY" in os.environ:
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]


class ReleaseManager(BaseAgentWrapper):
    """Release Manager with toolkit configuration management.

    This class extends BaseAgentWrapper to provide a Release Manager agent
    specialized for Red Hat Developer Hub (RHDH) release management.

    Toolkit Configuration:
    ---------------------
    - Google Drive: OAuth-based access to Google Docs, Sheets, and Presentations (required)
    - JIRA: API token-based access to JIRA issues (optional)
    - SystemPromptExtension: Extended instructions from Google Drive document (required if configured)

    The agent helps with:
    - Managing Y-stream releases (major versions like 1.7.0, 1.8.0)
    - Managing Z-stream releases (maintenance versions like 1.6.1, 1.6.2)
    - Tracking release progress, risks, and blockers
    - Coordinating with Engineering, QE, Documentation, and Product Management teams
    - Providing release status updates for meetings
    - Monitoring Jira for release-related issues, features, and bugs
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
        """Initialize the Release Manager with toolkit configurations.

        Args:
            shared_db: Shared database instance for session management
            token_storage: Token storage instance for credentials
            user_id: User identifier (wrapper is per-user+session)
            session_id: Session identifier (optional)
            temperature: Model temperature (0.0-2.0)
            max_tokens: Maximum tokens in response
            **model_kwargs: Additional model parameters
        """
        # Store token_storage for toolkit config initialization
        self._token_storage = token_storage

        # Call parent constructor (will call _initialize_toolkit_configs)
        super().__init__(
            shared_db=shared_db,
            user_id=user_id,
            session_id=session_id,
            temperature=temperature,
            max_tokens=max_tokens,
            **model_kwargs,
        )

    def _initialize_toolkit_configs(self) -> list[BaseToolkitConfig]:
        """
        Initialize toolkit configurations for Release Manager.

        Returns:
            List of toolkit configuration instances
        """
        # ORDER MATTERS: SystemPromptExtensionConfig depends on GoogleDriveConfig
        gdrive_config = GoogleDriveConfig(token_storage=self._token_storage)
        jira_config = JiraConfig(token_storage=self._token_storage)
        system_prompt_config = SystemPromptExtensionConfig(gdrive_config=gdrive_config, token_storage=self._token_storage)

        return [
            gdrive_config,
            jira_config,
            system_prompt_config,  # Must come after gdrive_config due to dependency
        ]

    def _get_agent_name(self) -> str:
        """Return agent name."""
        return "release-manager"

    def _get_agent_description(self) -> str:
        """Return agent description."""
        return "A helpful AI assistant"

    def _build_agent_instructions(self, user_id: str) -> list[str]:
        """
        Build agent-specific instructions for Release Manager.

        Args:
            user_id: User identifier

        Returns:
            List of instruction strings
        """
        return [
            "You are the Release Manager for Red Hat Developer Hub (RHDH).",
            "Your core responsibilities include:",
            "- Managing Y-stream releases (major versions like 1.7.0, 1.8.0)",
            "- Managing Z-stream releases (maintenance versions like 1.6.1, 1.6.2)",
            "- Tracking release progress, risks, and blockers",
            "- Coordinating with Engineering, QE, Documentation, and Product Management teams",
            "- Providing release status updates for meetings (SOS, Team Forum, Program Meeting)",
            "- Monitoring Jira for release-related issues, features, and bugs",
            "",
            "Available tools:",
            "- Jira: Query and analyze issues, epics, features, bugs, and CVEs",
            "- Google Drive: Access release schedules, test plans, documentation plans, and feature demos",
            "",
            "Output guidelines:",
            "- Use markdown formatting for all structured output",
            "- Be concise but comprehensive in your responses",
            "- Provide data-driven insights with Jira query results and metrics",
            "- Include relevant links to Jira issues, and Google Docs resources",
            "- Use tables and bullet points for clarity",
            "",
            "Behavioral guidelines:",
            "- Proactively identify risks and blockers",
            "- Escalate critical issues with clear impact analysis",
            "- Base recommendations on concrete data (Jira metrics, test results, schedules)",
            "- Maintain professional communication appropriate for cross-functional stakeholders",
            "- Follow established release processes and policies",
            "",
            "System Prompt Management:",
            "- Your instructions come from TWO sources:",
            "  1. Embedded system prompt (stable, rarely changes): Core identity and capabilities",
            "  2. External system prompt (dynamic, frequently updated): Current release context, processes, examples",
            "- The external prompt is stored in a Google Drive document that users can directly edit",
            "- When release context seems outdated or incomplete, suggest users update the external prompt",
            "- If configured, you will be informed of the external prompt document URL in your extended instructions",
        ]

    def _on_config_stored(self, config: BaseToolkitConfig, user_id: str) -> None:
        """
        Handle cross-config dependencies when configuration is stored.

        Special handling for GoogleDrive → SystemPromptExtension:
        When Google Drive credentials are updated, notify SystemPromptExtensionConfig
        to invalidate its cached system prompts.

        Args:
            config: The toolkit config that was stored
            user_id: User identifier
        """
        # When GoogleDrive credentials are updated, notify SystemPromptExtensionConfig
        if isinstance(config, GoogleDriveConfig):
            for other_config in self.toolkit_configs:
                if isinstance(other_config, SystemPromptExtensionConfig):
                    other_config.invalidate_for_gdrive_change(user_id)
                    logger.debug("Notified SystemPromptExtensionConfig of GDrive credential change")
                    break
