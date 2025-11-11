"""Google Drive OAuth configuration manager."""

import json
import os
import re

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from loguru import logger

from agentllm.tools.gdrive_toolkit import GoogleDriveTools

from .base import BaseToolkitConfig


class GoogleDriveConfig(BaseToolkitConfig):
    """Google Drive OAuth configuration manager.

    Handles:
    - Google Drive OAuth URL generation
    - Authorization code exchange for tokens
    - Credential storage and refresh
    - Per-user GoogleDriveTools toolkit creation

    Setup:
        Set GDRIVE_CLIENT_ID and GDRIVE_CLIENT_SECRET environment variables.
        See setup instructions below.

    Google Drive OAuth Setup:
    ------------------------
    To enable Google Drive integration, set up OAuth credentials:

    1. Go to https://console.cloud.google.com
    2. Create a new project or select an existing one
    3. Enable the Google Drive API:
       - Navigate to "APIs & Services" > "Library"
       - Search for "Google Drive API" and enable it
    4. Create OAuth 2.0 credentials:
       - Go to "APIs & Services" > "Credentials"
       - Click "Create Credentials" > "OAuth 2.0 Client ID"
       - Application type: "Web application"
       - Add authorized redirect URI: http://localhost
       - Click "Create"
    5. Copy the client_id and client_secret
    6. Set environment variables:
       - GDRIVE_CLIENT_ID=<your_client_id>
       - GDRIVE_CLIENT_SECRET=<your_client_secret>

    Users will then authorize via OAuth by:
    1. Visiting a generated authorization URL
    2. Signing in and granting permissions
    3. Copying the authorization code from the URL bar (after redirect to localhost)
    4. Pasting the code back into the chat
    """

    def __init__(self, token_storage=None):
        """Initialize Google Drive OAuth configuration.

        Args:
            token_storage: TokenStorage instance for database-backed credentials
        """
        super().__init__(token_storage)

        # Google Drive OAuth configuration from environment
        self._gdrive_client_id = os.environ.get("GDRIVE_CLIENT_ID")
        self._gdrive_client_secret = os.environ.get("GDRIVE_CLIENT_SECRET")
        self._gdrive_redirect_uri = "http://localhost"
        self._gdrive_scopes = [
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/documents.readonly",
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/presentations.readonly",
        ]

        # Store per-user Google Drive toolkits (in-memory cache)
        self._gdrive_toolkits: dict[str, GoogleDriveTools] = {}

    def is_configured(self, user_id: str) -> bool:
        """Check if Google Drive is configured for user.

        Args:
            user_id: User identifier

        Returns:
            True if user has valid Google Drive credentials
        """
        # Check database storage first (preferred)
        if self.token_storage:
            creds = self.token_storage.get_gdrive_credentials(user_id)
            if creds:
                return True

        # Fall back to legacy in-memory storage
        if user_id in self._user_configs and "gdrive_token" in self._user_configs[user_id]:
            return True

        return False

    def extract_and_store_config(self, message: str, user_id: str) -> str | None:
        """Extract and store Google Drive authorization code from message.

        Supports patterns like:
        - "my google drive code is 4/..."
        - "gdrive code: 4/..."
        - Standalone Google OAuth codes (starting with 4/)

        Args:
            message: User message that may contain auth code
            user_id: User identifier

        Returns:
            Confirmation message if code was extracted and stored,
            None if no code found in message

        Raises:
            ValueError: If authorization code is invalid
        """
        # Try to extract Google Drive auth code
        auth_code = self._extract_gdrive_code(message)

        if not auth_code:
            return None

        logger.info(f"Exchanging Google Drive authorization code for user {user_id}")

        try:
            # Exchange code for credentials
            creds = self._exchange_gdrive_code(auth_code, user_id)

            # Validate by making test API call
            service = build("drive", "v3", credentials=creds)
            user_info = service.about().get(fields="user").execute()

            logger.info(f"Google Drive token validated successfully for user {user_id}")

            # Store the credentials in database if available, otherwise in memory
            if self.token_storage:
                self.token_storage.upsert_gdrive_token(user_id, creds)
                logger.info(f"Stored Google Drive credentials in database for user {user_id}")
            else:
                # Fall back to in-memory storage (legacy)
                if user_id not in self._user_configs:
                    self._user_configs[user_id] = {}
                self._user_configs[user_id]["gdrive_token"] = creds.to_json()
                logger.info(f"Stored Google Drive credentials in memory for user {user_id}")

            # Create GoogleDriveTools toolkit for this user with credentials
            toolkit = GoogleDriveTools(credentials=creds)
            self._gdrive_toolkits[user_id] = toolkit
            logger.info(f"Created Google Drive toolkit for user {user_id}")

            # Return validation message
            user_name = user_info.get("user", {}).get("displayName", "Unknown")
            user_email = user_info.get("user", {}).get("emailAddress", "")
            return (
                f"✅ Google Drive authorized successfully!\n\n"
                f"Connected as: {user_name} ({user_email})\n\n"
                f"You can now ask me to access your Google Drive documents, "
                f"sheets, and presentations."
            )

        except Exception as e:
            logger.error(f"Failed to exchange Google Drive authorization code for user {user_id}: {e}")
            raise ValueError(f"Failed to authorize Google Drive: {str(e)}") from e

    def get_config_prompt(self, user_id: str) -> str | None:
        """Get prompt for Google Drive authorization.

        Args:
            user_id: User identifier

        Returns:
            Authorization prompt if not configured, None if configured
        """
        if self.is_configured(user_id):
            return None

        # Generate OAuth URL and return prompt
        try:
            oauth_url = self._generate_gdrive_oauth_url(user_id)
            prompt = (
                "🔐 **Google Drive Authorization Required**\n\n"
                "To use this agent, you need to authorize Google Drive access:\n\n"
                f"1. **Visit this URL**: {oauth_url}\n"
                "2. Sign in and authorize the application\n"
                "3. After authorizing, you'll be redirected to a page that won't load\n"
                "4. **Copy the entire URL** from your browser's address bar\n"
                "   It will look like: `http://localhost?code=4/0AeaYSHB...`\n"
                "5. **Paste the URL here** (or just the code starting with '4/')\n\n"
                "Once authorized, you'll be able to use the agent."
            )
            return prompt
        except ValueError as e:
            # OAuth not configured
            error_msg = (
                f"❌ {str(e)}\n\nGoogle Drive integration requires OAuth credentials to be configured. Please contact your administrator."
            )
            return error_msg

    def get_toolkit(self, user_id: str) -> GoogleDriveTools | None:
        """Get Google Drive toolkit for user if configured.

        Args:
            user_id: User identifier

        Returns:
            GoogleDriveTools instance if configured, None otherwise
        """
        # Ensure credentials are loaded (will create toolkit if needed)
        self._get_gdrive_credentials(user_id)

        return self._gdrive_toolkits.get(user_id)

    def check_authorization_request(self, message: str, user_id: str) -> str | None:
        """Check if message requests Google Drive access and handle authorization.

        Args:
            message: User message
            user_id: User identifier

        Returns:
            OAuth URL prompt if user needs to authorize, None otherwise
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

        # Check if user already has Google Drive credentials
        if self.is_configured(user_id):
            # User already authorized, proceed
            logger.info(f"User {user_id} has Google Drive access")
            return None

        # User needs to authorize - generate OAuth URL
        try:
            oauth_url = self._generate_gdrive_oauth_url(user_id)
            prompt = (
                "🔐 **Google Drive Authorization Required**\n\n"
                "To access Google Drive documents, please authorize:\n\n"
                f"1. **Visit this URL**: {oauth_url}\n"
                "2. Sign in and authorize the application\n"
                "3. After authorizing, you'll be redirected to a page that won't load\n"
                "4. **Copy the entire URL** from your browser's address bar\n"
                "   It will look like: `http://localhost?code=4/0AeaYSHB...`\n"
                "5. **Paste the URL here** (or just the code starting with '4/')\n\n"
                "Once authorized, I'll be able to access your Google Drive documents."
            )
            return prompt

        except ValueError as e:
            # OAuth not configured
            error_msg = (
                f"❌ {str(e)}\n\nGoogle Drive integration requires OAuth credentials to be configured. Please contact your administrator."
            )
            return error_msg

    def requires_agent_recreation(self, config_name: str) -> bool:
        """Check if this config requires agent recreation.

        Google Drive authorization adds new tools to the agent.

        Args:
            config_name: Configuration name

        Returns:
            True if config is gdrive_token
        """
        return config_name == "gdrive_token"

    def get_agent_instructions(self, user_id: str) -> list[str]:
        """Get Google Drive-specific agent instructions.

        Args:
            user_id: User identifier

        Returns:
            List of instruction strings
        """
        if self.get_toolkit(user_id):
            return [
                "You have access to Google Drive tools to download and manage "
                "Google Docs, Sheets, and Presentations. Use these tools when users "
                "ask about Google Drive documents."
            ]
        return []

    # Private helper methods

    def _extract_gdrive_code(self, message: str) -> str | None:
        """Extract Google Drive auth code from user message.

        Supports:
        - Full redirect URLs: http://localhost?code=4/0AeaYSHB...
        - Code parameter: code=4/0AeaYSHB...
        - Natural language: "my google drive code is 4/..."
        - Standalone codes: 4/0AeaYSHB...

        Args:
            message: User message text

        Returns:
            Extracted auth code or None if not found
        """
        # First, try to extract from URL (most common - user pastes redirect URL)
        # Match: http://localhost?code=4/... or http://localhost/?code=4/...
        url_pattern = r"(?:https?://[^\s]*[?&])?code=([^&\s]+)"
        match = re.search(url_pattern, message, re.IGNORECASE)
        if match:
            code = match.group(1)
            # Verify it looks like a Google OAuth code (starts with 4/)
            if code.startswith("4/"):
                return code

        # Create flexible regex patterns for natural language
        patterns = [
            # "my google drive code is 4/..."
            r"(?:my\s+)?(?:google\s+drive|gdrive|drive)\s+"
            r"(?:auth\s+)?code\s+(?:is|=|:)\s+([^\s]+)",
            # "set google drive code to 4/..."
            r"set\s+(?:google\s+drive|gdrive|drive)\s+code\s+to\s+([^\s]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                return match.group(1)

        # Try to detect standalone Google OAuth authorization codes
        # Google OAuth codes typically:
        # - Start with "4/"
        # - Are followed by many alphanumeric characters, underscores, hyphens
        oauth_code_pattern = r"(?:^|\s)(4/[A-Za-z0-9_\-\.]+)(?:\s|$)"
        match = re.search(oauth_code_pattern, message)
        if match:
            return match.group(1)

        return None

    def _generate_gdrive_oauth_url(self, user_id: str) -> str:
        """Generate Google Drive OAuth URL for user authorization.

        Args:
            user_id: User identifier (used as OAuth state parameter)

        Returns:
            OAuth authorization URL

        Raises:
            ValueError: If OAuth client credentials are not configured
        """
        if not self._gdrive_client_id or not self._gdrive_client_secret:
            raise ValueError(
                "Google Drive OAuth is not configured. Please set GDRIVE_CLIENT_ID and GDRIVE_CLIENT_SECRET environment variables."
            )

        # Create OAuth flow
        flow = Flow.from_client_config(
            {
                "installed": {
                    "client_id": self._gdrive_client_id,
                    "client_secret": self._gdrive_client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [self._gdrive_redirect_uri],
                }
            },
            scopes=self._gdrive_scopes,
        )
        flow.redirect_uri = self._gdrive_redirect_uri

        # Generate authorization URL with state parameter
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes=False,  # Don't include previously granted scopes
            state=user_id,
            prompt="consent",  # Force consent screen to ensure refresh_token
        )

        return auth_url

    def _exchange_gdrive_code(self, code: str, user_id: str) -> Credentials:
        """Exchange OAuth authorization code for access tokens.

        Args:
            code: Authorization code from OAuth flow
            user_id: User identifier

        Returns:
            Google OAuth2 credentials

        Raises:
            ValueError: If OAuth client credentials are not configured or code is invalid
        """
        if not self._gdrive_client_id or not self._gdrive_client_secret:
            raise ValueError(
                "Google Drive OAuth is not configured. Please set GDRIVE_CLIENT_ID and GDRIVE_CLIENT_SECRET environment variables."
            )

        try:
            # Create OAuth flow
            flow = Flow.from_client_config(
                {
                    "installed": {
                        "client_id": self._gdrive_client_id,
                        "client_secret": self._gdrive_client_secret,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "redirect_uris": [self._gdrive_redirect_uri],
                    }
                },
                scopes=self._gdrive_scopes,
            )
            flow.redirect_uri = self._gdrive_redirect_uri

            # Exchange code for tokens
            flow.fetch_token(code=code)

            return flow.credentials

        except Exception as e:
            logger.error(f"Failed to exchange Google Drive authorization code for user {user_id}: {e}")
            raise ValueError(f"Invalid authorization code: {str(e)}") from e

    def _get_gdrive_credentials(self, user_id: str) -> Credentials | None:
        """Get stored Google Drive credentials for a user.

        Also ensures the toolkit is created for the user if it doesn't exist.

        Args:
            user_id: User identifier

        Returns:
            Google OAuth2 credentials if stored, None otherwise
        """
        creds = None

        # Try to get from database first (preferred)
        if self.token_storage:
            creds = self.token_storage.get_gdrive_credentials(user_id)
            if creds:
                logger.debug(f"Retrieved Google Drive credentials from database for user {user_id}")

                # Refresh if expired
                if creds.expired and creds.refresh_token:
                    try:
                        creds.refresh(Request())
                        # Update stored credentials with new token
                        self.token_storage.upsert_gdrive_token(user_id, creds)
                        logger.info(f"Refreshed Google Drive token for user {user_id}")
                    except Exception as e:
                        logger.error(f"Failed to refresh Google Drive token for user {user_id}: {e}")

                # Ensure toolkit exists for this user
                if user_id not in self._gdrive_toolkits:
                    toolkit = GoogleDriveTools(credentials=creds)
                    self._gdrive_toolkits[user_id] = toolkit
                    logger.info(f"Recreated Google Drive toolkit for user {user_id}")

                return creds

        # Fall back to legacy in-memory storage
        if user_id in self._user_configs:
            token_json = self._user_configs[user_id].get("gdrive_token")
            if token_json:
                try:
                    # Parse credentials from JSON
                    token_data = json.loads(token_json)
                    creds = Credentials.from_authorized_user_info(token_data, self._gdrive_scopes)

                    # Refresh if expired
                    if creds.expired and creds.refresh_token:
                        creds.refresh(Request())
                        # Update stored credentials with new token
                        self._user_configs[user_id]["gdrive_token"] = creds.to_json()
                        logger.info(f"Refreshed Google Drive token (in-memory) for user {user_id}")

                    # Ensure toolkit exists for this user
                    if user_id not in self._gdrive_toolkits:
                        toolkit = GoogleDriveTools(credentials=creds)
                        self._gdrive_toolkits[user_id] = toolkit
                        logger.info(f"Recreated Google Drive toolkit (legacy) for user {user_id}")

                    return creds

                except Exception as e:
                    logger.error(f"Failed to load Google Drive credentials for user {user_id}: {e}")

        return None
