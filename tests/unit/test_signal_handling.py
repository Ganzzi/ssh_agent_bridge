"""Unit tests for signal handling.

Tests for send_signal and signal fallback behavior.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ssh_agent_bridge.exceptions import SessionError, SSHServiceError


@pytest.mark.unit
@pytest.mark.asyncio
class TestSignalHandling:
    """Test cases for signal handling."""

    async def test_send_signal_by_name(self, ssh_service, mock_asyncssh):
        """Test sending signal by name."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            session_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            session = ssh_service._sessions[session_id]

            await ssh_service.send_signal(session_id, "SIGINT")

            # Should convert SIGINT to signal number 2
            session.process.send_signal.assert_called_with(2)

    async def test_send_signal_by_number(self, ssh_service, mock_asyncssh):
        """Test sending signal by number."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            session_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            session = ssh_service._sessions[session_id]

            await ssh_service.send_signal(session_id, 9)  # SIGKILL

            session.process.send_signal.assert_called_with(9)

    async def test_send_signal_invalid_name(self, ssh_service, mock_asyncssh):
        """Test sending invalid signal name."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            session_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            with pytest.raises(SSHServiceError, match="Unsupported signal name"):
                await ssh_service.send_signal(session_id, "INVALID_SIGNAL")

    async def test_send_signal_invalid_session(self, ssh_service):
        """Test sending signal to invalid session."""
        with pytest.raises(SessionError, match="Session invalid does not exist"):
            await ssh_service.send_signal("invalid", "SIGINT")

    async def test_send_signal_fallback_to_kill(self, ssh_service, mock_asyncssh):
        """Test fallback to kill when send_signal fails."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            session_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            session = ssh_service._sessions[session_id]

            # Make send_signal raise AttributeError to trigger fallback
            session.process.send_signal = AsyncMock(
                side_effect=AttributeError("Not supported")
            )
            session.process.kill = MagicMock()

            await ssh_service.send_signal(session_id, "SIGKILL")

            session.process.kill.assert_called_once()