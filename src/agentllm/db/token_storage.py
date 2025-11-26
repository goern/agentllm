"""Token storage for OAuth credentials and API tokens.

This module provides SQLite-based storage for Jira and Google Drive tokens,
allowing per-user credential management.

All sensitive tokens are encrypted at rest using Fernet symmetric encryption.
"""

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger
from sqlalchemy import (
    Column,
    DateTime,
    Engine,
    Integer,
    String,
    Text,
    create_engine,
    text,
)
from sqlalchemy.orm import declarative_base, scoped_session, sessionmaker

from agentllm.db.encryption import DecryptionError, TokenEncryption
from agentllm.db.token_registry import TokenRegistry, TokenTypeConfig

if TYPE_CHECKING:
    from agno.db.sqlite import SqliteDb

Base = declarative_base()


class JiraToken(Base):
    """Table for storing Jira API tokens."""

    __tablename__ = "jira_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False, unique=True, index=True)
    token = Column(String, nullable=False)
    server_url = Column(String, nullable=False)
    username = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class GoogleDriveToken(Base):
    """Table for storing Google Drive OAuth tokens."""

    __tablename__ = "gdrive_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False, unique=True, index=True)
    token = Column(String, nullable=False)
    refresh_token = Column(String, nullable=True)
    token_uri = Column(String, nullable=True)
    client_id = Column(String, nullable=True)
    client_secret = Column(String, nullable=True)
    scopes = Column(Text, nullable=True)  # JSON array of scopes
    expiry = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class GitHubToken(Base):
    """Table for storing GitHub API tokens."""

    __tablename__ = "github_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False, unique=True, index=True)
    token = Column(String, nullable=False)
    server_url = Column(String, nullable=False, default="https://api.github.com")
    username = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RHCPToken(Base):
    """Table for storing Red Hat Customer Portal offline tokens."""

    __tablename__ = "rhcp_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False, unique=True, index=True)
    offline_token = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FavoriteColor(Base):
    """Table for storing user favorite colors (demo agent)."""

    __tablename__ = "favorite_colors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False, unique=True, index=True)
    color = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TokenStorage:
    """SQLite-based storage for API tokens and OAuth credentials."""

    def __init__(
        self,
        db_url: str | None = None,
        db_file: str | Path | None = None,
        db_engine: Engine | None = None,
        agno_db: "SqliteDb | None" = None,
        encryption_key: str | None = None,
    ):
        """Initialize token storage with database connection and encryption.

        Args:
            db_url: Database URL (e.g., "sqlite:///tokens.db")
            db_file: Path to SQLite database file
            db_engine: Pre-configured SQLAlchemy engine
            agno_db: Agno SqliteDb instance to reuse its engine (recommended)
            encryption_key: Fernet encryption key (loads from AGENTLLM_TOKEN_ENCRYPTION_KEY if None)

        Priority: agno_db > db_engine > db_url > db_file > default (./tokens.db)

        Raises:
            EncryptionKeyMissingError: If encryption key is not provided or found in environment
        """
        # Determine database engine
        if agno_db is not None:
            # Reuse the engine from Agno's SqliteDb
            self.db_engine = agno_db.db_engine
            logger.debug("Reusing Agno SqliteDb engine for TokenStorage")
        elif db_engine is not None:
            self.db_engine = db_engine
        elif db_url is not None:
            self.db_engine = create_engine(db_url)
        elif db_file is not None:
            db_path = Path(db_file).resolve()
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self.db_engine = create_engine(f"sqlite:///{db_path}")
        else:
            # Default to ./tokens.db in current directory
            db_path = Path("./tokens.db").resolve()
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self.db_engine = create_engine(f"sqlite:///{db_path}")

        # Create scoped session
        self.Session = scoped_session(sessionmaker(bind=self.db_engine))

        # Initialize encryption (raises EncryptionKeyMissingError if key not available)
        self._encryption = TokenEncryption(encryption_key)
        logger.info("TokenStorage initialized with encryption enabled")

        # Initialize token type registry
        self._registry = self._initialize_registry()
        logger.debug(f"Registered {len(self._registry.list_types())} token types")

        # Create tables
        self._create_tables()

        logger.debug(f"TokenStorage initialized with database: {self.db_engine.url}")

    @property
    def db_path(self) -> str:
        """Get the database path from the engine URL.

        Returns:
            Database path as a string
        """
        return str(self.db_engine.url)

    def _create_tables(self):
        """Create database tables if they don't exist."""
        Base.metadata.create_all(self.db_engine)
        logger.debug("Token storage tables created/verified")

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the database.

        Args:
            table_name: Name of the table to check

        Returns:
            True if table exists, False otherwise
        """
        try:
            with self.Session() as sess:
                result = sess.execute(text(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'"))
                return result.fetchone() is not None
        except Exception as e:
            logger.error(f"Error checking if table {table_name} exists: {e}")
            return False

    # Encryption helper methods

    def _encrypt_token(self, plaintext: str) -> str:
        """Encrypt token for database storage.

        Args:
            plaintext: The token string to encrypt

        Returns:
            Encrypted token (base64 string)

        Raises:
            EncryptionError: If encryption fails
        """
        try:
            return self._encryption.encrypt(plaintext)
        except Exception as e:
            logger.error(f"Token encryption failed: {e}")
            raise

    def _decrypt_token(self, encrypted: str) -> str:
        """Decrypt token from database storage.

        Args:
            encrypted: The encrypted token from database

        Returns:
            Decrypted plaintext token

        Raises:
            DecryptionError: If decryption fails
        """
        try:
            return self._encryption.decrypt(encrypted)
        except Exception as e:
            logger.error(f"Token decryption failed: {e}")
            raise

    # Token Type Registry

    def _initialize_registry(self) -> TokenRegistry:
        """Initialize token type registry with all known token types.

        Returns:
            Configured TokenRegistry instance
        """
        registry = TokenRegistry()

        # Register Jira tokens
        registry.register(
            "jira",
            TokenTypeConfig(
                model=JiraToken,
                encrypted_fields=["token"],
            ),
        )

        # Register GitHub tokens
        registry.register(
            "github",
            TokenTypeConfig(
                model=GitHubToken,
                encrypted_fields=["token"],
            ),
        )

        # Register Google Drive tokens
        # Import serializers from gdrive_config (late import to avoid circular dependency)
        from agentllm.agents.toolkit_configs.gdrive_config import (
            deserialize_gdrive_credentials,
            serialize_gdrive_credentials,
        )

        registry.register(
            "gdrive",
            TokenTypeConfig(
                model=GoogleDriveToken,
                encrypted_fields=["token", "refresh_token", "client_secret"],
                serializer=serialize_gdrive_credentials,
                deserializer=deserialize_gdrive_credentials,
            ),
        )

        # Register RHCP tokens
        registry.register(
            "rhcp",
            TokenTypeConfig(
                model=RHCPToken,
                encrypted_fields=["offline_token"],
            ),
        )

        return registry

    # Generic Token Operations

    def upsert_token(self, token_type: str, user_id: str, **data: Any) -> bool:
        """Store or update token for a user (generic method).

        Args:
            token_type: Token type identifier (e.g., "jira", "github", "gdrive", "rhcp")
            user_id: Unique user identifier
            **data: Token data fields (varies by token type)

        Returns:
            True if successful, False otherwise

        Raises:
            KeyError: If token_type is not registered

        Example:
            >>> storage.upsert_token("jira", "user123", token="abc", server_url="https://jira.com")
            >>> storage.upsert_token("github", "user123", token="ghp_xyz", server_url="https://api.github.com")
        """
        try:
            config = self._registry.get(token_type)

            with self.Session() as sess:
                # Check if token exists
                existing = sess.query(config.model).filter_by(user_id=user_id).first()

                # Prepare data for storage
                storage_data = data.copy()

                # Apply serializer if configured (e.g., for Google Credentials)
                if config.serializer and "credentials" in data:
                    storage_data = config.serializer(data["credentials"])

                # Encrypt sensitive fields
                for field_name in config.encrypted_fields:
                    if field_name in storage_data and storage_data[field_name]:
                        storage_data[field_name] = self._encrypt_token(storage_data[field_name])

                if existing:
                    # Update existing token
                    for key, value in storage_data.items():
                        if hasattr(existing, key):
                            setattr(existing, key, value)
                    existing.updated_at = datetime.utcnow()
                    logger.debug(f"Updating {token_type} token for user {user_id}")
                else:
                    # Insert new token
                    new_token = config.model(user_id=user_id, **storage_data)
                    sess.add(new_token)
                    logger.debug(f"Inserting new {token_type} token for user {user_id}")

                sess.commit()
                return True

        except KeyError:
            logger.error(f"Unknown token type: {token_type}")
            raise
        except Exception as e:
            logger.error(f"Error upserting {token_type} token for user {user_id}: {e}")
            return False

    def get_token(self, token_type: str, user_id: str) -> dict[str, Any] | Any | None:
        """Retrieve token for a user (generic method).

        Args:
            token_type: Token type identifier
            user_id: Unique user identifier

        Returns:
            Dictionary with token data (or deserialized object if deserializer configured),
            or None if not found or decryption fails

        Raises:
            KeyError: If token_type is not registered

        Example:
            >>> jira_data = storage.get_token("jira", "user123")
            >>> print(jira_data["token"])  # Decrypted token
            >>> gdrive_creds = storage.get_token("gdrive", "user123")  # Returns Credentials object
        """
        try:
            config = self._registry.get(token_type)

            with self.Session() as sess:
                token_record = sess.query(config.model).filter_by(user_id=user_id).first()

                if not token_record:
                    return None

                # Convert SQLAlchemy model to dict
                token_data = {}
                for column in config.model.__table__.columns:
                    value = getattr(token_record, column.name)
                    token_data[column.name] = value

                # Decrypt sensitive fields
                for field_name in config.encrypted_fields:
                    if field_name in token_data and token_data[field_name]:
                        try:
                            token_data[field_name] = self._decrypt_token(token_data[field_name])
                        except DecryptionError as e:
                            logger.error(f"Failed to decrypt {token_type} {field_name} for user {user_id}: {e}")
                            return None

                # Apply deserializer if configured (e.g., for Google Credentials)
                if config.deserializer:
                    return config.deserializer(token_data)

                return token_data

        except KeyError:
            logger.error(f"Unknown token type: {token_type}")
            raise
        except Exception as e:
            logger.error(f"Error retrieving {token_type} token for user {user_id}: {e}")
            return None

    def delete_token(self, token_type: str, user_id: str) -> bool:
        """Delete token for a user (generic method).

        Args:
            token_type: Token type identifier
            user_id: Unique user identifier

        Returns:
            True if successful, False otherwise

        Raises:
            KeyError: If token_type is not registered

        Example:
            >>> storage.delete_token("jira", "user123")
            >>> storage.delete_token("github", "user123")
        """
        try:
            config = self._registry.get(token_type)

            with self.Session() as sess:
                token_record = sess.query(config.model).filter_by(user_id=user_id).first()

                if token_record:
                    sess.delete(token_record)
                    sess.commit()
                    logger.debug(f"Deleted {token_type} token for user {user_id}")
                    return True

                logger.warning(f"No {token_type} token found for user {user_id}")
                return False

        except KeyError:
            logger.error(f"Unknown token type: {token_type}")
            raise
        except Exception as e:
            logger.error(f"Error deleting {token_type} token for user {user_id}: {e}")
            return False

    # Favorite Color Operations (demo agent - not using registry since it doesn't need encryption)

    def upsert_favorite_color(self, user_id: str, color: str) -> bool:
        """Store or update favorite color for a user.

        Args:
            user_id: Unique user identifier
            color: Favorite color name

        Returns:
            True if successful, False otherwise
        """
        try:
            with self.Session() as sess:
                # Check if color exists
                existing = sess.query(FavoriteColor).filter_by(user_id=user_id).first()

                if existing:
                    # Update existing color
                    existing.color = color
                    existing.updated_at = datetime.utcnow()
                    logger.debug(f"Updating favorite color for user {user_id} to {color}")
                else:
                    # Insert new color
                    new_color = FavoriteColor(
                        user_id=user_id,
                        color=color,
                    )
                    sess.add(new_color)
                    logger.debug(f"Inserting new favorite color for user {user_id}: {color}")

                sess.commit()
                return True

        except Exception as e:
            logger.error(f"Error upserting favorite color for user {user_id}: {e}")
            return False

    def get_favorite_color(self, user_id: str) -> str | None:
        """Retrieve favorite color for a user.

        Args:
            user_id: Unique user identifier

        Returns:
            Color string, or None if not found
        """
        try:
            with self.Session() as sess:
                color_record = sess.query(FavoriteColor).filter_by(user_id=user_id).first()

                if color_record:
                    logger.debug(f"Retrieved favorite color for user {user_id}: {color_record.color}")
                    return color_record.color

                logger.debug(f"No favorite color found for user {user_id}")
                return None

        except Exception as e:
            logger.error(f"Error retrieving favorite color for user {user_id}: {e}")
            return None

    def delete_favorite_color(self, user_id: str) -> bool:
        """Delete favorite color for a user.

        Args:
            user_id: Unique user identifier

        Returns:
            True if successful, False otherwise
        """
        try:
            with self.Session() as sess:
                color_record = sess.query(FavoriteColor).filter_by(user_id=user_id).first()

                if color_record:
                    sess.delete(color_record)
                    sess.commit()
                    logger.debug(f"Deleted favorite color for user {user_id}")
                    return True

                logger.warning(f"No favorite color found for user {user_id}")
                return False

        except Exception as e:
            logger.error(f"Error deleting favorite color for user {user_id}: {e}")
            return False

    def close(self):
        """Close database connection and cleanup."""
        try:
            self.Session.remove()
            self.db_engine.dispose()
            logger.debug("TokenStorage closed successfully")
        except Exception as e:
            logger.error(f"Error closing TokenStorage: {e}")
