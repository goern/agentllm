"""System prompt extension configuration for fetching extended instructions from Google Drive."""

import logging
import os
from typing import TYPE_CHECKING, Any

from agentllm.agents.toolkit_configs.base import BaseToolkitConfig

if TYPE_CHECKING:
    from agentllm.agents.toolkit_configs.gdrive_config import GoogleDriveConfig
    from agentllm.db.token_storage import TokenStorage

logger = logging.getLogger(__name__)


class SystemPromptExtensionConfig(BaseToolkitConfig):
    """Configuration manager for extending agent system prompts from Google Drive documents.

    This config fetches extended system instructions from a Google Drive document
    specified by the RELEASE_MANAGER_SYSTEM_PROMPT_GDRIVE_URL environment variable.

    Dependencies:
        - Requires GoogleDriveConfig to be configured for the user
        - Must be registered AFTER GoogleDriveConfig in toolkit_configs list

    Behavior:
        - Required toolkit (is_required() returns True)
        - Silent if env var not set or GDrive not configured
        - Fails agent creation if env var set, GDrive configured, but fetch fails
        - Caches fetched prompts per user
        - Invalidates cache when GDrive credentials change
    """

    def __init__(
        self,
        gdrive_config: "GoogleDriveConfig",
        token_storage: "TokenStorage | None" = None,
    ):
        """Initialize system prompt extension configuration.

        Args:
            gdrive_config: GoogleDriveConfig instance to use for fetching documents
            token_storage: Optional shared token storage (for consistency with base class)
        """
        super().__init__(token_storage)
        self._gdrive_config = gdrive_config
        self._doc_url = os.getenv("RELEASE_MANAGER_SYSTEM_PROMPT_GDRIVE_URL")
        # Per-user cache of fetched system prompts
        self._system_prompts: dict[str, str] = {}

        if self._doc_url:
            logger.info(f"System prompt extension configured with document: {self._doc_url}")
        else:
            logger.debug("System prompt extension not configured (RELEASE_MANAGER_SYSTEM_PROMPT_GDRIVE_URL not set)")

    def is_configured(self, user_id: str) -> bool:
        """Check if system prompt extension is fully configured for a user.

        Returns True if:
        - Environment variable RELEASE_MANAGER_SYSTEM_PROMPT_GDRIVE_URL is set, AND
        - Google Drive is configured for this user

        Args:
            user_id: User identifier

        Returns:
            True if configured, False otherwise
        """
        # If no document URL, extension is not configured
        if not self._doc_url:
            return False

        # Document URL is set, check if GDrive is configured
        return self._gdrive_config.is_configured(user_id)

    def extract_and_store_config(self, message: str, user_id: str) -> str | None:
        """Try to extract configuration from user message.

        System prompt extension has no extractable configuration from messages.
        Configuration comes from environment variables and GDrive credentials.

        Args:
            message: User message
            user_id: User identifier

        Returns:
            None (no configuration to extract)
        """
        return None

    def get_config_prompt(self, user_id: str) -> str | None:
        """Get prompt for missing configuration.

        System prompt extension is silent about its configuration needs.
        If GDrive is not configured, GoogleDriveConfig will handle prompting.

        Args:
            user_id: User identifier

        Returns:
            None (no prompt needed)
        """
        return None

    def get_toolkit(self, user_id: str) -> Any | None:
        """Get toolkit instance for user.

        System prompt extension doesn't provide a toolkit - it only extends
        agent instructions via get_agent_instructions().

        Args:
            user_id: User identifier

        Returns:
            None (no toolkit provided)
        """
        return None

    def check_authorization_request(self, message: str, user_id: str) -> str | None:
        """Check if message requests this toolkit and handle authorization.

        System prompt extension doesn't require separate authorization.
        It piggybacks on GoogleDriveConfig authorization.

        Args:
            message: User message
            user_id: User identifier

        Returns:
            None (no authorization needed)
        """
        return None

    def is_required(self) -> bool:
        """Check if this toolkit configuration is required.

        Returns:
            True - system prompt extension is required when configured
        """
        return True

    def get_agent_instructions(self, user_id: str) -> list[str]:
        """Get agent instructions by fetching extended system prompt from Google Drive.

        This is the core method that provides the extended system prompt to the agent.

        Behavior:
        - If env var not set: return empty list (silent)
        - If GDrive not configured: return empty list (silent, GDrive will handle prompting)
        - If GDrive configured: fetch prompt (failures propagate to fail agent creation)

        Args:
            user_id: User identifier

        Returns:
            List containing extended system prompt if available, empty list otherwise

        Raises:
            ValueError: If prompt fetch fails (will fail agent creation)
            Exception: Any other errors during fetch (will fail agent creation)
        """
        # If no document URL configured, nothing to do
        if not self._doc_url:
            logger.debug("System prompt extension skipped (no RELEASE_MANAGER_SYSTEM_PROMPT_GDRIVE_URL)")
            return []

        # If Google Drive is not configured for this user, skip silently
        # (GoogleDriveConfig will handle prompting the user)
        if not self._gdrive_config.is_configured(user_id):
            logger.info(
                f"System prompt extension skipped for user {user_id}: "
                "RELEASE_MANAGER_SYSTEM_PROMPT_GDRIVE_URL is set but Google Drive not configured"
            )
            return []

        # Google Drive is configured, so fetching the prompt is required
        # Any failures here should propagate to fail agent creation
        try:
            extended_prompt = self._fetch_extended_system_prompt(user_id)
            logger.info(f"Successfully fetched extended system prompt for user {user_id}")

            # Prepend metadata about the external prompt source
            instructions = [
                "",
                "=== EXTENDED SYSTEM PROMPT (from Google Drive) ===",
                f"Source: {self._doc_url}",
                "",
                "NOTE: Users can update this external prompt by editing the Google Doc directly.",
                "If release context seems outdated, you should:",
                "1. Inform the user about the external prompt document",
                "2. Provide the document URL above",
                "3. Suggest they update it with current release information",
                "",
                "Extended instructions below:",
                "---",
                "",
                extended_prompt,
            ]

            return instructions
        except Exception as e:
            logger.error(f"Failed to fetch extended system prompt for user {user_id}: {e}")
            # Re-raise to fail agent creation
            raise

    def _fetch_extended_system_prompt(self, user_id: str) -> str:
        """Fetch extended system prompt from Google Drive document.

        Implements caching: fetches once per user and caches the result.
        Cache is invalidated when GDrive credentials change.

        Args:
            user_id: User identifier

        Returns:
            Extended system prompt content

        Raises:
            ValueError: If document URL is not set or GDrive not configured
            Exception: If document fetch fails
        """
        # Check cache first
        if user_id in self._system_prompts:
            logger.debug(f"Using cached system prompt for user {user_id}")
            return self._system_prompts[user_id]

        # Validate prerequisites
        if not self._doc_url:
            raise ValueError("RELEASE_MANAGER_SYSTEM_PROMPT_GDRIVE_URL environment variable not set")

        if not self._gdrive_config.is_configured(user_id):
            raise ValueError(f"Google Drive is not configured for user {user_id}. Please authorize Google Drive access first.")

        # Get the Google Drive toolkit for this user
        toolkit = self._gdrive_config.get_toolkit(user_id)
        if not toolkit:
            raise ValueError(f"Failed to get Google Drive toolkit for user {user_id}. Please reconfigure Google Drive access.")

        logger.info(f"Fetching extended system prompt from {self._doc_url} for user {user_id}")

        try:
            # Fetch the document content using the toolkit
            content = toolkit.get_document_content(self._doc_url)

            if not content:
                raise ValueError(f"Failed to fetch content from {self._doc_url}. The document may be empty or inaccessible.")

            # Cache the content for this user
            self._system_prompts[user_id] = content
            logger.info(f"Successfully fetched and cached system prompt for user {user_id} ({len(content)} characters)")

            return content

        except Exception as e:
            logger.error(f"Error fetching extended system prompt from {self._doc_url}: {e}")
            raise ValueError(f"Failed to fetch extended system prompt from {self._doc_url}. Error: {str(e)}") from e

    def invalidate_for_gdrive_change(self, user_id: str) -> None:
        """Invalidate cached system prompt when Google Drive credentials change.

        This should be called by ReleaseManager when GoogleDriveConfig
        stores new credentials for a user.

        Args:
            user_id: User identifier
        """
        if user_id in self._system_prompts:
            logger.info(f"Invalidating cached system prompt for user {user_id} due to Google Drive credential change")
            del self._system_prompts[user_id]
        else:
            logger.debug(f"No cached system prompt to invalidate for user {user_id}")
