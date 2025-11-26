# Token Storage

SQLite-based token storage for Jira and Google Drive OAuth credentials.

## Overview

The `TokenStorage` class provides a secure, database-backed way to store and manage API tokens and OAuth credentials for multiple users. This eliminates the need to pass credentials directly each time and enables per-user credential management.

## Features

- **SQLite Storage**: Lightweight, file-based database with no external dependencies
- **Per-User Management**: Store credentials for multiple users with unique identifiers
- **Two Authentication Modes**:
  - Direct authentication (pass credentials directly)
  - Database authentication (fetch from storage)
- **Automatic Credential Refresh**: Google Drive tokens can be automatically refreshed
- **Thread-Safe**: Uses SQLAlchemy's scoped sessions

## Usage

### Initialize Token Storage

```python
from agentllm.db import TokenStorage

# Default: uses ./tokens.db
token_storage = TokenStorage()

# Custom database file
token_storage = TokenStorage(db_file="./my_tokens.db")

# Custom database URL
token_storage = TokenStorage(db_url="sqlite:///path/to/tokens.db")
```

### Jira Token Management

```python
# Store Jira token
token_storage.upsert_jira_token(
    user_id="user@example.com",
    token="jira_personal_access_token",
    server_url="https://issues.redhat.com",
    username="optional_username"  # For basic auth
)

# Retrieve Jira token
token_data = token_storage.get_jira_token("user@example.com")
# Returns: {
#   "user_id": "user@example.com",
#   "token": "jira_personal_access_token",
#   "server_url": "https://issues.redhat.com",
#   "username": "optional_username",
#   "created_at": datetime,
#   "updated_at": datetime
# }

# Delete Jira token
token_storage.delete_jira_token("user@example.com")

# List all users with Jira tokens
users = token_storage.list_users_with_jira_tokens()
```

### Google Drive Token Management

```python
from google.oauth2.credentials import Credentials

# Create OAuth credentials (from OAuth flow)
credentials = Credentials(
    token="ya29.a0AfB_...",
    refresh_token="1//0g...",
    token_uri="https://oauth2.googleapis.com/token",
    client_id="your_client_id.apps.googleusercontent.com",
    client_secret="your_client_secret",
    scopes=["https://www.googleapis.com/auth/drive"]
)

# Store Google Drive credentials
token_storage.upsert_gdrive_token(
    user_id="user@example.com",
    credentials=credentials
)

# Retrieve credentials as Credentials object
credentials = token_storage.get_gdrive_credentials("user@example.com")

# Get metadata without reconstructing Credentials
info = token_storage.get_gdrive_token_info("user@example.com")
# Returns: {
#   "user_id": "user@example.com",
#   "token": "ya29.a0AfB_...",  # Truncated for security
#   "has_refresh_token": True,
#   "scopes": [...],
#   "expiry": datetime,
#   "created_at": datetime,
#   "updated_at": datetime
# }

# Delete Google Drive token
token_storage.delete_gdrive_token("user@example.com")

# List all users with Google Drive tokens
users = token_storage.list_users_with_gdrive_tokens()
```

### Using with Toolkits

#### Jira Toolkit

```python
from agentllm.tools.jira_toolkit import JiraTools

# Database authentication
jira_tools = JiraTools(
    token_storage=token_storage,
    user_id="user@example.com"
)

# Direct authentication (backward compatible)
jira_tools = JiraTools(
    token="jira_token",
    server_url="https://issues.redhat.com"
)
```

#### Google Drive Toolkit

```python
from agentllm.tools.gdrive_toolkit import GoogleDriveTools

# Database authentication
gdrive_tools = GoogleDriveTools(
    token_storage=token_storage,
    user_id="user@example.com"
)

# Direct authentication (backward compatible)
gdrive_tools = GoogleDriveTools(credentials=credentials)
```

## Database Schema

### jira_tokens

| Column      | Type     | Description                  |
|-------------|----------|------------------------------|
| id          | Integer  | Primary key (auto-increment) |
| user_id     | String   | Unique user identifier       |
| token       | String   | Jira API token               |
| server_url  | String   | Jira server URL              |
| username    | String   | Optional username            |
| created_at  | DateTime | Record creation timestamp    |
| updated_at  | DateTime | Last update timestamp        |

### gdrive_tokens

| Column         | Type     | Description                  |
|----------------|----------|------------------------------|
| id             | Integer  | Primary key (auto-increment) |
| user_id        | String   | Unique user identifier       |
| token          | String   | OAuth access token           |
| refresh_token  | String   | OAuth refresh token          |
| token_uri      | String   | Token refresh endpoint       |
| client_id      | String   | OAuth client ID              |
| client_secret  | String   | OAuth client secret          |
| scopes         | Text     | JSON array of OAuth scopes   |
| expiry         | DateTime | Token expiration time        |
| created_at     | DateTime | Record creation timestamp    |
| updated_at     | DateTime | Last update timestamp        |

## Security Considerations

### Token Encryption (REQUIRED)

All sensitive tokens are encrypted at rest using Fernet symmetric encryption:

1. **Encryption Key**: Set `AGENTLLM_TOKEN_ENCRYPTION_KEY` environment variable
   - Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
   - Store securely in Kubernetes Secrets (production) or `.env.secrets` (local dev)
   - **CRITICAL**: If key is lost, all stored tokens are unrecoverable

2. **Encrypted Fields**:
   - Jira: `token`
   - GitHub: `token`
   - Google Drive: `token`, `refresh_token`, `client_secret`
   - RHCP: `offline_token`

3. **Fail-Fast Behavior**:
   - Application fails to start if encryption key not provided
   - Decryption failures return `None` (logged as errors)
   - No plaintext fallback

### Additional Security Measures

4. **File Permissions**: Ensure SQLite database file has restrictive permissions (600)
5. **Access Control**: Implement user authentication before token access
6. **Token Rotation**: Regularly rotate tokens and update database
7. **Audit Logging**: Track token access and modifications
8. **Key Rotation**: Not supported in v1 - changing key invalidates all tokens

For production deployment guidance, see `docs/deployment-encryption.md`.

## Examples

See `examples/token_storage_example.py` for complete working examples.

## Cleanup

Always close the token storage when done:

```python
token_storage.close()
```
