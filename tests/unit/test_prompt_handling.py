"""Unit tests for interactive input handling.

Tests for send_input and interactive prompt response functionality.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ssh_agent_bridge import SSHService
from ssh_agent_bridge.exceptions import SessionError


@pytest.mark.unit
@pytest.mark.asyncio
class TestPromptHandling:
    """Test cases for interactive input and prompt handling."""

    async def test_send_input_success(self, ssh_service, mock_asyncssh):
        """Test successful input sending."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            session_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            session = ssh_service._sessions[session_id]

            await ssh_service.send_input(session_id, "test input")

            # Verify input was sent with newline
            session.process.stdin.write.assert_called_with("test input\n")
            session.process.stdin.drain.assert_called_once()

    async def test_send_input_invalid_session(self, ssh_service):
        """Test sending input to invalid session."""
        with pytest.raises(SessionError, match="Session invalid does not exist"):
            await ssh_service.send_input("invalid", "input")

    async def test_send_input_closed_session(self, ssh_service, mock_asyncssh):
        """Test sending input to closed session."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            session_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            await ssh_service.end_session(session_id)

            with pytest.raises(SessionError, match="not active"):
                await ssh_service.send_input(session_id, "input")

    async def test_send_input_records_message(self, ssh_service, mock_asyncssh):
        """Test that send_input records messages to history."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            session_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            session = ssh_service._sessions[session_id]
            initial_history_len = len(session.history)

            await ssh_service.send_input(session_id, "user input")

            # Should have recorded the input message
            assert len(session.history) == initial_history_len + 1
            assert session.history[-1].direction == "input"
            assert session.history[-1].content == "user input"