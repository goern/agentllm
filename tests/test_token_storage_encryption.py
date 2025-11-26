"""Integration tests for TokenStorage encryption.

Tests that tokens are properly encrypted when stored and decrypted when retrieved,
covering all four token types: Jira, GitHub, Google Drive, and RHCP.
"""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest
from google.oauth2.credentials import Credentials

from agentllm.db.encryption import EncryptionKeyMissingError, TokenEncryption
from agentllm.db.token_storage import TokenStorage


class TestTokenStorageInitialization:
    """Test TokenStorage initialization with encryption."""

    def test_init_without_key_raises_error(self, monkeypatch):
        """TokenStorage should fail to initialize without encryption key."""
        monkeypatch.delenv("AGENTLLM_TOKEN_ENCRYPTION_KEY", raising=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = Path(tmpdir) / "test.db"

            with pytest.raises(EncryptionKeyMissingError):
                TokenStorage(db_file=db_file)

    def test_init_with_explicit_key(self):
        """TokenStorage should initialize successfully with explicit key."""
        key = TokenEncryption.generate_key()

        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = Path(tmpdir) / "test.db"
            storage = TokenStorage(db_file=db_file, encryption_key=key)

            assert storage is not None

    def test_init_with_env_key(self, monkeypatch):
        """TokenStorage should initialize with key from environment."""
        key = TokenEncryption.generate_key()
        monkeypatch.setenv("AGENTLLM_TOKEN_ENCRYPTION_KEY", key)

        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = Path(tmpdir) / "test.db"
            storage = TokenStorage(db_file=db_file)

            assert storage is not None


class TestJiraTokenEncryption:
    """Test Jira token encryption and decryption."""

    @pytest.fixture
    def storage(self):
        """Provide a TokenStorage instance with encryption."""
        key = TokenEncryption.generate_key()
        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = Path(tmpdir) / "test.db"
            yield TokenStorage(db_file=db_file, encryption_key=key)

    def test_jira_token_roundtrip(self, storage):
        """Jira token should be encrypted when stored and decrypted when retrieved."""
        user_id = "test-user"
        token = "jira-api-token-12345"
        server_url = "https://issues.redhat.com"
        username = "test@example.com"

        # Store token
        success = storage.upsert_token(
            "jira",
            user_id=user_id,
            token=token,
            server_url=server_url,
            username=username,
        )
        assert success is True

        # Retrieve token
        retrieved = storage.get_token("jira", user_id)
        assert retrieved is not None
        assert retrieved["token"] == token  # Should match original plaintext
        assert retrieved["server_url"] == server_url
        assert retrieved["username"] == username

    def test_jira_token_encrypted_at_rest(self, storage):
        """Jira token should be stored encrypted in database."""
        user_id = "test-user"
        plaintext_token = "jira-api-token-secret"
        server_url = "https://issues.redhat.com"

        # Store token
        storage.upsert_token(
            "jira",
            user_id=user_id,
            token=plaintext_token,
            server_url=server_url,
        )

        # Directly query database to verify encryption
        with storage.Session() as sess:
            from agentllm.db.token_storage import JiraToken

            record = sess.query(JiraToken).filter_by(user_id=user_id).first()
            assert record is not None
            assert record.token != plaintext_token  # Should be encrypted
            assert record.token.startswith("gAAAAA")  # Fernet prefix

    def test_jira_token_update_replaces_encrypted_value(self, storage):
        """Updating Jira token should replace with newly encrypted value."""
        user_id = "test-user"
        token1 = "first-token"
        token2 = "second-token"
        server_url = "https://issues.redhat.com"

        # Store first token
        storage.upsert_token("jira", user_id=user_id, token=token1, server_url=server_url)

        # Store second token (update)
        storage.upsert_token("jira", user_id=user_id, token=token2, server_url=server_url)

        # Retrieve - should get second token
        retrieved = storage.get_token("jira", user_id)
        assert retrieved["token"] == token2

    def test_jira_token_decrypt_with_wrong_key_returns_none(self):
        """Decrypting with wrong key should return None, not raise error."""
        key1 = TokenEncryption.generate_key()
        key2 = TokenEncryption.generate_key()

        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = Path(tmpdir) / "test.db"

            # Store with key1
            storage1 = TokenStorage(db_file=db_file, encryption_key=key1)
            storage1.upsert_token(
                "jira",
                user_id="test-user",
                token="secret-token",
                server_url="https://issues.redhat.com",
            )

            # Try to retrieve with key2
            storage2 = TokenStorage(db_file=db_file, encryption_key=key2)
            retrieved = storage2.get_token("jira", "test-user")
            assert retrieved is None  # Should return None, not raise


class TestGitHubTokenEncryption:
    """Test GitHub token encryption and decryption."""

    @pytest.fixture
    def storage(self):
        """Provide a TokenStorage instance with encryption."""
        key = TokenEncryption.generate_key()
        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = Path(tmpdir) / "test.db"
            yield TokenStorage(db_file=db_file, encryption_key=key)

    def test_github_token_roundtrip(self, storage):
        """GitHub token should be encrypted when stored and decrypted when retrieved."""
        user_id = "test-user"
        token = "github_pat_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"
        server_url = "https://api.github.com"
        username = "testuser"

        # Store token
        success = storage.upsert_token(
            "github",
            user_id=user_id,
            token=token,
            server_url=server_url,
            username=username,
        )
        assert success is True

        # Retrieve token
        retrieved = storage.get_token("github", user_id)
        assert retrieved is not None
        assert retrieved["token"] == token
        assert retrieved["server_url"] == server_url
        assert retrieved["username"] == username

    def test_github_token_encrypted_at_rest(self, storage):
        """GitHub token should be stored encrypted in database."""
        user_id = "test-user"
        plaintext_token = "ghp_secrettoken123"

        # Store token
        storage.upsert_token(
            "github",
            user_id=user_id,
            token=plaintext_token,
            server_url="https://api.github.com",
        )

        # Directly query database
        with storage.Session() as sess:
            from agentllm.db.token_storage import GitHubToken

            record = sess.query(GitHubToken).filter_by(user_id=user_id).first()
            assert record is not None
            assert record.token != plaintext_token  # Should be encrypted
            assert record.token.startswith("gAAAAA")  # Fernet prefix


class TestGoogleDriveTokenEncryption:
    """Test Google Drive token encryption and decryption."""

    @pytest.fixture
    def storage(self):
        """Provide a TokenStorage instance with encryption."""
        key = TokenEncryption.generate_key()
        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = Path(tmpdir) / "test.db"
            yield TokenStorage(db_file=db_file, encryption_key=key)

    def test_gdrive_token_roundtrip(self, storage):
        """Google Drive OAuth credentials should be encrypted and decrypted correctly."""
        user_id = "test-user"
        credentials = Credentials(
            token="access-token-12345",
            refresh_token="refresh-token-67890",
            token_uri="https://oauth2.googleapis.com/token",
            client_id="client-id-abc",
            client_secret="client-secret-xyz",
            scopes=["https://www.googleapis.com/auth/drive.readonly"],
        )
        credentials.expiry = datetime(2025, 12, 31)

        # Store credentials
        success = storage.upsert_token("gdrive", user_id=user_id, credentials=credentials)
        assert success is True

        # Retrieve credentials
        retrieved = storage.get_token("gdrive", user_id)
        assert retrieved is not None
        assert retrieved.token == credentials.token
        assert retrieved.refresh_token == credentials.refresh_token
        assert retrieved.client_secret == credentials.client_secret
        assert retrieved.scopes == credentials.scopes

    def test_gdrive_all_three_fields_encrypted_at_rest(self, storage):
        """All three sensitive fields should be encrypted: token, refresh_token, client_secret."""
        user_id = "test-user"
        credentials = Credentials(
            token="access-token",
            refresh_token="refresh-token",
            token_uri="https://oauth2.googleapis.com/token",
            client_id="client-id",
            client_secret="client-secret",
            scopes=["https://www.googleapis.com/auth/drive"],
        )

        # Store credentials
        storage.upsert_token("gdrive", user_id=user_id, credentials=credentials)

        # Directly query database
        with storage.Session() as sess:
            from agentllm.db.token_storage import GoogleDriveToken

            record = sess.query(GoogleDriveToken).filter_by(user_id=user_id).first()
            assert record is not None

            # All three fields should be encrypted
            assert record.token != credentials.token
            assert record.token.startswith("gAAAAA")

            assert record.refresh_token != credentials.refresh_token
            assert record.refresh_token.startswith("gAAAAA")

            assert record.client_secret != credentials.client_secret
            assert record.client_secret.startswith("gAAAAA")

            # Client ID should NOT be encrypted (not sensitive in this context)
            assert record.client_id == credentials.client_id

    def test_gdrive_token_with_none_refresh_token(self, storage):
        """Should handle None refresh_token and client_secret gracefully."""
        user_id = "test-user"
        credentials = Credentials(
            token="access-token-only",
            refresh_token=None,  # Can be None
            token_uri="https://oauth2.googleapis.com/token",
            client_id="client-id",
            client_secret=None,  # Can be None
            scopes=["https://www.googleapis.com/auth/drive"],
        )

        # Store credentials
        success = storage.upsert_token("gdrive", user_id=user_id, credentials=credentials)
        assert success is True

        # Retrieve credentials
        retrieved = storage.get_token("gdrive", user_id)
        assert retrieved is not None
        assert retrieved.token == credentials.token
        assert retrieved.refresh_token is None
        assert retrieved.client_secret is None


class TestRHCPTokenEncryption:
    """Test RHCP offline token encryption and decryption."""

    @pytest.fixture
    def storage(self):
        """Provide a TokenStorage instance with encryption."""
        key = TokenEncryption.generate_key()
        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = Path(tmpdir) / "test.db"
            yield TokenStorage(db_file=db_file, encryption_key=key)

    def test_rhcp_token_roundtrip(self, storage):
        """RHCP offline token should be encrypted and decrypted correctly."""
        user_id = "test-user"
        offline_token = "rhcp-offline-token-jwt-very-long-string"

        # Store token
        success = storage.upsert_token("rhcp", user_id=user_id, offline_token=offline_token)
        assert success is True

        # Retrieve token
        retrieved = storage.get_token("rhcp", user_id)
        assert retrieved is not None
        assert retrieved["offline_token"] == offline_token

    def test_rhcp_token_encrypted_at_rest(self, storage):
        """RHCP offline token should be stored encrypted in database."""
        user_id = "test-user"
        plaintext_token = "secret-offline-token"

        # Store token
        storage.upsert_token("rhcp", user_id=user_id, offline_token=plaintext_token)

        # Directly query database
        with storage.Session() as sess:
            from agentllm.db.token_storage import RHCPToken

            record = sess.query(RHCPToken).filter_by(user_id=user_id).first()
            assert record is not None
            assert record.offline_token != plaintext_token  # Should be encrypted
            assert record.offline_token.startswith("gAAAAA")  # Fernet prefix


class TestMultipleUsersIsolation:
    """Test that encryption works correctly with multiple users."""

    @pytest.fixture
    def storage(self):
        """Provide a TokenStorage instance with encryption."""
        key = TokenEncryption.generate_key()
        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = Path(tmpdir) / "test.db"
            yield TokenStorage(db_file=db_file, encryption_key=key)

    def test_multiple_users_jira_tokens(self, storage):
        """Multiple users' Jira tokens should be encrypted independently."""
        users = [
            ("user1", "token1"),
            ("user2", "token2"),
            ("user3", "token3"),
        ]

        # Store tokens for all users
        for user_id, token in users:
            storage.upsert_token(
                "jira",
                user_id=user_id,
                token=token,
                server_url="https://issues.redhat.com",
            )

        # Retrieve and verify each user's token
        for user_id, expected_token in users:
            retrieved = storage.get_token("jira", user_id)
            assert retrieved is not None
            assert retrieved["token"] == expected_token


class TestCorruptDataHandling:
    """Test handling of corrupt encrypted data."""

    @pytest.fixture
    def storage(self):
        """Provide a TokenStorage instance with encryption."""
        key = TokenEncryption.generate_key()
        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = Path(tmpdir) / "test.db"
            yield TokenStorage(db_file=db_file, encryption_key=key)

    def test_corrupt_jira_token_returns_none(self, storage):
        """Corrupt encrypted Jira token should return None, not crash."""
        user_id = "test-user"

        # Store a valid token first
        storage.upsert_token(
            "jira",
            user_id=user_id,
            token="valid-token",
            server_url="https://issues.redhat.com",
        )

        # Corrupt the token in database
        with storage.Session() as sess:
            from agentllm.db.token_storage import JiraToken

            record = sess.query(JiraToken).filter_by(user_id=user_id).first()
            record.token = "gAAAAAcorrupt_data_not_valid"
            sess.commit()

        # Try to retrieve - should return None
        retrieved = storage.get_token("jira", user_id)
        assert retrieved is None


class TestTokenDeletion:
    """Test that token deletion works with encryption."""

    @pytest.fixture
    def storage(self):
        """Provide a TokenStorage instance with encryption."""
        key = TokenEncryption.generate_key()
        with tempfile.TemporaryDirectory() as tmpdir:
            db_file = Path(tmpdir) / "test.db"
            yield TokenStorage(db_file=db_file, encryption_key=key)

    def test_delete_jira_token(self, storage):
        """Deleting Jira token should work correctly."""
        user_id = "test-user"

        # Store token
        storage.upsert_token(
            "jira",
            user_id=user_id,
            token="token-to-delete",
            server_url="https://issues.redhat.com",
        )

        # Verify it exists
        assert storage.get_token("jira", user_id) is not None

        # Delete token
        success = storage.delete_token("jira", user_id)
        assert success is True

        # Verify it's gone
        assert storage.get_token("jira", user_id) is None

    def test_delete_github_token(self, storage):
        """Deleting GitHub token should work correctly."""
        user_id = "test-user"

        # Store token
        storage.upsert_token(
            "github",
            user_id=user_id,
            token="token-to-delete",
            server_url="https://api.github.com",
        )

        # Delete and verify
        assert storage.delete_token("github", user_id) is True
        assert storage.get_token("github", user_id) is None

    def test_delete_gdrive_token(self, storage):
        """Deleting Google Drive token should work correctly."""
        user_id = "test-user"
        credentials = Credentials(
            token="access-token",
            refresh_token="refresh-token",
            token_uri="https://oauth2.googleapis.com/token",
            client_id="client-id",
            client_secret="client-secret",
            scopes=["https://www.googleapis.com/auth/drive"],
        )

        # Store and delete
        storage.upsert_token("gdrive", user_id=user_id, credentials=credentials)
        assert storage.delete_token("gdrive", user_id) is True
        assert storage.get_token("gdrive", user_id) is None

    def test_delete_rhcp_token(self, storage):
        """Deleting RHCP token should work correctly."""
        user_id = "test-user"

        # Store and delete
        storage.upsert_token("rhcp", user_id=user_id, offline_token="offline-token")
        assert storage.delete_token("rhcp", user_id) is True
        assert storage.get_token("rhcp", user_id) is None
