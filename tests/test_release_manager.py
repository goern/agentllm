"""Tests for the ReleaseManager agent with composition-based toolkit configs.

Tests both the agent's sync and async methods, including streaming functionality,
and verifies that toolkit configuration is properly checked before agent initialization.
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from dotenv import load_dotenv

from agentllm.agents.release_manager import ReleaseManager
from agentllm.agents.toolkit_configs import JiraConfig

# Load .env file for tests
load_dotenv()

# Map GEMINI_API_KEY to GOOGLE_API_KEY if needed
if "GOOGLE_API_KEY" not in os.environ and "GEMINI_API_KEY" in os.environ:
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]


class TestReleaseManagerBasics:
    """Basic tests for ReleaseManager instantiation and parameters."""

    def test_create_agent(self):
        """Test that ReleaseManager can be instantiated."""
        agent = ReleaseManager()
        assert agent is not None
        assert len(agent.toolkit_configs) > 0

    def test_create_agent_with_params(self):
        """Test that ReleaseManager accepts model parameters."""
        agent = ReleaseManager(temperature=0.5, max_tokens=100)
        assert agent is not None
        assert agent._temperature == 0.5
        assert agent._max_tokens == 100

    def test_toolkit_configs_initialized(self):
        """Test that toolkit configs are properly initialized."""
        agent = ReleaseManager()
        assert hasattr(agent, "toolkit_configs")
        assert isinstance(agent.toolkit_configs, list)
        # Should have at least GoogleDriveConfig
        assert len(agent.toolkit_configs) >= 1


class TestToolkitConfiguration:
    """Tests for toolkit configuration management."""

    def test_required_toolkit_prompts_immediately(self):
        """Test that required toolkits prompt for config before agent can be used."""
        # Create agent with a required toolkit
        agent = ReleaseManager()

        # Mock GoogleDrive as configured so we can test Jira prompting
        with patch.object(agent.toolkit_configs[0], "is_configured", return_value=True):
            # Mock SystemPromptExtensionConfig as configured (it depends on GDrive)
            with patch.object(agent.toolkit_configs[2], "is_configured", return_value=True):
                # Add a required toolkit config (mock JiraConfig as required)
                with patch.object(JiraConfig, "is_required", return_value=True):
                    with patch.object(JiraConfig, "is_configured", return_value=False):
                        with patch.object(JiraConfig, "get_config_prompt", return_value="Please configure JIRA"):
                            # Add the mocked required config
                            agent.toolkit_configs.append(JiraConfig())

                            # User tries to send a message without configuring
                            response = agent.run("Hello!", user_id="new-user")

                            # Should get config prompt, not agent response
                            content = str(response.content) if hasattr(response, "content") else str(response)
                            assert "configure" in content.lower() or "jira" in content.lower()

    def test_google_drive_is_required(self):
        """Test that Google Drive is required (like all toolkits)."""
        agent = ReleaseManager()

        # Should have GoogleDriveConfig, JiraConfig, and SystemPromptExtensionConfig
        assert len(agent.toolkit_configs) == 3
        gdrive_config = agent.toolkit_configs[0]
        assert gdrive_config.is_required(), "GoogleDriveConfig should be required"

    @patch("agentllm.tools.gdrive_toolkit.GoogleDriveTools")
    def test_google_drive_config_extracted_from_url(self, mock_gdrive_tools):
        """Test that Google Drive auth code is extracted from full redirect URL."""
        agent = ReleaseManager()

        # Mock Google Drive toolkit creation and validation
        mock_creds = MagicMock()
        with patch("agentllm.agents.toolkit_configs.gdrive_config.Flow") as mock_flow:
            with patch("agentllm.agents.toolkit_configs.gdrive_config.build") as mock_build:
                # Mock OAuth flow
                mock_flow_instance = MagicMock()
                mock_flow_instance.credentials = mock_creds
                mock_flow.from_client_config.return_value = mock_flow_instance

                # Mock Google Drive API user info
                mock_service = MagicMock()
                mock_user_info = {"user": {"displayName": "Test User", "emailAddress": "test@example.com"}}
                mock_service.about().get().execute.return_value = mock_user_info
                mock_build.return_value = mock_service

                # Test URL formats
                test_urls = [
                    "http://localhost?code=4/0AeaYSHBxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                    "http://localhost/?code=4/0AeaYSHBxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                    "4/0AeaYSHBxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
                ]

                for url in test_urls:
                    # Provide Google Drive auth code/URL
                    response = agent.run(url, user_id="test-user")

                    # Should get confirmation
                    content = str(response.content) if hasattr(response, "content") else str(response)
                    assert "google drive" in content.lower() or "authorized" in content.lower(), f"Failed to extract code from: {url}"

                    # Reset for next test
                    gdrive_config = agent.toolkit_configs[0]
                    if "test-user" in gdrive_config._user_configs:
                        del gdrive_config._user_configs["test-user"]

    def test_toolkit_config_is_configured_check(self):
        """Test that toolkit configs properly check if they're configured."""
        agent = ReleaseManager()

        # All toolkits should report not configured for new user
        for config in agent.toolkit_configs:
            assert not config.is_configured("brand-new-user"), (
                f"{config.__class__.__name__}.is_configured() should return False for new user"
            )

    @patch("agentllm.tools.gdrive_toolkit.GoogleDriveTools")
    def test_toolkit_becomes_configured_after_auth(self, mock_gdrive_tools):
        """Test that toolkit reports configured after successful authorization."""
        agent = ReleaseManager()
        gdrive_config = agent.toolkit_configs[0]  # GoogleDriveConfig

        # Initially not configured
        assert not gdrive_config.is_configured("test-user")

        # Mock Google Drive OAuth flow
        mock_creds = MagicMock()
        with patch("agentllm.agents.toolkit_configs.gdrive_config.Flow") as mock_flow:
            with patch("agentllm.agents.toolkit_configs.gdrive_config.build") as mock_build:
                # Mock token storage to avoid JSON serialization issues with MagicMock
                with patch.object(gdrive_config.token_storage, "upsert_gdrive_token"):
                    with patch.object(
                        gdrive_config.token_storage,
                        "get_gdrive_credentials",
                        return_value=mock_creds,
                    ):
                        mock_flow_instance = MagicMock()
                        mock_flow_instance.credentials = mock_creds
                        mock_flow.from_client_config.return_value = mock_flow_instance

                        mock_service = MagicMock()
                        mock_service.about().get().execute.return_value = {
                            "user": {"displayName": "Test", "emailAddress": "test@example.com"}
                        }
                        mock_build.return_value = mock_service

                        # Authorize
                        agent.run("4/0AeaYSHBxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", user_id="test-user")

                        # Now should be configured
                        assert gdrive_config.is_configured("test-user")

    def test_google_drive_prompts_auth_immediately(self):
        """Test that Google Drive prompts authorization immediately (required toolkit)."""
        agent = ReleaseManager()

        # Mock OAuth URL generation
        with patch("agentllm.agents.toolkit_configs.gdrive_config.Flow") as mock_flow:
            mock_flow_instance = MagicMock()
            mock_flow_instance.authorization_url.return_value = ("http://oauth.url", "state")
            mock_flow.from_client_config.return_value = mock_flow_instance

            # Any message should prompt for Google Drive auth (it's required)
            response = agent.run("Hello!", user_id="test-user")

            # Should get OAuth prompt
            content = str(response.content) if hasattr(response, "content") else str(response)
            assert "authorize" in content.lower() or "google drive" in content.lower()


class TestAgentExecution:
    """Tests for agent execution with configured toolkits."""

    @pytest.fixture
    def configured_agent(self):
        """Fixture that provides a ReleaseManager with Google Drive configured."""
        agent = ReleaseManager()

        # Mock and configure Google Drive (required toolkit)
        with patch("agentllm.agents.toolkit_configs.gdrive_config.Flow") as mock_flow:
            with patch("agentllm.agents.toolkit_configs.gdrive_config.build") as mock_build:
                mock_creds = MagicMock()
                mock_flow_instance = MagicMock()
                mock_flow_instance.credentials = mock_creds
                mock_flow.from_client_config.return_value = mock_flow_instance

                mock_service = MagicMock()
                mock_service.about().get().execute.return_value = {"user": {"displayName": "Test", "emailAddress": "test@example.com"}}
                mock_build.return_value = mock_service

                # Configure Google Drive
                agent.run("4/0AeaYSHBxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", user_id="test-user")

        return agent

    @pytest.mark.skipif(
        "GOOGLE_API_KEY" not in os.environ,
        reason="GOOGLE_API_KEY not set",
    )
    def test_sync_run(self, configured_agent):
        """Test synchronous run() method."""
        response = configured_agent.run("Hello! Can you help me?", user_id="test-user")

        assert response is not None
        assert hasattr(response, "content")
        assert len(str(response.content)) > 0

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        "GOOGLE_API_KEY" not in os.environ,
        reason="GOOGLE_API_KEY not set",
    )
    async def test_async_non_streaming(self, configured_agent):
        """Test async arun() without streaming."""
        response = await configured_agent.arun("Hello! Can you help me?", user_id="test-user", stream=False)

        assert response is not None
        assert hasattr(response, "content")
        assert len(str(response.content)) > 0

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        "GOOGLE_API_KEY" not in os.environ,
        reason="GOOGLE_API_KEY not set",
    )
    async def test_async_streaming(self, configured_agent):
        """Test async arun() WITH streaming."""
        # Call arun with streaming enabled
        result = configured_agent.arun("Hello! Can you help me?", user_id="test-user", stream=True)

        # Verify it's an async generator
        assert hasattr(result, "__aiter__"), "Result should be an async generator"

        # Iterate and collect chunks
        chunks = []
        async for chunk in result:
            chunks.append(chunk)

        # Verify we got chunks
        assert len(chunks) > 0, "Should receive at least one chunk"


class TestAgentCaching:
    """Tests for agent caching and invalidation."""

    @patch("agentllm.tools.gdrive_toolkit.GoogleDriveTools")
    def test_agent_cache_per_user(self, mock_gdrive_tools):
        """Test that agents are cached per user."""
        manager = ReleaseManager()

        # Configure Google Drive for both users
        with patch("agentllm.agents.toolkit_configs.gdrive_config.Flow") as mock_flow:
            with patch("agentllm.agents.toolkit_configs.gdrive_config.build") as mock_build:
                mock_creds = MagicMock()
                mock_flow_instance = MagicMock()
                mock_flow_instance.credentials = mock_creds
                mock_flow.from_client_config.return_value = mock_flow_instance

                mock_service = MagicMock()
                mock_service.about().get().execute.return_value = {"user": {"displayName": "Test", "emailAddress": "test@example.com"}}
                mock_build.return_value = mock_service

                # Configure for both users
                manager.run("4/0AeaYSHBxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", user_id="user1")
                manager.run("4/0AeaYSHBxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", user_id="user2")

        # Create agents for different users
        agent1 = manager._get_or_create_agent("user1")
        agent2 = manager._get_or_create_agent("user2")

        # Both should create underlying agents
        assert agent1 is not None
        assert agent2 is not None

        # Calling again on same user should return cached agent
        agent1_again = manager._get_or_create_agent("user1")
        assert agent1_again is agent1, "Should return cached agent"

    @patch("agentllm.tools.gdrive_toolkit.GoogleDriveTools")
    def test_agent_invalidated_after_new_toolkit_config(self, mock_gdrive_tools):
        """Test that agent is invalidated when new toolkit is configured."""
        agent = ReleaseManager()

        # Create agent for user (no toolkits configured)
        original_agent = agent._get_or_create_agent("test-user")
        assert original_agent is not None

        # Mock Google Drive OAuth to configure a toolkit
        mock_creds = MagicMock()
        with patch("agentllm.agents.toolkit_configs.gdrive_config.Flow") as mock_flow:
            with patch("agentllm.agents.toolkit_configs.gdrive_config.build") as mock_build:
                mock_flow_instance = MagicMock()
                mock_flow_instance.credentials = mock_creds
                mock_flow.from_client_config.return_value = mock_flow_instance

                mock_service = MagicMock()
                mock_service.about().get().execute.return_value = {"user": {"displayName": "Test", "emailAddress": "test@example.com"}}
                mock_build.return_value = mock_service

                # Configure Google Drive
                agent.run("4/0AeaYSHBxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", user_id="test-user")

        # Agent should have been invalidated
        assert "test-user" not in agent._agents or agent._agents.get("test-user") is None

        # Creating agent again should give new instance with tools
        new_agent = agent._get_or_create_agent("test-user")
        assert new_agent is not None
        # Can't easily check if it's different object since invalidation deletes the cache


class TestConfigurationValidation:
    """Tests for configuration validation and error handling."""

    @patch("agentllm.tools.gdrive_toolkit.GoogleDriveTools")
    def test_invalid_auth_code_returns_error(self, mock_gdrive_tools):
        """Test that invalid authorization code returns user-friendly error."""
        agent = ReleaseManager()

        # Mock failed OAuth exchange
        with patch("agentllm.agents.toolkit_configs.gdrive_config.Flow") as mock_flow:
            mock_flow_instance = MagicMock()
            mock_flow_instance.fetch_token.side_effect = Exception("Invalid code")
            mock_flow.from_client_config.return_value = mock_flow_instance

            # Provide invalid code
            response = agent.run("4/invalid_code", user_id="test-user")

            # Should get error message, not crash
            content = str(response.content) if hasattr(response, "content") else str(response)
            assert "failed" in content.lower() or "invalid" in content.lower()


class TestToolkitInstructions:
    """Tests for toolkit-specific agent instructions."""

    @patch("agentllm.tools.gdrive_toolkit.GoogleDriveTools")
    def test_agent_instructions_include_toolkit_info(self, mock_gdrive_tools):
        """Test that agent receives toolkit-specific instructions when configured."""
        agent = ReleaseManager()

        # Mock Google Drive OAuth
        mock_creds = MagicMock()
        with patch("agentllm.agents.toolkit_configs.gdrive_config.Flow") as mock_flow:
            with patch("agentllm.agents.toolkit_configs.gdrive_config.build") as mock_build:
                mock_flow_instance = MagicMock()
                mock_flow_instance.credentials = mock_creds
                mock_flow.from_client_config.return_value = mock_flow_instance

                mock_service = MagicMock()
                mock_service.about().get().execute.return_value = {"user": {"displayName": "Test", "emailAddress": "test@example.com"}}
                mock_build.return_value = mock_service

                # Configure Google Drive
                agent.run("4/0AeaYSHBxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", user_id="test-user")

        # Get toolkit instructions
        gdrive_config = agent.toolkit_configs[0]
        instructions = gdrive_config.get_agent_instructions("test-user")

        # Should have Google Drive-specific instructions
        assert len(instructions) > 0
        assert any("google drive" in inst.lower() for inst in instructions)

    def test_agent_instructions_empty_when_not_configured(self):
        """Test that toolkits don't add instructions when not configured."""
        agent = ReleaseManager()

        # Get instructions for unconfigured user
        for config in agent.toolkit_configs:
            instructions = config.get_agent_instructions("unconfigured-user")
            # Should be empty since not configured
            assert len(instructions) == 0


class TestRequiredVsOptionalConfigs:
    """Tests for required toolkit configuration behavior."""

    def test_all_toolkits_are_required_by_default(self):
        """Test that all toolkits are required by default."""
        agent = ReleaseManager()

        # All toolkits should be required
        for config in agent.toolkit_configs:
            assert config.is_required(), f"{config.__class__.__name__} should be required by default"

    def test_jira_config_is_required(self):
        """Test that JiraConfig is required (inherits from base)."""
        jira_config = JiraConfig()
        assert jira_config.is_required(), "JiraConfig should be required by default"

    def test_google_drive_is_required(self):
        """Test that GoogleDriveConfig is required."""
        agent = ReleaseManager()

        # Should have GoogleDriveConfig, JiraConfig, and SystemPromptExtensionConfig
        assert len(agent.toolkit_configs) == 3
        gdrive_config = agent.toolkit_configs[0]
        assert gdrive_config.is_required(), "GoogleDriveConfig should be required"

    @patch("agentllm.tools.jira_toolkit.JiraTools")
    def test_required_config_blocks_agent_until_configured(self, mock_jira_tools):
        """Test that required configs prevent agent usage until configured."""
        agent = ReleaseManager()

        # Mock GoogleDrive and SystemPromptExtension as configured so we can test Jira
        with patch.object(agent.toolkit_configs[0], "is_configured", return_value=True):
            with patch.object(agent.toolkit_configs[2], "is_configured", return_value=True):
                # Add a required config (JiraConfig is required by default)
                jira_config = JiraConfig()
                agent.toolkit_configs.append(jira_config)

                # Mock the prompt
                mock_jira_tools.return_value.validate_connection.return_value = (True, "Connected")

                # Try to use agent without configuring Jira
                response = agent.run("Hello!", user_id="new-user")

                # Should get JIRA config prompt, not agent response
                content = str(response.content) if hasattr(response, "content") else str(response)
                assert "jira" in content.lower() or "token" in content.lower()


# TestExtendedSystemPrompt tests removed - functionality moved to SystemPromptExtensionConfig
# and tested in test_system_prompt_extension_config.py
