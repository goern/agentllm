"""Base agent configurator class for managing configuration and agent building."""

from abc import ABC, abstractmethod
from typing import Any

from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.models.google import Gemini
from loguru import logger

from agentllm.agents.base.toolkit_config import BaseToolkitConfig


class AgentConfigurator(ABC):
    """Base class for agent configuration management and building.

    This class handles:
    - Configuration conversation management (OAuth flows, token extraction)
    - Toolkit management and collection
    - Agent construction with proper parameters
    - Configuration state persistence

    The configurator is bound to a specific user_id and session_id at construction time.
    All methods use these bound values rather than taking them as parameters.

    Subclasses must implement abstract methods to provide agent-specific:
    - Toolkit configurations
    - Agent instructions
    - Agent name and description
    """

    def __init__(
        self,
        user_id: str,
        session_id: str | None,
        shared_db: SqliteDb,
        temperature: float | None = None,
        max_tokens: int | None = None,
        agent_kwargs: dict[str, Any] | None = None,
        **model_kwargs: Any,
    ):
        """Initialize the agent configurator.

        Args:
            user_id: User identifier (configurator is bound to this user)
            session_id: Session identifier (configurator is bound to this session)
            shared_db: Shared database instance for session management
            temperature: Model temperature (0.0-2.0)
            max_tokens: Maximum tokens in response
            agent_kwargs: Additional Agent constructor kwargs (e.g., tool_call_limit, retries,
                add_history_to_context, num_history_runs, read_chat_history)
            **model_kwargs: Additional model parameters
        """
        logger.debug("=" * 80)
        logger.info(f"{self.__class__.__name__}.__init__() called")
        logger.debug(
            f"Parameters: user_id={user_id}, session_id={session_id}, "
            f"temperature={temperature}, max_tokens={max_tokens}, "
            f"agent_kwargs={agent_kwargs}, model_kwargs={model_kwargs}"
        )

        # Bind to user and session
        self.user_id = user_id
        self.session_id = session_id

        # Store dependencies
        self._shared_db = shared_db

        # Store model parameters
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._agent_kwargs = agent_kwargs or {}
        self._model_kwargs = model_kwargs

        # Initialize toolkit configurations (subclass-specific)
        logger.debug("Initializing toolkit configurations...")
        self.toolkit_configs = self._initialize_toolkit_configs()
        logger.info(f"Initialized {len(self.toolkit_configs)} toolkit config(s)")

        logger.info(f"✅ {self.__class__.__name__} initialization complete")
        logger.debug("=" * 80)

    # ========== ABSTRACT METHODS (SUBCLASS REQUIRED) ==========

    @abstractmethod
    def _initialize_toolkit_configs(self) -> list[BaseToolkitConfig]:
        """Initialize toolkit configurations for this agent.

        Returns:
            List of toolkit configuration instances
        """
        pass

    @abstractmethod
    def _build_agent_instructions(self) -> list[str]:
        """Build agent-specific instructions.

        Uses self.user_id from constructor.

        Returns:
            List of instruction strings
        """
        pass

    @abstractmethod
    def _get_agent_name(self) -> str:
        """Return agent name (e.g., 'demo-agent', 'release-manager').

        Returns:
            Agent name string
        """
        pass

    @abstractmethod
    def _get_agent_description(self) -> str:
        """Return agent description.

        Returns:
            Agent description string
        """
        pass

    # ========== HOOK METHODS (SUBCLASS OPTIONAL) ==========

    def _get_model_id(self) -> str:
        """Override to change model.

        Returns:
            Model ID (default: gemini-2.5-flash)
        """
        return "gemini-2.5-flash"

    def _get_knowledge_config(self) -> dict[str, Any] | None:
        """Override to provide knowledge base configuration for this agent.

        This method enables RAG (Retrieval Augmented Generation) by specifying:
        - knowledge_path: Path to knowledge base files (markdown, PDF, CSV)
        - table_name: LanceDB table name for vector storage
        - vector_db_path: (optional) Custom vector database directory

        Returns:
            None (default - no knowledge base) or dict with config:
                {
                    "knowledge_path": "examples/my_agent_knowledge",
                    "table_name": "my_agent_knowledge",
                    "vector_db_path": "custom/path"  # optional
                }

        Example:
            def _get_knowledge_config(self) -> dict[str, Any] | None:
                return {
                    "knowledge_path": "examples/demo_knowledge",
                    "table_name": "demo_agent_knowledge"
                }
        """
        return None

    def _get_agent_kwargs(self) -> dict[str, Any]:
        """Get all Agent constructor keyword arguments.

        This is the main method for customizing Agent creation. Override this
        method and call super() to extend the base defaults with your own parameters.

        This base implementation also handles knowledge base loading if
        _get_knowledge_config() is implemented by the subclass.

        Returns:
            Dict of Agent constructor kwargs
        """
        kwargs = {
            "db": self._shared_db,
            "add_history_to_context": True,
            "num_history_runs": 10,
            "read_chat_history": True,
            "markdown": True,
        }

        # Handle knowledge base loading if configured
        knowledge_config = self._get_knowledge_config()
        if knowledge_config is not None:
            from agentllm.knowledge import KnowledgeManagerFactory

            agent_name = self._get_agent_name()
            logger.info(f"Requesting knowledge base for {agent_name}...")
            logger.debug(f"Knowledge config: {knowledge_config}")

            # Get or create knowledge manager for this agent type
            # Factory will log cache hit/miss
            knowledge_manager = KnowledgeManagerFactory.get_or_create(agent_name=agent_name, config=knowledge_config)

            # Load knowledge (lazy loading, cached after first call within manager)
            logger.debug(f"Calling knowledge_manager.load_knowledge() for {agent_name}...")
            knowledge = knowledge_manager.load_knowledge()
            logger.debug(f"Knowledge object received: {type(knowledge).__name__}")

            # Add to agent kwargs
            kwargs["knowledge"] = knowledge
            kwargs["search_knowledge"] = True
            logger.info(f"✅ Knowledge base integrated into agent {agent_name}")

        return kwargs

    def _on_config_stored(self, config: BaseToolkitConfig) -> None:  # noqa: B027
        """Hook called after a config is stored.

        Can be overridden by subclasses to trigger side effects like:
        - Invalidating dependent configs
        - Rebuilding agent with new configuration

        Args:
            config: The toolkit config that was just stored
        """
        # Default: no-op
        pass

    # ========== PUBLIC METHODS ==========

    def handle_configuration(self, message: str) -> Any | None:
        """Handle configuration conversation (OAuth flows, token extraction).

        This method manages the configuration conversation with the user. It:
        1. Checks if user is authenticated/configured
        2. Extracts configuration from messages (OAuth codes, API tokens)
        3. Returns prompts for missing configuration

        Uses self.user_id from constructor.

        Args:
            message: User message to extract configuration from

        Returns:
            Response object if configuration needed, None if configured
        """
        logger.info("=" * 80)
        logger.info(f">>> {self.__class__.__name__}.handle_configuration() STARTED")
        logger.info(f"User: {self.user_id}, Message length: {len(message)}")

        # Phase 1: Try to extract configuration from message
        logger.info("🔄 Phase 1: Attempting to extract configuration from message")
        for config in self.toolkit_configs:
            logger.debug(f"Checking {config.__class__.__name__} for extractable config...")

            try:
                confirmation = config.extract_and_store_config(message, self.user_id)
            except ValueError as e:
                # Invalid configuration (e.g., invalid color)
                error_msg = f"❌ Configuration Error: {str(e)}"
                logger.warning(f"{config.__class__.__name__} validation failed: {e}")
                logger.info("<<< handle_configuration() FINISHED (validation error)")
                logger.info("=" * 80)
                return self._create_simple_response(error_msg)

            if confirmation:
                logger.info(f"✅ Extracted configuration from message for {config.__class__.__name__}")

                # Call hook for side effects (e.g., invalidating dependent configs)
                self._on_config_stored(config)

                logger.info("<<< handle_configuration() FINISHED (config stored)")
                logger.info("=" * 80)
                return self._create_simple_response(confirmation)

        # Phase 2: Check if any required toolkits are unconfigured
        logger.info("🔍 Phase 2: Checking required toolkit configurations")
        for config in self.toolkit_configs:
            if config.is_required() and not config.is_configured(self.user_id):
                config_name = config.__class__.__name__
                logger.info(f"⚠ Required toolkit {config_name} is NOT configured for user {self.user_id}")

                prompt = config.get_config_prompt(self.user_id)
                if prompt:
                    logger.info(f"Returning configuration prompt for {config_name}")
                    logger.debug(f"Prompt: {prompt[:100]}...")
                    logger.info("<<< handle_configuration() FINISHED (required config prompt)")
                    logger.info("=" * 80)
                    return self._create_simple_response(prompt)

        # Phase 3: Check if optional toolkits detect authorization requests
        logger.info("🔍 Phase 3: Checking optional toolkit authorization requests")
        for config in self.toolkit_configs:
            if not config.is_required():
                config_name = config.__class__.__name__
                logger.debug(f"  Checking optional toolkit {config_name}...")

                auth_prompt = config.check_authorization_request(message, self.user_id)
                if auth_prompt:
                    logger.info(f"Optional toolkit {config_name} detected authorization request")
                    logger.debug(f"Auth prompt: {auth_prompt[:100]}...")
                    logger.info("<<< handle_configuration() FINISHED (optional config prompt)")
                    logger.info("=" * 80)
                    return self._create_simple_response(auth_prompt)

        # All checks passed, proceed to agent
        logger.info("✓ All configuration checks passed, proceeding to agent")
        logger.info("<<< handle_configuration() FINISHED (proceed to agent)")
        logger.info("=" * 80)
        return None

    def build_agent(self) -> Agent:
        """Build a fresh Agno agent instance.

        Uses self.user_id and self.session_id from constructor.
        Does NOT cache the agent (caching is handled by BaseAgentWrapper).

        Returns:
            Configured Agno Agent instance
        """
        logger.info("=" * 80)
        logger.info(f">>> {self.__class__.__name__}.build_agent() STARTED")
        logger.info(f"Building agent for user={self.user_id}, session={self.session_id}")

        # Build all components
        model_params = self._build_model_params()
        instructions = self._build_complete_instructions()
        toolkits = self._collect_toolkits()
        agent_kwargs = self._build_agent_constructor_kwargs()

        # Create agent instance
        agent = self._create_agent_instance(
            model_params=model_params,
            instructions=instructions,
            toolkits=toolkits,
            agent_kwargs=agent_kwargs,
        )

        logger.info(f"✅ Agent built successfully for user {self.user_id}")
        logger.info("<<< build_agent() FINISHED")
        logger.info("=" * 80)
        return agent

    def invalidate(self) -> None:
        """Invalidate configuration state.

        Called when configuration changes (e.g., token refresh).
        Subclasses can override to clear additional state.
        """
        logger.info(f"Invalidating configuration state for user {self.user_id}")
        # Base implementation: no-op
        # Agent cache is handled by BaseAgentWrapper, not here

    # ========== INTERNAL METHODS ==========

    def _create_simple_response(self, content: str) -> Any:
        """Create a simple response object.

        This wraps text content in a minimal object with a content attribute,
        matching the structure of an Agno Agent response.

        Args:
            content: Text content to return

        Returns:
            Response object with content attribute
        """

        class SimpleResponse:
            def __init__(self, text: str):
                self.content = text

            def __str__(self):
                return self.content

        return SimpleResponse(content)

    def _build_model_params(self) -> dict[str, Any]:
        """Build model parameters for Agent constructor.

        Uses self._temperature, self._max_tokens, and self._model_kwargs.

        Returns:
            Dict of model parameters
        """
        params = {"id": self._get_model_id()}

        if self._temperature is not None:
            params["temperature"] = self._temperature

        if self._max_tokens is not None:
            # Gemini uses max_output_tokens instead of max_tokens
            params["max_output_tokens"] = self._max_tokens

        # Add any additional model kwargs
        params.update(self._model_kwargs)

        logger.debug(f"Built model params: {params}")
        return params

    def _use_constructor_session_ids(self) -> bool:
        """Return whether to use constructor-bound session IDs.

        Returns:
            True (configurator is always bound to user+session)
        """
        return True

    def _collect_toolkits(self) -> list[Any]:
        """Collect configured toolkits.

        Uses self.user_id from constructor.

        Returns:
            List of toolkit instances
        """
        logger.debug(f"Collecting toolkits for user {self.user_id}...")
        toolkits = []

        for config in self.toolkit_configs:
            config_name = config.__class__.__name__
            is_configured = config.is_configured(self.user_id)
            logger.info(f"  {config_name}: is_configured={is_configured}")

            if is_configured:
                toolkit = config.get_toolkit(self.user_id)
                if toolkit:
                    toolkits.append(toolkit)
                    toolkit_name = toolkit.name if hasattr(toolkit, "name") else type(toolkit).__name__
                    logger.info(f"  ✅ Added toolkit: {toolkit_name} from {config_name}")
                else:
                    logger.warning(f"  ⚠️ {config_name} is configured but get_toolkit() returned None!")

        logger.info(f"🎯 Collected {len(toolkits)} toolkit(s) total")
        return toolkits

    def _build_complete_instructions(self) -> list[str]:
        """Build complete agent instructions (base + toolkit-specific).

        Uses self.user_id from constructor.

        Returns:
            List of instruction strings
        """
        logger.debug("Building complete agent instructions...")

        # Get base instructions from subclass
        instructions = self._build_agent_instructions()
        logger.debug(f"Base instructions: {len(instructions)} lines")

        # Add toolkit-specific instructions
        logger.debug("Adding toolkit-specific instructions...")
        for config in self.toolkit_configs:
            toolkit_instructions = config.get_agent_instructions(self.user_id)
            if toolkit_instructions:
                instructions.extend([""] + toolkit_instructions)
                logger.debug(f"Added {len(toolkit_instructions)} lines from {config.__class__.__name__}")

        logger.info(f"Total instruction lines: {len(instructions)}")
        return instructions

    def _build_agent_constructor_kwargs(self) -> dict[str, Any]:
        """Build Agent constructor kwargs.

        Uses self.user_id and self.session_id from constructor.

        Returns:
            Dict of Agent constructor kwargs
        """
        logger.debug("Building Agent constructor kwargs...")

        # Start with base defaults from subclass
        agent_kwargs = self._get_agent_kwargs()

        # Add custom agent kwargs passed to constructor
        # These override defaults but can be overridden by session IDs
        agent_kwargs.update(self._agent_kwargs)

        # Use constructor session IDs (always true for configurator)
        if self._use_constructor_session_ids():
            agent_kwargs["user_id"] = self.user_id
            if self.session_id is not None:
                agent_kwargs["session_id"] = self.session_id

        logger.debug(f"Agent kwargs: {list(agent_kwargs.keys())}")
        return agent_kwargs

    def _create_agent_instance(
        self,
        model_params: dict[str, Any],
        instructions: list[str],
        toolkits: list[Any],
        agent_kwargs: dict[str, Any],
    ) -> Agent:
        """Create the Agno Agent instance.

        Args:
            model_params: Model parameters
            instructions: Agent instructions
            toolkits: Configured toolkits
            agent_kwargs: Agent constructor kwargs

        Returns:
            Agno Agent instance
        """
        logger.debug("Creating Agno Agent instance...")
        logger.info(f"Creating agent with model: {model_params.get('id')}")

        agent = Agent(
            name=self._get_agent_name(),
            model=Gemini(**model_params),
            description=self._get_agent_description(),
            instructions=instructions,
            tools=toolkits if toolkits else None,
            **agent_kwargs,
        )

        logger.info("✅ Agno Agent instance created successfully")
        return agent
