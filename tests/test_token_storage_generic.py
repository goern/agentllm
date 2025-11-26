"""Tests for generic token storage API.

This module demonstrates how the new generic token storage API works,
and shows how easy it is to add new token types without modifying TokenStorage.
"""

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.orm import declarative_base

from agentllm.db.token_registry import TokenTypeConfig
from agentllm.db.token_storage import TokenStorage

Base = declarative_base()


class CustomServiceToken(Base):
    """Example custom token type for demonstration."""

    __tablename__ = "custom_service_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False, unique=True, index=True)
    api_key = Column(String, nullable=False)
    api_secret = Column(String, nullable=False)
    endpoint = Column(String, nullable=False)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)


@pytest.fixture
def encryption_key():
    """Generate a test encryption key."""
    return Fernet.generate_key().decode()


@pytest.fixture
def storage(encryption_key, tmp_path):
    """Create TokenStorage instance for testing."""
    db_file = tmp_path / "test_generic.db"
    storage = TokenStorage(db_file=str(db_file), encryption_key=encryption_key)
    yield storage
    storage.close()


class TestGenericTokenAPI:
    """Test suite for generic token storage API."""

    def test_existing_token_types_via_generic_api_jira(self, storage):
        """Test that existing token types work via generic API."""
        # Store token using generic API
        result = storage.upsert_token(
            "jira",
            "user123",
            token="jira-token-abc",
            server_url="https://jira.example.com",
            username="john.doe",
        )
        assert result is True

        # Retrieve token using generic API
        token_data = storage.get_token("jira", "user123")
        assert token_data is not None
        assert token_data["token"] == "jira-token-abc"
        assert token_data["server_url"] == "https://jira.example.com"
        assert token_data["username"] == "john.doe"

        # Delete token using generic API
        result = storage.delete_token("jira", "user123")
        assert result is True

        # Verify deletion
        token_data = storage.get_token("jira", "user123")
        assert token_data is None

    def test_existing_token_types_via_generic_api_github(self, storage):
        """Test GitHub tokens via generic API."""
        result = storage.upsert_token(
            "github",
            "user456",
            token="ghp_abc123",
            server_url="https://api.github.com",
            username="janedoe",
        )
        assert result is True

        token_data = storage.get_token("github", "user456")
        assert token_data is not None
        assert token_data["token"] == "ghp_abc123"
        assert token_data["server_url"] == "https://api.github.com"

    def test_existing_token_types_via_generic_api_rhcp(self, storage):
        """Test RHCP tokens via generic API."""
        result = storage.upsert_token(
            "rhcp",
            "user789",
            offline_token="rhcp-offline-token-xyz",
        )
        assert result is True

        token_data = storage.get_token("rhcp", "user789")
        assert token_data is not None
        assert token_data["offline_token"] == "rhcp-offline-token-xyz"

    def test_unknown_token_type_raises_key_error(self, storage):
        """Test that unknown token types raise KeyError."""
        with pytest.raises(KeyError, match="Unknown token type: nonexistent"):
            storage.upsert_token("nonexistent", "user123", token="abc")

        with pytest.raises(KeyError, match="Unknown token type: nonexistent"):
            storage.get_token("nonexistent", "user123")

        with pytest.raises(KeyError, match="Unknown token type: nonexistent"):
            storage.delete_token("nonexistent", "user123")

    def test_registry_lists_all_token_types(self, storage):
        """Test that registry provides list of registered types."""
        token_types = storage._registry.list_types()
        assert "jira" in token_types
        assert "github" in token_types
        assert "gdrive" in token_types
        assert "rhcp" in token_types

    def test_adding_new_token_type_at_runtime(self, storage, encryption_key):
        """Demonstrate how to add a new token type at runtime (for testing/development)."""
        # Register custom token type
        storage._registry.register(
            "custom-service",
            TokenTypeConfig(
                model=CustomServiceToken,
                encrypted_fields=["api_key", "api_secret"],
            ),
        )

        # Create the table
        CustomServiceToken.__table__.create(storage.db_engine, checkfirst=True)

        # Now use it like any other token type
        result = storage.upsert_token(
            "custom-service",
            "user999",
            api_key="key-abc-123",
            api_secret="secret-xyz-789",
            endpoint="https://api.custom-service.com",
        )
        assert result is True

        # Retrieve and verify encryption worked
        token_data = storage.get_token("custom-service", "user999")
        assert token_data is not None
        assert token_data["api_key"] == "key-abc-123"  # Decrypted
        assert token_data["api_secret"] == "secret-xyz-789"  # Decrypted
        assert token_data["endpoint"] == "https://api.custom-service.com"  # Not encrypted

        # Verify it was actually encrypted in database
        from agentllm.db.token_storage import text

        with storage.Session() as sess:
            result = sess.execute(text("SELECT api_key, api_secret FROM custom_service_tokens WHERE user_id = 'user999'"))
            row = result.fetchone()
            stored_api_key = row[0]
            stored_api_secret = row[1]

            # Encrypted values should start with gAAAAAB (Fernet prefix)
            assert stored_api_key.startswith("gAAAAA")
            assert stored_api_secret.startswith("gAAAAA")
            # They should NOT be plaintext
            assert stored_api_key != "key-abc-123"
            assert stored_api_secret != "secret-xyz-789"


class TestGenericAPIConsistency:
    """Verify generic API works consistently across token types."""

    def test_jira_token_operations(self, storage):
        """Test Jira token operations via generic API."""
        # Use generic API
        result = storage.upsert_token(
            "jira",
            user_id="user123",
            token="jira-token-abc",
            server_url="https://jira.example.com",
            username="john.doe",
        )
        assert result is True

        token_data = storage.get_token("jira", "user123")
        assert token_data is not None
        assert token_data["token"] == "jira-token-abc"

        result = storage.delete_token("jira", "user123")
        assert result is True

    def test_github_token_operations(self, storage):
        """Test GitHub token operations via generic API."""
        result = storage.upsert_token(
            "github",
            user_id="user456",
            token="ghp_abc123",
            server_url="https://api.github.com",
        )
        assert result is True

        token_data = storage.get_token("github", "user456")
        assert token_data is not None
        assert token_data["token"] == "ghp_abc123"

    def test_rhcp_token_operations(self, storage):
        """Test RHCP token operations via generic API."""
        result = storage.upsert_token(
            "rhcp",
            user_id="user789",
            offline_token="rhcp-offline-token-xyz",
        )
        assert result is True

        token_data = storage.get_token("rhcp", "user789")
        assert token_data is not None
        assert token_data["offline_token"] == "rhcp-offline-token-xyz"

    def test_mixing_generic_and_specific_apis(self, storage):
        """Test that generic and specific APIs can be used interchangeably."""
        # Store with specific API
        storage.upsert_token(
            "jira",
            user_id="user123",
            token="jira-token-abc",
            server_url="https://jira.example.com",
        )

        # Retrieve with generic API
        token_data = storage.get_token("jira", "user123")
        assert token_data is not None
        assert token_data["token"] == "jira-token-abc"

        # Update with generic API
        storage.upsert_token(
            "jira",
            "user123",
            token="jira-token-updated",
            server_url="https://jira.example.com",
        )

        # Retrieve with specific API
        token_data = storage.get_token("jira", "user123")
        assert token_data is not None
        assert token_data["token"] == "jira-token-updated"
