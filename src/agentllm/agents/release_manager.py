"""Release Manager agent for managing software releases and changelogs."""

import os
from pathlib import Path
from typing import Any

from agno.agent import Agent, RunCompletedEvent
from agno.db.sqlite import SqliteDb
from agno.models.google import Gemini
from loguru import logger

from agentllm.agents.toolkit_configs import GoogleDriveConfig
from agentllm.agents.toolkit_configs.jira_config import JiraConfig
from agentllm.agents.toolkit_configs.system_prompt_extension_config import (
    SystemPromptExtensionConfig,
)
from agentllm.db import TokenStorage

# Map GEMINI_API_KEY to GOOGLE_API_KEY if not set
if "GOOGLE_API_KEY" not in os.environ and "GEMINI_API_KEY" in os.environ:
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]

# Shared database for all agents to enable session management
DB_PATH = Path("tmp/agno_sessions.db")
DB_PATH.parent.mkdir(exist_ok=True)
shared_db = SqliteDb(db_file=str(DB_PATH))

# Create token storage using the shared database
# This stores Jira and Google Drive credentials in the same database
token_storage = TokenStorage(agno_db=shared_db)


class ReleaseManager:
    """Release Manager with toolkit configuration management.

    This class wraps an Agno agent and manages user-specific toolkit configurations
    (e.g., Google Drive OAuth, JIRA tokens). It intercepts run() and arun() calls to:
    1. Check if toolkits are configured for the user
    2. Extract configuration from user messages if provided
    3. Prompt users for missing configurations when they request toolkit features
    4. Delegate to the wrapped agent once configured

    The class maintains the same interface as Agno Agent, making it transparent
    to LiteLLM and other callers.

    Toolkit Configuration:
    ---------------------
    Toolkits are managed via composition using BaseToolkitConfig implementations.
    Each toolkit handles its own configuration flow, validation, and provisioning.

    Currently supported toolkits:
    - Google Drive: OAuth-based access to Google Docs, Sheets, and Presentations
    - JIRA: API token-based access to JIRA issues (optional, can be enabled)

    See individual toolkit config classes for setup instructions.
    """

    def __init__(
        self,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **model_kwargs,
    ):
        """Initialize the Release Manager with toolkit configurations.

        Args:
            temperature: Model temperature (0.0-2.0)
            max_tokens: Maximum tokens in response
            **model_kwargs: Additional model parameters
        """
        # Initialize toolkit configurations with shared token storage
        # ORDER MATTERS: SystemPromptExtensionConfig depends on GoogleDriveConfig
        gdrive_config = GoogleDriveConfig(token_storage=token_storage)
        jira_config = JiraConfig(token_storage=token_storage)
        system_prompt_config = SystemPromptExtensionConfig(
            gdrive_config=gdrive_config, token_storage=token_storage
        )

        self.toolkit_configs = [
            gdrive_config,
            jira_config,
            system_prompt_config,  # Must come after gdrive_config due to dependency
        ]

        # Store model parameters for later agent creation
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._model_kwargs = model_kwargs

        # Store agents per user_id (agents are not shared across users)
        self._agents: dict[str, Agent] = {}

    def _invalidate_agent(self, user_id: str) -> None:
        """Invalidate cached agent for a user.

        This forces agent recreation on next request, useful when
        user authorizes new tools (e.g., Google Drive).

        Args:
            user_id: User identifier
        """
        if user_id in self._agents:
            logger.info(f"⚠ Invalidating cached agent for user {user_id}")
            del self._agents[user_id]
            logger.debug(f"Agent removed from cache. Remaining cached agents: {len(self._agents)}")
        else:
            logger.debug(f"No cached agent found for user {user_id} (nothing to invalidate)")

    def _check_and_invalidate_agent(self, config_name: str, user_id: str) -> None:
        """Check if config requires agent recreation and invalidate if needed.

        Args:
            config_name: Configuration name that was just stored
            user_id: User identifier
        """
        # Check if any toolkit config requires agent recreation for this config
        for config in self.toolkit_configs:
            if config.requires_agent_recreation(config_name):
                self._invalidate_agent(user_id)
                logger.info(f"Config '{config_name}' requires agent recreation for user {user_id}")
                break

    def _get_or_create_agent(self, user_id: str) -> Agent:
        """Get or create the underlying Agno agent for a specific user.

        Agents are created per-user and include their configured toolkits.

        Args:
            user_id: User identifier

        Returns:
            The Agno agent instance for this user
        """
        logger.debug(f"_get_or_create_agent() called for user_id={user_id}")

        # Return existing agent for this user if available
        if user_id in self._agents:
            logger.info(f"✓ Using CACHED agent for user {user_id}")
            return self._agents[user_id]

        # Create the agent for this user
        logger.info(f"✗ Cache MISS - Creating NEW agent for user {user_id}")
        logger.debug("Building model parameters...")
        model_params = {"id": "gemini-2.5-flash"}
        if self._temperature is not None:
            model_params["temperature"] = self._temperature
        if self._max_tokens is not None:
            model_params["max_tokens"] = self._max_tokens
        model_params.update(self._model_kwargs)
        logger.debug(f"Model params: {model_params}")

        # Collect all configured toolkits for this user
        logger.debug("Collecting configured toolkits...")
        tools = []
        for config in self.toolkit_configs:
            toolkit = config.get_toolkit(user_id)
            if toolkit:
                tools.append(toolkit)
                logger.info(
                    f"  ✓ Adding {config.__class__.__name__} toolkit to agent for user {user_id}"
                )

        logger.debug(f"Total tools collected: {len(tools)}")

        # Create base instructions
        logger.debug("Building base instructions...")
        instructions = [
            "You are the Release Manager for Red Hat Developer Hub (RHDH).",
            "Your core responsibilities include:",
            "- Managing Y-stream releases (major versions like 1.7.0, 1.8.0)",
            "- Managing Z-stream releases (maintenance versions like 1.6.1, 1.6.2)",
            "- Tracking release progress, risks, and blockers",
            "- Coordinating with Engineering, QE, Documentation, and Product Management teams",
            "- Providing release status updates for meetings (SOS, Team Forum, Program Meeting)",
            "- Monitoring Jira for release-related issues, features, and bugs",
            "",
            "Available tools:",
            "- Jira: Query and analyze issues, epics, features, bugs, and CVEs",
            "- Google Drive: Access release schedules, test plans, documentation plans, and feature demos",
            "",
            "Output guidelines:",
            "- Use markdown formatting for all structured output",
            "- Be concise but comprehensive in your responses",
            "- Provide data-driven insights with Jira query results and metrics",
            "- Include relevant links to Jira issues, and Google Docs resources",
            "- Use tables and bullet points for clarity",
            "",
            "Behavioral guidelines:",
            "- Proactively identify risks and blockers",
            "- Escalate critical issues with clear impact analysis",
            "- Base recommendations on concrete data (Jira metrics, test results, schedules)",
            "- Maintain professional communication appropriate for cross-functional stakeholders",
            "- Follow established release processes and policies",
            "",
            "System Prompt Management:",
            "- Your instructions come from TWO sources:",
            "  1. Embedded system prompt (stable, rarely changes): Core identity and capabilities",
            "  2. External system prompt (dynamic, frequently updated): Current release context, processes, examples",
            "- The external prompt is stored in a Google Drive document that users can directly edit",
            "- When release context seems outdated or incomplete, suggest users update the external prompt",
            "- If configured, you will be informed of the external prompt document URL in your extended instructions",
        ]

        # Add toolkit-specific instructions (including extended system prompt if configured)
        logger.debug("Adding toolkit-specific instructions...")
        for config in self.toolkit_configs:
            toolkit_instructions = config.get_agent_instructions(user_id)
            if toolkit_instructions:
                logger.debug(
                    f"  + {config.__class__.__name__} added {len(toolkit_instructions)} instruction lines"
                )
            instructions.extend(toolkit_instructions)

        logger.debug(f"Total instruction lines: {len(instructions)}")
        logger.debug("Creating Agno Agent instance...")

        agent = Agent(
            name="release-manager",
            model=Gemini(**model_params),
            description="A helpful AI assistant",
            instructions=instructions,
            markdown=True,
            tools=tools if tools else None,
            # Session management
            db=shared_db,
            add_history_to_context=True,
            num_history_runs=10,  # Include last 10 messages
            read_chat_history=True,  # Allow agent to read full history
        )

        logger.debug("Agno Agent instance created successfully")

        # Cache the agent for this user
        self._agents[user_id] = agent
        logger.info(
            f"✓ Created and cached agent for user {user_id} with {len(tools)} tools. "
            f"Total cached agents: {len(self._agents)}"
        )

        return agent

    def _create_simple_response(self, content: str) -> Any:
        """Create a simple response object that mimics Agno's RunResponse.

        Args:
            content: Message content to return

        Returns:
            Response object with content attribute
        """

        class SimpleResponse:
            def __init__(self, content: str):
                self.content = content

            def __str__(self):
                return self.content

        return SimpleResponse(content)

    def _handle_configuration(self, message: str, user_id: str | None) -> Any | None:
        """Handle configuration extraction and validation.

        This method (in order):
        1. Tries to extract and store configuration from user message (OAuth codes, tokens, etc.)
        2. Checks if any required toolkit is not configured and prompts if needed
        3. Checks if any optional toolkit detects an authorization request and prompts if needed
        4. Returns None if no configuration handling needed (proceed to agent)

        The order is important: extraction must happen first so that when a user provides
        config, it gets stored before we check if required configs are missing.

        Args:
            message: User message
            user_id: User identifier

        Returns:
            Response with configuration message, or None if no config handling needed
        """
        logger.debug(f"_handle_configuration() called for user_id={user_id}")

        if not user_id:
            logger.debug("No user_id provided, skipping configuration handling")
            return None

        # FIRST: Try to extract and store configuration from message
        # This must happen before checking required configs, so that if the user
        # provides config (e.g., OAuth code), it gets stored before we check again
        logger.debug("[1/3] Checking for configuration in user message...")
        for config in self.toolkit_configs:
            try:
                confirmation = config.extract_and_store_config(message, user_id)
                if confirmation:
                    # Configuration was extracted and stored successfully
                    # Invalidate agent so it's recreated with new tools
                    self._invalidate_agent(user_id)
                    logger.info(
                        f"✓ Configuration stored for {config.__class__.__name__}, "
                        f"agent invalidated for user {user_id}"
                    )

                    # If Google Drive credentials were updated, notify SystemPromptExtensionConfig
                    # to invalidate its cached system prompts
                    if isinstance(config, GoogleDriveConfig):
                        for other_config in self.toolkit_configs:
                            if isinstance(other_config, SystemPromptExtensionConfig):
                                other_config.invalidate_for_gdrive_change(user_id)
                                logger.debug(
                                    "Notified SystemPromptExtensionConfig of GDrive credential change"
                                )
                                break

                    return self._create_simple_response(confirmation)
            except ValueError as e:
                # Configuration validation failed
                error_msg = (
                    f"❌ Configuration validation failed: {str(e)}\n\n"
                    "Please check your credentials and try again."
                )
                logger.warning(
                    f"⚠ Configuration validation failed for "
                    f"{config.__class__.__name__}, user {user_id}: {e}"
                )
                return self._create_simple_response(error_msg)

        # SECOND: Check if any REQUIRED toolkit is not configured
        # This happens after extraction, so if user provided config above, it's already stored
        logger.debug("[2/3] Checking required toolkit configurations...")
        for config in self.toolkit_configs:
            if config.is_required() and not config.is_configured(user_id):
                # Required toolkit not configured - prompt user
                prompt = config.get_config_prompt(user_id)
                if prompt:
                    logger.info(
                        f"⚠ User {user_id} needs to configure required toolkit: "
                        f"{config.__class__.__name__}"
                    )
                    return self._create_simple_response(prompt)

        # THIRD: Check if any OPTIONAL toolkit detects an authorization request
        # (e.g., user mentions the toolkit but hasn't authorized yet)
        logger.debug("[3/3] Checking optional toolkit authorization requests...")
        for config in self.toolkit_configs:
            if not config.is_required():
                auth_prompt = config.check_authorization_request(message, user_id)
                if auth_prompt:
                    logger.info(
                        f"Optional toolkit {config.__class__.__name__} detected authorization request"
                    )
                    return self._create_simple_response(auth_prompt)

        # No configuration handling needed, proceed to agent
        logger.debug("✓ All configuration checks passed, proceeding to agent")
        return None

    def run(self, message: str, user_id: str | None = None, **kwargs) -> Any:
        """Run the agent with configuration management.

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
        logger.info(f">>> ReleaseManager.run() STARTED - user_id={user_id}")
        logger.info(f"Message length: {len(message)}, kwargs: {kwargs}")

        # Check configuration and handle if needed
        logger.info("Checking configuration...")
        config_response = self._handle_configuration(message, user_id)

        # If config_response is not None, user needs to configure
        if config_response is not None:
            logger.info("Configuration handling returned response, returning to user")
            logger.info("<<< ReleaseManager.run() FINISHED (config response)")
            logger.info("=" * 80)
            return config_response

        # User is configured, get/create agent and run it
        if not user_id:
            error_msg = "❌ User ID is required to create an agent."
            logger.error("Cannot create agent: user_id is None")
            logger.info("<<< ReleaseManager.run() FINISHED (error)")
            logger.info("=" * 80)
            return self._create_simple_response(error_msg)

        try:
            logger.info(f"Getting or creating agent for user {user_id}...")
            agent = self._get_or_create_agent(user_id)
            logger.info(f"Running agent.run() for user {user_id}...")
            result = agent.run(message, user_id=user_id, **kwargs)
            logger.info(f"Agent.run() completed, result type: {type(result)}")
            logger.info("<<< ReleaseManager.run() FINISHED (success)")
            logger.info("=" * 80)
            return result
        except Exception as e:
            # Agent creation or execution failed
            error_msg = f"❌ Error: {str(e)}"
            logger.error(f"Failed to run agent for user {user_id}: {e}", exc_info=True)
            logger.info("<<< ReleaseManager.run() FINISHED (exception)")
            logger.info("=" * 80)
            return self._create_simple_response(error_msg)

    async def _arun_non_streaming(self, message: str, user_id: str | None = None, **kwargs):
        """Internal async method for non-streaming mode."""
        logger.info("=" * 80)
        logger.info(f">>> ReleaseManager._arun_non_streaming() STARTED - user_id={user_id}")
        logger.info(f"Message length: {len(message)}, kwargs: {kwargs}")

        # Check configuration and handle if needed
        logger.info("Checking configuration...")
        config_response = self._handle_configuration(message, user_id)

        if config_response is not None:
            logger.info("Configuration handling returned response, returning to user")
            logger.info("<<< ReleaseManager._arun_non_streaming() FINISHED (config response)")
            logger.info("=" * 80)
            return config_response

        if not user_id:
            error_msg = "❌ User ID is required to create an agent."
            logger.error("Cannot create agent: user_id is None")
            logger.info("<<< ReleaseManager._arun_non_streaming() FINISHED (error)")
            logger.info("=" * 80)
            return self._create_simple_response(error_msg)

        try:
            logger.info(f"Getting or creating agent for user {user_id}...")
            agent = self._get_or_create_agent(user_id)
            logger.info(f"Running agent.arun() for user {user_id} (non-streaming)...")
            result = await agent.arun(message, user_id=user_id, **kwargs)
            logger.info(f"Agent.arun() completed, result type: {type(result)}")
            logger.info("<<< ReleaseManager._arun_non_streaming() FINISHED (success)")
            logger.info("=" * 80)
            return result
        except Exception as e:
            # Agent creation or execution failed
            error_msg = f"❌ Error: {str(e)}"
            logger.error(f"Failed to run agent for user {user_id}: {e}", exc_info=True)
            logger.info("<<< ReleaseManager._arun_non_streaming() FINISHED (exception)")
            logger.info("=" * 80)
            return self._create_simple_response(error_msg)

    async def _arun_streaming(self, message: str, user_id: str | None = None, **kwargs):
        """Internal async generator for streaming mode."""
        logger.info("=" * 80)
        logger.info(f">>> ReleaseManager._arun_streaming() STARTED - user_id={user_id}")
        logger.info(f"Message length: {len(message)}, kwargs: {kwargs}")

        # Check configuration and handle if needed
        logger.info("Checking configuration...")
        config_response = self._handle_configuration(message, user_id)

        if config_response is not None:
            logger.info("Configuration handling returned response, yielding to user")
            content = (
                config_response.content
                if hasattr(config_response, "content")
                else str(config_response)
            )
            yield content
            logger.info("<<< ReleaseManager._arun_streaming() FINISHED (config response)")
            logger.info("=" * 80)
            return

        if not user_id:
            error_msg = "❌ User ID is required to create an agent."
            logger.error("Cannot create agent: user_id is None")
            yield error_msg
            logger.info("<<< ReleaseManager._arun_streaming() FINISHED (error)")
            logger.info("=" * 80)
            return

        try:
            logger.info(f"Getting or creating agent for user {user_id}...")
            agent = self._get_or_create_agent(user_id)

            logger.info(f"Starting agent.arun() streaming for user {user_id}...")
            chunk_count = 0

            # When streaming, agent.arun() returns an async generator directly
            # Don't await it, just iterate over it
            logger.info("Entering async for loop over agent.arun()...")

            # Get the async generator from agent.arun()
            # Use stream_events=True to get RunCompletedEvent (not just RunContent events)
            # Note: stream=True is already in kwargs, so we don't pass it explicitly
            # Extract session_id from kwargs if present
            session_id = kwargs.get("session_id")

            stream = agent.arun(
                message,
                stream=True,  # Explicit stream mode
                stream_events=True,  # Get all events, not just RunContent
                user_id=user_id,
                session_id=session_id,  # Pass session_id explicitly
            )
            logger.debug(f"Stream type: {type(stream)}")

            # Iterate over stream events without timeout
            # Rely on RunCompletedEvent and StopAsyncIteration for proper completion
            try:
                async for chunk in stream:
                    chunk_count += 1

                    chunk_type = type(chunk).__name__
                    chunk_content = getattr(chunk, "content", None)
                    chunk_event = getattr(chunk, "event", None)

                    logger.info(
                        f"Event #{chunk_count}: type={chunk_type}, "
                        f"event={chunk_event}, "
                        f"content_length={len(chunk_content) if chunk_content else 0}"
                    )

                    # Log event attributes for debugging
                    if hasattr(chunk, "__dict__"):
                        logger.debug(f"Event #{chunk_count} attributes: {vars(chunk)}")
                    else:
                        logger.debug(f"Event #{chunk_count} dir: {dir(chunk)}")

                    # Check for RunCompletedEvent (signals proper stream end)
                    if isinstance(chunk, RunCompletedEvent):
                        logger.info(
                            f"✓ RunCompletedEvent received! Stream completed after {chunk_count} events."
                        )
                        # Don't yield RunCompletedEvent - it's a control signal, not content
                        break

                    # Yield the event to upstream consumer
                    yield chunk
                    logger.debug(f"Event #{chunk_count} yielded successfully")

                logger.info(f"Stream iteration complete, total events processed: {chunk_count}")

            except StopAsyncIteration:
                # Natural stream end (should not happen if RunCompletedEvent is sent)
                logger.info("Stream ended via StopAsyncIteration (no RunCompletedEvent received)")
            except Exception as e:
                logger.error(f"Error during stream iteration: {e}", exc_info=True)
                raise
            logger.info("<<< ReleaseManager._arun_streaming() FINISHED (success)")
            logger.info("=" * 80)
        except Exception as e:
            # Agent creation or execution failed
            error_msg = f"❌ Error: {str(e)}"
            logger.error(f"Failed to run agent for user {user_id}: {e}", exc_info=True)
            yield error_msg
            logger.info("<<< ReleaseManager._arun_streaming() FINISHED (exception)")
            logger.info("=" * 80)

    def arun(self, message: str, user_id: str | None = None, **kwargs):
        """Async version of run() with same configuration management logic.

        Handles both streaming and non-streaming modes. Returns either a coroutine
        (non-streaming) or an async generator (streaming) based on the stream parameter.

        Args:
            message: User message
            user_id: User identifier from OpenWebUI
            **kwargs: Additional arguments to pass to wrapped agent

        Returns:
            Coroutine (non-streaming) or AsyncGenerator (streaming)
        """
        stream = kwargs.get("stream", False)
        logger.info("=" * 80)
        logger.info(f">>> ReleaseManager.arun() called - user_id={user_id}, stream={stream}")
        logger.info(f"Message length: {len(message)}, kwargs: {kwargs}")

        if stream:
            # Return async generator for streaming
            logger.info("Delegating to _arun_streaming()")
            return self._arun_streaming(message, user_id=user_id, **kwargs)
        else:
            # Return coroutine for non-streaming
            logger.info("Delegating to _arun_non_streaming()")
            return self._arun_non_streaming(message, user_id=user_id, **kwargs)
