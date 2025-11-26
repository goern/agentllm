"""Custom LiteLLM handler for Agno provider using dynamic registration."""

import os
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import litellm
from agno.db.sqlite import SqliteDb
from litellm import CustomLLM
from litellm.types.utils import Choices, Message, ModelResponse
from loguru import logger

from agentllm.agents.base import AgentRegistry
from agentllm.db import TokenStorage
from agentllm.db.encryption import EncryptionKeyMissingError
from agentllm.utils.logging import safe_log_content

# Configure logging for our custom handler using loguru
# Remove default handler
logger.remove()

# Determine log file path - use temp directory (consistent with DB and gdrive workspace)
log_dir = os.getenv("AGENTLLM_DATA_DIR", "tmp")
log_file = Path(log_dir) / "agno_handler.log"

# Add file handler for detailed logs (DEBUG level)
logger.add(
    log_file,
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
    rotation="10 MB",
    retention="7 days",
)

# Add console handler for important logs only (INFO level)
logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
)

# Shared database for all agents to enable session management
DB_PATH = Path(log_dir) / "agno_sessions.db"
shared_db = SqliteDb(db_file=str(DB_PATH))
logger.info(f"Initialized shared database at {DB_PATH}")

# Discover and register all toolkit token types
# This imports all toolkit configs which auto-register their token models
from agentllm.agents.toolkit_configs import discover_and_register_toolkits  # noqa: E402

discover_and_register_toolkits()

# Create token storage using the shared database (with encryption)
try:
    token_storage = TokenStorage(agno_db=shared_db)  # Loads key from AGENTLLM_TOKEN_ENCRYPTION_KEY env var
    logger.info("Initialized token storage with encryption enabled")
except EncryptionKeyMissingError as e:
    logger.error(f"CRITICAL: Token encryption key not configured: {e}")
    logger.error("Set AGENTLLM_TOKEN_ENCRYPTION_KEY environment variable")
    raise  # Fail fast - don't start without encryption

# Initialize agent registry and discover plugins
agent_registry = AgentRegistry()
agent_registry.discover_agents()
logger.info(f"Agent registry initialized. Discovered agents: {agent_registry.list_agents()}")


class AgnoCustomLLM(CustomLLM):
    """Custom LiteLLM handler for Agno agents.

    This allows dynamic registration without modifying LiteLLM source code.
    Supports Agno session management for conversation continuity.
    """

    def __init__(self):
        """Initialize the custom LLM handler with agent cache."""
        super().__init__()
        # Cache agents by (agent_name, temperature, max_tokens, user_id)
        self._agent_cache: dict[tuple, Any] = {}
        logger.info("Initialized AgnoCustomLLM with agent caching")

    def _extract_session_info(self, kwargs: dict[str, Any]) -> tuple[str | None, str | None]:
        """Extract session_id and user_id from request kwargs.

        Checks multiple sources in priority order:
        1. Request body metadata (from OpenWebUI pipe functions)
        2. OpenWebUI headers (X-OpenWebUI-User-Id, X-OpenWebUI-Chat-Id)
        3. LiteLLM metadata
        4. User field

        Args:
            kwargs: Request parameters

        Returns:
            Tuple of (session_id, user_id)
        """
        logger.debug("_extract_session_info() called")
        session_id = None
        user_id = None

        # 1. Check request body for metadata (from OpenWebUI pipe functions)
        litellm_params = kwargs.get("litellm_params", {})
        proxy_request = litellm_params.get("proxy_server_request", {})
        request_body = proxy_request.get("body", {})
        body_metadata = request_body.get("metadata", {})

        if body_metadata:
            session_id = body_metadata.get("session_id") or body_metadata.get("chat_id")
            user_id = body_metadata.get("user_id")
            logger.info(f"[1/4] Found in body metadata: session_id={session_id}, user_id={user_id}")

        # 2. Check OpenWebUI headers (ENABLE_FORWARD_USER_INFO_HEADERS)
        headers = litellm_params.get("metadata", {}).get("headers", {})
        if not session_id and headers:
            # Check for chat_id header (might be X-OpenWebUI-Chat-Id)
            session_id = headers.get("x-openwebui-chat-id") or headers.get("X-OpenWebUI-Chat-Id")
            if session_id:
                logger.info(f"[2/4] Found in headers: session_id={session_id}")

        if not user_id and headers:
            # Check for user_id header
            user_id = (
                headers.get("x-openwebui-user-id")
                or headers.get("X-OpenWebUI-User-Id")
                or headers.get("x-openwebui-user-email")
                or headers.get("X-OpenWebUI-User-Email")
            )
            if user_id:
                logger.info(f"[2/4] Found in headers: user_id={user_id}")

        # 3. Check LiteLLM metadata
        if not session_id and "litellm_params" in kwargs:
            litellm_metadata = litellm_params.get("metadata", {})
            session_id = litellm_metadata.get("session_id") or litellm_metadata.get("conversation_id")
            if session_id:
                logger.info(f"[3/4] Found in LiteLLM metadata: session_id={session_id}")

        # 4. Fallback to user field
        if not user_id:
            user_id = kwargs.get("user")
            if user_id:
                logger.info(f"[4/4] Found in user field: user_id={user_id}")

        # Log what we're using
        logger.info(f"✓ Final extracted session info: user_id={user_id}, session_id={session_id}")

        # Log full structure for debugging (only if nothing found)
        if not session_id and not user_id:
            logger.warning("⚠ No session/user info found! Logging full request structure:")
            logger.warning(f"Headers available: {list(headers.keys()) if headers else 'None'}")
            logger.warning(f"Body metadata keys: {list(body_metadata.keys()) if body_metadata else 'None'}")
            logger.warning(f"LiteLLM metadata keys: {list(litellm_params.get('metadata', {}).keys())}")

        return session_id, user_id

    def _get_agent(self, model: str, user_id: str | None = None, session_id: str | None = None, **kwargs):
        """Get agent instance from model name with parameters.

        Uses caching to reuse agent instances for the same configuration and user.

        Args:
            model: Model name (e.g., "agno/release-manager" or just "release-manager")
            user_id: User ID for agent isolation
            session_id: Session ID for conversation isolation
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Returns:
            Agent instance (cached or newly created)

        Raises:
            Exception: If agent not found
        """
        logger.debug(f"_get_agent() called with model={model}, user_id={user_id}, session_id={session_id}")

        # Extract agent name from model (handle both "agno/release-manager" and "release-manager")
        agent_name = model.replace("agno/", "")
        logger.debug(f"Extracted agent_name: {agent_name}")

        # Extract OpenAI parameters to pass to agent
        temperature = kwargs.get("temperature")
        max_tokens = kwargs.get("max_tokens")
        logger.debug(f"Agent parameters: temperature={temperature}, max_tokens={max_tokens}, session_id={session_id}")

        # Build cache key from agent configuration, user_id, and session_id
        # Each user+session combination gets its own wrapper instance
        cache_key = (agent_name, temperature, max_tokens, user_id, session_id)

        # Check if agent exists in cache
        if cache_key in self._agent_cache:
            logger.info(f"✓ Using CACHED agent for key: {cache_key}")
            return self._agent_cache[cache_key]

        # Create new agent and cache it
        logger.info(f"✗ Cache MISS - Creating NEW agent for key: {cache_key}")

        # Ensure user_id is not None (default to "unknown" if not provided)
        effective_user_id = user_id if user_id is not None else "unknown"
        if user_id is None:
            logger.warning("user_id is None, using 'unknown' as default")

        # Get agent from registry (plugin system)
        factory = agent_registry.get_factory(agent_name)

        if factory:
            logger.debug(f"Creating agent '{agent_name}' via registry factory...")
            agent = factory.create_agent(
                shared_db=shared_db,
                token_storage=token_storage,
                user_id=effective_user_id,
                session_id=session_id,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            logger.debug(f"Agent '{agent_name}' instantiated successfully via factory")
        else:
            # Agent not found
            available_agents = agent_registry.list_agents()
            error_msg = f"Agent '{agent_name}' not found. Available agents: {', '.join(available_agents)}"
            logger.error(error_msg)
            raise Exception(error_msg)

        self._agent_cache[cache_key] = agent
        logger.info(f"✓ Agent cached. Total cached agents: {len(self._agent_cache)}")
        logger.debug(f"Cache keys: {list(self._agent_cache.keys())}")
        return agent

    def _build_response(self, model: str, content: str) -> ModelResponse:
        """Build a ModelResponse from agent output.

        Args:
            model: Model name
            content: Agent response content

        Returns:
            ModelResponse object
        """
        logger.info(f"_build_response() called for model={model}, content_length={len(content)}")
        logger.debug(safe_log_content(content, "Content being added to response"))

        message = Message(role="assistant", content=content)
        logger.debug(f"Created Message object: role={message.role}, content_length={len(message.content) if message.content else 0}")

        choice = Choices(finish_reason="stop", index=0, message=message)
        logger.debug(f"Created Choices object with finish_reason={choice.finish_reason}")

        model_response = ModelResponse()
        model_response.model = model
        model_response.choices = [choice]
        model_response.usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

        logger.info(f"ModelResponse built: model={model_response.model}, choices_count={len(model_response.choices)}")
        logger.debug(
            f"Response first choice content: {model_response.choices[0].message.content[:200] if model_response.choices[0].message.content else 'None'}"
        )
        return model_response

    def _extract_request_params(self, messages: list[dict[str, Any]], kwargs: dict[str, Any]) -> tuple[str, str | None, str | None]:
        """Extract common request parameters.

        Args:
            messages: OpenAI-format messages
            kwargs: Request parameters

        Returns:
            Tuple of (user_message, session_id, user_id)
        """
        logger.debug("_extract_request_params() called")
        user_message = self._extract_user_message(messages)
        logger.debug(f"Extracted user_message (length={len(user_message)})")
        session_id, user_id = self._extract_session_info(kwargs)
        logger.debug(f"Extracted session_id={session_id}, user_id={user_id}")
        return user_message, session_id, user_id

    def completion(
        self,
        model: str,
        messages: list[dict[str, Any]],
        api_base: str | None = None,
        custom_llm_provider: str = "agno",
        **kwargs,
    ) -> ModelResponse:
        """Handle completion requests for Agno agents.

        Args:
            model: Model name (e.g., "agno/release-manager" or just "release-manager")
            messages: OpenAI-format messages
            api_base: API base URL (not used for in-process)
            custom_llm_provider: Provider name
            **kwargs: Additional parameters (stream, temperature, etc.)

        Returns:
            ModelResponse object
        """
        logger.info("=" * 80)
        logger.info(f">>> completion() STARTED - model={model}")
        logger.info(f"kwargs: {kwargs}")
        logger.info(f"messages: {messages}")

        # Check if streaming is requested
        stream = kwargs.get("stream", False)
        if stream:
            logger.info("Streaming requested, delegating to streaming()")
            # Return streaming iterator
            return self.streaming(
                model=model,
                messages=messages,
                api_base=api_base,
                custom_llm_provider=custom_llm_provider,
                **kwargs,
            )

        logger.info("Extracting request parameters...")
        # Extract request parameters first (need user_id for agent cache)
        user_message, session_id, user_id = self._extract_request_params(messages, kwargs)
        logger.info(f"Extracted: user_message_length={len(user_message)}, session_id={session_id}, user_id={user_id}")

        logger.info("Getting agent instance...")
        # Get agent instance (with caching based on user_id and session_id)
        agent = self._get_agent(model, user_id=user_id, session_id=session_id, **kwargs)

        logger.info(f"Running agent with session_id={session_id}, user_id={user_id}")
        # Run the agent with session management
        response = agent.run(user_message, stream=False, session_id=session_id, user_id=user_id)
        logger.info(f"Agent run completed, response type: {type(response)}")

        # Extract content and build response
        content = response.content if hasattr(response, "content") else str(response)
        logger.info(f"Extracted content length: {len(content) if content else 0}")
        logger.info(f"Content type: {type(content)}")
        logger.info(safe_log_content(content, "Content value"))
        logger.debug(f"Response object attributes: {vars(response) if hasattr(response, '__dict__') else dir(response)}")

        result = self._build_response(model, str(content))
        logger.info(f"<<< completion() FINISHED - model={model}")
        logger.info("=" * 80)
        return result

    def streaming(
        self,
        model: str,
        messages: list[dict[str, Any]],
        api_base: str | None = None,
        custom_llm_provider: str = "agno",
        **kwargs,
    ) -> Iterator[dict[str, Any]]:
        """Handle streaming requests for Agno agents.

        Note: Streaming is not fully supported in sync mode.
        Returns a single complete response instead of chunks.
        For true streaming with tool call visibility and reasoning events,
        use async requests which will call astreaming().

        Args:
            model: Model name
            messages: OpenAI-format messages
            api_base: API base URL (not used)
            custom_llm_provider: Provider name
            **kwargs: Additional parameters

        Yields:
            GenericStreamingChunk dictionary with text field
        """
        logger.info("=" * 80)
        logger.info(f">>> streaming() STARTED - model={model}")
        logger.info(f"kwargs: {kwargs}")

        logger.info("Getting complete response via completion() (sync streaming not fully supported)")
        # Get the complete response
        result = self.completion(
            model=model,
            messages=messages,
            api_base=api_base,
            custom_llm_provider=custom_llm_provider,
            **{k: v for k, v in kwargs.items() if k != "stream"},
        )

        # Extract content from the ModelResponse
        content = ""
        if result.choices and len(result.choices) > 0:
            content = result.choices[0].message.content or ""

        logger.info(f"Yielding single streaming chunk with content_length={len(content)}")
        # Return as GenericStreamingChunk format (required by CustomLLM interface)
        chunk = {
            "text": content,
            "finish_reason": "stop",
            "index": 0,
            "is_finished": True,
            "tool_use": None,
            "usage": {
                "completion_tokens": (result.usage.get("completion_tokens", 0) if result.usage else 0),
                "prompt_tokens": (result.usage.get("prompt_tokens", 0) if result.usage else 0),
                "total_tokens": (result.usage.get("total_tokens", 0) if result.usage else 0),
            },
        }
        yield chunk
        logger.info(f"<<< streaming() FINISHED - model={model}")
        logger.info("=" * 80)

    async def acompletion(
        self,
        model: str,
        messages: list[dict[str, Any]],
        api_base: str | None = None,
        custom_llm_provider: str = "agno",
        **kwargs,
    ) -> ModelResponse:
        """Async completion using agent.arun().

        Args:
            model: Model name (e.g., "agno/release-manager" or just "release-manager")
            messages: OpenAI-format messages
            api_base: API base URL (not used for in-process)
            custom_llm_provider: Provider name
            **kwargs: Additional parameters (stream, temperature, etc.)

        Returns:
            ModelResponse object
        """
        logger.info("=" * 80)
        logger.info(f">>> acompletion() STARTED - model={model}")
        logger.info(f"kwargs: {kwargs}")
        logger.info(f"messages: {messages}")

        logger.info("Extracting request parameters...")
        # Extract request parameters first (need user_id for agent cache)
        user_message, session_id, user_id = self._extract_request_params(messages, kwargs)
        logger.info(f"Extracted: user_message_length={len(user_message)}, session_id={session_id}, user_id={user_id}")

        logger.info("Getting agent instance...")
        # Get agent instance (with caching based on user_id and session_id)
        agent = self._get_agent(model, user_id=user_id, session_id=session_id, **kwargs)

        logger.info(f"Running agent asynchronously with session_id={session_id}, user_id={user_id}")
        # Run the agent asynchronously with session management
        response = await agent.arun(user_message, stream=False, session_id=session_id, user_id=user_id)
        logger.info(f"Agent arun completed, response type: {type(response)}")

        # Extract content and build response
        content = response.content if hasattr(response, "content") else str(response)
        logger.info(f"Extracted content length: {len(content) if content else 0}")
        logger.info(f"Content type: {type(content)}")
        logger.info(safe_log_content(content, "Content value"))
        logger.debug(f"Response object attributes: {vars(response) if hasattr(response, '__dict__') else dir(response)}")

        result = self._build_response(model, str(content))
        logger.info(f"<<< acompletion() FINISHED - model={model}")
        logger.info("=" * 80)
        return result

    async def astreaming(
        self,
        model: str,
        messages: list[dict[str, Any]],
        api_base: str | None = None,
        custom_llm_provider: str = "agno",
        **kwargs,
    ) -> AsyncIterator[dict[str, Any]]:
        """Async streaming - passes through GenericStreamingChunk dicts from agents.

        Agent wrappers handle all Agno event processing and yield pre-formatted
        GenericStreamingChunk dictionaries. This method is now provider-agnostic.

        Args:
            model: Model name
            messages: OpenAI-format messages
            api_base: API base URL (not used)
            custom_llm_provider: Provider name
            **kwargs: Additional parameters

        Yields:
            GenericStreamingChunk dictionaries with text field
        """
        logger.info("=" * 80)
        logger.info(f">>> astreaming() STARTED - model={model}")
        logger.info(f"kwargs: {kwargs}")
        logger.info(f"messages: {messages}")

        logger.info("Extracting request parameters...")
        # Extract request parameters first (need user_id for agent cache)
        user_message, session_id, user_id = self._extract_request_params(messages, kwargs)
        logger.info(f"Extracted: user_message_length={len(user_message)}, session_id={session_id}, user_id={user_id}")

        logger.info("Getting agent instance...")
        # Get agent instance (with caching based on user_id and session_id)
        agent = self._get_agent(model, user_id=user_id, session_id=session_id, **kwargs)

        logger.info(f"Starting async streaming with session_id={session_id}, user_id={user_id}")

        # Agent.arun() yields GenericStreamingChunk dicts directly
        # Just pass them through to LiteLLM
        chunk_count = 0
        async for chunk_dict in agent.arun(user_message, stream=True, session_id=session_id, user_id=user_id):
            chunk_count += 1
            logger.debug(f"[custom_handler] Passing through chunk #{chunk_count} to LiteLLM")
            yield chunk_dict

        logger.info(f"Stream completed, total chunks: {chunk_count}")
        logger.info(f"<<< astreaming() FINISHED - model={model}")
        logger.info("=" * 80)

    def _extract_user_message(self, messages: list[dict[str, Any]]) -> str:
        """Extract the last user message from messages list.

        Args:
            messages: OpenAI-format messages

        Returns:
            User message content
        """
        logger.debug(f"_extract_user_message() called with {len(messages)} messages")

        # Find the last user message
        for idx, message in enumerate(reversed(messages)):
            if message.get("role") == "user":
                content = message.get("content", "")
                logger.debug(f"Found user message at position {len(messages) - idx - 1} (length={len(content)})")
                return content

        # If no user message found, concatenate all messages
        logger.warning("No user message found, concatenating all messages")
        combined = " ".join(msg.get("content", "") for msg in messages)
        logger.debug(f"Combined message length: {len(combined)}")
        return combined

    # Note: _add_messages_to_agent() method removed
    # Agno now handles conversation history automatically via:
    # - db=shared_db (enables session storage)
    # - add_history_to_context=True (adds previous messages to context)
    # - session_id/user_id passed to agent.run()


# Create a singleton instance
agno_handler = AgnoCustomLLM()


# Register the handler
def register_agno_provider():
    """Register the Agno provider with LiteLLM.

    Call this before using the proxy or making completion calls.
    """
    litellm.custom_provider_map = [{"provider": "agno", "custom_handler": agno_handler}]
    print("✅ Registered Agno provider with LiteLLM")


if __name__ == "__main__":
    # Auto-register when run as script
    register_agno_provider()
    print("\n🚀 Agno provider registered!")
    print("   You can now use models like: agno/release-manager")
