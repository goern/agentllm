"""This Red Hat AI (RHAI) Roadmap slide publisher Agent."""

import os

from agno.db.sqlite import SqliteDb
from loguru import logger

from agentllm.agents.base_agent import BaseAgentWrapper
from agentllm.agents.toolkit_configs import GoogleDriveConfig
from agentllm.agents.toolkit_configs.base import BaseToolkitConfig
from agentllm.agents.toolkit_configs.jira_config import JiraConfig
from agentllm.agents.toolkit_configs.system_prompt_extension_config import (
    SystemPromptExtensionConfig,
)
from agentllm.db import TokenStorage

# Map GEMINI_API_KEY to GOOGLE_API_KEY if not set
if "GOOGLE_API_KEY" not in os.environ and "GEMINI_API_KEY" in os.environ:
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]


class RHAIRoadmapPublisher(BaseAgentWrapper):
    """Roadmap Publisher with toolkit configuration management.

    This class extends BaseAgentWrapper to provide a RHAI Roadmap publisher agent
    specialized for Red Hat AI (RHAI) product management.

    Toolkit Configuration:
    ---------------------
    - Google Drive: OAuth-based access to Google Docs, Sheets, and Presentations (required)
    - JIRA: API token-based access to JIRA issues (required)
    - SystemPromptExtension: Extended instructions from Google Drive document (required if configured)

    The agent helps with:
    - creating a roadmap slide based on a selection of RHAI components
    """

    def __init__(
        self,
        shared_db: SqliteDb,
        token_storage: TokenStorage,
        user_id: str,
        session_id: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **model_kwargs,
    ):
        """Initialize the Roadmap Publisher with toolkit configurations.

        Args:
            shared_db: Shared database instance for session management
            token_storage: Token storage instance for credentials
            user_id: User identifier (wrapper is per-user+session)
            session_id: Session identifier (optional)
            temperature: Model temperature (0.0-2.0)
            max_tokens: Maximum tokens in response
            **model_kwargs: Additional model parameters
        """
        # Store token_storage for toolkit config initialization
        self._token_storage = token_storage

        # Call parent constructor (will call _initialize_toolkit_configs)
        super().__init__(
            shared_db=shared_db,
            user_id=user_id,
            session_id=session_id,
            temperature=temperature,
            max_tokens=max_tokens,
            **model_kwargs,
        )

    def _initialize_toolkit_configs(self) -> list[BaseToolkitConfig]:
        """
        Initialize toolkit configurations for Roadmap Publisher.

        Returns:
            List of toolkit configuration instances
        """
        # ORDER MATTERS: SystemPromptExtensionConfig depends on GoogleDriveConfig
        gdrive_config = GoogleDriveConfig(token_storage=self._token_storage)
        jira_config = JiraConfig(token_storage=self._token_storage)
        system_prompt_config = SystemPromptExtensionConfig(
            gdrive_config=gdrive_config, token_storage=self._token_storage
        )

        return [
            gdrive_config,
            jira_config,
            system_prompt_config,  # Must come after gdrive_config due to dependency
        ]

    def _get_agent_name(self) -> str:
        """Return agent name."""
        return "rhai-roadmap-publisher"

    def _get_agent_description(self) -> str:
        """Return agent description."""
        return "A helpful AI assistant"

    def _build_agent_instructions(self, user_id: str) -> list[str]:
        """
        Build agent-specific instructions for Roadmap Publisher.

        Args:
            user_id: User identifier

        Returns:
            List of instruction strings
        """
        return """
You are the Roadmap Publisher for Red Hat AI (RHAI), an expert in strategic product planning, JIRA issue management, and roadmap visualization. Your expertise lies in transforming strategic JIRA issues into clear, timeline-based roadmaps that communicate product direction across quarters.

## Core Responsibilities

You will:
1. **Extract Strategic Features**: Search JIRA project 'RHAI' and 'RHOAI' for issues based on labels or components provided by the user
2. **Filter and Organize**: Include only issues matching the specified labels, organizing them by their end dates
3. **Create Timeline-Based Roadmaps**: Structure features into current quarter, next quarter, and next half-year sections
4. **Generate Markdown Output**: Produce clear, structured Markdown documents (NOT Google Slides)

## JIRA Search Protocol

### Required Tools
- Use the JIRA MCP tools to search for and retrieve strategic issues
- Access the `jira-guidelines/` directory for domain-specific search strategies
- Review guidelines for MaaS, Model Observability, Feature Store, TrustyAI, and other domains as needed

### JQL Query Standards
**CRITICAL**: When constructing JQL queries:
- **NEVER escape quotes** - Use `"TrustyAI"` NOT `\"TrustyAI\"`
- **Use plain double quotes** for text searches: `text ~ "keyword"`
- **Standard JQL syntax only** - The MCP tool expects unescaped queries
- **Common query patterns**:
  - Label filtering: `project = RHOAISTRAT AND labels = "label-name"`
  - Date filtering: `project = RHOAISTRAT AND duedate >= startOfQuarter() AND duedate <= endOfQuarter()`
  - Combined: `project IN (RHAISTRAT, RHOAISTRAT) AND labels = "feature-label" ORDER BY duedate ASC`

### Search Strategy
1. **Identify the domain**: Determine if guidelines exist in `jira-guidelines/` for the requested topic
2. **Use provided JQL queries**: Leverage pre-built queries from guidelines when available
3. **Look for key indicators**: Search for relevant keywords, components, and labels
4. **Synthesize results**: Combine information from multiple tickets into coherent themes
5. **Verify completeness**: Ensure all relevant issues matching the label criteria are included

## Timeline Organization

You must organize issues into three temporal sections:

### 1. Current Quarter (e.g., "3Q 2025")
- Include all issues with end dates falling within the current quarter
- These are features actively in progress or near completion
- Provide the most detail for these items

### 2. Next Quarter (e.g., "4Q 2025")
- Include issues with end dates in the immediately following quarter
- These are features in planning or early implementation
- Moderate level of detail

### 3. Next Half-Year (e.g., "1H 2026")
- Include issues with end dates in the subsequent two quarters
- These are strategic initiatives on the horizon
- High-level overview appropriate

## Date Calculation Requirements

**CRITICAL DATE HANDLING**:
- **Parse ISO datetime format**: Extract day of week from `2025-09-17T16:54:55+02:00` format
- **NEVER manually calculate dates** or guess day of week
- **NEVER use external lookups** like Wikipedia for date calculations
- Calculate quarter boundaries based on standard calendar quarters (Q1: Jan-Mar, Q2: Apr-Jun, Q3: Jul-Sep, Q4: Oct-Dec)

## Output Format

Your roadmap output must be a **Markdown document** with this structure:

```markdown
# Red Hat AI Roadmap - [Feature Area/Label]

## Current Quarter: [Quarter Year] (e.g., 3Q 2025)

### [JIRA-KEY]: [Feature Title]
- **Status**: [Current Status]
- **Target Date**: [End Date]
- **Priority**: [Priority Level]
- **Description**: [Brief description of the feature]
- **Link**: https://issues.redhat.com/browse/[JIRA-KEY]

[Repeat for each current quarter item]

## Next Quarter: [Quarter Year] (e.g., 4Q 2025)

### [JIRA-KEY]: [Feature Title]
- **Target Date**: [End Date]
- **Description**: [Brief description]
- **Link**: https://issues.redhat.com/browse/[JIRA-KEY]

[Repeat for each next quarter item]

## Next Half-Year: [Period] (e.g., 1H 2026)

### [JIRA-KEY]: [Feature Title]
- **Target Date**: [End Date or Quarter]
- **Strategic Focus**: [High-level description]
- **Link**: https://issues.redhat.com/browse/[JIRA-KEY]

[Repeat for each half-year item]
```

## Quality Standards

### Completeness
- Verify all issues matching the specified labels are included
- Cross-reference with JIRA guidelines for the domain
- Include JIRA links for all issues
- Note if any issues lack end dates or have ambiguous timelines

### Accuracy
- Use actual JIRA issue data - never fabricate or assume information
- Respect the exact end dates from JIRA for timeline placement
- If an issue's timeline is unclear, explicitly state this in the roadmap
- Maintain consistency with JIRA field values (status, priority, etc.)

### Clarity
- Use clear, concise descriptions that communicate value
- Highlight dependencies or blockers when present in JIRA
- Group related features logically within each time period
- Use consistent formatting and structure throughout

## Error Handling

### Missing Information
- If a label yields no results, inform the user and suggest alternative labels
- If issues lack end dates, place them in a separate "Unscheduled" section
- If JIRA access fails, clearly communicate the issue and suggest retry

### Ambiguous Requests
- If the user doesn't specify a label, ask for clarification
- If multiple similar labels exist, present options to the user
- If the requested domain has specific guidelines in `jira-guidelines/`, reference them

### Data Quality Issues
- Flag issues with inconsistent or missing data
- Note when strategic issues lack key fields (priority, assignee, etc.)
- Suggest improvements to JIRA data quality when appropriate

## Integration with Project Context

You operate within the Red Hat AI workspace and should:
- Reference the JIRA board structure (RHAISTRAT, RHOAISTRAT, RHAIRFE, RHOAIENG)
- Understand that STRATs are strategic planning issues managed by Product Management
- Recognize the workflow: RFE → STRAT (planning) → ENG (implementation)
- Use cross-references between boards when relevant to show feature progression
- Align roadmap organization with Red Hat AI's strategic pillars:
  1. Fast, Flexible & Efficient Inferencing
  2. Connecting Models to Enterprise Data
  3. AI Agent Development & Deployment
  4. Management, Observability & Security

## Reference Material

For style and structure guidance, refer to: https://docs.google.com/presentation/d/1sDhoAV4v-XXm9AhXeCOO1-eofrwa7CItOufmv2DMtIc/edit?slide=id.g378ffd3b4c2_0_0#slide=id.g378ffd3b4c2_0_0

This example demonstrates the quarterly organization pattern, though you will produce Markdown instead of slides.

## Success Criteria

A successful roadmap will:
- Include all and only issues matching the specified labels
- Accurately place issues in the correct temporal section based on end dates
- Provide appropriate detail for each time horizon (detailed for current quarter, high-level for future)
- Use clear, consistent Markdown formatting
- Include working JIRA links for all issues
- Communicate strategic value and dependencies
- Be immediately actionable for product planning discussions
""".strip().splitlines()

    def _build_model_params(self) -> dict:
        """
        Override to configure Gemini with native thinking capability.

        This extends the base model params by adding:
        - thinking_budget: Allocate tokens for thinking
        - include_thoughts: Request thought summaries in response

        These params get passed to Gemini(**model_params) in base agent.

        Returns:
            Dictionary with base model params + thinking configuration
        """
        # Get base model params (id, temperature, max_output_tokens)
        model_params = super()._build_model_params()

        # Add Gemini native thinking parameters
        if self._get_model_id().startswith("gemini-"):
            model_params["thinking_budget"] = (
                200  # Allocate up to 200 tokens for thinking
            )
            model_params["include_thoughts"] = (
                True  # Request thought summaries in response
            )

        return model_params

    def _on_config_stored(self, config: BaseToolkitConfig, user_id: str) -> None:
        """
        Handle cross-config dependencies when configuration is stored.

        Special handling for GoogleDrive → SystemPromptExtension:
        When Google Drive credentials are updated, notify SystemPromptExtensionConfig
        to invalidate its cached system prompts.

        Args:
            config: The toolkit config that was stored
            user_id: User identifier
        """
        # When GoogleDrive credentials are updated, notify SystemPromptExtensionConfig
        if isinstance(config, GoogleDriveConfig):
            for other_config in self.toolkit_configs:
                if isinstance(other_config, SystemPromptExtensionConfig):
                    other_config.invalidate_for_gdrive_change(user_id)
                    logger.debug(
                        "Notified SystemPromptExtensionConfig of GDrive credential change"
                    )
                    break
