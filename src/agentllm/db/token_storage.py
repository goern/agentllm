"""Token storage for OAuth credentials and API tokens.

This module provides SQLite-based storage for Jira and Google Drive tokens,
allowing per-user credential management.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from google.oauth2.credentials import Credentials
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


class TokenStorage:
    """SQLite-based storage for API tokens and OAuth credentials."""

    def __init__(
        self,
        db_url: str | None = None,
        db_file: str | Path | None = None,
        db_engine: Engine | None = None,
        agno_db: "SqliteDb | None" = None,
    ):
        """Initialize token storage with database connection.

        Args:
            db_url: Database URL (e.g., "sqlite:///tokens.db")
            db_file: Path to SQLite database file
            db_engine: Pre-configured SQLAlchemy engine
            agno_db: Agno SqliteDb instance to reuse its engine (recommended)

        Priority: agno_db > db_engine > db_url > db_file > default (./tokens.db)
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

        # Create tables
        self._create_tables()

        logger.debug(f"TokenStorage initialized with database: {self.db_engine.url}")

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

    # Jira Token Operations

    def upsert_jira_token(
        self,
        user_id: str,
        token: str,
        server_url: str,
        username: str | None = None,
    ) -> bool:
        """Store or update Jira API token for a user.

        Args:
            user_id: Unique user identifier
            token: Jira API token or personal access token
            server_url: Jira server URL (e.g., "https://issues.redhat.com")
            username: Optional username for basic auth

        Returns:
            True if successful, False otherwise
        """
        try:
            with self.Session() as sess:
                # Check if token exists
                existing = sess.query(JiraToken).filter_by(user_id=user_id).first()

                if existing:
                    # Update existing token
                    existing.token = token
                    existing.server_url = server_url
                    existing.username = username
                    existing.updated_at = datetime.utcnow()
                    logger.debug(f"Updating Jira token for user {user_id}")
                else:
                    # Insert new token
                    new_token = JiraToken(
                        user_id=user_id,
                        token=token,
                        server_url=server_url,
                        username=username,
                    )
                    sess.add(new_token)
                    logger.debug(f"Inserting new Jira token for user {user_id}")

                sess.commit()
                return True

        except Exception as e:
            logger.error(f"Error upserting Jira token for user {user_id}: {e}")
            return False

    def get_jira_token(self, user_id: str) -> dict[str, Any] | None:
        """Retrieve Jira token for a user.

        Args:
            user_id: Unique user identifier

        Returns:
            Dictionary with token data, or None if not found
        """
        try:
            with self.Session() as sess:
                token_record = sess.query(JiraToken).filter_by(user_id=user_id).first()

                if token_record:
                    return {
                        "user_id": token_record.user_id,
                        "token": token_record.token,
                        "server_url": token_record.server_url,
                        "username": token_record.username,
                        "created_at": token_record.created_at,
                        "updated_at": token_record.updated_at,
                    }

                return None

        except Exception as e:
            logger.error(f"Error retrieving Jira token for user {user_id}: {e}")
            return None

    def delete_jira_token(self, user_id: str) -> bool:
        """Delete Jira token for a user.

        Args:
            user_id: Unique user identifier

        Returns:
            True if successful, False otherwise
        """
        try:
            with self.Session() as sess:
                token_record = sess.query(JiraToken).filter_by(user_id=user_id).first()

                if token_record:
                    sess.delete(token_record)
                    sess.commit()
                    logger.debug(f"Deleted Jira token for user {user_id}")
                    return True

                logger.warning(f"No Jira token found for user {user_id}")
                return False

        except Exception as e:
            logger.error(f"Error deleting Jira token for user {user_id}: {e}")
            return False

    # Google Drive Token Operations

    def upsert_gdrive_token(
        self,
        user_id: str,
        credentials: Credentials,
    ) -> bool:
        """Store or update Google Drive OAuth credentials for a user.

        Args:
            user_id: Unique user identifier
            credentials: Google OAuth2 credentials object

        Returns:
            True if successful, False otherwise
        """
        try:
            with self.Session() as sess:
                # Serialize scopes as JSON
                scopes_json = json.dumps(credentials.scopes) if credentials.scopes else None

                # Check if token exists
                existing = sess.query(GoogleDriveToken).filter_by(user_id=user_id).first()

                if existing:
                    # Update existing token
                    existing.token = credentials.token
                    existing.refresh_token = credentials.refresh_token
                    existing.token_uri = credentials.token_uri
                    existing.client_id = credentials.client_id
                    existing.client_secret = credentials.client_secret
                    existing.scopes = scopes_json
                    existing.expiry = credentials.expiry
                    existing.updated_at = datetime.utcnow()
                    logger.debug(f"Updating Google Drive token for user {user_id}")
                else:
                    # Insert new token
                    new_token = GoogleDriveToken(
                        user_id=user_id,
                        token=credentials.token,
                        refresh_token=credentials.refresh_token,
                        token_uri=credentials.token_uri,
                        client_id=credentials.client_id,
                        client_secret=credentials.client_secret,
                        scopes=scopes_json,
                        expiry=credentials.expiry,
                    )
                    sess.add(new_token)
                    logger.debug(f"Inserting new Google Drive token for user {user_id}")

                sess.commit()
                return True

        except Exception as e:
            logger.error(f"Error upserting Google Drive token for user {user_id}: {e}")
            return False

    def get_gdrive_credentials(self, user_id: str) -> Credentials | None:
        """Retrieve Google Drive OAuth credentials for a user.

        Args:
            user_id: Unique user identifier

        Returns:
            Google OAuth2 Credentials object, or None if not found
        """
        try:
            with self.Session() as sess:
                token_record = sess.query(GoogleDriveToken).filter_by(user_id=user_id).first()

                if token_record:
                    # Deserialize scopes
                    scopes = json.loads(token_record.scopes) if token_record.scopes else None

                    # Reconstruct Credentials object
                    credentials = Credentials(
                        token=token_record.token,
                        refresh_token=token_record.refresh_token,
                        token_uri=token_record.token_uri,
                        client_id=token_record.client_id,
                        client_secret=token_record.client_secret,
                        scopes=scopes,
                    )

                    # Set expiry if available
                    if token_record.expiry:
                        credentials.expiry = token_record.expiry

                    return credentials

                return None

        except Exception as e:
            logger.error(f"Error retrieving Google Drive token for user {user_id}: {e}")
            return None

    def get_gdrive_token_info(self, user_id: str) -> dict[str, Any] | None:
        """Retrieve Google Drive token metadata (without reconstructing Credentials).

        Args:
            user_id: Unique user identifier

        Returns:
            Dictionary with token metadata, or None if not found
        """
        try:
            with self.Session() as sess:
                token_record = sess.query(GoogleDriveToken).filter_by(user_id=user_id).first()

                if token_record:
                    return {
                        "user_id": token_record.user_id,
                        "token": token_record.token[:20] + "...",  # Truncated for security
                        "has_refresh_token": token_record.refresh_token is not None,
                        "scopes": (json.loads(token_record.scopes) if token_record.scopes else None),
                        "expiry": token_record.expiry,
                        "created_at": token_record.created_at,
                        "updated_at": token_record.updated_at,
                    }

                return None

        except Exception as e:
            logger.error(f"Error retrieving Google Drive token info for user {user_id}: {e}")
            return None

    def delete_gdrive_token(self, user_id: str) -> bool:
        """Delete Google Drive token for a user.

        Args:
            user_id: Unique user identifier

        Returns:
            True if successful, False otherwise
        """
        try:
            with self.Session() as sess:
                token_record = sess.query(GoogleDriveToken).filter_by(user_id=user_id).first()

                if token_record:
                    sess.delete(token_record)
                    sess.commit()
                    logger.debug(f"Deleted Google Drive token for user {user_id}")
                    return True

                logger.warning(f"No Google Drive token found for user {user_id}")
                return False

        except Exception as e:
            logger.error(f"Error deleting Google Drive token for user {user_id}: {e}")
            return False

    # Utility Methods

    def list_users_with_jira_tokens(self) -> list[str]:
        """Get list of all user IDs with stored Jira tokens.

        Returns:
            List of user IDs
        """
        try:
            with self.Session() as sess:
                results = sess.query(JiraToken.user_id).all()
                return [r[0] for r in results]

        except Exception as e:
            logger.error(f"Error listing users with Jira tokens: {e}")
            return []

    def list_users_with_gdrive_tokens(self) -> list[str]:
        """Get list of all user IDs with stored Google Drive tokens.

        Returns:
            List of user IDs
        """
        try:
            with self.Session() as sess:
                results = sess.query(GoogleDriveToken.user_id).all()
                return [r[0] for r in results]

        except Exception as e:
            logger.error(f"Error listing users with Google Drive tokens: {e}")
            return []

    def close(self):
        """Close database connection and cleanup."""
        try:
            self.Session.remove()
            self.db_engine.dispose()
            logger.debug("TokenStorage closed successfully")
        except Exception as e:
            logger.error(f"Error closing TokenStorage: {e}")
