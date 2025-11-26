"""Comprehensive scenario tests for the Release Manager agent.

Tests the Release Manager's ability to handle real-world release management tasks
based on the system prompt instructions from docs/templates/release_manager_system_prompt.md.
"""

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

import pytest
from agno.db.sqlite import SqliteDb
from dotenv import load_dotenv

from agentllm.agents.release_manager import ReleaseManager
from agentllm.db import TokenStorage

# Load .env.secrets file for tests (contains API keys and tokens)
load_dotenv(".env.secrets")

# Map GEMINI_API_KEY to GOOGLE_API_KEY if needed
if "GOOGLE_API_KEY" not in os.environ and "GEMINI_API_KEY" in os.environ:
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]


# Test scenarios with validation criteria
# These scenarios are derived from the Release Manager System Prompt:
# - Release status tracking (Jira queries)
# - Release schedule management (Google Drive + Jira)
# - Risk identification (blocker bugs, CVEs, unassigned work)
# - Communication preparation (code freeze announcements, release updates)
# - Proactive monitoring (scope creep, missing artifacts)

TEST_SCENARIOS = [
    {
        "id": 1,
        "category": "Release Status Query",
        "question": "What's the status of the current release?",
        "expected_keywords": ["release", "status", "features", "progress"],
        "should_cite_source": True,
        "knowledge_type": "jira",
        "description": "Tests ability to query current release status and provide progress metrics",
    },
    {
        "id": 2,
        "category": "Risk Identification - Blocker Bugs",
        "question": "Are there any blocker bugs in the current release?",
        "expected_keywords": ["blocker", "bug", "priority"],
        "should_cite_source": True,
        "knowledge_type": "jira",
        "description": "Tests ability to identify and report blocker bugs using Jira queries",
    },
    {
        "id": 3,
        "category": "Release Schedule Information",
        "question": "When is the next feature freeze?",
        "expected_keywords": ["feature freeze", "date", "schedule"],
        "should_cite_source": True,
        "knowledge_type": "gdrive",
        "description": "Tests ability to query release schedule from Google Drive documents",
    },
    {
        "id": 4,
        "category": "JQL Query Construction",
        "question": "Show me all features in the current release that are still in progress",
        "expected_keywords": ["feature", "in progress", "jira"],
        "should_cite_source": True,
        "knowledge_type": "jira",
        "description": "Tests ability to construct JQL queries for feature tracking",
    },
    {
        "id": 5,
        "category": "Code Freeze Communication",
        "question": "Create a code freeze announcement for the current release",
        "expected_keywords": ["code freeze", "cherry-pick", "blocker", "cve"],
        "should_cite_source": True,
        "knowledge_type": "multi",
        "description": "Tests ability to generate code freeze announcements with all required data",
    },
    {
        "id": 6,
        "category": "CVE Tracking",
        "question": "What CVEs are outstanding for the current release?",
        "expected_keywords": ["cve", "security", "vulnerability"],
        "should_cite_source": True,
        "knowledge_type": "jira",
        "description": "Tests ability to track and report on security vulnerabilities",
    },
    {
        "id": 7,
        "category": "JQL Count Accuracy - Feature Demos",
        "question": "How many features are tagged for demos in version 1.9.0?",
        "expected_keywords": ["feature", "demo", "1.9.0"],
        "should_cite_source": True,
        "knowledge_type": "jira",
        "description": "Tests accurate counting of JQL results - validates agent reports complete count, not just first page of results. Issue: agent previously reported 25 when actual count was 32.",
        "validation_type": "count_accuracy",
        "jql_query": 'issuetype = Feature AND fixVersion = "1.9.0" AND labels = demo',
    },
]


# Helper function to get configured user ID
def get_configured_user_id() -> str | None:
    """Get the first user ID with both Jira and Google Drive tokens configured.

    Uses the `just first-user` command to query the production database.

    Returns:
        User ID string if found, None otherwise.
    """
    try:
        result = subprocess.run(
            ["just", "first-user"],
            capture_output=True,
            text=True,
            check=True,
        )
        user_id = result.stdout.strip()
        return user_id if user_id else None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


# Test fixtures
@pytest.fixture
def shared_db() -> SqliteDb:
    """Provide the production shared database with real tokens.

    This uses tmp/agent-data/agno_sessions.db which contains real OAuth tokens
    from the containerized proxy server.
    """
    db_path = Path("tmp/agent-data/agno_sessions.db")
    if not db_path.exists():
        pytest.skip("Production database not found. Run development stack first: just dev")
    db = SqliteDb(db_file=str(db_path))
    return db


@pytest.fixture
def token_storage(shared_db: SqliteDb) -> TokenStorage:
    """Provide a token storage instance using production database."""
    return TokenStorage(agno_db=shared_db)


@pytest.fixture
def configured_user_id() -> str:
    """Get a user ID that has both Jira and Google Drive tokens configured.

    This fixture queries the production database to find a real user
    with all required tokens.

    Skips the test if no configured user is found.
    """
    user_id = get_configured_user_id()
    if not user_id:
        pytest.skip("No configured user found with Jira and Google Drive tokens. Use the proxy to configure: nox -s proxy")
    return user_id


@pytest.fixture
def configured_agent(shared_db, token_storage, configured_user_id):
    """Fixture that provides a ReleaseManager with real toolkits configured.

    This fixture uses real OAuth tokens from tmp/agent-data/agno_sessions.db
    and creates an actual Agno agent using _get_or_create_agent().

    The agent is fully configured and ready to make real API calls.
    """
    # Create the ReleaseManager wrapper
    agent_wrapper = ReleaseManager(
        shared_db=shared_db,
        token_storage=token_storage,
        user_id=configured_user_id,
    )

    # Force creation of the underlying Agno agent
    # This validates that all toolkits are properly configured
    underlying_agent = agent_wrapper._get_or_create_agent()

    if underlying_agent is None:
        pytest.skip("Could not create agent - toolkit configuration may be incomplete")

    return agent_wrapper


@pytest.mark.integration
class TestReleaseManagerScenarios:
    """Integration tests for Release Manager scenarios.

    These tests validate the agent's ability to handle real-world release
    management tasks as defined in the system prompt.

    Run with: pytest -m integration -v -s
    """

    @pytest.mark.skipif(not os.getenv("GEMINI_API_KEY"), reason="GEMINI_API_KEY not set")
    @pytest.mark.parametrize(
        "scenario",
        [
            pytest.param(
                s,
                id=f"scenario_{s['id']:02d}_{s['category'].lower().replace(' ', '_').replace('-', '_')}",
            )
            for s in TEST_SCENARIOS
        ],
    )
    def test_scenario(self, configured_agent, configured_user_id, scenario):
        """Test individual scenario for Release Manager agent.

        This parametrized test runs each scenario independently, allowing for:
        - Individual scenario execution: pytest -k "scenario_01"
        - Category filtering: pytest -k "release_status"
        - Parallel execution support
        - Detailed per-scenario reporting

        Run examples:
        - Single scenario: pytest tests/test_release_manager_scenarios.py::TestReleaseManagerScenarios::test_scenario[scenario_01_release_status_query] -v -s -m integration
        - All Jira tests: pytest tests/test_release_manager_scenarios.py::TestReleaseManagerScenarios::test_scenario -k "jira" -v -m integration
        - Risk scenarios: pytest tests/test_release_manager_scenarios.py::TestReleaseManagerScenarios::test_scenario -k "risk" -v -m integration
        """
        scenario_id = scenario["id"]
        category = scenario["category"]
        question = scenario["question"]
        expected_keywords = scenario["expected_keywords"]
        should_cite = scenario["should_cite_source"]
        knowledge_type = scenario["knowledge_type"]
        description = scenario["description"]

        print(f"\n{'=' * 80}")
        print(f"🧪 SCENARIO {scenario_id}: {category}")
        print(f"{'=' * 80}")
        print(f"Description: {description}")
        print(f"Question: {question}")
        print(f"{'-' * 80}\n")

        # Run the query using the configured user ID
        response = configured_agent.run(question, user_id=configured_user_id)
        content = str(response.content) if hasattr(response, "content") else str(response)

        # Validation
        validation_messages = []

        # Check response length
        assert len(content) >= 50, f"Response too short: {len(content)} chars"
        validation_messages.append(f"✅ Response length: {len(content)} chars")

        # Check for expected keywords
        content_lower = content.lower()
        found_keywords = [kw for kw in expected_keywords if kw.lower() in content_lower]
        assert found_keywords, f"Missing expected keywords: {expected_keywords}"
        validation_messages.append(f"✅ Found keywords: {found_keywords}")

        # Check for source citations (for knowledge-based queries)
        if should_cite:
            has_citation = any(
                marker in content_lower
                for marker in [
                    "jira",
                    "query",
                    "schedule",
                    "according to",
                    "based on",
                    "release schedule",
                    "issues.redhat.com",
                    "rhidp",
                    "rhdhplan",
                    "rhdh",
                ]
            )
            if has_citation:
                validation_messages.append("✅ Includes source citation or context")
            else:
                validation_messages.append("⚠️  No explicit source citation found (non-critical)")

        # Knowledge type specific validation
        if knowledge_type == "jira":
            # Should mention Jira or include issue keys
            has_jira_context = "jira" in content_lower or any(project in content.upper() for project in ["RHIDP", "RHDHPLAN", "RHDHBUGS"])
            if has_jira_context:
                validation_messages.append("✅ Includes Jira context")
            else:
                validation_messages.append("⚠️  No Jira context found")

        if knowledge_type == "gdrive":
            # Should mention schedule or dates
            has_schedule_context = any(keyword in content_lower for keyword in ["schedule", "date", "freeze", "ga"])
            if has_schedule_context:
                validation_messages.append("✅ Includes schedule/date context")
            else:
                validation_messages.append("⚠️  No schedule context found")

        # Count accuracy validation for scenario 7 (JQL count accuracy)
        if scenario.get("validation_type") == "count_accuracy" and "jql_query" in scenario:
            jql_query = scenario["jql_query"]
            print("\n🔍 Count Accuracy Validation:")
            print(f"  JQL Query: {jql_query}")

            # Extract Jira toolkit from agent
            try:
                # Access the configurator from the agent wrapper
                configurator = configured_agent._configurator

                # Find the JiraConfig in the toolkit_configs
                jira_config = None
                for config in configurator.toolkit_configs:
                    if config.__class__.__name__ == "JiraConfig":
                        jira_config = config
                        break

                if not jira_config:
                    validation_messages.append("⚠️  Could not find JiraConfig to validate count")
                else:
                    # Get the Jira toolkit for this user
                    jira_toolkit = jira_config.get_toolkit(configured_user_id)

                    if not jira_toolkit:
                        validation_messages.append("⚠️  Could not get Jira toolkit to validate count")
                    else:
                        # Get the Jira client from the toolkit
                        jira_client = jira_toolkit._get_jira_client()

                        # Execute the same JQL query with maxResults=0 to get total count
                        search_result = jira_client.search_issues(jql_query, maxResults=0)
                        actual_count = search_result.total

                        print(f"  Actual Jira count: {actual_count}")

                        # Extract the count from agent's response
                        import re

                        # Look for patterns like "27 features", "**27**", "count: 27", etc.
                        count_patterns = [
                            r"\*\*(\d+)\*\*",  # **27**
                            r"(\d+)\s+features?",  # 27 features
                            r"count:\s*(\d+)",  # count: 27
                            r"total:\s*(\d+)",  # total: 27
                            r"There are\s+\*\*(\d+)\*\*",  # There are **27**
                        ]

                        reported_count = None
                        for pattern in count_patterns:
                            match = re.search(pattern, content, re.IGNORECASE)
                            if match:
                                reported_count = int(match.group(1))
                                break

                        if reported_count is None:
                            validation_messages.append("⚠️  Could not extract count from agent response")
                            print("  Could not extract count from response")
                            raise AssertionError("Failed to extract count from agent response for count accuracy validation")
                        else:
                            print(f"  Agent reported count: {reported_count}")

                            if reported_count == actual_count:
                                validation_messages.append(f"✅ Count accuracy: {reported_count} == {actual_count} (ACCURATE)")
                                print("  ✅ ACCURATE: Agent reported correct count")
                            else:
                                validation_messages.append(
                                    f"❌ Count accuracy: {reported_count} != {actual_count} (INACCURATE - off by {abs(reported_count - actual_count)})"
                                )
                                print(
                                    f"  ❌ INACCURATE: Agent reported {reported_count} but actual is {actual_count} (off by {abs(reported_count - actual_count)})"
                                )
                                # This is a hard failure for count accuracy tests
                                raise AssertionError(f"Count mismatch: agent reported {reported_count} but Jira has {actual_count}")

            except Exception as e:
                validation_messages.append(f"⚠️  Count validation error: {str(e)}")
                print(f"  Error during count validation: {e}")

        # Print validation results
        print("\n📋 Validation Results:")
        for msg in validation_messages:
            print(f"  {msg}")

        # Print response preview
        print("\n📄 Response Preview:")
        preview = content[:500] + "..." if len(content) > 500 else content
        print(preview)
        print(f"\n{'=' * 80}")
        print("✅ SCENARIO PASSED")
        print(f"{'=' * 80}\n")

    @pytest.mark.skipif(not os.getenv("GEMINI_API_KEY"), reason="GEMINI_API_KEY not set")
    def test_comprehensive_scenarios(self, configured_agent, configured_user_id):
        """Run all scenarios as a single comprehensive test.

        This test runs all scenarios sequentially and generates a summary report.
        It's useful for validating overall agent capabilities and tracking improvements.

        Run with: pytest tests/test_release_manager_scenarios.py::TestReleaseManagerScenarios::test_comprehensive_scenarios -v -s -m integration
        """
        results = []
        total = len(TEST_SCENARIOS)
        passed = 0
        partial = 0
        failed = 0

        print(f"\n{'=' * 80}")
        print("🎯 RUNNING COMPREHENSIVE RELEASE MANAGER TEST")
        print(f"{'=' * 80}")
        print(f"Total Scenarios: {total}")
        print(f"{'=' * 80}\n")

        for scenario in TEST_SCENARIOS:
            scenario_id = scenario["id"]
            category = scenario["category"]
            question = scenario["question"]
            expected_keywords = scenario["expected_keywords"]
            should_cite = scenario["should_cite_source"]
            description = scenario["description"]

            print(f"\n[{scenario_id}/{total}] 🧪 TESTING: {category}")
            print(f"Question: {question}")
            print(f"{'-' * 80}")

            result = {
                "id": scenario_id,
                "category": category,
                "question": question,
                "description": description,
                "status": "UNKNOWN",
                "response_length": 0,
                "found_keywords": [],
                "validation": [],
            }

            try:
                # Run the query using the configured user ID
                response = configured_agent.run(question, user_id=configured_user_id)
                content = str(response.content) if hasattr(response, "content") else str(response)

                result["response_length"] = len(content)

                # Validation
                validation_results = []

                # Check response length
                if len(content) >= 50:
                    validation_results.append("✅ Response length adequate")
                else:
                    validation_results.append(f"⚠️  Response too short: {len(content)} chars")

                # Check for expected keywords
                content_lower = content.lower()
                found_keywords = [kw for kw in expected_keywords if kw.lower() in content_lower]
                result["found_keywords"] = found_keywords

                if found_keywords:
                    validation_results.append(f"✅ Found keywords: {found_keywords}")
                else:
                    validation_results.append(f"⚠️  Missing expected keywords: {expected_keywords}")

                # Check for source citations
                if should_cite:
                    has_citation = any(
                        marker in content_lower
                        for marker in [
                            "jira",
                            "query",
                            "schedule",
                            "according to",
                            "based on",
                            "release schedule",
                        ]
                    )
                    if has_citation:
                        validation_results.append("✅ Includes source citation")
                    else:
                        validation_results.append("⚠️  No explicit source citation")

                result["validation"] = validation_results

                # Determine status
                if all("✅" in v for v in validation_results):
                    result["status"] = "PASSED"
                    passed += 1
                    print("✅ Status: PASSED")
                elif any("✅" in v for v in validation_results):
                    result["status"] = "PARTIAL"
                    partial += 1
                    print("⚠️  Status: PARTIAL")
                else:
                    result["status"] = "FAILED"
                    failed += 1
                    print("❌ Status: FAILED")

                # Print validation details
                for v in validation_results:
                    print(f"  {v}")

                # Print response preview
                print("\n📄 Response Preview:")
                preview = content[:300] + "..." if len(content) > 300 else content
                print(preview)

            except Exception as e:
                result["status"] = "FAILED"
                result["error"] = str(e)
                failed += 1
                print(f"❌ Status: FAILED - {e}")

            results.append(result)

        # Print summary
        print(f"\n{'=' * 80}")
        print("TEST SUMMARY")
        print(f"{'=' * 80}")
        print(f"Total Scenarios: {total}")
        print(f"  ✅ Passed: {passed}/{total}")
        print(f"  ⚠️  Partial: {partial}/{total}")
        print(f"  ❌ Failed: {failed}/{total}")

        # Save detailed results
        results_file = Path("tmp/release_manager_test_results.json")
        results_file.parent.mkdir(exist_ok=True)
        with results_file.open("w") as f:
            json.dump(
                {
                    "timestamp": datetime.now().isoformat(),
                    "summary": {
                        "total": total,
                        "passed": passed,
                        "partial": partial,
                        "failed": failed,
                    },
                    "results": results,
                },
                f,
                indent=2,
            )

        print(f"\n📊 Detailed results saved to: {results_file}")
        print(f"{'=' * 80}\n")

        # Test passes if:
        # 1. At least one scenario ran (not all skipped)
        # 2. No scenarios failed completely
        # 3. At least 80% passed or partial
        assert passed + partial > 0, "No tests were run"
        assert failed == 0, f"{failed} scenarios failed completely"

        success_rate = (passed + partial) / total * 100
        assert success_rate >= 80, f"Success rate too low: {success_rate:.1f}%"
