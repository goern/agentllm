"""Tests for SystemPromptExtensionConfig."""

import os
from unittest.mock import MagicMock, patch

import pytest

from agentllm.agents.toolkit_configs.gdrive_config import GoogleDriveConfig
from agentllm.agents.toolkit_configs.system_prompt_extension_config import (
    SystemPromptExtensionConfig,
)


class TestSystemPromptExtensionConfigBasics:
    """Basic tests for SystemPromptExtensionConfig instantiation."""

    def test_create_config(self):
        """Test that SystemPromptExtensionConfig can be instantiated."""
        mock_gdrive_config = MagicMock(spec=GoogleDriveConfig)
        config = SystemPromptExtensionConfig(gdrive_config=mock_gdrive_config)
        assert config is not None
        assert config._gdrive_config is mock_gdrive_config

    def test_create_config_with_token_storage(self):
        """Test that SystemPromptExtensionConfig accepts token storage."""
        mock_gdrive_config = MagicMock(spec=GoogleDriveConfig)
        mock_token_storage = MagicMock()
        config = SystemPromptExtensionConfig(gdrive_config=mock_gdrive_config, token_storage=mock_token_storage)
        assert config is not None
        assert config.token_storage is mock_token_storage

    def test_reads_env_var_on_init(self):
        """Test that config reads RELEASE_MANAGER_SYSTEM_PROMPT_GDRIVE_URL on init."""
        mock_gdrive_config = MagicMock(spec=GoogleDriveConfig)

        with patch.dict(os.environ, {"RELEASE_MANAGER_SYSTEM_PROMPT_GDRIVE_URL": "https://doc.url"}):
            config = SystemPromptExtensionConfig(gdrive_config=mock_gdrive_config)
            assert config._doc_url == "https://doc.url"

    def test_handles_missing_env_var(self):
        """Test that config handles missing environment variable."""
        mock_gdrive_config = MagicMock(spec=GoogleDriveConfig)

        with patch.dict(os.environ, {}, clear=True):
            # Make sure GEMINI_API_KEY is set so other code doesn't break
            os.environ["GEMINI_API_KEY"] = "test-key"
            config = SystemPromptExtensionConfig(gdrive_config=mock_gdrive_config)
            assert config._doc_url is None


class TestIsConfigured:
    """Tests for is_configured() method."""

    def test_not_configured_when_no_env_var(self):
        """Test that config is not configured when env var is not set."""
        mock_gdrive_config = MagicMock(spec=GoogleDriveConfig)

        with patch.dict(os.environ, {}, clear=True):
            os.environ["GEMINI_API_KEY"] = "test-key"
            config = SystemPromptExtensionConfig(gdrive_config=mock_gdrive_config)
            assert not config.is_configured("user123")

    def test_not_configured_when_gdrive_not_configured(self):
        """Test that config is not configured when GDrive is not configured."""
        mock_gdrive_config = MagicMock(spec=GoogleDriveConfig)
        mock_gdrive_config.is_configured.return_value = False

        with patch.dict(os.environ, {"RELEASE_MANAGER_SYSTEM_PROMPT_GDRIVE_URL": "https://doc.url"}):
            config = SystemPromptExtensionConfig(gdrive_config=mock_gdrive_config)
            assert not config.is_configured("user123")
            mock_gdrive_config.is_configured.assert_called_once_with("user123")

    def test_configured_when_env_var_and_gdrive_configured(self):
        """Test that config is configured when both env var and GDrive are configured."""
        mock_gdrive_config = MagicMock(spec=GoogleDriveConfig)
        mock_gdrive_config.is_configured.return_value = True

        with patch.dict(os.environ, {"RELEASE_MANAGER_SYSTEM_PROMPT_GDRIVE_URL": "https://doc.url"}):
            config = SystemPromptExtensionConfig(gdrive_config=mock_gdrive_config)
            assert config.is_configured("user123")
            mock_gdrive_config.is_configured.assert_called_once_with("user123")


class TestExtractAndStoreConfig:
    """Tests for extract_and_store_config() method."""

    def test_returns_none(self):
        """Test that extract_and_store_config always returns None."""
        mock_gdrive_config = MagicMock(spec=GoogleDriveConfig)
        config = SystemPromptExtensionConfig(gdrive_config=mock_gdrive_config)

        result = config.extract_and_store_config("some message", "user123")
        assert result is None


class TestGetConfigPrompt:
    """Tests for get_config_prompt() method."""

    def test_returns_none(self):
        """Test that get_config_prompt always returns None (silent config)."""
        mock_gdrive_config = MagicMock(spec=GoogleDriveConfig)
        config = SystemPromptExtensionConfig(gdrive_config=mock_gdrive_config)

        result = config.get_config_prompt("user123")
        assert result is None


class TestGetToolkit:
    """Tests for get_toolkit() method."""

    def test_returns_none(self):
        """Test that get_toolkit always returns None (no toolkit provided)."""
        mock_gdrive_config = MagicMock(spec=GoogleDriveConfig)
        config = SystemPromptExtensionConfig(gdrive_config=mock_gdrive_config)

        result = config.get_toolkit("user123")
        assert result is None


class TestCheckAuthorizationRequest:
    """Tests for check_authorization_request() method."""

    def test_returns_none(self):
        """Test that check_authorization_request always returns None."""
        mock_gdrive_config = MagicMock(spec=GoogleDriveConfig)
        config = SystemPromptExtensionConfig(gdrive_config=mock_gdrive_config)

        result = config.check_authorization_request("some message", "user123")
        assert result is None


class TestIsRequired:
    """Tests for is_required() method."""

    def test_is_required(self):
        """Test that this is a required toolkit."""
        mock_gdrive_config = MagicMock(spec=GoogleDriveConfig)
        config = SystemPromptExtensionConfig(gdrive_config=mock_gdrive_config)

        assert config.is_required() is True


class TestGetAgentInstructions:
    """Tests for get_agent_instructions() method - the core functionality."""

    def test_returns_empty_when_no_env_var(self):
        """Test that returns empty list when env var not set."""
        mock_gdrive_config = MagicMock(spec=GoogleDriveConfig)

        with patch.dict(os.environ, {}, clear=True):
            os.environ["GEMINI_API_KEY"] = "test-key"
            config = SystemPromptExtensionConfig(gdrive_config=mock_gdrive_config)

            result = config.get_agent_instructions("user123")
            assert result == []

    def test_returns_empty_when_gdrive_not_configured(self):
        """Test that returns empty list when GDrive not configured (silent)."""
        mock_gdrive_config = MagicMock(spec=GoogleDriveConfig)
        mock_gdrive_config.is_configured.return_value = False

        with patch.dict(os.environ, {"RELEASE_MANAGER_SYSTEM_PROMPT_GDRIVE_URL": "https://doc.url"}):
            config = SystemPromptExtensionConfig(gdrive_config=mock_gdrive_config)

            result = config.get_agent_instructions("user123")
            assert result == []
            mock_gdrive_config.is_configured.assert_called_once_with("user123")

    def test_fetches_and_returns_prompt_when_configured(self):
        """Test that fetches and returns prompt when everything is configured."""
        mock_gdrive_config = MagicMock(spec=GoogleDriveConfig)
        mock_gdrive_config.is_configured.return_value = True

        mock_toolkit = MagicMock()
        mock_toolkit.get_document_content.return_value = "Extended prompt content"
        mock_gdrive_config.get_toolkit.return_value = mock_toolkit

        with patch.dict(os.environ, {"RELEASE_MANAGER_SYSTEM_PROMPT_GDRIVE_URL": "https://doc.url"}):
            config = SystemPromptExtensionConfig(gdrive_config=mock_gdrive_config)

            result = config.get_agent_instructions("user123")

            # Result should be a list containing metadata and the extended prompt
            assert isinstance(result, list)
            assert len(result) > 0
            # Check that the extended prompt content is included
            assert "Extended prompt content" in result
            # Check that metadata is included
            assert any("EXTENDED SYSTEM PROMPT" in item for item in result)
            assert any("https://doc.url" in item for item in result)
            # is_configured is called twice: once in get_agent_instructions, once in _fetch_extended_system_prompt
            assert mock_gdrive_config.is_configured.call_count == 2
            mock_gdrive_config.get_toolkit.assert_called_once_with("user123")
            mock_toolkit.get_document_content.assert_called_once_with("https://doc.url")

    def test_raises_exception_when_fetch_fails(self):
        """Test that exceptions propagate to fail agent creation."""
        mock_gdrive_config = MagicMock(spec=GoogleDriveConfig)
        mock_gdrive_config.is_configured.return_value = True

        mock_toolkit = MagicMock()
        mock_toolkit.get_document_content.side_effect = ValueError("Document not found")
        mock_gdrive_config.get_toolkit.return_value = mock_toolkit

        with patch.dict(os.environ, {"RELEASE_MANAGER_SYSTEM_PROMPT_GDRIVE_URL": "https://doc.url"}):
            config = SystemPromptExtensionConfig(gdrive_config=mock_gdrive_config)

            with pytest.raises(ValueError, match="Failed to fetch extended system prompt"):
                config.get_agent_instructions("user123")

    def test_caches_prompt_per_user(self):
        """Test that prompt is cached per user."""
        mock_gdrive_config = MagicMock(spec=GoogleDriveConfig)
        mock_gdrive_config.is_configured.return_value = True

        mock_toolkit = MagicMock()
        mock_toolkit.get_document_content.return_value = "Extended prompt content"
        mock_gdrive_config.get_toolkit.return_value = mock_toolkit

        with patch.dict(os.environ, {"RELEASE_MANAGER_SYSTEM_PROMPT_GDRIVE_URL": "https://doc.url"}):
            config = SystemPromptExtensionConfig(gdrive_config=mock_gdrive_config)

            # First call - should fetch
            result1 = config.get_agent_instructions("user123")
            assert "Extended prompt content" in result1
            assert any("EXTENDED SYSTEM PROMPT" in item for item in result1)
            assert mock_toolkit.get_document_content.call_count == 1

            # Second call - should use cache
            result2 = config.get_agent_instructions("user123")
            assert "Extended prompt content" in result2
            assert result1 == result2  # Should return same cached result
            assert mock_toolkit.get_document_content.call_count == 1  # Not called again

            # Different user - should fetch again
            result3 = config.get_agent_instructions("user456")
            assert "Extended prompt content" in result3
            assert mock_toolkit.get_document_content.call_count == 2  # Called again


class TestFetchExtendedSystemPrompt:
    """Tests for _fetch_extended_system_prompt() internal method."""

    def test_raises_when_env_var_not_set(self):
        """Test that raises ValueError when env var not set."""
        mock_gdrive_config = MagicMock(spec=GoogleDriveConfig)

        with patch.dict(os.environ, {}, clear=True):
            os.environ["GEMINI_API_KEY"] = "test-key"
            config = SystemPromptExtensionConfig(gdrive_config=mock_gdrive_config)

            with pytest.raises(ValueError, match="RELEASE_MANAGER_SYSTEM_PROMPT_GDRIVE_URL"):
                config._fetch_extended_system_prompt("user123")

    def test_raises_when_gdrive_not_configured(self):
        """Test that raises ValueError when GDrive not configured."""
        mock_gdrive_config = MagicMock(spec=GoogleDriveConfig)
        mock_gdrive_config.is_configured.return_value = False

        with patch.dict(os.environ, {"RELEASE_MANAGER_SYSTEM_PROMPT_GDRIVE_URL": "https://doc.url"}):
            config = SystemPromptExtensionConfig(gdrive_config=mock_gdrive_config)

            with pytest.raises(ValueError, match="Google Drive is not configured"):
                config._fetch_extended_system_prompt("user123")

    def test_raises_when_toolkit_returns_none(self):
        """Test that raises ValueError when get_toolkit returns None."""
        mock_gdrive_config = MagicMock(spec=GoogleDriveConfig)
        mock_gdrive_config.is_configured.return_value = True
        mock_gdrive_config.get_toolkit.return_value = None

        with patch.dict(os.environ, {"RELEASE_MANAGER_SYSTEM_PROMPT_GDRIVE_URL": "https://doc.url"}):
            config = SystemPromptExtensionConfig(gdrive_config=mock_gdrive_config)

            with pytest.raises(ValueError, match="Failed to get Google Drive toolkit"):
                config._fetch_extended_system_prompt("user123")

    def test_raises_when_document_content_empty(self):
        """Test that raises ValueError when document returns empty content."""
        mock_gdrive_config = MagicMock(spec=GoogleDriveConfig)
        mock_gdrive_config.is_configured.return_value = True

        mock_toolkit = MagicMock()
        mock_toolkit.get_document_content.return_value = ""
        mock_gdrive_config.get_toolkit.return_value = mock_toolkit

        with patch.dict(os.environ, {"RELEASE_MANAGER_SYSTEM_PROMPT_GDRIVE_URL": "https://doc.url"}):
            config = SystemPromptExtensionConfig(gdrive_config=mock_gdrive_config)

            with pytest.raises(ValueError, match="may be empty or inaccessible"):
                config._fetch_extended_system_prompt("user123")

    def test_successful_fetch_and_cache(self):
        """Test successful fetch and caching."""
        mock_gdrive_config = MagicMock(spec=GoogleDriveConfig)
        mock_gdrive_config.is_configured.return_value = True

        mock_toolkit = MagicMock()
        mock_toolkit.get_document_content.return_value = "Extended prompt content"
        mock_gdrive_config.get_toolkit.return_value = mock_toolkit

        with patch.dict(os.environ, {"RELEASE_MANAGER_SYSTEM_PROMPT_GDRIVE_URL": "https://doc.url"}):
            config = SystemPromptExtensionConfig(gdrive_config=mock_gdrive_config)

            result = config._fetch_extended_system_prompt("user123")

            assert result == "Extended prompt content"
            assert "user123" in config._system_prompts
            assert config._system_prompts["user123"] == "Extended prompt content"


class TestInvalidateForGdriveChange:
    """Tests for invalidate_for_gdrive_change() method."""

    def test_invalidates_cached_prompt(self):
        """Test that invalidates cached prompt when called."""
        mock_gdrive_config = MagicMock(spec=GoogleDriveConfig)
        config = SystemPromptExtensionConfig(gdrive_config=mock_gdrive_config)

        # Manually add cached prompt
        config._system_prompts["user123"] = "Cached prompt"

        # Invalidate
        config.invalidate_for_gdrive_change("user123")

        # Should be removed
        assert "user123" not in config._system_prompts

    def test_handles_no_cached_prompt_gracefully(self):
        """Test that handles invalidation when no cache exists."""
        mock_gdrive_config = MagicMock(spec=GoogleDriveConfig)
        config = SystemPromptExtensionConfig(gdrive_config=mock_gdrive_config)

        # Should not raise exception
        config.invalidate_for_gdrive_change("user123")

        assert "user123" not in config._system_prompts

    def test_invalidation_forces_refetch(self):
        """Test that invalidation forces a fresh fetch on next call."""
        mock_gdrive_config = MagicMock(spec=GoogleDriveConfig)
        mock_gdrive_config.is_configured.return_value = True

        mock_toolkit = MagicMock()
        mock_toolkit.get_document_content.side_effect = [
            "First fetch",
            "Second fetch after invalidation",
        ]
        mock_gdrive_config.get_toolkit.return_value = mock_toolkit

        with patch.dict(os.environ, {"RELEASE_MANAGER_SYSTEM_PROMPT_GDRIVE_URL": "https://doc.url"}):
            config = SystemPromptExtensionConfig(gdrive_config=mock_gdrive_config)

            # First fetch
            result1 = config.get_agent_instructions("user123")
            assert "First fetch" in result1
            assert any("EXTENDED SYSTEM PROMPT" in item for item in result1)
            assert mock_toolkit.get_document_content.call_count == 1

            # Invalidate
            config.invalidate_for_gdrive_change("user123")

            # Second fetch - should get new content
            result2 = config.get_agent_instructions("user123")
            assert "Second fetch after invalidation" in result2
            assert "First fetch" not in result2  # Old content should not be in new result
            assert mock_toolkit.get_document_content.call_count == 2
