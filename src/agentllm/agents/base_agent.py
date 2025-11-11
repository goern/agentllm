"""Base agent wrapper class for LiteLLM integration with toolkit configuration."""

import json
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from agno.agent import (
    Agent,
    ReasoningStepEvent,
    RunCompletedEvent,
    RunContentEvent,
    ToolCallCompletedEvent,
    ToolCallStartedEvent,
)
from agno.db.sqlite import SqliteDb
from agno.models.google import Gemini
from loguru import logger

from agentllm.agents.toolkit_configs.base import BaseToolkitConfig


class BaseAgentWrapper(ABC):
    """
    Base class for agent wrappers with toolkit configuration management.

    This class provides common functionality for wrapping Agno agents with:
    - Toolkit configuration management (OAuth, API tokens, etc.)
    - Configuration extraction from user messages
    - Agent lifecycle management (create agents with configured toolkits)
    - Streaming/non-streaming execution
    - Provider-agnostic interface (yields LiteLLM GenericStreamingChunk format)

    Subclasses must implement abstract methods to provide agent-specific:
    - Toolkit configurations
    - Agent instructions
    - Agent name and description

    Architecture:
    - NO caching of agents (custom_handler.py caches wrapper instances)
    - Dependency injection (shared_db passed as constructor param)
    - Agno event processing (converts to LiteLLM format for custom_handler)
    """

    def __init__(
        self,
        shared_db: SqliteDb,
        user_id: str,
        session_id: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **model_kwargs: Any,
    ):
        """
        Initialize the agent wrapper.

        Args:
            shared_db: Shared database instance for session management
            user_id: User identifier (wrapper is per-user+session)
            session_id: Session identifier (optional)
            temperature: Model temperature (0.0-2.0)
            max_tokens: Maximum tokens in response
            **model_kwargs: Additional model parameters
        """
        logger.debug("=" * 80)
        logger.info(f"{self.__class__.__name__}.__init__() called")
        logger.debug(
            f"Parameters: user_id={user_id}, session_id={session_id}, temperature={temperature}, max_tokens={max_tokens}, model_kwargs={model_kwargs}"
        )

        # Store dependencies
        self._shared_db = shared_db

        # Store user and session identifiers
        # Note: This wrapper instance is per-user+session (cached in custom_handler)
        self._user_id = user_id
        self._session_id = session_id

        # Store model parameters
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._model_kwargs = model_kwargs

        # Store single Agno agent instance for this wrapper
        # Note: This wrapper is already per-user+session (cached in custom_handler),
        # so we only need one agent instance, not a dict
        self._agent: Agent | None = None

        # Initialize toolkit configurations (subclass-specific)
        logger.debug("Initializing toolkit configurations...")
        self.toolkit_configs = self._initialize_toolkit_configs()
        logger.info(f"Initialized {len(self.toolkit_configs)} toolkit config(s)")

        logger.info(f"✅ {self.__class__.__name__} initialization complete")
        logger.debug("=" * 80)

    # ========== ABSTRACT METHODS (SUBCLASS REQUIRED) ==========

    @abstractmethod
    def _initialize_toolkit_configs(self) -> list[BaseToolkitConfig]:
        """
        Initialize toolkit configurations for this agent.

        Returns:
            List of toolkit configuration instances
        """
        pass

    @abstractmethod
    def _build_agent_instructions(self, user_id: str) -> list[str]:
        """
        Build agent-specific instructions.

        Args:
            user_id: User identifier

        Returns:
            List of instruction strings
        """
        pass

    @abstractmethod
    def _get_agent_name(self) -> str:
        """
        Return agent name (e.g., 'demo-agent', 'release-manager').

        Returns:
            Agent name string
        """
        pass

    @abstractmethod
    def _get_agent_description(self) -> str:
        """
        Return agent description.

        Returns:
            Agent description string
        """
        pass

    # ========== HOOK METHODS (SUBCLASS OPTIONAL) ==========

    def _get_model_id(self) -> str:
        """
        Override to change model.

        Returns:
            Model ID (default: gemini-2.5-flash)
        """
        return "gemini-2.5-flash"

    def _get_agent_kwargs(self) -> dict[str, Any]:
        """
        Get all Agent constructor keyword arguments.

        This is the main method for customizing Agent creation. Override this
        method and call super() to extend the base defaults with your own parameters.

        Base defaults include:
        - db: Database for session management
        - add_history_to_context: Include chat history in messages (default: True)
        - num_history_runs: Number of historical runs to include (default: 10)
        - read_chat_history: Add tool for reading chat history (default: True)
        - markdown: Format output using markdown (default: True)

        Common parameters to add:
        - reasoning: Enable step-by-step reasoning (default: False)
        - reasoning_model: Model to use for reasoning
        - reasoning_min_steps: Minimum reasoning steps (default: 1)
        - reasoning_max_steps: Maximum reasoning steps (default: 10)
        - tool_call_limit: Maximum tool calls per run
        - cache_session: Cache session in memory (default: False)
        - enable_session_summaries: Create/update session summaries (default: False)
        - add_session_summary_to_context: Add summaries to context
        - max_tool_calls_from_history: Limit tool calls from history
        - enable_agentic_memory: Allow agent to manage user memories (default: False)
        - enable_user_memories: Create/update user memories (default: False)

        See Agno Agent documentation for complete list of available parameters.

        Example:
            def _get_agent_kwargs(self) -> dict[str, Any]:
                kwargs = super()._get_agent_kwargs()  # Get base defaults
                kwargs["reasoning"] = True  # Enable reasoning
                kwargs["reasoning_max_steps"] = 15  # More steps
                return kwargs

        Returns:
            Dictionary of Agent constructor keyword arguments
        """
        return {
            "db": self._shared_db,
            "add_history_to_context": True,
            "num_history_runs": 10,  # Include last 10 messages
            "read_chat_history": True,  # Allow agent to read full history
            "markdown": True,
        }

    def _on_config_stored(self, config: BaseToolkitConfig, user_id: str) -> None:  # noqa: B027
        """
        Override for cross-config dependencies (e.g., SystemPromptExtension).

        Called after a configuration is successfully extracted and stored.

        Args:
            config: The toolkit config that was stored
            user_id: User identifier
        """
        # Hook method - subclasses can override to handle config dependencies
        pass

    # ========== CONCRETE METHODS (SHARED IMPLEMENTATION) ==========

    def _create_simple_response(self, content: str) -> Any:
        """
        Create a simple response object that mimics Agno's RunResponse.

        Args:
            content: Message content to return

        Returns:
            Response object with content attribute
        """
        logger.debug(f"_create_simple_response() called with content length: {len(content)}")

        class SimpleResponse:
            def __init__(self, content: str):
                self.content = content

            def __str__(self):
                return self.content

        response = SimpleResponse(content)
        logger.debug("Created SimpleResponse object")
        return response

    def _handle_configuration(self, message: str, user_id: str | None) -> Any | None:
        """
        Handle toolkit configuration from user messages.

        This method implements a three-phase configuration check:
        1. Extract and store: Try to extract configuration from message
        2. Check required: If any required toolkit is unconfigured, prompt user
        3. Check optional: If optional toolkit detects authorization request, prompt

        Args:
            message: User's message
            user_id: User identifier

        Returns:
            SimpleResponse with prompt/confirmation if config handling needed,
            None if all checks passed (proceed to agent)
        """
        logger.debug("=" * 80)
        logger.info(f">>> _handle_configuration() STARTED - user_id={user_id}")
        logger.debug(f"Message length: {len(message)}")

        if not user_id:
            logger.warning("user_id is None, cannot handle configuration")
            logger.info("<<< _handle_configuration() FINISHED (no user_id)")
            logger.debug("=" * 80)
            return None

        # Phase 1: Try to extract and store configuration from message
        logger.info("📝 Phase 1: Attempting to extract configuration from message")
        for config in self.toolkit_configs:
            config_name = config.__class__.__name__
            logger.debug(f"  Checking {config_name}...")

            try:
                confirmation = config.extract_and_store_config(message, user_id)
                if confirmation:
                    logger.info(f"✅ {config_name} extracted and stored configuration")
                    logger.debug(f"Confirmation message: {confirmation[:100]}...")

                    # Invalidate cached agent so it's recreated with new toolkit
                    if self._agent is not None:
                        logger.info("⚠ Invalidating cached agent due to config change")
                        self._agent = None
                    else:
                        logger.debug("No cached agent to invalidate")

                    # Call hook for subclass-specific handling
                    self._on_config_stored(config, user_id)

                    logger.info("<<< _handle_configuration() FINISHED (config stored)")
                    logger.debug("=" * 80)
                    return self._create_simple_response(confirmation)
                else:
                    logger.debug(f"  {config_name} did not extract configuration")
            except ValueError as e:
                # Invalid configuration (e.g., invalid color)
                error_msg = f"❌ Configuration Error: {str(e)}"
                logger.warning(f"{config_name} validation failed: {e}")
                logger.info("<<< _handle_configuration() FINISHED (validation error)")
                logger.debug("=" * 80)
                return self._create_simple_response(error_msg)

        logger.debug("No configuration extracted from message")

        # Phase 2: Check if any required toolkits are unconfigured
        logger.info("🔍 Phase 2: Checking required toolkit configurations")
        for config in self.toolkit_configs:
            if config.is_required() and not config.is_configured(user_id):
                config_name = config.__class__.__name__
                logger.info(f"⚠ Required toolkit {config_name} is NOT configured for user {user_id}")

                prompt = config.get_config_prompt(user_id)
                if prompt:
                    logger.info(f"Returning configuration prompt for {config_name}")
                    logger.debug(f"Prompt: {prompt[:100]}...")
                    logger.info("<<< _handle_configuration() FINISHED (required config prompt)")
                    logger.debug("=" * 80)
                    return self._create_simple_response(prompt)

        logger.debug("All required toolkits are configured")

        # Phase 3: Check if optional toolkits detect authorization requests
        logger.info("🔍 Phase 3: Checking optional toolkit authorization requests")
        for config in self.toolkit_configs:
            if not config.is_required():
                config_name = config.__class__.__name__
                logger.debug(f"  Checking optional toolkit {config_name}...")

                auth_prompt = config.check_authorization_request(message, user_id)
                if auth_prompt:
                    logger.info(f"Optional toolkit {config_name} detected authorization request")
                    logger.debug(f"Auth prompt: {auth_prompt[:100]}...")
                    logger.info("<<< _handle_configuration() FINISHED (optional config prompt)")
                    logger.debug("=" * 80)
                    return self._create_simple_response(auth_prompt)

        # No configuration handling needed, proceed to agent
        logger.info("✓ All configuration checks passed, proceeding to agent")
        logger.info("<<< _handle_configuration() FINISHED (proceed to agent)")
        logger.debug("=" * 80)
        return None

    def _build_model_params(self) -> dict[str, Any]:
        """
        Build model parameters.

        Returns:
            Dictionary of model parameters
        """
        logger.debug("Building model parameters...")
        model_params: dict[str, Any] = {"id": self._get_model_id()}

        if self._temperature is not None:
            model_params["temperature"] = self._temperature
            logger.debug(f"  + temperature: {self._temperature}")

        if self._max_tokens is not None:
            # Gemini uses max_output_tokens instead of max_tokens
            model_params["max_output_tokens"] = self._max_tokens
            logger.debug(f"  + max_output_tokens: {self._max_tokens}")

        model_params.update(self._model_kwargs)
        logger.debug(f"Final model params: {model_params}")

        return model_params

    def _use_constructor_session_ids(self) -> bool:
        """
        Control whether to pass session_id/user_id to Agent constructor.

        Override this to control session handling behavior:
        - True (default): Pass to constructor as defaults (Use Case 1 - OpenWebUI pattern)
        - False: Don't pass to constructor, pass on every run() call (Use Case 2 - Multi-user pattern)

        Returns:
            True to use constructor defaults, False to pass per-call
        """
        return True  # Default: Use Case 1 (OpenWebUI pattern - wrapper is per-user+session)

    def _collect_toolkits(self, user_id: str) -> list[Any]:
        """
        Collect all configured toolkits for the user.

        Override this method to customize toolkit collection logic,
        such as filtering or reordering based on user properties.

        Args:
            user_id: User identifier

        Returns:
            List of toolkit instances
        """
        logger.debug("Collecting configured toolkits...")
        tools = []
        for config in self.toolkit_configs:
            toolkit = config.get_toolkit(user_id)
            if toolkit:
                tools.append(toolkit)
                logger.info(f"  ✓ Adding {config.__class__.__name__} toolkit to agent for user {user_id}")

        logger.debug(f"Total tools collected: {len(tools)}")
        return tools

    def _build_complete_instructions(self, user_id: str) -> list[str]:
        """
        Build complete instruction list (base + toolkit instructions).

        Override this method to customize instruction assembly,
        such as inserting instructions between base and toolkit,
        or filtering toolkit instructions.

        Args:
            user_id: User identifier

        Returns:
            Complete list of instruction strings
        """
        # Build base instructions (subclass-specific)
        logger.debug("Building base instructions...")
        instructions = self._build_agent_instructions(user_id)
        logger.debug(f"Base instructions: {len(instructions)} lines")

        # Add toolkit-specific instructions
        logger.debug("Adding toolkit-specific instructions...")
        for config in self.toolkit_configs:
            toolkit_instructions = config.get_agent_instructions(user_id)
            if toolkit_instructions:
                logger.debug(f"  + {config.__class__.__name__} added {len(toolkit_instructions)} instruction lines")
                instructions.extend(toolkit_instructions)

        logger.debug(f"Total instruction lines: {len(instructions)}")
        return instructions

    def _build_agent_constructor_kwargs(self) -> dict[str, Any]:
        """
        Build all Agent constructor keyword arguments.

        This gets the base kwargs from _get_agent_kwargs() and adds session IDs.
        Override _get_agent_kwargs() to customize Agent parameters.

        Returns:
            Dictionary of Agent constructor kwargs
        """
        logger.debug("Building Agent constructor kwargs...")

        # Get all agent kwargs (includes base defaults + subclass customizations)
        agent_kwargs = self._get_agent_kwargs()
        logger.debug(f"Agent kwargs from _get_agent_kwargs(): {list(agent_kwargs.keys())}")

        # Add session_id and user_id if using constructor defaults (Use Case 1)
        if self._use_constructor_session_ids():
            logger.debug("Using constructor session IDs (Use Case 1 - wrapper is per-user+session)")
            if self._session_id:
                agent_kwargs["session_id"] = self._session_id
                logger.debug(f"  + session_id: {self._session_id}")
            if self._user_id:
                agent_kwargs["user_id"] = self._user_id
                logger.debug(f"  + user_id: {self._user_id}")
        else:
            logger.debug("NOT using constructor session IDs (Use Case 2 - pass on each run() call)")

        logger.debug(f"Final agent kwargs: {list(agent_kwargs.keys())}")
        return agent_kwargs

    def _create_agent_instance(
        self,
        model_params: dict[str, Any],
        tools: list[Any],
        instructions: list[str],
        agent_kwargs: dict[str, Any],
    ) -> Agent:
        """
        Create the Agno Agent instance.

        Override this method to use a different Agent class or add
        pre/post-creation hooks.

        Args:
            model_params: Model configuration parameters
            tools: List of toolkit instances
            instructions: Complete instruction list
            agent_kwargs: Agent constructor kwargs

        Returns:
            Configured Agent instance
        """
        logger.debug("Creating Agno Agent instance...")

        agent = Agent(
            name=self._get_agent_name(),
            model=Gemini(**model_params),
            description=self._get_agent_description(),
            instructions=instructions,
            tools=tools if tools else None,
            **agent_kwargs,
        )

        logger.info("✅ Agno Agent instance created successfully")
        return agent

    def _get_or_create_agent(self, user_id: str) -> Agent:
        """
        Get or create the underlying Agno agent.

        This method orchestrates agent creation by delegating to smaller,
        overridable methods. Subclasses can override specific parts without
        reimplementing the entire method.

        Note: This wrapper instance is already per-user+session (cached in custom_handler),
        so we only need to store a single agent instance.

        Args:
            user_id: User identifier

        Returns:
            The Agno agent instance
        """
        logger.debug("=" * 80)
        logger.info(f"_get_or_create_agent() called for user_id={user_id}")

        # Return existing agent if available (cache hit)
        if self._agent is not None:
            logger.info("✓ Using CACHED agent (wrapper is per-user+session)")
            logger.debug("=" * 80)
            return self._agent

        # Create new agent (cache miss - first time for this wrapper instance)
        logger.info("✗ Cache MISS - Creating NEW agent")

        # Collect components using extracted methods (all overridable)
        model_params = self._build_model_params()
        tools = self._collect_toolkits(user_id)
        instructions = self._build_complete_instructions(user_id)
        agent_kwargs = self._build_agent_constructor_kwargs()

        # Create agent instance
        agent = self._create_agent_instance(model_params, tools, instructions, agent_kwargs)

        # Store the agent for reuse
        self._agent = agent
        logger.debug("Agent stored in wrapper instance")
        logger.debug("=" * 80)

        return agent

    def run(self, message: str, user_id: str | None = None, **kwargs) -> Any:
        """
        Run the agent with configuration management (synchronous).

        Flow:
        1. Check if user is configured
        2. If not configured, handle configuration (extract tokens or prompt)
        3. If configured, create agent (if needed) and run it

        Args:
            message: User message
            user_id: User identifier from OpenWebUI
            **kwargs: Additional arguments to pass to wrapped agent

        Returns:
            RunResponse from agent or configuration prompt
        """
        logger.info("=" * 80)
        logger.info(f">>> {self.__class__.__name__}.run() STARTED - user_id={user_id}")
        logger.info(f"Message length: {len(message)}, kwargs: {kwargs}")

        # Check configuration and handle if needed
        logger.info("Checking configuration...")
        config_response = self._handle_configuration(message, user_id)

        # If config_response is not None, user needs to configure
        if config_response is not None:
            logger.info("Configuration handling returned response, returning to user")
            logger.info(f"<<< {self.__class__.__name__}.run() FINISHED (config response)")
            logger.info("=" * 80)
            return config_response

        # User is configured, get/create agent and run it
        if not user_id:
            error_msg = "❌ User ID is required to create an agent."
            logger.error("Cannot create agent: user_id is None")
            logger.info(f"<<< {self.__class__.__name__}.run() FINISHED (error)")
            logger.info("=" * 80)
            return self._create_simple_response(error_msg)

        try:
            logger.info(f"Creating agent for user {user_id}...")
            agent = self._get_or_create_agent(user_id)
            logger.info(f"Running agent.run() for user {user_id}...")
            result = agent.run(message, user_id=user_id, **kwargs)
            logger.info(f"✅ Agent.run() completed, result type: {type(result)}")
            logger.info(f"<<< {self.__class__.__name__}.run() FINISHED (success)")
            logger.info("=" * 80)
            return result
        except Exception as e:
            # Agent creation or execution failed
            error_msg = f"❌ Error: {str(e)}"
            logger.error(f"Failed to run agent for user {user_id}: {e}", exc_info=True)
            logger.info(f"<<< {self.__class__.__name__}.run() FINISHED (exception)")
            logger.info("=" * 80)
            return self._create_simple_response(error_msg)

    async def _arun_non_streaming(self, message: str, user_id: str | None = None, **kwargs):
        """Internal async method for non-streaming mode."""
        logger.info("=" * 80)
        logger.info(f">>> {self.__class__.__name__}._arun_non_streaming() STARTED - user_id={user_id}")
        logger.info(f"Message length: {len(message)}, kwargs: {kwargs}")

        # Check configuration and handle if needed
        logger.info("Checking configuration...")
        config_response = self._handle_configuration(message, user_id)

        if config_response is not None:
            logger.info("Configuration handling returned response, returning to user")
            logger.info(f"<<< {self.__class__.__name__}._arun_non_streaming() FINISHED (config response)")
            logger.info("=" * 80)
            return config_response

        if not user_id:
            error_msg = "❌ User ID is required to create an agent."
            logger.error("Cannot create agent: user_id is None")
            logger.info(f"<<< {self.__class__.__name__}._arun_non_streaming() FINISHED (error)")
            logger.info("=" * 80)
            return self._create_simple_response(error_msg)

        try:
            logger.info(f"Creating agent for user {user_id}...")
            agent = self._get_or_create_agent(user_id)
            logger.info(f"Running agent.arun() for user {user_id} (non-streaming)...")
            result = await agent.arun(message, user_id=user_id, **kwargs)
            logger.info(f"✅ Agent.arun() completed, result type: {type(result)}")
            logger.info(f"<<< {self.__class__.__name__}._arun_non_streaming() FINISHED (success)")
            logger.info("=" * 80)
            return result
        except Exception as e:
            # Agent creation or execution failed
            error_msg = f"❌ Error: {str(e)}"
            logger.error(f"Failed to run agent for user {user_id}: {e}", exc_info=True)
            logger.info(f"<<< {self.__class__.__name__}._arun_non_streaming() FINISHED (exception)")
            logger.info("=" * 80)
            return self._create_simple_response(error_msg)

    async def _arun_streaming(self, message: str, user_id: str | None = None, **kwargs) -> AsyncIterator[dict[str, Any]]:
        """
        Internal async generator for streaming mode.

        Converts Agno events to LiteLLM GenericStreamingChunk format.
        This removes Agno-specific logic from custom_handler.py.

        Yields:
            GenericStreamingChunk dictionaries with text field
        """
        logger.info("=" * 80)
        logger.info(f">>> {self.__class__.__name__}._arun_streaming() STARTED - user_id={user_id}")
        logger.info(f"Message length: {len(message)}, kwargs: {kwargs}")

        # Check configuration and handle if needed
        logger.info("Checking configuration...")
        config_response = self._handle_configuration(message, user_id)

        if config_response is not None:
            logger.info("Configuration handling returned response, yielding to user")

            # Yield config message as GenericStreamingChunk
            yield {
                "text": config_response.content,
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

            # Yield final chunk
            yield {
                "text": "",
                "finish_reason": "stop",
                "index": 0,
                "is_finished": True,
                "tool_use": None,
                "usage": {
                    "completion_tokens": 0,
                    "prompt_tokens": 0,
                    "total_tokens": 0,
                },
            }

            logger.info(f"<<< {self.__class__.__name__}._arun_streaming() FINISHED (config response)")
            logger.info("=" * 80)
            return

        if not user_id:
            error_msg = "❌ User ID is required to create an agent."
            logger.error("Cannot create agent: user_id is None")

            # Yield error as GenericStreamingChunk
            yield {
                "text": error_msg,
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

            # Yield final chunk
            yield {
                "text": "",
                "finish_reason": "stop",
                "index": 0,
                "is_finished": True,
                "tool_use": None,
                "usage": {
                    "completion_tokens": 0,
                    "prompt_tokens": 0,
                    "total_tokens": 0,
                },
            }

            logger.info(f"<<< {self.__class__.__name__}._arun_streaming() FINISHED (error)")
            logger.info("=" * 80)
            return

        try:
            logger.info(f"Creating agent for user {user_id}...")
            agent = self._get_or_create_agent(user_id)

            logger.info(f"Starting agent.arun() streaming for user {user_id}...")
            chunk_count = 0

            # Extract session_id from kwargs if present
            session_id = kwargs.get("session_id")

            # Get the async generator from agent.arun()
            logger.info("Calling agent.arun() with stream=True...")
            stream = agent.arun(
                message,
                stream=True,  # Explicit stream mode
                stream_events=True,  # Get all events, not just RunContent
                user_id=user_id,
                session_id=session_id,  # Pass session_id explicitly
            )
            logger.debug(f"Stream type: {type(stream)}")

            logger.info("Entering async for loop over agent stream...")

            # Iterate over Agno stream events and convert to GenericStreamingChunk format
            try:
                async for chunk in stream:
                    chunk_count += 1
                    chunk_type = type(chunk).__name__

                    logger.debug(f"[base_agent] Received event #{chunk_count} from agent: type={chunk_type}")

                    # Process different Agno event types and convert to LiteLLM format

                    if isinstance(chunk, RunContentEvent):
                        # Extract content from chunk
                        content = chunk.content if hasattr(chunk, "content") else str(chunk)

                        if not content:
                            logger.debug(f"Skipping empty RunContentEvent #{chunk_count}")
                            continue

                        logger.debug(f"Yielding RunContentEvent #{chunk_count}, content_length={len(content)}")

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

                    elif isinstance(chunk, ToolCallStartedEvent):
                        # Tool call is starting - send formatted text
                        if hasattr(chunk, "tool") and chunk.tool:
                            tool = chunk.tool
                            tool_name = tool.tool_name if hasattr(tool, "tool_name") else "unknown"
                            tool_args = tool.tool_args if hasattr(tool, "tool_args") else {}

                            logger.info(f"🔧 ToolCallStartedEvent #{chunk_count}: {tool_name}({json.dumps(tool_args)})")

                            # Format tool call as visible text (similar to Gemini's reasoning blocks)
                            args_json = json.dumps(tool_args, indent=2) if tool_args else "{}"
                            tool_call_text = f'\n<details type="tool_call" open="true">\n<summary>🔧 Tool: {tool_name}</summary>\n\n```json\n{args_json}\n```\n\n'

                            yield {
                                "text": tool_call_text,
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
                        else:
                            logger.warning(f"ToolCallStartedEvent #{chunk_count} has no tool attribute, skipping")

                    elif isinstance(chunk, ToolCallCompletedEvent):
                        # Tool call completed - show result and close the details block
                        if hasattr(chunk, "tool") and chunk.tool:
                            tool = chunk.tool
                            tool_name = tool.tool_name if hasattr(tool, "tool_name") else "unknown"
                            tool_result = tool.result if hasattr(tool, "result") else "No result"

                            logger.info(f"✅ ToolCallCompletedEvent #{chunk_count}: {tool_name} → {str(tool_result)[:100]}")

                            # Include the tool result in the details block
                            completion_text = f"**Result:**\n\n{tool_result}\n\n✅ Completed\n</details>\n\n"

                            yield {
                                "text": completion_text,
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
                        else:
                            logger.warning(f"ToolCallCompletedEvent #{chunk_count} has no tool attribute, skipping")

                    elif isinstance(chunk, ReasoningStepEvent):
                        # Reasoning step - format similar to Gemini's reasoning blocks
                        reasoning_text = (
                            chunk.reasoning_content
                            if hasattr(chunk, "reasoning_content")
                            else str(chunk.content)
                            if hasattr(chunk, "content")
                            else ""
                        )

                        if reasoning_text:
                            logger.info(f"💭 ReasoningStepEvent #{chunk_count}: {reasoning_text[:100]}")

                            # Format as collapsible details block (similar to Gemini)
                            reasoning_block = (
                                f'\n<details type="reasoning">\n<summary>💭 Reasoning Step</summary>\n\n{reasoning_text}\n\n</details>\n\n'
                            )

                            yield {
                                "text": reasoning_block,
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
                        else:
                            logger.debug(f"ReasoningStepEvent #{chunk_count} has no content, skipping")

                    elif isinstance(chunk, RunCompletedEvent):
                        # RunCompletedEvent signals proper stream end
                        logger.info(f"✓ RunCompletedEvent received! Stream completed after {chunk_count} events.")
                        # Don't yield RunCompletedEvent - it's a control signal, not content
                        break

                    else:
                        # Log other events for debugging (e.g., RunStartedEvent, etc.)
                        logger.debug(f"Received event: {chunk_type} (not yielding)")

                logger.info(f"Stream iteration complete, total events processed: {chunk_count}")

            except StopAsyncIteration:
                # Natural stream end (should not happen if RunCompletedEvent is sent)
                logger.info("Stream ended via StopAsyncIteration (no RunCompletedEvent received)")
            except Exception as e:
                logger.error(f"Error during stream iteration: {e}", exc_info=True)
                raise

            # Send final chunk with finish_reason
            logger.info("Sending final chunk with finish_reason=stop")
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

            logger.info(f"<<< {self.__class__.__name__}._arun_streaming() FINISHED (success)")
            logger.info("=" * 80)

        except Exception as e:
            # Agent creation or execution failed
            error_msg = f"❌ Error: {str(e)}"
            logger.error(f"Failed to stream from agent for user {user_id}: {e}", exc_info=True)

            # Yield error as GenericStreamingChunk
            yield {
                "text": error_msg,
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

            # Yield final chunk
            yield {
                "text": "",
                "finish_reason": "stop",
                "index": 0,
                "is_finished": True,
                "tool_use": None,
                "usage": {
                    "completion_tokens": 0,
                    "prompt_tokens": 0,
                    "total_tokens": 0,
                },
            }

            logger.info(f"<<< {self.__class__.__name__}._arun_streaming() FINISHED (exception)")
            logger.info("=" * 80)

    def arun(self, message: str, user_id: str | None = None, stream: bool = False, **kwargs):
        """
        Run the agent asynchronously with configuration management.

        Args:
            message: User message
            user_id: User identifier
            stream: Whether to stream responses
            **kwargs: Additional arguments to pass to wrapped agent

        Returns:
            Coroutine[RunResponse] (non-streaming) or AsyncIterator of GenericStreamingChunk dicts (streaming)
        """
        logger.debug(f"arun() called with stream={stream}")

        if stream:
            logger.debug("Delegating to _arun_streaming()")
            # Return async generator directly for streaming
            return self._arun_streaming(message, user_id, **kwargs)
        else:
            logger.debug("Delegating to _arun_non_streaming()")
            # Return coroutine for non-streaming (caller must await)
            return self._arun_non_streaming(message, user_id, **kwargs)
