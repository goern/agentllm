"""Tests for the Custom LiteLLM handler."""

import pytest

from agentllm.custom_handler import AgnoCustomLLM, register_agno_provider


class TestAgnoCustomLLM:
    """Tests for AgnoCustomLLM handler."""

    def test_completion_with_valid_agent(self):
        """Test completion with a valid agent."""
        handler = AgnoCustomLLM()

        response = handler.completion(
            model="agno/release-manager",
            messages=[{"role": "user", "content": "Hello!"}],
        )

        assert response is not None
        assert response.model == "agno/release-manager"
        assert hasattr(response, "choices")
        assert len(response.choices) > 0
        assert response.choices[0]["message"]["role"] == "assistant"
        assert isinstance(response.choices[0]["message"]["content"], str)

    def test_completion_without_agno_prefix(self):
        """Test that model name works with or without agno/ prefix."""
        handler = AgnoCustomLLM()

        # Should work with just "release-manager"
        response = handler.completion(model="release-manager", messages=[{"role": "user", "content": "Test"}])

        assert response is not None
        assert response.choices[0]["message"]["role"] == "assistant"

    def test_completion_with_invalid_agent(self):
        """Test that invalid agent raises error."""
        handler = AgnoCustomLLM()

        with pytest.raises(Exception) as exc_info:
            handler.completion(model="agno/nonexistent", messages=[{"role": "user", "content": "Test"}])

        assert "not found" in str(exc_info.value).lower()

    def test_completion_extracts_user_message(self):
        """Test that user message is correctly extracted."""
        handler = AgnoCustomLLM()

        response = handler.completion(
            model="release-manager",
            messages=[
                {"role": "system", "content": "You are helpful"},
                {"role": "user", "content": "This is my message"},
            ],
        )

        assert response is not None
        # The release-manager agent should process the user message

    def test_streaming_flag(self):
        """Test that streaming parameter is handled."""
        handler = AgnoCustomLLM()

        # Request with stream=True should return iterator
        result = handler.completion(
            model="release-manager",
            messages=[{"role": "user", "content": "Stream this"}],
            stream=True,
        )

        # Should be an iterator/generator
        assert hasattr(result, "__iter__") or hasattr(result, "__next__")

    def test_register_provider(self):
        """Test that register_agno_provider works."""
        import litellm

        # Clear any existing custom providers
        litellm.custom_provider_map = []

        # Register
        register_agno_provider()

        # Check it was registered
        assert len(litellm.custom_provider_map) > 0
        assert any(p.get("provider") == "agno" for p in litellm.custom_provider_map)

    def test_model_response_structure(self):
        """Test that ModelResponse has correct structure."""
        handler = AgnoCustomLLM()

        response = handler.completion(model="release-manager", messages=[{"role": "user", "content": "Test"}])

        # Check required fields
        assert hasattr(response, "model")
        assert hasattr(response, "choices")
        assert hasattr(response, "usage")

        # Check choices structure
        choice = response.choices[0]
        assert hasattr(choice, "message")
        assert hasattr(choice.message, "role")
        assert hasattr(choice.message, "content")
        assert hasattr(choice, "finish_reason")
        assert choice.message.role == "assistant"
        assert len(choice.message.content) > 0

        # Check usage structure
        assert "prompt_tokens" in response.usage
        assert "completion_tokens" in response.usage
        assert "total_tokens" in response.usage
