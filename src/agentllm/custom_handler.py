"""Custom LiteLLM handler for Agno provider using dynamic registration."""

import logging
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import litellm
from litellm import CustomLLM
from litellm.types.utils import Choices, Message, ModelResponse

from agentllm.agents.release_manager import ReleaseManager

# Configure logging for our custom handler
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Determine log file path - use temp directory (consistent with DB and gdrive workspace)
log_dir = os.getenv("AGENTLLM_DATA_DIR", "tmp")
log_file = Path(log_dir) / "agno_handler.log"

# File handler for detailed logs
file_handler = logging.FileHandler(log_file)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))

# Console handler for important logs only
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter("[AGNO] %(levelname)s: %(message)s"))

logger.addHandler(file_handler)
logger.addHandler(console_handler)


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
            logger.info(f"Found in body metadata: session_id={session_id}, user_id={user_id}")

        # 2. Check OpenWebUI headers (ENABLE_FORWARD_USER_INFO_HEADERS)
        headers = litellm_params.get("metadata", {}).get("headers", {})
        if not session_id and headers:
            # Check for chat_id header (might be X-OpenWebUI-Chat-Id)
            session_id = headers.get("x-openwebui-chat-id") or headers.get("X-OpenWebUI-Chat-Id")
            logger.info(f"Found in headers: session_id={session_id}")

        if not user_id and headers:
            # Check for user_id header
            user_id = (
                headers.get("x-openwebui-user-id")
                or headers.get("X-OpenWebUI-User-Id")
                or headers.get("x-openwebui-user-email")
                or headers.get("X-OpenWebUI-User-Email")
            )
            logger.info(f"Found in headers: user_id={user_id}")

        # 3. Check LiteLLM metadata
        if not session_id and "litellm_params" in kwargs:
            litellm_metadata = litellm_params.get("metadata", {})
            session_id = litellm_metadata.get("session_id") or litellm_metadata.get(
                "conversation_id"
            )
            if session_id:
                logger.info(f"Found in LiteLLM metadata: session_id={session_id}")

        # 4. Fallback to user field
        if not user_id:
            user_id = kwargs.get("user")
            if user_id:
                logger.info(f"Found in user field: user_id={user_id}")

        # Log what we're using
        logger.info(f"Final extracted session info: user_id={user_id}, session_id={session_id}")

        # Log full structure for debugging (only if nothing found)
        if not session_id and not user_id:
            logger.warning("No session/user info found! Logging full request structure:")
            logger.warning(f"Headers available: {list(headers.keys()) if headers else 'None'}")
            logger.warning(
                f"Body metadata keys: {list(body_metadata.keys()) if body_metadata else 'None'}"
            )
            logger.warning(
                f"LiteLLM metadata keys: {list(litellm_params.get('metadata', {}).keys())}"
            )

        return session_id, user_id

    def _get_agent(self, model: str, user_id: str | None = None, **kwargs):
        """Get agent instance from model name with parameters.

        Uses caching to reuse agent instances for the same configuration and user.

        Args:
            model: Model name (e.g., "agno/release-manager" or just "release-manager")
            user_id: User ID for agent isolation
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Returns:
            Agent instance (cached or newly created)

        Raises:
            Exception: If agent not found
        """
        # Extract agent name from model (handle both "agno/release-manager" and "release-manager")
        agent_name = model.replace("agno/", "")

        # Extract OpenAI parameters to pass to agent
        temperature = kwargs.get("temperature")
        max_tokens = kwargs.get("max_tokens")

        # Build cache key from agent configuration and user_id
        cache_key = (agent_name, temperature, max_tokens, user_id)

        # Check if agent exists in cache
        if cache_key in self._agent_cache:
            logger.info(f"Using cached agent for key: {cache_key}")
            return self._agent_cache[cache_key]

        # Create new agent and cache it
        logger.info(f"Creating new agent for key: {cache_key}")

        # Instantiate the agent class based on agent_name
        if agent_name == "release-manager":
            agent = ReleaseManager(temperature=temperature, max_tokens=max_tokens)
        else:
            raise Exception(f"Agent '{agent_name}' not found. Only 'release-manager' is available.")

        self._agent_cache[cache_key] = agent
        logger.info(f"Cached agent. Total cached agents: {len(self._agent_cache)}")
        return agent

    def _build_response(self, model: str, content: str) -> ModelResponse:
        """Build a ModelResponse from agent output.

        Args:
            model: Model name
            content: Agent response content

        Returns:
            ModelResponse object
        """
        message = Message(role="assistant", content=content)
        choice = Choices(finish_reason="stop", index=0, message=message)

        model_response = ModelResponse()
        model_response.model = model
        model_response.choices = [choice]
        model_response.usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

        return model_response

    def _extract_request_params(
        self, messages: list[dict[str, Any]], kwargs: dict[str, Any]
    ) -> tuple[str, str | None, str | None]:
        """Extract common request parameters.

        Args:
            messages: OpenAI-format messages
            kwargs: Request parameters

        Returns:
            Tuple of (user_message, session_id, user_id)
        """
        user_message = self._extract_user_message(messages)
        session_id, user_id = self._extract_session_info(kwargs)
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
        logger.info(f"completion() called with model={model}")
        logger.info(f"kwargs: {kwargs}")
        logger.info(f"messages: {messages}")

        # Check if streaming is requested
        stream = kwargs.get("stream", False)
        if stream:
            # Return streaming iterator
            return self.streaming(
                model=model,
                messages=messages,
                api_base=api_base,
                custom_llm_provider=custom_llm_provider,
                **kwargs,
            )

        # Extract request parameters first (need user_id for agent cache)
        user_message, session_id, user_id = self._extract_request_params(messages, kwargs)

        # Get agent instance (with caching based on user_id)
        agent = self._get_agent(model, user_id=user_id, **kwargs)

        # Run the agent with session management
        response = agent.run(user_message, stream=False, session_id=session_id, user_id=user_id)

        # Extract content and build response
        content = response.content if hasattr(response, "content") else str(response)
        return self._build_response(model, str(content))

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
        For true streaming, use async requests which will call astreaming().

        Args:
            model: Model name
            messages: OpenAI-format messages
            api_base: API base URL (not used)
            custom_llm_provider: Provider name
            **kwargs: Additional parameters

        Yields:
            GenericStreamingChunk dictionary with text field
        """
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

        # Return as GenericStreamingChunk format (required by CustomLLM interface)
        yield {
            "text": content,
            "finish_reason": "stop",
            "index": 0,
            "is_finished": True,
            "tool_use": None,
            "usage": {
                "completion_tokens": (
                    result.usage.get("completion_tokens", 0) if result.usage else 0
                ),
                "prompt_tokens": (result.usage.get("prompt_tokens", 0) if result.usage else 0),
                "total_tokens": (result.usage.get("total_tokens", 0) if result.usage else 0),
            },
        }

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
        logger.info(f"acompletion() called with model={model}")
        logger.info(f"kwargs: {kwargs}")
        logger.info(f"messages: {messages}")

        # Extract request parameters first (need user_id for agent cache)
        user_message, session_id, user_id = self._extract_request_params(messages, kwargs)

        # Get agent instance (with caching based on user_id)
        agent = self._get_agent(model, user_id=user_id, **kwargs)

        # Run the agent asynchronously with session management
        response = await agent.arun(
            user_message, stream=False, session_id=session_id, user_id=user_id
        )

        # Extract content and build response
        content = response.content if hasattr(response, "content") else str(response)
        return self._build_response(model, str(content))

    async def astreaming(
        self,
        model: str,
        messages: list[dict[str, Any]],
        api_base: str | None = None,
        custom_llm_provider: str = "agno",
        **kwargs,
    ) -> AsyncIterator[dict[str, Any]]:
        """Async streaming using Agno's native streaming support.

        Args:
            model: Model name
            messages: OpenAI-format messages
            api_base: API base URL (not used)
            custom_llm_provider: Provider name
            **kwargs: Additional parameters

        Yields:
            GenericStreamingChunk dictionaries with text field
        """
        logger.info(f"astreaming() called with model={model}")
        logger.info(f"kwargs: {kwargs}")
        logger.info(f"messages: {messages}")

        # Extract request parameters first (need user_id for agent cache)
        user_message, session_id, user_id = self._extract_request_params(messages, kwargs)

        # Get agent instance (with caching based on user_id)
        agent = self._get_agent(model, user_id=user_id, **kwargs)

        # Use Agno's real async streaming with session management
        chunk_count = 0

        async for chunk in agent.arun(
            user_message, stream=True, session_id=session_id, user_id=user_id
        ):
            # Extract content from chunk
            content = chunk.content if hasattr(chunk, "content") else str(chunk)

            if not content:
                continue

            # Yield GenericStreamingChunk format
            yield {
                "text": content,
                "finish_reason": None,
                "index": 0,
                "is_finished": False,
                "tool_use": None,
                "usage": {
                    "completion_tokens": 0,
                    "prompt_tokens": 0,
                    "total_tokens": 0,
                },
            }
            chunk_count += 1

        # Send final chunk with finish_reason
        yield {
            "text": "",
            "finish_reason": "stop",
            "index": 0,
            "is_finished": True,
            "tool_use": None,
            "usage": {
                "completion_tokens": chunk_count,
                "prompt_tokens": 0,
                "total_tokens": chunk_count,
            },
        }

    def _extract_user_message(self, messages: list[dict[str, Any]]) -> str:
        """Extract the last user message from messages list.

        Args:
            messages: OpenAI-format messages

        Returns:
            User message content
        """
        # Find the last user message
        for message in reversed(messages):
            if message.get("role") == "user":
                return message.get("content", "")

        # If no user message found, concatenate all messages
        return " ".join(msg.get("content", "") for msg in messages)

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
