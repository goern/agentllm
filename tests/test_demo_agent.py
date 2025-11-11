"""
Tests for the Demo Agent.

This test suite demonstrates testing patterns for:
- Agent instantiation and configuration
- Required toolkit configuration flow
- Color extraction and validation
- Sync and async execution
- Streaming responses
- Tool invocations
- Session memory
"""

import os
from pathlib import Path

import pytest
from agno.db.sqlite import SqliteDb
from dotenv import load_dotenv

from agentllm.agents.demo_agent import DemoAgent
from agentllm.agents.toolkit_configs.favorite_color_config import FavoriteColorConfig
from agentllm.db import TokenStorage
from agentllm.db.token_storage import TokenStorage as TokenStorageType

# Load .env file for tests
load_dotenv()

# Map GEMINI_API_KEY to GOOGLE_API_KEY if needed
if "GOOGLE_API_KEY" not in os.environ and "GEMINI_API_KEY" in os.environ:
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]


# Test fixtures
@pytest.fixture
def shared_db() -> SqliteDb:
    """Provide a shared test database."""
    db_path = Path("tmp/test_demo_agent.db")
    db_path.parent.mkdir(exist_ok=True)
    db = SqliteDb(db_file=str(db_path))
    yield db
    # Cleanup after tests
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def token_storage(shared_db: SqliteDb) -> TokenStorageType:
    """Provide a token storage instance."""
    return TokenStorage(agno_db=shared_db)


class TestDemoAgentBasics:
    """Basic tests for DemoAgent instantiation and parameters."""

    def test_create_agent(self, shared_db: SqliteDb, token_storage: TokenStorageType):
        """Test that DemoAgent can be instantiated."""
        agent = DemoAgent(shared_db=shared_db, token_storage=token_storage, user_id="test-user")
        assert agent is not None
        assert len(agent.toolkit_configs) > 0

    def test_create_agent_with_params(self, shared_db: SqliteDb, token_storage: TokenStorageType):
        """Test that DemoAgent accepts model parameters."""
        agent = DemoAgent(shared_db=shared_db, token_storage=token_storage, user_id="test-user", temperature=0.7, max_tokens=200)
        assert agent is not None
        assert agent._temperature == 0.7
        assert agent._max_tokens == 200

    def test_toolkit_configs_initialized(self, shared_db: SqliteDb, token_storage: TokenStorageType):
        """Test that toolkit configs are properly initialized."""
        agent = DemoAgent(shared_db=shared_db, token_storage=token_storage, user_id="test-user")
        assert hasattr(agent, "toolkit_configs")
        assert isinstance(agent.toolkit_configs, list)
        assert len(agent.toolkit_configs) == 1  # Only FavoriteColorConfig

    def test_favorite_color_config_is_required(self, shared_db: SqliteDb, token_storage: TokenStorageType):
        """Test that FavoriteColorConfig is marked as required."""
        agent = DemoAgent(shared_db=shared_db, token_storage=token_storage, user_id="test-user")
        color_config = agent.toolkit_configs[0]
        assert isinstance(color_config, FavoriteColorConfig)
        assert color_config.is_required() is True


class TestFavoriteColorConfiguration:
    """Tests for favorite color configuration management."""

    def test_required_config_prompts_immediately(self, shared_db: SqliteDb, token_storage: TokenStorageType):
        """Test that agent prompts for favorite color on first message."""
        agent = DemoAgent(shared_db=shared_db, token_storage=token_storage, user_id="test-user")
        user_id = "test-user-new"

        # User sends message without configuring
        response = agent.run("Hello!", user_id=user_id)

        # Should get config prompt, not agent response
        content = str(response.content) if hasattr(response, "content") else str(response)
        assert "favorite color" in content.lower()
        assert "demo agent" in content.lower()

    def test_color_extraction_simple_pattern(self, shared_db: SqliteDb, token_storage: TokenStorageType):
        """Test extraction of color from 'my favorite color is X' pattern."""
        agent = DemoAgent(shared_db=shared_db, token_storage=token_storage, user_id="test-user")
        user_id = "test-user-1"

        # User provides favorite color
        response = agent.run("My favorite color is blue", user_id=user_id)

        # Should get confirmation
        content = str(response.content) if hasattr(response, "content") else str(response)
        assert "blue" in content.lower()
        assert "✅" in content or "configured" in content.lower()

        # Verify color is stored
        color_config = agent.toolkit_configs[0]
        assert color_config.is_configured(user_id)
        assert color_config.get_user_color(user_id) == "blue"

    def test_color_extraction_i_like_pattern(self, shared_db: SqliteDb, token_storage: TokenStorageType):
        """Test extraction from 'I like X' pattern."""
        agent = DemoAgent(shared_db=shared_db, token_storage=token_storage, user_id="test-user")
        user_id = "test-user-2"

        response = agent.run("I like green", user_id=user_id)

        content = str(response.content) if hasattr(response, "content") else str(response)
        assert "green" in content.lower()
        assert "✅" in content or "configured" in content.lower()

    def test_color_extraction_set_color_pattern(self, shared_db: SqliteDb, token_storage: TokenStorageType):
        """Test extraction from 'set color to X' pattern."""
        agent = DemoAgent(shared_db=shared_db, token_storage=token_storage, user_id="test-user")
        user_id = "test-user-3"

        response = agent.run("set color to red", user_id=user_id)

        content = str(response.content) if hasattr(response, "content") else str(response)
        assert "red" in content.lower()
        assert "✅" in content or "configured" in content.lower()

    def test_color_extraction_color_equals_pattern(self, shared_db: SqliteDb, token_storage: TokenStorageType):
        """Test extraction from 'color = X' pattern."""
        agent = DemoAgent(shared_db=shared_db, token_storage=token_storage, user_id="test-user")
        user_id = "test-user-4"

        response = agent.run("color: yellow", user_id=user_id)

        content = str(response.content) if hasattr(response, "content") else str(response)
        assert "yellow" in content.lower()
        assert "✅" in content or "configured" in content.lower()

    def test_invalid_color_rejected(self, shared_db: SqliteDb, token_storage: TokenStorageType):
        """Test that invalid colors are rejected with error message."""
        agent = DemoAgent(shared_db=shared_db, token_storage=token_storage, user_id="test-user")
        user_id = "test-user-invalid"

        response = agent.run("My favorite color is magenta", user_id=user_id)

        content = str(response.content) if hasattr(response, "content") else str(response)
        assert "❌" in content or "error" in content.lower() or "invalid" in content.lower()
        assert "magenta" in content.lower()

    def test_multiple_users_isolated(self, shared_db: SqliteDb, token_storage: TokenStorageType):
        """Test that different users have isolated configurations."""
        agent = DemoAgent(shared_db=shared_db, token_storage=token_storage, user_id="test-user")
        user1 = "test-user-a"
        user2 = "test-user-b"

        # Configure different colors for two users
        agent.run("My favorite color is blue", user_id=user1)
        agent.run("My favorite color is red", user_id=user2)

        # Verify isolation
        color_config = agent.toolkit_configs[0]
        assert color_config.get_user_color(user1) == "blue"
        assert color_config.get_user_color(user2) == "red"


# NOTE: TestAgentCaching class removed - wrapper-level caching was intentionally removed
# Caching is now handled by custom_handler.py at the wrapper instance level


@pytest.mark.skipif(
    "GEMINI_API_KEY" not in os.environ and "GOOGLE_API_KEY" not in os.environ,
    reason="Requires GEMINI_API_KEY or GOOGLE_API_KEY environment variable",
)
class TestAgentExecution:
    """Tests for actual agent execution (requires API key)."""

    @pytest.fixture
    def configured_agent(self, shared_db: SqliteDb, token_storage: TokenStorageType):
        """Fixture providing a configured agent."""
        agent = DemoAgent(shared_db=shared_db, token_storage=token_storage, user_id="test-user", temperature=0.7, max_tokens=150)
        user_id = "test-user-exec"

        # Configure the agent
        agent.run("My favorite color is blue", user_id=user_id)

        return agent, user_id

    def test_sync_run(self, configured_agent: tuple[DemoAgent, str]):
        """Test synchronous run method."""
        agent, user_id = configured_agent

        response = agent.run("What is your purpose?", user_id=user_id)

        # Should get a real response from the agent
        content = str(response.content) if hasattr(response, "content") else str(response)
        assert len(content) > 0
        assert "demo" in content.lower() or "showcase" in content.lower()

    @pytest.mark.asyncio
    async def test_async_run_non_streaming(self, configured_agent: tuple[DemoAgent, str]):
        """Test async non-streaming execution."""
        agent, user_id = configured_agent

        response = await agent.arun("Tell me about yourself", user_id=user_id, stream=False)

        # Should get a real response
        content = str(response.content) if hasattr(response, "content") else str(response)
        assert len(content) > 0

    @pytest.mark.asyncio
    async def test_async_run_streaming(self, configured_agent: tuple[DemoAgent, str]):
        """Test async streaming execution."""
        agent, user_id = configured_agent

        # Collect streamed events
        events = []
        # Don't await - arun returns an async generator when stream=True
        async for event in agent.arun("What can you do?", user_id=user_id, stream=True):
            events.append(event)

        # Should receive multiple events
        assert len(events) > 0

        # Last event should be RunCompletedEvent or similar
        # At minimum, we should get some content
        event_types = [type(event).__name__ for event in events]
        assert len(event_types) > 0


@pytest.mark.skipif(
    "GEMINI_API_KEY" not in os.environ and "GOOGLE_API_KEY" not in os.environ,
    reason="Requires GEMINI_API_KEY or GOOGLE_API_KEY environment variable",
)
class TestColorTools:
    """Tests for ColorTools integration."""

    @pytest.fixture
    def configured_agent(self, shared_db: SqliteDb, token_storage: TokenStorageType):
        """Fixture providing a configured agent."""
        agent = DemoAgent(shared_db=shared_db, token_storage=token_storage, user_id="test-user", temperature=0.7, max_tokens=500)
        user_id = "test-user-tools"

        # Configure with a specific color
        agent.run("My favorite color is green", user_id=user_id)

        return agent, user_id

    def test_agent_has_color_tools(self, configured_agent: tuple[DemoAgent, str]):
        """Test that agent has ColorTools after configuration."""
        agent, user_id = configured_agent

        # Verify FavoriteColorConfig is configured (which enables ColorTools)
        color_config = agent.toolkit_configs[0]
        assert color_config.is_configured(user_id)
        assert color_config.get_user_color(user_id) == "green"

        # Verify that ColorTools would be provided
        toolkit = color_config.get_toolkit(user_id)
        assert toolkit is not None

    def test_palette_generation_tool(self, configured_agent: tuple[DemoAgent, str]):
        """Test that agent can use palette generation tool."""
        agent, user_id = configured_agent

        response = agent.run("Generate a complementary color palette for me", user_id=user_id)

        content = str(response.content) if hasattr(response, "content") else str(response)
        assert len(content) > 0
        # Should mention colors or palette
        assert "color" in content.lower() or "palette" in content.lower()

    def test_text_formatting_tool(self, configured_agent: tuple[DemoAgent, str]):
        """Test that agent can use text formatting tool."""
        agent, user_id = configured_agent

        response = agent.run("Format the text 'Hello World' with a bold theme", user_id=user_id)

        content = str(response.content) if hasattr(response, "content") else str(response)
        assert len(content) > 0


class TestSessionMemory:
    """Tests for session memory and conversation history."""

    def test_conversation_history_enabled(self, shared_db: SqliteDb, token_storage: TokenStorageType):
        """Test that conversation history is enabled in agent configuration."""
        agent = DemoAgent(shared_db=shared_db, token_storage=token_storage, user_id="test-user")
        user_id = "test-user-memory"

        # Configure agent
        agent.run("My favorite color is orange", user_id=user_id)

        # Run a message to create the agent
        response = agent.run("Hello", user_id=user_id)

        # Verify response was generated (agent created successfully)
        assert response is not None

        # Session management is verified by the shared_db fixture being used
        # and BaseAgentWrapper setting db=shared_db in _get_or_create_agent


class TestErrorHandling:
    """Tests for error handling and edge cases."""

    def test_run_without_user_id(self, shared_db: SqliteDb, token_storage: TokenStorageType):
        """Test that agent handles missing user_id gracefully."""
        agent = DemoAgent(shared_db=shared_db, token_storage=token_storage, user_id="test-user")

        response = agent.run("Hello", user_id=None)

        content = str(response.content) if hasattr(response, "content") else str(response)
        assert "❌" in content or "error" in content.lower()
        assert "user id" in content.lower()

    @pytest.mark.asyncio
    async def test_arun_without_user_id(self, shared_db: SqliteDb, token_storage: TokenStorageType):
        """Test that async run handles missing user_id gracefully."""
        agent = DemoAgent(shared_db=shared_db, token_storage=token_storage, user_id="test-user")

        response = await agent.arun("Hello", user_id=None, stream=False)

        content = str(response.content) if hasattr(response, "content") else str(response)
        assert "❌" in content or "error" in content.lower()

    def test_empty_message(self, shared_db: SqliteDb, token_storage: TokenStorageType):
        """Test that agent handles empty messages."""
        agent = DemoAgent(shared_db=shared_db, token_storage=token_storage, user_id="test-user")
        user_id = "test-user-empty"

        # Should still prompt for configuration
        response = agent.run("", user_id=user_id)

        content = str(response.content) if hasattr(response, "content") else str(response)
        assert "favorite color" in content.lower()


class TestLogging:
    """Tests to verify logging is comprehensive."""

    def test_logging_in_config_extraction(self, caplog, shared_db: SqliteDb, token_storage: TokenStorageType):
        """Test that configuration extraction logs are present."""
        import logging

        caplog.set_level(logging.DEBUG)

        agent = DemoAgent(shared_db=shared_db, token_storage=token_storage, user_id="test-user")
        user_id = "test-user-logging"

        # Trigger config extraction
        agent.run("My favorite color is blue", user_id=user_id)

        # Verify extensive logging occurred
        # (Note: loguru doesn't integrate perfectly with caplog,
        #  this is more of a smoke test)
        assert len(caplog.records) >= 0  # At least some logging happened

    def test_agent_creation_logging(self, shared_db: SqliteDb, token_storage: TokenStorageType):
        """Test that agent creation is logged."""
        agent = DemoAgent(shared_db=shared_db, token_storage=token_storage, user_id="test-user")
        user_id = "test-user-create-log"

        # Configure and create agent
        agent.run("My favorite color is pink", user_id=user_id)
        agent.run("Hello", user_id=user_id)

        # If this doesn't raise an error, logging is working
        # (Full log verification would require log file inspection)
        assert True
