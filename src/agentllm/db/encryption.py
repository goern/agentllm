"""Token encryption module using Fernet symmetric encryption.

This module provides secure encryption for sensitive tokens stored in the database.
All tokens (Jira, GitHub, Google Drive, RHCP) are encrypted at rest using Fernet,
which provides authenticated encryption (AES-128-CBC + HMAC-SHA256).

Usage:
    from agentllm.db.encryption import TokenEncryption

    # Initialize with encryption key
    encryption = TokenEncryption()  # Loads from AGENTLLM_TOKEN_ENCRYPTION_KEY

    # Encrypt token before storing
    encrypted = encryption.encrypt("my-secret-token")

    # Decrypt token after retrieving
    plaintext = encryption.decrypt(encrypted)

Security Notes:
    - Encryption key must be 32 bytes (44 chars base64-encoded)
    - Key is loaded from AGENTLLM_TOKEN_ENCRYPTION_KEY environment variable
    - If key is missing, EncryptionKeyMissingError is raised (fail-fast)
    - Encrypted tokens are returned as base64 strings (safe for SQLite TEXT)
    - Never log tokens or encryption keys
"""

import logging
import os

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class EncryptionError(Exception):
    """Base exception for encryption-related errors."""

    pass


class EncryptionKeyMissingError(EncryptionError):
    """Raised when encryption key is not configured."""

    pass


class DecryptionError(EncryptionError):
    """Raised when decryption fails (corrupt data or wrong key)."""

    pass


class TokenEncryption:
    """Handles encryption and decryption of tokens using Fernet symmetric encryption.

    Fernet provides authenticated encryption, ensuring both confidentiality and integrity.
    It uses AES-128 in CBC mode with PKCS7 padding and HMAC-SHA256 for authentication.

    Attributes:
        _cipher: Fernet cipher instance for encryption/decryption operations
    """

    def __init__(self, encryption_key: str | None = None):
        """Initialize token encryption with the provided or environment key.

        Args:
            encryption_key: Base64-encoded Fernet key (32 bytes).
                          If None, loads from AGENTLLM_TOKEN_ENCRYPTION_KEY env var.

        Raises:
            EncryptionKeyMissingError: If no encryption key is provided or found in environment
            EncryptionError: If the encryption key format is invalid
        """
        # Load key from parameter or environment
        key = encryption_key or os.getenv("AGENTLLM_TOKEN_ENCRYPTION_KEY")

        if not key:
            raise EncryptionKeyMissingError(
                "Encryption key not configured. Set AGENTLLM_TOKEN_ENCRYPTION_KEY environment variable. "
                'Generate a key with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
            )

        # Validate and initialize Fernet cipher
        try:
            self._cipher = Fernet(key.encode())
            logger.debug("Token encryption initialized successfully")
        except Exception as e:
            raise EncryptionError(f"Invalid encryption key format. Key must be 44 characters (32 bytes base64-encoded). Error: {e}") from e

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext token.

        Args:
            plaintext: The token string to encrypt

        Returns:
            Base64-encoded encrypted token (safe for SQLite TEXT columns)

        Raises:
            EncryptionError: If encryption fails

        Example:
            >>> encryption = TokenEncryption()
            >>> encrypted = encryption.encrypt("my-secret-token")
            >>> print(encrypted)  # gAAAAABl...base64...
        """
        try:
            # Convert string to bytes, encrypt, return as base64 string
            encrypted_bytes = self._cipher.encrypt(plaintext.encode("utf-8"))
            return encrypted_bytes.decode("utf-8")
        except Exception as e:
            logger.error(f"Token encryption failed: {e}")
            raise EncryptionError(f"Failed to encrypt token: {e}") from e

    def decrypt(self, encrypted: str) -> str:
        """Decrypt an encrypted token.

        Args:
            encrypted: Base64-encoded encrypted token

        Returns:
            Decrypted plaintext token

        Raises:
            DecryptionError: If decryption fails (corrupt data, wrong key, or tampered data)

        Example:
            >>> encryption = TokenEncryption()
            >>> plaintext = encryption.decrypt("gAAAAABl...base64...")
            >>> print(plaintext)  # my-secret-token
        """
        try:
            # Convert base64 string to bytes, decrypt, return as string
            decrypted_bytes = self._cipher.decrypt(encrypted.encode("utf-8"))
            return decrypted_bytes.decode("utf-8")
        except InvalidToken:
            # Fernet raises InvalidToken for wrong key, corrupt data, or tampered data
            raise DecryptionError(
                "Failed to decrypt token. This could mean: (1) wrong encryption key, (2) corrupt data, or (3) tampered data"
            ) from None
        except Exception as e:
            logger.error(f"Token decryption failed: {e}")
            raise DecryptionError(f"Failed to decrypt token: {e}") from e

    @staticmethod
    def generate_key() -> str:
        """Generate a new Fernet encryption key.

        Returns:
            Base64-encoded 32-byte key suitable for Fernet encryption

        Example:
            >>> key = TokenEncryption.generate_key()
            >>> print(key)  # eSsSRZhHEmUJyrC43OFHUed0fDjhrKtTaDWQKVZpRRY=
            >>> print(len(key))  # 44 characters
        """
        return Fernet.generate_key().decode("utf-8")
