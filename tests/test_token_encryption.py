"""Unit tests for token encryption module.

Tests the TokenEncryption class for proper encryption, decryption, error handling,
and edge cases. These tests ensure that the encryption module provides secure,
reliable token protection.
"""

import pytest
from cryptography.fernet import Fernet

from agentllm.db.encryption import (
    DecryptionError,
    EncryptionError,
    EncryptionKeyMissingError,
    TokenEncryption,
)


class TestKeyGeneration:
    """Test encryption key generation."""

    def test_generate_key_produces_valid_fernet_key(self):
        """Generated key should be valid for Fernet encryption."""
        key = TokenEncryption.generate_key()

        # Should be 44 characters (32 bytes base64-encoded)
        assert len(key) == 44
        assert isinstance(key, str)

        # Should be a valid Fernet key
        Fernet(key.encode())  # Should not raise

    def test_generate_key_produces_unique_keys(self):
        """Each call should produce a unique key."""
        key1 = TokenEncryption.generate_key()
        key2 = TokenEncryption.generate_key()

        assert key1 != key2


class TestInitialization:
    """Test TokenEncryption initialization."""

    def test_init_with_explicit_key(self):
        """Should initialize successfully with explicit key parameter."""
        key = TokenEncryption.generate_key()
        encryption = TokenEncryption(encryption_key=key)

        assert encryption is not None

    def test_init_with_env_key(self, monkeypatch):
        """Should load key from AGENTLLM_TOKEN_ENCRYPTION_KEY environment variable."""
        key = TokenEncryption.generate_key()
        monkeypatch.setenv("AGENTLLM_TOKEN_ENCRYPTION_KEY", key)

        encryption = TokenEncryption()  # No explicit key

        assert encryption is not None

    def test_init_missing_key_raises_error(self, monkeypatch):
        """Should raise EncryptionKeyMissingError if no key provided."""
        # Ensure environment variable is not set
        monkeypatch.delenv("AGENTLLM_TOKEN_ENCRYPTION_KEY", raising=False)

        with pytest.raises(EncryptionKeyMissingError) as exc_info:
            TokenEncryption()

        assert "not configured" in str(exc_info.value).lower()
        assert "AGENTLLM_TOKEN_ENCRYPTION_KEY" in str(exc_info.value)

    def test_init_invalid_key_raises_error(self):
        """Should raise EncryptionError if key format is invalid."""
        with pytest.raises(EncryptionError) as exc_info:
            TokenEncryption(encryption_key="invalid-key-too-short")

        assert "invalid" in str(exc_info.value).lower()

    def test_init_explicit_key_overrides_env(self, monkeypatch):
        """Explicit key parameter should take precedence over environment variable."""
        env_key = TokenEncryption.generate_key()
        explicit_key = TokenEncryption.generate_key()
        monkeypatch.setenv("AGENTLLM_TOKEN_ENCRYPTION_KEY", env_key)

        encryption = TokenEncryption(encryption_key=explicit_key)

        # Encrypt with explicit key, should decrypt with same key
        plaintext = "test-token"
        encrypted = encryption.encrypt(plaintext)
        decrypted = encryption.decrypt(encrypted)

        assert decrypted == plaintext


class TestEncryption:
    """Test token encryption functionality."""

    @pytest.fixture
    def encryption(self):
        """Provide a TokenEncryption instance for testing."""
        key = TokenEncryption.generate_key()
        return TokenEncryption(encryption_key=key)

    def test_encrypt_returns_different_output_than_input(self, encryption):
        """Encrypted token should differ from plaintext."""
        plaintext = "my-secret-token"
        encrypted = encryption.encrypt(plaintext)

        assert encrypted != plaintext

    def test_encrypt_produces_base64_string(self, encryption):
        """Encrypted output should be a base64 string."""
        plaintext = "test-token"
        encrypted = encryption.encrypt(plaintext)

        assert isinstance(encrypted, str)
        # Fernet tokens start with "gAAAAA" prefix
        assert encrypted.startswith("gAAAAA")

    def test_encrypt_same_input_produces_different_output(self, encryption):
        """Encrypting same plaintext twice should produce different ciphertexts (nonce randomness)."""
        plaintext = "my-secret-token"
        encrypted1 = encryption.encrypt(plaintext)
        encrypted2 = encryption.encrypt(plaintext)

        # Different due to random IV/nonce
        assert encrypted1 != encrypted2

    def test_encrypt_empty_string(self, encryption):
        """Should successfully encrypt empty string."""
        encrypted = encryption.encrypt("")

        assert encrypted != ""
        assert isinstance(encrypted, str)

    def test_encrypt_unicode_characters(self, encryption):
        """Should handle Unicode characters correctly."""
        plaintext = "token-with-émojis-🔐-and-中文"
        encrypted = encryption.encrypt(plaintext)

        assert encrypted != plaintext
        assert isinstance(encrypted, str)

    def test_encrypt_long_token(self, encryption):
        """Should handle long tokens (e.g., GitHub fine-grained tokens ~93 chars)."""
        # Simulate a GitHub fine-grained token
        plaintext = "github_pat_" + "A" * 82  # 93 characters total
        encrypted = encryption.encrypt(plaintext)

        assert encrypted != plaintext
        assert isinstance(encrypted, str)


class TestDecryption:
    """Test token decryption functionality."""

    @pytest.fixture
    def encryption(self):
        """Provide a TokenEncryption instance for testing."""
        key = TokenEncryption.generate_key()
        return TokenEncryption(encryption_key=key)

    def test_decrypt_roundtrip(self, encryption):
        """Encrypt then decrypt should return original plaintext."""
        plaintext = "my-secret-token"
        encrypted = encryption.encrypt(plaintext)
        decrypted = encryption.decrypt(encrypted)

        assert decrypted == plaintext

    def test_decrypt_empty_string(self, encryption):
        """Should successfully decrypt empty string."""
        encrypted = encryption.encrypt("")
        decrypted = encryption.decrypt(encrypted)

        assert decrypted == ""

    def test_decrypt_unicode_characters(self, encryption):
        """Should correctly decrypt Unicode characters."""
        plaintext = "token-with-émojis-🔐-and-中文"
        encrypted = encryption.encrypt(plaintext)
        decrypted = encryption.decrypt(encrypted)

        assert decrypted == plaintext

    def test_decrypt_long_token(self, encryption):
        """Should correctly decrypt long tokens."""
        plaintext = "github_pat_" + "A" * 82
        encrypted = encryption.encrypt(plaintext)
        decrypted = encryption.decrypt(encrypted)

        assert decrypted == plaintext

    def test_decrypt_with_wrong_key_raises_error(self):
        """Decrypting with different key should raise DecryptionError."""
        key1 = TokenEncryption.generate_key()
        key2 = TokenEncryption.generate_key()

        encryption1 = TokenEncryption(encryption_key=key1)
        encryption2 = TokenEncryption(encryption_key=key2)

        plaintext = "my-secret-token"
        encrypted = encryption1.encrypt(plaintext)

        with pytest.raises(DecryptionError) as exc_info:
            encryption2.decrypt(encrypted)

        assert "decrypt" in str(exc_info.value).lower()

    def test_decrypt_corrupt_data_raises_error(self, encryption):
        """Decrypting corrupt data should raise DecryptionError."""
        # Corrupt encrypted data
        corrupt_data = "gAAAAABcorrupt_base64_data_that_is_not_valid"

        with pytest.raises(DecryptionError) as exc_info:
            encryption.decrypt(corrupt_data)

        assert "decrypt" in str(exc_info.value).lower()

    def test_decrypt_tampered_data_raises_error(self, encryption):
        """Fernet should detect tampered data (authenticated encryption)."""
        plaintext = "my-secret-token"
        encrypted = encryption.encrypt(plaintext)

        # Tamper with encrypted data (flip a bit in the middle)
        tampered = encrypted[:20] + ("X" if encrypted[20] != "X" else "Y") + encrypted[21:]

        with pytest.raises(DecryptionError):
            encryption.decrypt(tampered)

    def test_decrypt_invalid_base64_raises_error(self, encryption):
        """Decrypting invalid base64 should raise DecryptionError."""
        invalid_data = "not-valid-base64!@#$%"

        with pytest.raises(DecryptionError):
            encryption.decrypt(invalid_data)


class TestMultipleInstances:
    """Test encryption/decryption across multiple TokenEncryption instances."""

    def test_same_key_different_instances_can_decrypt(self):
        """Two instances with same key should be able to decrypt each other's tokens."""
        key = TokenEncryption.generate_key()
        encryption1 = TokenEncryption(encryption_key=key)
        encryption2 = TokenEncryption(encryption_key=key)

        plaintext = "my-secret-token"
        encrypted = encryption1.encrypt(plaintext)
        decrypted = encryption2.decrypt(encrypted)

        assert decrypted == plaintext

    def test_different_keys_cannot_decrypt(self):
        """Instances with different keys should not be able to decrypt each other's tokens."""
        key1 = TokenEncryption.generate_key()
        key2 = TokenEncryption.generate_key()
        encryption1 = TokenEncryption(encryption_key=key1)
        encryption2 = TokenEncryption(encryption_key=key2)

        plaintext = "my-secret-token"
        encrypted = encryption1.encrypt(plaintext)

        with pytest.raises(DecryptionError):
            encryption2.decrypt(encrypted)


class TestErrorMessages:
    """Test that error messages are helpful for debugging."""

    def test_missing_key_error_includes_generation_command(self, monkeypatch):
        """Error message should help users generate a key."""
        monkeypatch.delenv("AGENTLLM_TOKEN_ENCRYPTION_KEY", raising=False)

        with pytest.raises(EncryptionKeyMissingError) as exc_info:
            TokenEncryption()

        error_msg = str(exc_info.value)
        assert "generate" in error_msg.lower()
        assert "python -c" in error_msg

    def test_invalid_key_error_includes_format_info(self):
        """Error message should explain expected key format."""
        with pytest.raises(EncryptionError) as exc_info:
            TokenEncryption(encryption_key="too-short")

        error_msg = str(exc_info.value)
        assert "44 characters" in error_msg or "32 bytes" in error_msg

    def test_decryption_error_includes_possible_causes(self):
        """Decryption error should list possible causes."""
        key1 = TokenEncryption.generate_key()
        key2 = TokenEncryption.generate_key()
        encryption1 = TokenEncryption(encryption_key=key1)
        encryption2 = TokenEncryption(encryption_key=key2)

        encrypted = encryption1.encrypt("test")

        with pytest.raises(DecryptionError) as exc_info:
            encryption2.decrypt(encrypted)

        error_msg = str(exc_info.value).lower()
        # Should mention possible causes
        assert "wrong" in error_msg or "corrupt" in error_msg or "tampered" in error_msg
