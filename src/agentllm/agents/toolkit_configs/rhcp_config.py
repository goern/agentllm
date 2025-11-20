"""Red Hat Customer Portal (RHCP) configuration manager.

IMPORTANT: This configuration provides READ-ONLY access to RHCP.
The toolkit does not support creating, updating, or modifying customer cases.
"""

import re

from loguru import logger

from agentllm.tools.rhcp_toolkit import RHCPTools

from .base import BaseToolkitConfig


class RHCPConfig(BaseToolkitConfig):
    """Red Hat Customer Portal configuration manager.

    Handles:
    - RHCP offline token extraction from messages
    - RHCP connection validation
    - Per-user RHCP toolkit creation and management

    READ-ONLY ACCESS:
        This configuration provides read-only access to customer cases.
        No case creation, updates, or modifications are supported.

    Setup:
        Users provide their RHCP offline token through chat messages.
        The token is validated by exchanging it for an access token.
    """

    def __init__(self, token_storage=None):
        """Initialize RHCP configuration.

        Args:
            token_storage: TokenStorage instance for database-backed credentials
        """
        super().__init__(token_storage)

        # Store per-user RHCP toolkits (in-memory cache)
        self._rhcp_toolkits: dict[str, RHCPTools] = {}

    def is_configured(self, user_id: str) -> bool:
        """Check if RHCP is configured for user.

        Args:
            user_id: User identifier

        Returns:
            True if user has a valid RHCP offline token
        """
        # Check database storage first (preferred)
        if self.token_storage:
            token_data = self.token_storage.get_rhcp_token(user_id)
            if token_data:
                return True

        # Fall back to legacy in-memory storage
        if user_id in self._user_configs and "rhcp_offline_token" in self._user_configs[user_id]:
            return True

        return False

    def extract_and_store_config(self, message: str, user_id: str) -> str | None:
        """Extract and store RHCP offline token from user message.

        Supports patterns like:
        - "my rhcp token is abc123..."
        - "rhcp token: abc123..."
        - "rhcp_token = abc123..."
        - "set rhcp token to abc123..."
        - "my offline token is abc123..."
        - Standalone long alphanumeric tokens (100+ characters)

        Args:
            message: User message that may contain RHCP offline token
            user_id: User identifier

        Returns:
            Confirmation message if token was extracted and stored,
            None if no token found in message

        Raises:
            ValueError: If RHCP offline token is invalid
        """
        # Try to extract RHCP offline token
        offline_token = self._extract_rhcp_token(message)

        if not offline_token:
            return None

        logger.info(f"Validating RHCP offline token for user {user_id}")

        try:
            # Create toolkit with the offline token
            toolkit = RHCPTools(
                offline_token=offline_token,
                get_case=True,
                search_cases=True,
            )

            # Validate the connection
            success, validation_message = toolkit.validate_connection()

            if not success:
                logger.error(f"RHCP token validation failed for user {user_id}: {validation_message}")
                raise ValueError(f"Invalid RHCP offline token: {validation_message}")

            logger.info(f"RHCP offline token validated successfully for user {user_id}")

            # Store the token in database if available, otherwise in memory
            if self.token_storage:
                self.token_storage.upsert_rhcp_token(
                    user_id=user_id,
                    offline_token=offline_token,
                )
                logger.info(f"Stored RHCP offline token in database for user {user_id}")
            else:
                # Fall back to in-memory storage (legacy)
                if user_id not in self._user_configs:
                    self._user_configs[user_id] = {}
                self._user_configs[user_id]["rhcp_offline_token"] = offline_token
                logger.info(f"Stored RHCP offline token in memory for user {user_id}")

            # Store the toolkit for this user
            self._rhcp_toolkits[user_id] = toolkit

            # Return confirmation with validation message
            return (
                f"{validation_message}\n\n"
                f"You can now ask me to:\n"
                f"- Get customer case information\n"
                f"- Check case severity and escalation status\n"
                f"- Verify customer entitlements"
            )

        except Exception as e:
            logger.error(f"Failed to validate RHCP offline token for user {user_id}: {e}")
            raise ValueError(f"Failed to validate RHCP offline token: {str(e)}") from e

    def get_config_prompt(self, user_id: str) -> str | None:
        """Get prompt for RHCP offline token.

        Args:
            user_id: User identifier

        Returns:
            Prompt if not configured, None if configured
        """
        if self.is_configured(user_id):
            return None

        return (
            "🔑 **Red Hat Customer Portal (RHCP) Configuration Required**\n\n"
            "To access customer case information, please provide your RHCP offline token:\n\n"
            "Say: 'My RHCP offline token is YOUR_OFFLINE_TOKEN_HERE'\n\n"
            "To get an RHCP offline token:\n"
            "1. Go to https://access.redhat.com/management/api\n"
            "2. Click 'Generate Token' under 'Offline Token'\n"
            "3. Copy the token (it will be a long string)\n"
            "4. Send it to me in the format above\n\n"
            "See also: https://access.redhat.com/articles/3626371"
        )

    def get_toolkit(self, user_id: str) -> RHCPTools | None:
        """Get RHCP toolkit for user if configured.

        Args:
            user_id: User identifier

        Returns:
            RHCPTools instance if configured, None otherwise
        """
        # Return cached toolkit if available
        if user_id in self._rhcp_toolkits:
            return self._rhcp_toolkits[user_id]

        # If we have token but no toolkit (e.g., after restart), recreate it
        if not self.is_configured(user_id):
            return None

        # Recreate toolkit from database or memory
        toolkit = None
        if self.token_storage:
            # Get credentials from database
            try:
                token_data = self.token_storage.get_rhcp_token(user_id)
                if not token_data:
                    logger.error(f"No RHCP offline token found in database for user {user_id}")
                    return None

                toolkit = RHCPTools(
                    offline_token=token_data["offline_token"],
                    get_case=True,
                    search_cases=True,
                )
                logger.info(f"Recreated RHCP toolkit from database for user {user_id}")
            except Exception as e:
                logger.error(f"Failed to create RHCP toolkit from database: {e}")
                return None
        else:
            # Use legacy in-memory authentication
            if user_id in self._user_configs and "rhcp_offline_token" in self._user_configs[user_id]:
                offline_token = self._user_configs[user_id]["rhcp_offline_token"]
                toolkit = RHCPTools(
                    offline_token=offline_token,
                    get_case=True,
                    search_cases=True,
                )
                logger.info(f"Recreated RHCP toolkit (legacy) for user {user_id}")

        if toolkit:
            self._rhcp_toolkits[user_id] = toolkit

        return toolkit

    def check_authorization_request(self, message: str, user_id: str) -> str | None:
        """Check if message requests RHCP access and prompt if needed.

        Args:
            message: User message
            user_id: User identifier

        Returns:
            RHCP token prompt if user needs to configure, None otherwise
        """
        # Check if message mentions RHCP or customer cases
        rhcp_keywords = [
            "rhcp",
            "customer portal",
            "customer case",
            "case number",
            "entitlement",
            "access.redhat.com",
        ]

        message_lower = message.lower()
        mentions_rhcp = any(keyword in message_lower for keyword in rhcp_keywords)

        if not mentions_rhcp:
            return None

        # Check if user already has RHCP configured
        if self.is_configured(user_id):
            logger.info(f"User {user_id} has RHCP access")
            return None

        # User needs to configure RHCP
        return self.get_config_prompt(user_id)

    def requires_agent_recreation(self, config_name: str) -> bool:
        """Check if this config requires agent recreation.

        RHCP offline token configuration adds new tools to the agent.

        Args:
            config_name: Configuration name

        Returns:
            True if config is rhcp_offline_token
        """
        return config_name == "rhcp_offline_token"

    def get_agent_instructions(self, user_id: str) -> list[str]:
        """Get RHCP-specific agent instructions.

        Args:
            user_id: User identifier

        Returns:
            List of instruction strings
        """
        if self.get_toolkit(user_id):
            return [
                "You have access to Red Hat Customer Portal (RHCP) tools to get customer case information, "
                "check case severity, escalation status, and verify entitlements. "
                "Use these tools when users ask about customer cases or entitlements."
            ]
        return []

    def is_required(self) -> bool:
        """Check if this toolkit is required.

        Returns:
            False - RHCP is optional (only prompted when mentioned)
        """
        return False

    # Private helper methods

    def _extract_rhcp_token(self, message: str) -> str | None:
        """Extract RHCP offline token from user message.

        Args:
            message: User message text

        Returns:
            Extracted offline token or None if not found
        """
        # Create flexible regex patterns for explicit mentions
        patterns = [
            # "my rhcp token is VALUE"
            r"(?:my\s+)?rhcp\s+(?:offline\s+)?token\s+(?:is|=|:)\s+([^\s]+)",
            # "set rhcp token to VALUE"
            r"set\s+rhcp\s+(?:offline\s+)?token\s+to\s+([^\s]+)",
            # "rhcp token: VALUE"
            r"rhcp\s+(?:offline\s+)?token:\s*([^\s]+)",
            # "my offline token is VALUE"
            r"(?:my\s+)?offline\s+token\s+(?:is|=|:)\s+([^\s]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                return match.group(1)

        # Try to detect standalone long tokens (100+ characters)
        # RHCP offline tokens are typically very long (200+ chars)
        # Format: eyJhbGciOiJIUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICJhZD...
        token_pattern = r"(?:^|\s)([A-Za-z0-9_\-\.]{100,})(?:\s|$)"
        match = re.search(token_pattern, message)
        if match:
            potential_token = match.group(1)
            # RHCP tokens typically start with "eyJ" (base64 JWT header)
            if potential_token.startswith("eyJ"):
                return potential_token

        return None
