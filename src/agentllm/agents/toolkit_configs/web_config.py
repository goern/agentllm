"""Web access configuration for fetching public documentation.

This configuration provides web scraping capabilities for accessing
public documentation pages, particularly Red Hat documentation.
"""

from loguru import logger

from agentllm.tools.web_toolkit import WebToolkit

from .base import BaseToolkitConfig


class WebConfig(BaseToolkitConfig):
    """Web access configuration manager.

    Provides access to public web pages for documentation fetching.
    No authentication required as this accesses public URLs only.
    """

    def __init__(self, allowed_domains: list[str] | None = None):
        """Initialize Web configuration.

        Args:
            allowed_domains: Optional list of allowed domains (for display only).
                           Domain restriction is enforced at toolkit level (*.redhat.com).
        """
        super().__init__(token_storage=None)  # No token storage needed
        self._allowed_domains = allowed_domains or ["*.redhat.com"]
        self._web_toolkit: WebToolkit | None = None

    def is_configured(self, user_id: str) -> bool:
        """Check if web access is configured.

        Web access is always available for public URLs.

        Args:
            user_id: User identifier (unused, always returns True)

        Returns:
            True (web access is always available)
        """
        return True

    def extract_and_store_config(self, message: str, user_id: str) -> str | None:
        """Extract and store configuration from user message.

        Web access requires no configuration.

        Args:
            message: User message (unused)
            user_id: User identifier (unused)

        Returns:
            None (no configuration needed)
        """
        return None

    def get_config_prompt(self, user_id: str) -> str | None:
        """Get prompt for configuration.

        Web access requires no configuration.

        Args:
            user_id: User identifier (unused)

        Returns:
            None (no prompt needed)
        """
        return None

    def get_toolkit(self, user_id: str) -> WebToolkit | None:
        """Get web toolkit.

        Args:
            user_id: User identifier (unused)

        Returns:
            WebToolkit instance
        """
        if self._web_toolkit is None:
            logger.info("Creating WebToolkit instance")
            self._web_toolkit = WebToolkit(
                fetch_url=True,
            )

        return self._web_toolkit

    def check_authorization_request(self, message: str, user_id: str) -> str | None:
        """Check if message requests web access.

        Web access requires no authorization.

        Args:
            message: User message (unused)
            user_id: User identifier (unused)

        Returns:
            None (no authorization needed)
        """
        return None

    def requires_agent_recreation(self, config_name: str) -> bool:
        """Check if this config requires agent recreation.

        Web access requires no configuration changes.

        Args:
            config_name: Configuration name (unused)

        Returns:
            False (never requires recreation)
        """
        return False

    def get_agent_instructions(self, user_id: str) -> list[str]:
        """Get web access specific agent instructions.

        Args:
            user_id: User identifier (unused)

        Returns:
            List of instruction strings
        """
        return [
            "Web Access Tools:",
            "- You have access to fetch content from public web pages",
            "- Available tool: fetch_url(url, extract_text=True)",
            "- Use this to access Red Hat documentation pages like:",
            "  * RHDH Lifecycle: https://access.redhat.com/support/policy/updates/developerhub",
            "  * Red Hat severity definitions: https://access.redhat.com/support/policy/severity",
            "  * Red Hat SLA policy: https://access.redhat.com/support/offerings/production/sla",
            f"- Allowed domains: {', '.join(self._allowed_domains)}",
            "- The tool extracts readable text from HTML by default",
            "- Use extract_text=False if you need raw HTML content",
        ]

    def is_required(self) -> bool:
        """Check if this toolkit is required.

        Returns:
            False - Web access is optional (always available but not mandatory)
        """
        return False
