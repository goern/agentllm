"""
Demo Agent - A simple example agent for showcasing AgentLLM features.

This agent demonstrates:
- Required configuration flow (favorite color)
- Simple utility tools (color palette generation)
- Extensive logging for debugging and education
- Session memory and conversation history
- Streaming and non-streaming responses
"""

import os

from agno.db.sqlite import SqliteDb

from agentllm.agents.base_agent import BaseAgentWrapper
from agentllm.agents.toolkit_configs.base import BaseToolkitConfig
from agentllm.agents.toolkit_configs.favorite_color_config import FavoriteColorConfig
from agentllm.db import TokenStorage

# Map GEMINI_API_KEY to GOOGLE_API_KEY if not set
if "GOOGLE_API_KEY" not in os.environ and "GEMINI_API_KEY" in os.environ:
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]


class DemoAgent(BaseAgentWrapper):
    """
    Demo Agent for showcasing AgentLLM platform features.

    This agent is intentionally simple and well-documented to serve as:
    1. A reference implementation for creating new agents
    2. A demonstration of the platform's capabilities
    3. An educational tool with extensive logging

    Key Features Demonstrated:
    - Required toolkit configuration (FavoriteColorConfig)
    - Simple utility tools (ColorTools)
    - Session memory and conversation history
    - Streaming and non-streaming responses
    - Per-user agent isolation
    - Configuration validation and error handling
    - Extensive logging throughout execution flow (inherited from base)

    The agent extends BaseAgentWrapper, which provides all common functionality.
    This class only implements agent-specific customizations.
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
        """
        Initialize the Demo Agent with toolkit configurations.

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
        Initialize toolkit configurations for Demo Agent.

        Returns:
            List of toolkit configuration instances
        """
        return [
            FavoriteColorConfig(token_storage=self._token_storage),  # Required: user must configure before using agent
        ]

    def _get_agent_name(self) -> str:
        """Return agent name."""
        return "demo-agent"

    def _get_agent_description(self) -> str:
        """Return agent description."""
        return "A demo agent showcasing AgentLLM features"

    def _build_agent_instructions(self, user_id: str) -> list[str]:
        """
        Build agent-specific instructions for Demo Agent.

        Args:
            user_id: User identifier

        Returns:
            List of instruction strings
        """
        return [
            "You are the **Demo Agent** - a simple example agent designed to showcase AgentLLM platform features.",
            "",
            "🎯 **Your Purpose:**",
            "- Demonstrate required configuration flow (favorite color)",
            "- Showcase simple utility tools (color palettes)",
            "- Illustrate session memory and conversation history",
            "- Provide educational examples with clear explanations",
            "",
            "🛠 **Your Capabilities:**",
            "- Generate color palettes (complementary, analogous, monochromatic)",
            "- Format text with color-themed styling",
            "- Explain your own architecture and configuration",
            "- Maintain conversation history across sessions",
            "",
            "💬 **Communication Style:**",
            "- Be friendly and educational",
            "- Use markdown formatting for clarity",
            "- Explain what you're doing when using tools",
            "- Reference the user's favorite color when relevant",
            "",
            "📚 **Educational Notes:**",
            "- You are a DEMO agent - your primary purpose is to showcase features",
            "- When users ask about your implementation, be transparent",
            "- You can explain: configuration flow, tool creation, logging, session management",
            "- Point users to relevant code files when discussing architecture",
            "",
            "🎨 **About the Favorite Color Configuration:**",
            "- This demonstrates the **required configuration pattern**",
            "- Users must configure their favorite color before you can assist them",
            "- The configuration is stored per-user and persists across sessions",
            "- Changing the favorite color recreates your agent with updated tools",
        ]

    def _get_agent_kwargs(self) -> dict:
        """
        Override to add reasoning capability to Demo Agent.

        This extends the base defaults by calling super() and adding
        reasoning=True. This is the standard pattern for customizing
        Agent constructor parameters.

        Returns:
            Dictionary with base defaults + reasoning=True
        """
        # Get base defaults (db, add_history_to_context, etc.)
        kwargs = super()._get_agent_kwargs()

        # Add demo agent-specific parameters
        kwargs["reasoning"] = True  # Enable step-by-step reasoning

        return kwargs
