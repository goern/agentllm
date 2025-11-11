"""Google Drive service account configuration manager.

This configuration uses a Google Cloud service account for authentication
instead of user OAuth flows. This is ideal for:
- Accessing shared team documents
- System-level document access (e.g., Release Manager system prompts)
- Enterprise deployments where all users access the same documents

Setup:
    1. Create service account in Google Cloud Console
    2. Download JSON key file
    3. Share documents with service account email
    4. Set GDRIVE_SERVICE_ACCOUNT_PATH or GDRIVE_SERVICE_ACCOUNT_JSON

See docs/google_service_account_setup.md for detailed setup instructions.
"""

import json
import os
from pathlib import Path

from google.oauth2 import service_account
from loguru import logger

from agentllm.tools.gdrive_toolkit import GoogleDriveTools

from .base import BaseToolkitConfig


class GDriveServiceAccountConfig(BaseToolkitConfig):
    """Google Drive service account configuration manager.

    Handles:
    - Service account credential loading from file or environment variable
    - Shared GoogleDriveTools toolkit creation (same for all users)
    - No per-user configuration required

    Environment Variables:
        GDRIVE_SERVICE_ACCOUNT_PATH: Path to service account JSON key file
        GDRIVE_SERVICE_ACCOUNT_JSON: Embedded service account JSON (alternative)

    Note: Only one environment variable is needed (prefer GDRIVE_SERVICE_ACCOUNT_PATH).
    """

    # Google Drive scopes for service account
    SCOPES = [
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/documents.readonly",
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/presentations.readonly",
    ]

    def __init__(self, token_storage=None):
        """Initialize Google Drive service account configuration.

        Args:
            token_storage: TokenStorage instance (not used for service accounts,
                          but kept for interface compatibility)
        """
        super().__init__(token_storage)

        # Service account credentials (shared across all users)
        self._credentials = None
        self._toolkit = None  # Single shared toolkit instance

        # Load credentials on initialization
        self._load_credentials()

    def is_required(self) -> bool:
        """Service account config is optional.

        Returns:
            False - only used when explicitly configured
        """
        return False

    def is_configured(self, user_id: str) -> bool:
        """Check if service account is configured.

        Service accounts are not user-specific - either configured for all or none.

        Args:
            user_id: User identifier (ignored for service accounts)

        Returns:
            True if service account credentials are loaded
        """
        return self._credentials is not None

    def extract_and_store_config(self, message: str, user_id: str) -> str | None:
        """Service accounts don't extract config from messages.

        Service accounts are configured via environment variables, not user messages.

        Args:
            message: User message (ignored)
            user_id: User identifier (ignored)

        Returns:
            None (no config extraction)
        """
        return None

    def get_config_prompt(self, user_id: str) -> str | None:
        """Get prompt for missing service account configuration.

        Args:
            user_id: User identifier (ignored)

        Returns:
            Error message if not configured, None if configured
        """
        if self.is_configured(user_id):
            return None

        # Service account not configured
        return (
            "❌ **Google Drive Service Account Not Configured**\n\n"
            "This agent requires a Google Cloud service account to access Google Drive documents.\n\n"
            "Administrator setup required:\n"
            "1. Create a service account in Google Cloud Console\n"
            "2. Share documents with the service account email\n"
            "3. Configure `GDRIVE_SERVICE_ACCOUNT_PATH` environment variable\n\n"
            "See `docs/google_service_account_setup.md` for detailed instructions.\n\n"
            "Please contact your administrator to complete setup."
        )

    def get_toolkit(self, user_id: str) -> GoogleDriveTools | None:
        """Get Google Drive toolkit (shared across all users).

        Args:
            user_id: User identifier (ignored - same toolkit for all users)

        Returns:
            GoogleDriveTools instance if configured, None otherwise
        """
        if not self.is_configured(user_id):
            return None

        # Return shared toolkit instance
        return self._toolkit

    def check_authorization_request(self, message: str, user_id: str) -> str | None:
        """Check if message requests Google Drive access.

        Service accounts don't require per-user authorization, so this only
        checks if the service account is configured at all.

        Args:
            message: User message
            user_id: User identifier

        Returns:
            Configuration prompt if service account not set up, None otherwise
        """
        # Check if message mentions Google Drive
        gdrive_keywords = [
            "google drive",
            "gdrive",
            "google doc",
            "google sheet",
            "google slides",
            "drive.google.com",
        ]

        message_lower = message.lower()
        mentions_gdrive = any(keyword in message_lower for keyword in gdrive_keywords)

        if not mentions_gdrive:
            return None

        # Check if service account is configured
        if self.is_configured(user_id):
            # Already configured - proceed
            return None

        # Service account not configured
        return self.get_config_prompt(user_id)

    def requires_agent_recreation(self, config_name: str) -> bool:
        """Service accounts don't require agent recreation.

        Args:
            config_name: Configuration name (ignored)

        Returns:
            False - service account is either configured at startup or not at all
        """
        return False

    def get_agent_instructions(self, user_id: str) -> list[str]:
        """Get Google Drive service account instructions.

        Args:
            user_id: User identifier (ignored)

        Returns:
            List of instruction strings if configured, empty list otherwise
        """
        if self.get_toolkit(user_id):
            return [
                "You have access to Google Drive tools to download and read "
                "Google Docs, Sheets, and Presentations. These tools access documents "
                "that have been shared with the service account. Use these tools when users "
                "ask about Google Drive documents."
            ]
        return []

    # Private helper methods

    def _load_credentials(self):
        """Load service account credentials from environment.

        Tries in order:
        1. GDRIVE_SERVICE_ACCOUNT_PATH - path to JSON key file
        2. GDRIVE_SERVICE_ACCOUNT_JSON - embedded JSON string

        Sets self._credentials and self._toolkit if successful.
        """
        # Try loading from file path first
        key_path = os.environ.get("GDRIVE_SERVICE_ACCOUNT_PATH")
        if key_path:
            try:
                credentials = self._load_credentials_from_file(key_path)
                self._credentials = credentials
                self._toolkit = GoogleDriveTools(credentials=credentials)
                logger.info(f"Loaded Google Drive service account credentials from: {key_path}")
                return
            except Exception as e:
                logger.error(f"Failed to load service account from path {key_path}: {e}")
                # Don't return - try JSON env var next

        # Try loading from embedded JSON
        key_json = os.environ.get("GDRIVE_SERVICE_ACCOUNT_JSON")
        if key_json:
            try:
                credentials = self._load_credentials_from_json(key_json)
                self._credentials = credentials
                self._toolkit = GoogleDriveTools(credentials=credentials)
                logger.info("Loaded Google Drive service account credentials from environment JSON")
                return
            except Exception as e:
                logger.error(f"Failed to load service account from JSON env var: {e}")

        # No service account configured
        logger.warning(
            "Google Drive service account not configured. Set GDRIVE_SERVICE_ACCOUNT_PATH or GDRIVE_SERVICE_ACCOUNT_JSON to enable."
        )

    def _load_credentials_from_file(self, key_path: str) -> service_account.Credentials:
        """Load service account credentials from JSON key file.

        Args:
            key_path: Path to service account JSON key file

        Returns:
            Service account credentials

        Raises:
            FileNotFoundError: If key file doesn't exist
            ValueError: If key file is invalid
        """
        path = Path(key_path)
        if not path.exists():
            raise FileNotFoundError(f"Service account key file not found: {key_path}")

        try:
            credentials = service_account.Credentials.from_service_account_file(str(path), scopes=self.SCOPES)
            logger.debug(f"Service account email: {credentials.service_account_email}")
            return credentials
        except Exception as e:
            raise ValueError(f"Invalid service account key file: {e}") from e

    def _load_credentials_from_json(self, key_json: str) -> service_account.Credentials:
        """Load service account credentials from JSON string.

        Args:
            key_json: JSON string containing service account key

        Returns:
            Service account credentials

        Raises:
            ValueError: If JSON is invalid
        """
        try:
            key_data = json.loads(key_json)
            credentials = service_account.Credentials.from_service_account_info(key_data, scopes=self.SCOPES)
            logger.debug(f"Service account email: {credentials.service_account_email}")
            return credentials
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid service account JSON: {e}") from e
        except Exception as e:
            raise ValueError(f"Failed to create credentials from JSON: {e}") from e
