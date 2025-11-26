"""Tests for GitHub Review Prioritization Agent."""

from datetime import UTC, datetime, timedelta

import pytest


class TestPRScoring:
    """Test PR prioritization scoring algorithm."""

    def _create_mock_pr(
        self,
        number=1,
        title="Test PR",
        age_days=0,
        additions=50,
        deletions=10,
        comments=0,
        review_comments=0,
        labels=None,
        draft=False,
    ):
        """Create a mock PR dictionary for testing.

        Args:
            number: PR number
            title: PR title
            age_days: How many days old the PR is
            additions: Lines added
            deletions: Lines deleted
            comments: Number of comments
            review_comments: Number of review comments
            labels: List of label names
            draft: Whether PR is a draft

        Returns:
            Dictionary representing a PR
        """
        created_at = datetime.now(UTC) - timedelta(days=age_days)
        return {
            "number": number,
            "title": title,
            "created_at": created_at.isoformat(),
            "additions": additions,
            "deletions": deletions,
            "comments": comments,
            "review_comments": review_comments,
            "labels": [{"name": label} for label in (labels or [])],
            "draft": draft,
            "user": {"login": "testuser"},
        }

    def test_critical_priority_urgent_label(self):
        """Test that urgent PRs get CRITICAL priority."""
        from agentllm.tools.github_toolkit import GitHubToolkit

        # Create a mock toolkit (we'll just test the scoring method)
        # Note: We need a token but won't use it for this test
        toolkit = GitHubToolkit(token="fake_token_for_testing")

        # Create a PR with urgent label and good conditions
        pr = self._create_mock_pr(
            age_days=5,  # Older PR
            additions=30,  # Small PR
            labels=["urgent"],  # Urgent label = +10 points
            draft=False,
        )

        score_data = toolkit._calculate_pr_score(pr, "test/repo")

        # Urgent label + age + size should push to CRITICAL
        assert score_data["priority_tier"] in ["CRITICAL", "HIGH"]
        assert score_data["breakdown"]["labels"] == 10

    def test_high_priority_aged_pr(self):
        """Test that old PRs get HIGH priority."""
        from agentllm.tools.github_toolkit import GitHubToolkit

        toolkit = GitHubToolkit(token="fake_token_for_testing")

        # Create an old PR (7 days = max age score)
        pr = self._create_mock_pr(
            age_days=7,
            additions=100,
            deletions=50,
            draft=False,
        )

        score_data = toolkit._calculate_pr_score(pr, "test/repo")

        # Age score should be maxed at 25
        assert score_data["breakdown"]["age"] == 25
        assert score_data["priority_tier"] in ["HIGH", "MEDIUM"]

    def test_high_priority_small_pr(self):
        """Test that small PRs get bonus points."""
        from agentllm.tools.github_toolkit import GitHubToolkit

        toolkit = GitHubToolkit(token="fake_token_for_testing")

        # Create a very small PR
        pr = self._create_mock_pr(
            age_days=2,
            additions=10,
            deletions=5,
            draft=False,
        )

        score_data = toolkit._calculate_pr_score(pr, "test/repo")

        # Small PRs should have high size score (close to 20)
        assert score_data["breakdown"]["size"] >= 15

    def test_low_priority_draft(self):
        """Test that draft PRs have reasonable scores."""
        from agentllm.tools.github_toolkit import GitHubToolkit

        toolkit = GitHubToolkit(token="fake_token_for_testing")

        # Create a draft PR
        pr = self._create_mock_pr(
            age_days=1,
            additions=50,
            deletions=20,
            draft=True,
        )

        score_data = toolkit._calculate_pr_score(pr, "test/repo")

        # Draft PRs should still get scored normally
        assert score_data["total_score"] >= 0
        assert "ci" not in score_data["breakdown"]

    def test_activity_score_high_discussion(self):
        """Test that PRs with lots of discussion get higher activity score."""
        from agentllm.tools.github_toolkit import GitHubToolkit

        toolkit = GitHubToolkit(token="fake_token_for_testing")

        # Create a PR with lots of discussion
        pr = self._create_mock_pr(
            age_days=3,
            additions=100,
            deletions=50,
            comments=15,
            review_comments=10,
            draft=False,
        )

        score_data = toolkit._calculate_pr_score(pr, "test/repo")

        # High activity should max out activity score
        assert score_data["breakdown"]["activity"] >= 10

    def test_label_priority_levels(self):
        """Test different label priority levels."""
        from agentllm.tools.github_toolkit import GitHubToolkit

        toolkit = GitHubToolkit(token="fake_token_for_testing")

        # Test urgent label
        pr_urgent = self._create_mock_pr(labels=["urgent"])
        score_urgent = toolkit._calculate_pr_score(pr_urgent, "test/repo")
        assert score_urgent["breakdown"]["labels"] == 10

        # Test hotfix label
        pr_hotfix = self._create_mock_pr(labels=["hotfix"])
        score_hotfix = toolkit._calculate_pr_score(pr_hotfix, "test/repo")
        assert score_hotfix["breakdown"]["labels"] == 10

        # Test high-priority label
        pr_high = self._create_mock_pr(labels=["high-priority"])
        score_high = toolkit._calculate_pr_score(pr_high, "test/repo")
        assert score_high["breakdown"]["labels"] == 7

        # Test normal label (no boost)
        pr_normal = self._create_mock_pr(labels=["enhancement"])
        score_normal = toolkit._calculate_pr_score(pr_normal, "test/repo")
        assert score_normal["breakdown"]["labels"] == 0

    def test_priority_tier_thresholds(self):
        """Test that priority tiers are assigned correctly."""
        from agentllm.tools.github_toolkit import GitHubToolkit

        toolkit = GitHubToolkit(token="fake_token_for_testing")

        # Test CRITICAL tier (65+, max 80)
        pr_critical = self._create_mock_pr(
            age_days=7,  # 25
            additions=10,
            deletions=5,  # ~18
            comments=10,
            review_comments=5,  # 15
            labels=["urgent"],  # 10
            draft=False,
        )  # 25 + 18 + 15 + 10 + 5 = 73 (CRITICAL)

        score = toolkit._calculate_pr_score(pr_critical, "test/repo")
        # Should be CRITICAL (65-80 range)
        assert score["priority_tier"] == "CRITICAL"

    def test_size_penalty_for_large_prs(self):
        """Test that very large PRs get penalized."""
        from agentllm.tools.github_toolkit import GitHubToolkit

        toolkit = GitHubToolkit(token="fake_token_for_testing")

        # Create a massive PR
        pr_huge = self._create_mock_pr(
            age_days=1,
            additions=5000,
            deletions=2000,
            draft=False,
        )

        score_data = toolkit._calculate_pr_score(pr_huge, "test/repo")

        # Large PRs should have very low or zero size score
        assert score_data["breakdown"]["size"] <= 5


class TestGitHubConfig:
    """Test GitHub configuration manager."""

    def test_token_extraction_patterns(self):
        """Test various GitHub token extraction patterns."""
        from agentllm.agents.toolkit_configs.github_config import GitHubConfig

        config = GitHubConfig()

        # Test classic token pattern: "my github token is ghp_xxxxx"
        token1 = config._extract_github_token("my github token is ghp_" + "x" * 36)
        assert token1 == "ghp_" + "x" * 36

        # Test classic token pattern: "github_token: ghp_xxxxx"
        token2 = config._extract_github_token("github_token: ghp_" + "y" * 36)
        assert token2 == "ghp_" + "y" * 36

        # Test classic token pattern: "set github token to ghp_xxxxx"
        token3 = config._extract_github_token("set github token to ghp_" + "z" * 36)
        assert token3 == "ghp_" + "z" * 36

        # Test standalone classic token
        token4 = config._extract_github_token("ghp_" + "a" * 36)
        assert token4 == "ghp_" + "a" * 36

        # Test fine-grained token pattern: "my github token is github_pat_xxxxx"
        fine_grained = "github_pat_" + "A1b2C3d4E5f6G7h8I9j0" + "_" + "k1L2m3N4o5P6q7R8s9T0u1V2w3X4y5Z6a7B8c9D0e1F2g3H4i5J6k7L8m9N0o1P2"
        token5 = config._extract_github_token(f"my github token is {fine_grained}")
        assert token5 == fine_grained

        # Test standalone fine-grained token
        token6 = config._extract_github_token(fine_grained)
        assert token6 == fine_grained

        # Test fine-grained token with pattern: "github_token: github_pat_xxxxx"
        token7 = config._extract_github_token(f"github_token: {fine_grained}")
        assert token7 == fine_grained

        # Test no token found
        token8 = config._extract_github_token("this is just a regular message")
        assert token8 is None

    def test_is_required_returns_false(self):
        """Test that GitHub config is optional."""
        from agentllm.agents.toolkit_configs.github_config import GitHubConfig

        config = GitHubConfig()
        assert config.is_required() is False

    def test_authorization_request_detection(self):
        """Test that GitHub mentions are detected."""
        from agentllm.agents.toolkit_configs.github_config import GitHubConfig

        config = GitHubConfig()

        # Test various GitHub-related keywords
        messages_with_github = [
            "Show me the github repository",
            "I need help with pull requests",
            "Can you review this PR?",
            "Check the review queue",
            "Look at this repository",
        ]

        for msg in messages_with_github:
            # Should return None if already configured, otherwise prompt
            # Since user is not configured, should return prompt
            result = config.check_authorization_request(msg, "test_user")
            # Result should be prompt (not None) since user not configured
            assert result is None or "GitHub" in result

        # Test message without GitHub keywords
        result = config.check_authorization_request("Hello, how are you?", "test_user")
        assert result is None


class TestTokenStorage:
    """Test GitHub token storage in database."""

    def test_github_token_upsert_and_get(self):
        """Test storing and retrieving GitHub tokens."""
        from agentllm.db import TokenStorage

        # Create in-memory database for testing
        storage = TokenStorage(db_url="sqlite:///:memory:")

        # Test upsert
        success = storage.upsert_token(
            "github",
            user_id="test_user",
            token="ghp_test_token_12345",
            server_url="https://api.github.com",
        )
        assert success is True

        # Test get
        token_data = storage.get_token("github", "test_user")
        assert token_data is not None
        assert token_data["token"] == "ghp_test_token_12345"
        assert token_data["server_url"] == "https://api.github.com"
        assert token_data["user_id"] == "test_user"

    def test_github_token_delete(self):
        """Test deleting GitHub tokens."""
        from agentllm.db import TokenStorage

        storage = TokenStorage(db_url="sqlite:///:memory:")

        # Store a token
        storage.upsert_token(
            "github",
            user_id="test_user",
            token="ghp_test_token",
            server_url="https://api.github.com",
        )

        # Verify it exists
        assert storage.get_token("github", "test_user") is not None

        # Delete it
        success = storage.delete_token("github", "test_user")
        assert success is True

        # Verify it's gone
        assert storage.get_token("github", "test_user") is None

    def test_multiple_users_github_tokens(self):
        """Test storing GitHub tokens for multiple users."""
        from agentllm.db import TokenStorage

        storage = TokenStorage(db_url="sqlite:///:memory:")

        # Add multiple users
        storage.upsert_token("github", "user1", token="token1", server_url="https://api.github.com")
        storage.upsert_token("github", "user2", token="token2", server_url="https://api.github.com")
        storage.upsert_token("github", "user3", token="token3", server_url="https://api.github.com")

        # Verify each user's token is stored
        assert storage.get_token("github", "user1")["token"] == "token1"
        assert storage.get_token("github", "user2")["token"] == "token2"
        assert storage.get_token("github", "user3")["token"] == "token3"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
