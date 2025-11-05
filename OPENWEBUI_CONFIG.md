# OpenWebUI Configuration for Session Tracking

This guide explains how to configure OpenWebUI to send session and user information to the LiteLLM proxy and Agno agents.

## Option C: Enable Header Forwarding

OpenWebUI can forward user information as HTTP headers when `ENABLE_FORWARD_USER_INFO_HEADERS` is enabled.

### Headers Sent by OpenWebUI

When enabled, OpenWebUI sends these headers with every request:
- `X-OpenWebUI-User-Name` - User's display name
- `X-OpenWebUI-User-Id` - User's unique ID
- `X-OpenWebUI-User-Email` - User's email address
- `X-OpenWebUI-User-Role` - User's role (admin, user, etc.)

**Note:** `chat_id` and `session_id` are NOT sent as headers by default.

### How to Enable

#### Docker Compose

Add to your OpenWebUI service in `docker-compose.yml`:

```yaml
services:
  openwebui:
    image: ghcr.io/open-webui/open-webui:main
    environment:
      - ENABLE_FORWARD_USER_INFO_HEADERS=true
      - OPENAI_API_BASE=http://litellm:8890/v1
      - OPENAI_API_KEY=sk-agno-test-key-12345
    # ... other config
```

#### Environment Variable

Set in your shell or `.env` file:

```bash
export ENABLE_FORWARD_USER_INFO_HEADERS=true
```

#### Docker Run

```bash
docker run -d \
  -e ENABLE_FORWARD_USER_INFO_HEADERS=true \
  -e OPENAI_API_BASE=http://your-litellm-host:8890/v1 \
  -e OPENAI_API_KEY=sk-agno-test-key-12345 \
  ghcr.io/open-webui/open-webui:main
```

## What Our Custom Handler Extracts

The updated custom handler in `src/agentllm/custom_handler.py` now checks multiple sources:

### 1. Request Body Metadata (Priority 1)
```python
body_metadata.get("session_id")
body_metadata.get("chat_id")
body_metadata.get("user_id")
```
This requires an OpenWebUI Pipe Function to be installed (not implemented yet).

### 2. OpenWebUI Headers (Priority 2)
```python
headers.get("X-OpenWebUI-User-Id")
headers.get("X-OpenWebUI-User-Email")
headers.get("X-OpenWebUI-Chat-Id")  # May not be available
```
This works when `ENABLE_FORWARD_USER_INFO_HEADERS=true`.

### 3. LiteLLM Metadata (Priority 3)
```python
litellm_metadata.get("session_id")
litellm_metadata.get("conversation_id")
```

### 4. User Field (Priority 4)
```python
kwargs.get("user")
```

## LiteLLM Configuration

The `proxy_config.yaml` has been updated to map OpenWebUI headers:

```yaml
general_settings:
  user_header_name: X-OpenWebUI-User-Id
  user_header_mappings:
    - header_name: X-OpenWebUI-User-Id
      litellm_user_role: internal_user
    - header_name: X-OpenWebUI-User-Email
      litellm_user_role: customer
```

## Testing

After configuring OpenWebUI:

1. **Restart LiteLLM proxy**:
   ```bash
   # Stop existing proxy
   pkill -f "litellm --config"

   # Start with new config
   nox -s proxy
   ```

2. **Check logs** in `agno_handler.log`:
   ```bash
   tail -f agno_handler.log
   ```

3. **Send a test message** from OpenWebUI

4. **Look for these log entries**:
   ```
   INFO - Found in headers: user_id=<user_id>
   INFO - Final extracted session info: user_id=<user_id>, session_id=<session_id>
   ```

## Current Limitations

### Missing chat_id in Headers

OpenWebUI does NOT send `chat_id` as a header by default, even with `ENABLE_FORWARD_USER_INFO_HEADERS=true`.

**Workaround Options:**

1. **Use user_id as session identifier** (current behavior)
   - Agno will auto-generate session IDs per user
   - Different chats from the same user will share context

2. **Implement an OpenWebUI Pipe Function** (recommended)
   - Extract `chat_id` from `__metadata__`
   - Add it to request body
   - Custom handler picks it up from body metadata

3. **Generate session IDs server-side**
   - Use conversation context heuristics
   - Cache mapping of user + conversation start time

## Expected Behavior

### With ENABLE_FORWARD_USER_INFO_HEADERS=true

✅ User ID extracted from headers
✅ User email extracted from headers
❌ Chat ID NOT available (requires pipe function)
✅ Agno agents use user_id for session management

### Without Configuration

❌ No user tracking
❌ No session tracking
⚠️ Each request treated as new conversation

## Verification

Check if headers are being received:

```bash
# Watch the logs in real-time
tail -f agno_handler.log | grep -i "found in"
```

Expected output when working:
```
INFO - Found in headers: user_id=abc123@example.com
INFO - Final extracted session info: user_id=abc123@example.com, session_id=None
```

## Next Steps

For full chat_id support, see: `PIPE_FUNCTION.md` (to be created)
