"""
Favorite Color Configuration for Demo Agent.

This is a simple example toolkit config that demonstrates the configuration
flow without requiring external APIs or complex OAuth flows.
"""

import re
from typing import Any

from loguru import logger

from agentllm.utils.logging import safe_log_content

from .base import BaseToolkitConfig


class FavoriteColorConfig(BaseToolkitConfig):
    """
    Simple configuration example: stores user's favorite color.

    This toolkit demonstrates:
    - Required configuration flow (prompts immediately on first use)
    - Natural language extraction from user messages
    - Simple validation logic
    - In-memory storage (no database required)
    - Extensive logging for educational purposes
    """

    # Supported colors for validation
    VALID_COLORS = [
        "red",
        "blue",
        "green",
        "darkseagreen4",
        "yellow",
        "purple",
        "orange",
        "pink",
        "black",
        "white",
        "brown",
    ]

    def __init__(self, token_storage=None):
        """
        Initialize FavoriteColorConfig.

        Args:
            token_storage: Optional token storage (not used in this simple example)
        """
        logger.debug("=" * 80)
        logger.debug("FavoriteColorConfig.__init__() called")
        super().__init__(token_storage)

        # In-memory storage: user_id -> color
        self._user_colors: dict[str, str] = {}

        logger.debug(f"Initialized with valid colors: {', '.join(self.VALID_COLORS)}")
        logger.debug("=" * 80)

    def is_required(self) -> bool:
        """
        Mark this as a required configuration.

        Required configs prompt immediately when user first interacts with agent,
        blocking execution until configured.
        """
        logger.debug("is_required() called -> returning True (required config)")
        return True

    def is_configured(self, user_id: str) -> bool:
        """
        Check if user has configured their favorite color.

        Args:
            user_id: User identifier

        Returns:
            True if color is stored, False otherwise
        """
        logger.debug("=" * 80)
        logger.debug(f"is_configured() called for user_id={user_id}")

        configured = user_id in self._user_colors

        if configured:
            color = self._user_colors[user_id]
            logger.info(f"User {user_id} IS configured with color: {color}")
        else:
            logger.info(f"User {user_id} is NOT configured yet")

        logger.debug(f"is_configured() returning: {configured}")
        logger.debug("=" * 80)

        return configured

    def extract_and_store_config(self, message: str, user_id: str) -> str | None:
        """
        Extract favorite color from user message and store it.

        Supports patterns like:
        - "my favorite color is blue"
        - "favorite color: red"
        - "I like green"
        - "set color to yellow"

        Args:
            message: User's message
            user_id: User identifier

        Returns:
            Confirmation message if color found and stored, None otherwise

        Raises:
            ValueError: If color is invalid
        """
        logger.debug("=" * 80)
        logger.info(f">>> extract_and_store_config() STARTED - user_id={user_id}")
        logger.debug(safe_log_content(message, "Message to analyze"))

        # Try to extract color using regex patterns
        color = self._extract_color_from_message(message)

        if not color:
            logger.debug("No color pattern found in message")
            logger.info("<<< extract_and_store_config() FINISHED (no color found)")
            logger.debug("=" * 80)
            return None

        logger.info(f"Extracted color candidate: '{color}'")

        # Validate color
        if color not in self.VALID_COLORS:
            error_msg = f"Invalid color '{color}'. Supported colors: {', '.join(self.VALID_COLORS)}"
            logger.warning(f"Color validation failed: {error_msg}")
            logger.info("<<< extract_and_store_config() FINISHED (validation error)")
            logger.debug("=" * 80)
            raise ValueError(error_msg)

        logger.info(f"✅ Color '{color}' is valid")

        # Store the color
        self._user_colors[user_id] = color
        logger.info(f"✅ Stored color '{color}' for user {user_id}")
        logger.debug(f"Current user colors storage: {self._user_colors}")

        # Create confirmation message
        confirmation = (
            f"✅ **Favorite Color Configured!**\n\n"
            f"Your favorite color has been set to: **{color}**\n\n"
            f"The demo agent will now use this preference in conversations and tools."
        )

        logger.info("<<< extract_and_store_config() FINISHED (success)")
        logger.debug("=" * 80)

        return confirmation

    def _extract_color_from_message(self, message: str) -> str | None:
        """
        Extract color from message using various patterns.

        Args:
            message: User's message

        Returns:
            Extracted color (lowercase) or None
        """
        logger.debug("_extract_color_from_message() called")

        # Pattern 1: "my favorite color is X"
        pattern1 = r"(?:my\s+)?favorite\s+color\s+(?:is|=|:)\s+(\w+)"
        match = re.search(pattern1, message, re.IGNORECASE)
        if match:
            color = match.group(1).lower()
            logger.debug(f"Pattern 1 matched: '{color}' (my favorite color is X)")
            return color

        # Pattern 2: "I like X" or "I love X"
        pattern2 = r"I\s+(?:like|love|prefer)\s+(\w+)"
        match = re.search(pattern2, message, re.IGNORECASE)
        if match:
            color = match.group(1).lower()
            logger.debug(f"Pattern 2 matched: '{color}' (I like/love X)")
            return color

        # Pattern 3: "set color to X" or "configure color X"
        pattern3 = r"(?:set|configure)\s+color\s+(?:to\s+)?(\w+)"
        match = re.search(pattern3, message, re.IGNORECASE)
        if match:
            color = match.group(1).lower()
            logger.debug(f"Pattern 3 matched: '{color}' (set color to X)")
            return color

        # Pattern 4: "color: X" or "color = X"
        pattern4 = r"color\s*[:=]\s*(\w+)"
        match = re.search(pattern4, message, re.IGNORECASE)
        if match:
            color = match.group(1).lower()
            logger.debug(f"Pattern 4 matched: '{color}' (color: X)")
            return color

        logger.debug("No color pattern matched")
        return None

    def get_config_prompt(self, user_id: str) -> str | None:
        """
        Return prompt asking user for their favorite color.

        Args:
            user_id: User identifier

        Returns:
            Configuration prompt if not configured, None if already configured
        """
        logger.debug("=" * 80)
        logger.debug(f"get_config_prompt() called for user_id={user_id}")

        if self.is_configured(user_id):
            logger.debug("User already configured, returning None")
            logger.debug("=" * 80)
            return None

        prompt = (
            "🎨 **Welcome to the Demo Agent!**\n\n"
            "Before we begin, I need to know your favorite color. "
            "This is a simple example of the **required configuration flow** in AgentLLM.\n\n"
            "**Please tell me your favorite color:**\n\n"
            "Examples:\n"
            "- 'My favorite color is blue'\n"
            "- 'I like green'\n"
            "- 'Set color to red'\n\n"
            f"**Supported colors:** {', '.join(self.VALID_COLORS)}\n\n"
            "_(This demonstrates how agents can require configuration before proceeding)_"
        )

        logger.info(f"Returning configuration prompt for user {user_id}")
        logger.debug("=" * 80)

        return prompt

    def get_toolkit(self, user_id: str) -> Any | None:
        """
        Get toolkit instance for this configuration.

        Returns ColorTools configured with the user's favorite color.

        Args:
            user_id: User identifier

        Returns:
            ColorTools instance if configured, None otherwise
        """
        logger.debug(f"get_toolkit() called for user_id={user_id}")

        if not self.is_configured(user_id):
            logger.debug(f"User {user_id} not configured, returning None")
            return None

        favorite_color = self.get_user_color(user_id)
        if favorite_color:
            logger.info(f"Creating ColorTools for user {user_id} with color={favorite_color}")
            from agentllm.tools.color_toolkit import ColorTools

            return ColorTools(favorite_color=favorite_color)

        logger.warning(f"User {user_id} configured but color is None, returning None")
        return None

    def check_authorization_request(self, message: str, user_id: str) -> str | None:
        """
        Check if message is requesting color configuration.

        This is used for optional configs that prompt when user mentions
        related features. Since this is a required config, this method
        isn't typically used, but we implement it for completeness.

        Args:
            message: User's message
            user_id: User identifier

        Returns:
            Configuration prompt if request detected, None otherwise
        """
        logger.debug(f"check_authorization_request() called for user_id={user_id}")

        # Since this is required config, we don't need special detection
        # But we can still detect explicit requests to reconfigure
        reconfigure_patterns = [
            r"change.*color",
            r"update.*color",
            r"reconfigure.*color",
            r"reset.*color",
        ]

        for pattern in reconfigure_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                logger.info(f"Detected reconfiguration request for user {user_id}")
                return self.get_config_prompt(user_id)

        logger.debug("No authorization request detected")
        return None

    def get_agent_instructions(self, user_id: str) -> list[str]:
        """
        Get agent instructions that include user's favorite color.

        These instructions are added to the agent's system prompt.

        Args:
            user_id: User identifier

        Returns:
            List of instruction strings
        """
        logger.debug("=" * 80)
        logger.debug(f"get_agent_instructions() called for user_id={user_id}")

        if not self.is_configured(user_id):
            logger.debug("User not configured, returning empty instructions")
            logger.debug("=" * 80)
            return []

        color = self._user_colors[user_id]

        instructions = [
            f"The user's favorite color is {color}.",
            f"When relevant to the conversation, incorporate references to {color}.",
            "Use the color tools to generate palettes and themes based on this preference.",
        ]

        logger.info(f"Returning {len(instructions)} instructions for user {user_id}")
        logger.debug(f"Instructions: {instructions}")
        logger.debug("=" * 80)

        return instructions

    def get_user_color(self, user_id: str) -> str | None:
        """
        Get the stored favorite color for a user.

        This is a helper method for other components (like ColorTools)
        to access the configured color.

        Args:
            user_id: User identifier

        Returns:
            Color string or None if not configured
        """
        logger.debug(f"get_user_color() called for user_id={user_id}")
        color = self._user_colors.get(user_id)
        logger.debug(f"Returning color: {color}")
        return color

    def requires_agent_recreation(self, config_name: str) -> bool:
        """
        Determine if agent needs recreation when this config changes.

        Since changing the favorite color changes the agent's instructions
        and available tools, we need to recreate the agent.

        Args:
            config_name: Name of the configuration that changed

        Returns:
            True if agent should be recreated
        """
        logger.debug(f"requires_agent_recreation() called for config: {config_name}")

        # Recreate agent when favorite color is configured/changed
        # Accept both "favorite_color" and "favoritecolor" (without underscore)
        should_recreate = config_name in ["favorite_color", "favoritecolor"]

        logger.debug(f"Returning: {should_recreate}")
        return should_recreate
