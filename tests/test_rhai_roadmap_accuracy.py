"""Accuracy evaluation tests for RHAI Roadmap Publisher agent.

This module uses Agno's AccuracyEval framework with Anthropic Claude Haiku
as the LLM-as-judge evaluator to measure agent performance across multiple aspects:
- Completeness: All matching issues included in the roadmap
- Accuracy: Issues placed in correct timeline sections
- Structure: Proper markdown formatting
- Content: Correct issue metadata and descriptions

Each test scenario can run independently and requires ANTHROPIC_API_KEY.
"""

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from agno.agent import Agent
from agno.db.sqlite import SqliteDb
from agno.models.anthropic import Claude
from pydantic import BaseModel, Field

from agentllm.db import TokenStorage
from tests.fixtures.rhai_jira_synthetic_data import (
    SCENARIO_BASIC,
    JiraSyntheticIssue,
)

# =============================================================================
# Response Models
# =============================================================================


class RoadmapEvaluationResponse(BaseModel):
    """Response model for roadmap evaluation with 0-100 scoring."""

    accuracy_score: int = Field(
        ...,
        ge=0,
        le=100,
        description="Accuracy score between 0 and 100",
    )
    accuracy_reason: str = Field(
        ...,
        description="Detailed reasoning for the score",
    )


# =============================================================================
# Pytest Fixtures
# =============================================================================


@pytest.fixture(scope="module")
def anthropic_api_key():
    """Check for ANTHROPIC_API_KEY and skip if not available."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY environment variable not set")
    return api_key


@pytest.fixture(scope="module")
def evaluator_model(anthropic_api_key):
    """Claude Haiku model for LLM-as-judge evaluation.

    Uses Haiku for cost-effectiveness and speed.
    Temperature=0 for deterministic scoring.
    """
    return Claude(
        id="claude-3-5-haiku-20241022",
        api_key=anthropic_api_key,
        temperature=0,  # Deterministic scoring
    )


@pytest.fixture
def shared_db():
    """Provide a shared test database for agent sessions."""
    db_path = Path("tmp/test_rhai_roadmap_accuracy.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Remove existing db for clean state
    if db_path.exists():
        db_path.unlink()

    db = SqliteDb(db_file=str(db_path))
    yield db

    # Cleanup after tests
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def token_storage(shared_db):
    """Provide token storage for agent credentials."""
    return TokenStorage(agno_db=shared_db)


@pytest.fixture
def mock_jira_search():
    """Factory fixture for creating JIRA search mocks with scenario data.

    Returns a function that creates a mock search function for a scenario.
    """

    def create_search_mock(scenario_issues: list[JiraSyntheticIssue]):
        """Create a mock search function that returns synthetic issues.

        Args:
            scenario_issues: List of JiraSyntheticIssue to return

        Returns:
            Mock function that returns list of mock JIRA Issue objects
        """

        def mock_search(jql: str, **kwargs):
            """Mock JIRA search_issues method."""
            # Convert synthetic issues to mock JIRA Issue objects
            mock_issues = []
            for synthetic_issue in scenario_issues:
                mock_issue = MagicMock()
                mock_issue.key = synthetic_issue.key
                mock_issue.fields.summary = synthetic_issue.summary
                mock_issue.fields.description = synthetic_issue.description

                # Status
                mock_status = MagicMock()
                mock_status.name = synthetic_issue.status
                mock_issue.fields.status = mock_status

                # Priority
                mock_priority = MagicMock()
                mock_priority.name = synthetic_issue.priority
                mock_issue.fields.priority = mock_priority

                # Assignee
                if synthetic_issue.assignee:
                    mock_assignee = MagicMock()
                    mock_assignee.displayName = synthetic_issue.assignee
                    mock_issue.fields.assignee = mock_assignee
                else:
                    mock_issue.fields.assignee = None

                # Reporter
                if synthetic_issue.reporter:
                    mock_reporter = MagicMock()
                    mock_reporter.displayName = synthetic_issue.reporter
                    mock_issue.fields.reporter = mock_reporter
                else:
                    mock_issue.fields.reporter = None

                # Dates
                mock_issue.fields.created = synthetic_issue.created_date
                mock_issue.fields.updated = synthetic_issue.updated_date
                mock_issue.fields.duedate = synthetic_issue.due_date

                # Components
                mock_components = []
                for comp_name in synthetic_issue.components:
                    mock_comp = MagicMock()
                    mock_comp.name = comp_name
                    mock_components.append(mock_comp)
                mock_issue.fields.components = mock_components

                # Labels
                mock_issue.fields.labels = synthetic_issue.labels

                # Target version (custom field)
                if synthetic_issue.target_version:
                    mock_issue.fields.customfield_12311240 = synthetic_issue.target_version
                else:
                    mock_issue.fields.customfield_12311240 = None

                # Product manager (custom field)
                if synthetic_issue.product_manager:
                    mock_pm = MagicMock()
                    mock_pm.displayName = synthetic_issue.product_manager
                    mock_issue.fields.customfield_12315948 = mock_pm
                else:
                    mock_issue.fields.customfield_12315948 = None

                mock_issues.append(mock_issue)

            return mock_issues

        return mock_search

    return create_search_mock


@pytest.fixture
def mock_gdrive_credentials():
    """Mock Google Drive credentials for agent initialization."""
    mock_creds = MagicMock()
    mock_creds.valid = True
    return mock_creds


@pytest.fixture(scope="module")
def gemini_api_key():
    """Check for GEMINI_API_KEY and skip if not available."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        pytest.skip("GEMINI_API_KEY environment variable not set")
    return api_key


@pytest.fixture
def rhai_agent(shared_db, token_storage, gemini_api_key):
    """Create RHAIRoadmapPublisher agent for testing.

    This agent will have mocked JIRA toolkit to return synthetic data.
    """
    from agentllm.agents.rhai_roadmap_publisher import RHAIRoadmapPublisher

    # Create agent with test user
    agent = RHAIRoadmapPublisher(
        shared_db=shared_db,
        token_storage=token_storage,
        user_id="eval-test-user",
        session_id="eval-test-session",
        temperature=0.7,
        max_tokens=4000,
    )

    return agent


# =============================================================================
# Evaluator Agent Fixtures (One per aspect)
# =============================================================================


@pytest.fixture(scope="module")
def evaluator_agent_completeness(evaluator_model):
    """Evaluator agent for completeness scoring."""
    instructions = [
        "You are evaluating the completeness of a RHAI roadmap document.",
        "",
        "Your task is to compare the agent's generated roadmap to the expected roadmap and score how completely all issues are included.",
        "",
        "Scoring Criteria (0-100):",
        "- 100: All expected JIRA issues present with correct keys and summaries",
        "- 90-99: 1 issue missing or 1 extra issue present",
        "- 80-89: 2-3 issues missing/extra",
        "- 70-79: 4-5 issues missing/extra",
        "- Below 70: More than 5 issues missing/extra",
        "",
        "Important:",
        "- Check JIRA issue keys (e.g., SYNTHETIC-001)",
        "- Verify issue summaries match",
        "- Ignore formatting differences (focus on content)",
        "- Minor description variations are acceptable",
        "",
        "Provide your score (0-100) and detailed reasoning.",
    ]

    return Agent(
        model=evaluator_model,
        instructions=instructions,
        output_schema=RoadmapEvaluationResponse,
        structured_outputs=True,
    )


@pytest.fixture(scope="module")
def evaluator_agent_accuracy(evaluator_model):
    """Evaluator agent for timeline accuracy scoring."""
    instructions = [
        "You are evaluating the timeline accuracy of a RHAI roadmap document.",
        "",
        "Your task is to verify that JIRA issues are placed in the correct time period sections.",
        "",
        "Timeline Rules:",
        "- Current Quarter: Issues with end date falling in the current quarter",
        "- Next Quarter: Issues with end date in the next quarter",
        "- Next Half-Year: Issues with end date 2+ quarters out, OR no end date, OR status 'New'",
        "",
        "Scoring Criteria (0-100):",
        "- 100: All issues in correct sections",
        "- 95-99: 1 issue misplaced",
        "- 85-94: 2 issues misplaced",
        "- 70-84: 3-4 issues misplaced",
        "- Below 70: 5+ issues misplaced",
        "",
        "Provide your score (0-100) and detailed reasoning.",
    ]

    return Agent(
        model=evaluator_model,
        instructions=instructions,
        output_schema=RoadmapEvaluationResponse,
        structured_outputs=True,
    )


@pytest.fixture(scope="module")
def evaluator_agent_structure(evaluator_model):
    """Evaluator agent for markdown structure scoring."""
    instructions = [
        "You are evaluating the markdown structure of a RHAI roadmap document.",
        "",
        "Your task is to verify proper formatting according to the template.",
        "",
        "Required Structure:",
        "1. H1 Title: '# Red Hat AI Roadmap - [Label]'",
        "2. H2 Section: '## Releases' (with release info)",
        "3. H2 Section: '## Current Quarter: [Quarter Year]'",
        "4. H2 Section: '## Next Quarter: [Quarter Year]'",
        "5. H2 Section: '## Next Half-Year: [Period]'",
        "6. H3 Subsections: '### [JIRA-KEY]: [Title]' for each issue",
        "7. Bullet points: '- **Field**: Value' format",
        "8. Links: 'https://issues.redhat.com/browse/[KEY]'",
        "",
        "Scoring Criteria (0-100):",
        "- 100: Perfect structure, all sections present, consistent formatting",
        "- 90-99: Minor formatting inconsistencies (spacing, bullet alignment)",
        "- 80-89: 1-2 sections have structural issues",
        "- 70-79: 3-4 sections have structural issues",
        "- Below 70: Major structural problems",
        "",
        "Provide your score (0-100) and detailed reasoning.",
    ]

    return Agent(
        model=evaluator_model,
        instructions=instructions,
        output_schema=RoadmapEvaluationResponse,
        structured_outputs=True,
    )


@pytest.fixture(scope="module")
def evaluator_agent_content(evaluator_model):
    """Evaluator agent for content accuracy scoring."""
    instructions = [
        "You are evaluating the content accuracy of a RHAI roadmap document.",
        "",
        "Your task is to verify that issue metadata and descriptions are correct.",
        "",
        "Check Each Issue For:",
        "- Status matches JIRA data",
        "- Target Version matches JIRA data (if present)",
        "- Description captures key points from JIRA description",
        "- JIRA key is correct",
        "- No fabricated or hallucinated information",
        "",
        "Scoring Criteria (0-100):",
        "- 100: All metadata accurate, descriptions faithful to JIRA",
        "- 90-99: 1-2 minor metadata errors or description omissions",
        "- 80-89: 3-4 metadata errors or inaccurate descriptions",
        "- 70-79: 5-6 metadata errors or significant description problems",
        "- Below 70: Widespread inaccuracies or fabrication",
        "",
        "Provide your score (0-100) and detailed reasoning.",
    ]

    return Agent(
        model=evaluator_model,
        instructions=instructions,
        output_schema=RoadmapEvaluationResponse,
        structured_outputs=True,
    )


# =============================================================================
# Helper Functions
# =============================================================================


def run_accuracy_evaluation(
    agent_output: str,
    expected_output: str,
    evaluator_agent: Agent,
    eval_name: str,
    aspect: str,
) -> float:
    """Run accuracy evaluation and return score.

    Args:
        agent_output: Generated roadmap from RHAI agent
        expected_output: Expected roadmap output
        evaluator_agent: Evaluator agent for this aspect
        eval_name: Name for the evaluation run
        aspect: Aspect being evaluated (for logging)

    Returns:
        Score from 0-100

    Raises:
        AssertionError: If score is below 95.0
    """
    # Construct evaluation prompt
    evaluation_prompt = f"""
Compare the following two roadmaps for {aspect}.

**Expected Roadmap:**
{expected_output}

**Agent-Generated Roadmap:**
{agent_output}

Evaluate the agent-generated roadmap according to the scoring criteria in your instructions.
"""

    # Run evaluator agent
    result = evaluator_agent.run(evaluation_prompt)

    # Extract score from structured output
    if not result.content or not isinstance(result.content, RoadmapEvaluationResponse):
        raise ValueError(f"Evaluator returned invalid response: {result.content}")

    score = result.content.accuracy_score
    reason = result.content.accuracy_reason

    print(f"\n{'=' * 70}")
    print(f"Evaluation: {eval_name}")
    print(f"Aspect: {aspect}")
    print(f"Score: {score}/100")
    print(f"Reason: {reason[:200]}...")
    print(f"{'=' * 70}\n")

    return float(score)


# =============================================================================
# Phase 2 Tests: Framework Validation
# =============================================================================


@pytest.mark.integration
class TestEvaluationFrameworkSetup:
    """Test that evaluation framework is correctly set up."""

    def test_anthropic_api_key_available(self, anthropic_api_key):
        """Verify ANTHROPIC_API_KEY is available."""
        assert anthropic_api_key is not None
        assert len(anthropic_api_key) > 0

    def test_evaluator_model_instantiation(self, evaluator_model):
        """Verify evaluator model can be instantiated."""
        assert evaluator_model is not None
        assert evaluator_model.id == "claude-3-5-haiku-20241022"
        assert evaluator_model.temperature == 0

    def test_evaluator_agents_created(
        self,
        evaluator_agent_completeness,
        evaluator_agent_accuracy,
        evaluator_agent_structure,
        evaluator_agent_content,
    ):
        """Verify all evaluator agents are created."""
        assert evaluator_agent_completeness is not None
        assert evaluator_agent_accuracy is not None
        assert evaluator_agent_structure is not None
        assert evaluator_agent_content is not None

    def test_mock_jira_search_fixture(self, mock_jira_search):
        """Test that JIRA search mock works."""
        # Create a search mock with SCENARIO_BASIC issues
        search_fn = mock_jira_search(SCENARIO_BASIC.issues)

        # Call the mock
        results = search_fn('project = "TEST"')

        # Verify results
        assert len(results) == 7
        assert results[0].key == "SYNTHETIC-001"
        assert results[0].fields.summary == SCENARIO_BASIC.issues[0].summary


# =============================================================================
# Phase 3 Tests: Basic Scenario Evaluations
# =============================================================================


@pytest.mark.integration
class TestCompletenessEvaluation:
    """Test completeness aspect: all issues included in roadmap."""

    def test_basic_scenario_completeness_with_expected_output(
        self,
        evaluator_agent_completeness,
    ):
        """Test completeness evaluation using expected output directly.

        This test validates the evaluation framework by comparing
        the expected output to itself (should score 100).
        """
        # Use expected output as both agent output and expected
        # This should score 100% since they're identical
        agent_output = SCENARIO_BASIC.expected_output
        expected_output = SCENARIO_BASIC.expected_output

        score = run_accuracy_evaluation(
            agent_output=agent_output,
            expected_output=expected_output,
            evaluator_agent=evaluator_agent_completeness,
            eval_name="rhai_roadmap_completeness_framework_test",
            aspect="completeness (framework validation)",
        )

        # Score should be 100 for identical outputs
        assert score >= 95.0, f"Completeness score {score} below threshold 95.0 (expected 100 for identical outputs)"

    def test_basic_scenario_completeness_with_agent(
        self,
        rhai_agent,
        evaluator_agent_completeness,
        mock_jira_search,
    ):
        """Test completeness evaluation with actual agent execution.

        This test runs the RHAIRoadmapPublisher agent with mocked JIRA data
        and evaluates the completeness of its generated roadmap.
        """
        from unittest.mock import patch

        # Create mock JIRA client
        mock_search_fn = mock_jira_search(SCENARIO_BASIC.issues)
        mock_jira_client = MagicMock()
        mock_jira_client.search_issues = mock_search_fn

        # Mock Google Drive credentials (required for agent initialization)
        with patch("agentllm.agents.toolkit_configs.gdrive_config.get_gdrive_credentials") as mock_gdrive:
            mock_creds = MagicMock()
            mock_creds.valid = True
            mock_gdrive.return_value = mock_creds

            # Mock JIRA client initialization
            with patch("agentllm.tools.jira_toolkit.JIRA", return_value=mock_jira_client):
                # Run agent with user message
                user_message = f"Create a roadmap for label '{SCENARIO_BASIC.labels[0]}'"

                # Execute agent
                result = rhai_agent.run(user_message)

                # Extract agent output
                agent_output = str(result.content) if hasattr(result, "content") else str(result)

                # Run evaluation
                score = run_accuracy_evaluation(
                    agent_output=agent_output,
                    expected_output=SCENARIO_BASIC.expected_output,
                    evaluator_agent=evaluator_agent_completeness,
                    eval_name="rhai_roadmap_completeness_basic_with_agent",
                    aspect="completeness (agent execution)",
                )

                # Assert score threshold
                assert score >= 95.0, f"Completeness score {score} below threshold 95.0"


@pytest.mark.integration
class TestAccuracyEvaluation:
    """Test accuracy aspect: issues placed in correct timeline sections."""

    def test_basic_scenario_accuracy_with_agent(
        self,
        rhai_agent,
        evaluator_agent_accuracy,
        mock_jira_search,
    ):
        """Test timeline accuracy evaluation with actual agent execution."""
        from unittest.mock import patch

        # Create mock JIRA client
        mock_search_fn = mock_jira_search(SCENARIO_BASIC.issues)
        mock_jira_client = MagicMock()
        mock_jira_client.search_issues = mock_search_fn

        # Mock Google Drive credentials
        with patch("agentllm.agents.toolkit_configs.gdrive_config.get_gdrive_credentials") as mock_gdrive:
            mock_creds = MagicMock()
            mock_creds.valid = True
            mock_gdrive.return_value = mock_creds

            # Mock JIRA client initialization
            with patch("agentllm.tools.jira_toolkit.JIRA", return_value=mock_jira_client):
                # Run agent
                user_message = f"Create a roadmap for label '{SCENARIO_BASIC.labels[0]}'"
                result = rhai_agent.run(user_message)

                # Extract agent output
                agent_output = str(result.content) if hasattr(result, "content") else str(result)

                # Run evaluation
                score = run_accuracy_evaluation(
                    agent_output=agent_output,
                    expected_output=SCENARIO_BASIC.expected_output,
                    evaluator_agent=evaluator_agent_accuracy,
                    eval_name="rhai_roadmap_accuracy_basic_with_agent",
                    aspect="timeline accuracy (agent execution)",
                )

                # Assert score threshold
                assert score >= 95.0, f"Accuracy score {score} below threshold 95.0"


@pytest.mark.integration
class TestStructureEvaluation:
    """Test structure aspect: proper markdown formatting."""

    def test_basic_scenario_structure_with_agent(
        self,
        rhai_agent,
        evaluator_agent_structure,
        mock_jira_search,
    ):
        """Test markdown structure evaluation with actual agent execution."""
        from unittest.mock import patch

        # Create mock JIRA client
        mock_search_fn = mock_jira_search(SCENARIO_BASIC.issues)
        mock_jira_client = MagicMock()
        mock_jira_client.search_issues = mock_search_fn

        # Mock Google Drive credentials
        with patch("agentllm.agents.toolkit_configs.gdrive_config.get_gdrive_credentials") as mock_gdrive:
            mock_creds = MagicMock()
            mock_creds.valid = True
            mock_gdrive.return_value = mock_creds

            # Mock JIRA client initialization
            with patch("agentllm.tools.jira_toolkit.JIRA", return_value=mock_jira_client):
                # Run agent
                user_message = f"Create a roadmap for label '{SCENARIO_BASIC.labels[0]}'"
                result = rhai_agent.run(user_message)

                # Extract agent output
                agent_output = str(result.content) if hasattr(result, "content") else str(result)

                # Run evaluation
                score = run_accuracy_evaluation(
                    agent_output=agent_output,
                    expected_output=SCENARIO_BASIC.expected_output,
                    evaluator_agent=evaluator_agent_structure,
                    eval_name="rhai_roadmap_structure_basic_with_agent",
                    aspect="markdown structure (agent execution)",
                )

                # Assert score threshold
                assert score >= 95.0, f"Structure score {score} below threshold 95.0"


@pytest.mark.integration
class TestContentEvaluation:
    """Test content aspect: correct issue metadata and descriptions."""

    def test_basic_scenario_content_with_agent(
        self,
        rhai_agent,
        evaluator_agent_content,
        mock_jira_search,
    ):
        """Test content accuracy evaluation with actual agent execution."""
        from unittest.mock import patch

        # Create mock JIRA client
        mock_search_fn = mock_jira_search(SCENARIO_BASIC.issues)
        mock_jira_client = MagicMock()
        mock_jira_client.search_issues = mock_search_fn

        # Mock Google Drive credentials
        with patch("agentllm.agents.toolkit_configs.gdrive_config.get_gdrive_credentials") as mock_gdrive:
            mock_creds = MagicMock()
            mock_creds.valid = True
            mock_gdrive.return_value = mock_creds

            # Mock JIRA client initialization
            with patch("agentllm.tools.jira_toolkit.JIRA", return_value=mock_jira_client):
                # Run agent
                user_message = f"Create a roadmap for label '{SCENARIO_BASIC.labels[0]}'"
                result = rhai_agent.run(user_message)

                # Extract agent output
                agent_output = str(result.content) if hasattr(result, "content") else str(result)

                # Run evaluation
                score = run_accuracy_evaluation(
                    agent_output=agent_output,
                    expected_output=SCENARIO_BASIC.expected_output,
                    evaluator_agent=evaluator_agent_content,
                    eval_name="rhai_roadmap_content_basic_with_agent",
                    aspect="content accuracy (agent execution)",
                )

                # Assert score threshold
                assert score >= 95.0, f"Content score {score} below threshold 95.0"
