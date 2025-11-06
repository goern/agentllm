"""
Example usage of TokenStorage for managing Jira and Google Drive credentials.

This demonstrates how to:
1. Store tokens in the database
2. Retrieve tokens from the database
3. Initialize toolkits with database-backed authentication
"""

from google.oauth2.credentials import Credentials

from agentllm.db import TokenStorage
from agentllm.tools.gdrive_toolkit import GoogleDriveTools
from agentllm.tools.jira_toolkit import JiraTools


def example_jira_token_storage():
    """Example: Store and retrieve Jira tokens."""
    # Initialize token storage (uses ./tokens.db by default)
    token_storage = TokenStorage(db_file="./examples/tokens.db")

    # Store Jira token for a user
    user_id = "user@example.com"
    token_storage.upsert_jira_token(
        user_id=user_id,
        token="your_jira_token_here",
        server_url="https://issues.redhat.com",
        username="your_username",  # Optional
    )

    # Retrieve token
    jira_token_data = token_storage.get_jira_token(user_id)
    print(f"Retrieved Jira token: {jira_token_data}")

    # Get credentials from token storage
    if not jira_token_data:
        raise ValueError(f"No Jira token found for user {user_id}")

    # Initialize JiraTools with credentials
    _jira_tools = JiraTools(
        token=jira_token_data["token"],
        server_url=jira_token_data["server_url"],
        username=jira_token_data.get("username"),
        get_issue=True,
        search_issues=True,
    )

    # Use the toolkit
    # result = _jira_tools.get_issue("PROJ-123")
    # print(result)

    token_storage.close()


def example_gdrive_token_storage():
    """Example: Store and retrieve Google Drive OAuth credentials."""
    # Initialize token storage
    token_storage = TokenStorage(db_file="./examples/tokens.db")

    # Create OAuth credentials (normally obtained from OAuth flow)
    credentials = Credentials(
        token="ya29.a0AfB_...",  # Your access token
        refresh_token="1//0g...",  # Your refresh token
        token_uri="https://oauth2.googleapis.com/token",
        client_id="your_client_id.apps.googleusercontent.com",
        client_secret="your_client_secret",
        scopes=[
            "https://www.googleapis.com/auth/drive",
            "https://www.googleapis.com/auth/documents",
        ],
    )

    # Store Google Drive credentials for a user
    user_id = "user@example.com"
    token_storage.upsert_gdrive_token(
        user_id=user_id,
        credentials=credentials,
    )

    # Retrieve credentials
    retrieved_credentials = token_storage.get_gdrive_credentials(user_id)
    print(f"Retrieved credentials: {retrieved_credentials is not None}")

    # Get credentials from token storage
    credentials = token_storage.get_gdrive_credentials(user_id)
    if not credentials:
        raise ValueError(f"No Google Drive credentials found for user {user_id}")

    # Initialize GoogleDriveTools with credentials
    _gdrive_tools = GoogleDriveTools(credentials=credentials)

    # Use the toolkit
    # content = _gdrive_tools.get_document_content("https://docs.google.com/document/d/...")
    # print(content)

    token_storage.close()


def example_list_users():
    """Example: List all users with stored tokens."""
    token_storage = TokenStorage(db_file="./examples/tokens.db")

    jira_users = token_storage.list_users_with_jira_tokens()
    print(f"Users with Jira tokens: {jira_users}")

    gdrive_users = token_storage.list_users_with_gdrive_tokens()
    print(f"Users with Google Drive tokens: {gdrive_users}")

    token_storage.close()


def example_direct_authentication():
    """Example: Using toolkits with direct authentication (backward compatible)."""

    # Jira - Direct authentication (no database)
    _jira_tools = JiraTools(
        token="your_jira_token",
        server_url="https://issues.redhat.com",
        username="your_username",  # Optional
    )

    # Google Drive - Direct authentication (no database)
    credentials = Credentials(
        token="ya29.a0AfB_...",
        refresh_token="1//0g...",
        token_uri="https://oauth2.googleapis.com/token",
        client_id="your_client_id.apps.googleusercontent.com",
        client_secret="your_client_secret",
        scopes=["https://www.googleapis.com/auth/drive"],
    )

    _gdrive_tools = GoogleDriveTools(credentials=credentials)

    print("Direct authentication initialized successfully")


if __name__ == "__main__":
    print("=== Jira Token Storage Example ===")
    # example_jira_token_storage()

    print("\n=== Google Drive Token Storage Example ===")
    # example_gdrive_token_storage()

    print("\n=== List Users Example ===")
    # example_list_users()

    print("\n=== Direct Authentication Example ===")
    example_direct_authentication()
