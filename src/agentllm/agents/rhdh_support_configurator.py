"""RHDH Support Focal Configurator - Configuration management for Support Focal Agent."""

from typing import Any

from agno.db.sqlite import SqliteDb

from agentllm.agents.base import AgentConfigurator, BaseToolkitConfig
from agentllm.agents.toolkit_configs import GoogleDriveConfig, JiraConfig, RHCPConfig
from agentllm.agents.toolkit_configs.system_prompt_extension_config import (
    SystemPromptExtensionConfig,
)


class RHDHSupportConfigurator(AgentConfigurator):
    """Configurator for RHDH Support Focal Agent.

    Handles configuration management and agent building for the Support Focal.
    """

    def __init__(
        self,
        user_id: str,
        session_id: str | None,
        shared_db: SqliteDb,
        token_storage,
        temperature: float | None = None,
        max_tokens: int | None = None,
        agent_kwargs: dict[str, Any] | None = None,
        **model_kwargs: Any,
    ):
        """Initialize RHDH Support Focal configurator.

        Args:
            user_id: User identifier
            session_id: Session identifier
            shared_db: Shared database
            token_storage: TokenStorage instance
            temperature: Optional model temperature
            max_tokens: Optional max tokens
            agent_kwargs: Additional Agent constructor kwargs
            **model_kwargs: Additional model parameters
        """
        # Store token_storage for use in _initialize_toolkit_configs
        self._token_storage = token_storage

        # Call parent constructor (will call _initialize_toolkit_configs)
        super().__init__(
            user_id=user_id,
            session_id=session_id,
            shared_db=shared_db,
            temperature=temperature,
            max_tokens=max_tokens,
            agent_kwargs=agent_kwargs,
            **model_kwargs,
        )

    def _get_agent_name(self) -> str:
        """Get agent name for identification.

        Returns:
            str: Agent name
        """
        return "rhdh-support"

    def _get_agent_description(self) -> str:
        """Get agent description.

        Returns:
            str: Human-readable description
        """
        return "A helpful AI assistant for RHDH Support Focal"

    def _initialize_toolkit_configs(self) -> list[BaseToolkitConfig]:
        """Initialize toolkit configurations for Support Focal.

        Returns:
            list[BaseToolkitConfig]: List of toolkit configs
        """
        # ORDER MATTERS: SystemPromptExtensionConfig depends on GoogleDriveConfig
        gdrive_config = GoogleDriveConfig(token_storage=self._token_storage)
        jira_config = JiraConfig(
            jira_server="https://issues.redhat.com",
            token_storage=self._token_storage,
        )
        rhcp_config = RHCPConfig(token_storage=self._token_storage)
        system_prompt_config = SystemPromptExtensionConfig(gdrive_config=gdrive_config, token_storage=self._token_storage)

        return [
            gdrive_config,
            jira_config,
            rhcp_config,
            system_prompt_config,  # Must come after gdrive_config due to dependency
        ]

    def _build_agent_instructions(self) -> list[str]:
        """Build system prompt instructions for Support Focal.

        Returns:
            list[str]: List of instruction strings
        """
        return [
            "You are the Support Focal for Red Hat Developer Hub (RHDH).",
            "",
            "Your core responsibilities include:",
            "- Monitoring RHDHSUPP issues created by the Support team requesting Engineering assistance",
            "- Ensuring RHDHSUPP issues get assigned to an RHDH Scrum Team based on severity and SLA",
            "- Tracking linked customer cases from Red Hat Customer Portal (RHCP)",
            "- Monitoring related issues in RHDHPLAN (RFEs) and RHDHBUGS (defects)",
            "- Providing status updates and insights to Support managers and Engineering leads",
            "",
            "Available tools and integrations:",
            "- JIRA: Query RHDHSUPP, RHDHPLAN, and RHDHBUGS issues (READ-ONLY)",
            "  - Key fields: Assignee, Team, Priority, customfield_12313441 (case number)",
            "  - No case creation, updates, or comments allowed",
            "- Red Hat Customer Portal (RHCP): Fetch customer case information (READ-ONLY)",
            "  - Case data: severity, escalation status, entitlement level, SLA information",
            "  - No case creation or modification allowed - only read access",
            "- Google Drive: Access RHDH support process documentation",
            "  - RHDHSUPP CEE Process: https://docs.google.com/document/d/153AHMAAV8aPQdtd80nrPLAROHHIvFnXqjYx0wa1ywxw/",
            "  - RHDHSUPP Engineering Process: https://docs.google.com/document/d/153AHMAAV8aPQdtd80nrPLAROHHIvFnXqjYx0wa1ywxw/",
            "  - RHDHSUPP Simplified Workflow: https://docs.google.com/document/d/1hd5Acy9y9ZERKY7TBIhsPr1GQqJuCrIETVZUkHAYkPA/",
            "  - RHDHSUPP Playbook: https://docs.google.com/drawings/d/1RymlzkeJMRP8uPvGLbtANN2QduCIRhpc4DlPWx_teiM/",
            "",
            "Priority Guidelines:",
            "- Priority field should reflect the linked customer case severity",
            "- Escalated cases (case_customer_escalation=true) should be Priority: Blocker",
            "- Follow Red Hat severity definitions: https://access.redhat.com/support/policy/severity",
            "- Follow Red Hat SLA policy: https://access.redhat.com/support/offerings/production/sla",
            "",
            "Reference Documentation:",
            "- RHDH Lifecycle (version support): https://access.redhat.com/support/policy/updates/developerhub",
            "- Plugin support levels: https://docs.redhat.com/en/documentation/red_hat_developer_hub/1.8/html-single/dynamic_plugins_reference/",
            "",
            "Output guidelines:",
            "- Use markdown formatting for all structured output",
            "- Return markdown tables for data visualization",
            "- Be concise but comprehensive in your responses",
            "- Provide data-driven insights with JIRA queries and RHCP case data",
            "- Include relevant links to JIRA issues, RHCP cases, and process documentation",
            "- Use tables and bullet points for clarity",
            "",
            "Behavioral guidelines:",
            "- CRITICAL: Read-only operations ONLY",
            "  - Do NOT create, update, or comment on JIRA issues",
            "  - Do NOT create, update, or modify customer cases in RHCP",
            "  - You can only read and query data, never modify it",
            "- Proactively identify unassigned issues and SLA risks",
            "- Cross-reference JIRA issues with customer cases to provide full context",
            "- When asked about version support, parse version from issue description and check lifecycle doc",
            "- When asked about plugin support, reference the plugin support levels documentation",
            "- Base recommendations on concrete data (JIRA queries, case severity, SLA status)",
            "- Maintain professional communication appropriate for Support and Engineering stakeholders",
            "",
            "System Prompt Management:",
            "- Your instructions come from TWO sources:",
            "  1. Embedded system prompt (stable, rarely changes): Core identity and capabilities",
            "  2. External system prompt (dynamic, frequently updated): Current process details and examples",
            "- The external prompt is stored in a Google Drive document that users can directly edit",
            "- When process context seems outdated or incomplete, suggest users update the external prompt",
            "- If configured, you will be informed of the external prompt document URL in your extended instructions",
        ]

    def _build_model_params(self) -> dict[str, Any]:
        """Build model parameters with Gemini native thinking capability.

        Returns:
            dict: Model configuration parameters
        """
        params = super()._build_model_params()

        # Add Gemini native thinking parameters
        params["thinking_budget"] = 200  # Allocate up to 200 tokens for thinking
        params["include_thoughts"] = True  # Request thought summaries in response

        return params

    def _on_config_stored(self, config: BaseToolkitConfig) -> None:
        """Handle cross-config dependencies when configuration is stored.

        Special handling for GoogleDrive → SystemPromptExtension:
        When Google Drive credentials are updated, notify SystemPromptExtensionConfig
        to invalidate its cached system prompts.

        Args:
            config: The toolkit config that was stored
        """
        # When GoogleDrive credentials are updated, notify SystemPromptExtensionConfig
        if isinstance(config, GoogleDriveConfig):
            for other_config in self.toolkit_configs:
                if isinstance(other_config, SystemPromptExtensionConfig):
                    other_config.invalidate_for_gdrive_change(self.user_id)
                    break
