"""Unit tests for SSH session lifecycle management.

Tests for create_session, end_session, close_session, shutdown, and
session summary/history methods.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ssh_agent_bridge import (
    SSHService,
    ConnectionInfo,
    SessionInfo,
    SessionHistory,
    SessionSummary,
    HistoryConfig,
    Message,
)
from ssh_agent_bridge.exceptions import SessionError, SSHServiceError


@pytest.mark.unit
@pytest.mark.asyncio
class TestSessionLifecycle:
    """Test cases for session creation and management."""

    async def test_create_session_success(self, ssh_service, mock_asyncssh):
        """Test successful session creation."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            session_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            assert session_id in ssh_service._sessions
            session = ssh_service._sessions[session_id]

            assert session.agent_id == "test-agent"
            assert session.status == "active"
            assert session.session_id == session_id
            assert session.buffer == ""
            assert session.markers == set()

    async def test_create_session_with_key_auth(self, ssh_service, mock_asyncssh):
        """Test session creation with private key authentication."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            with patch("os.path.isfile", return_value=True):
                session_id = await ssh_service.create_session(
                    agent_id="test-agent",
                    host="example.com",
                    username="testuser",
                    private_key="/path/to/key",
                )

            assert session_id in ssh_service._sessions

    async def test_end_session_success(self, ssh_service, mock_asyncssh):
        """Test successful session ending."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            session_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            # Verify session exists
            assert session_id in ssh_service._sessions
            assert ssh_service._sessions[session_id].status == "active"

            # End session
            await ssh_service.end_session(session_id)

            # Verify session status is closed (not removed, just marked as closed)
            assert session_id in ssh_service._sessions
            assert ssh_service._sessions[session_id].status == "closed"
            assert session_id not in ssh_service._session_locks

    async def test_end_session_not_found(self, ssh_service):
        """Test ending a non-existent session."""
        with pytest.raises(SessionError, match="Session nonexistent does not exist"):
            await ssh_service.end_session("nonexistent")

    async def test_end_session_already_closed(self, ssh_service, mock_asyncssh):
        """Test ending an already closed session."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            session_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            await ssh_service.end_session(session_id)

            with pytest.raises(SessionError, match="already closed"):
                await ssh_service.end_session(session_id)

    async def test_close_session_removes_state(self, ssh_service, mock_asyncssh):
        """Test close_session removes session state."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            session_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            await ssh_service.close_session(session_id)

            assert session_id not in ssh_service._sessions
            assert session_id not in ssh_service._session_locks

    async def test_service_shutdown(self, ssh_service):
        """Test that service shuts down cleanly."""
        await ssh_service.shutdown()

    async def test_list_sessions_single_agent(self, ssh_service):
        """Test listing sessions for a single agent."""
        mock_conn = MagicMock()
        mock_conn.host = "example.com"
        mock_conn.username = "testuser"

        conn_info = ConnectionInfo(
            connection=mock_conn,
            host="example.com",
            username="testuser",
            agent_id="agent-1",
            metadata={"port": 22},
        )

        session_info = SessionInfo(
            session_id="session-1",
            agent_id="agent-1",
            connection_info=conn_info,
            process=MagicMock(),
            buffer="",
            markers=set(),
            reader_task=None,
            lock=asyncio.Lock(),
            condition=asyncio.Condition(),
            status="active",
            history=[],
            history_config=HistoryConfig(),
            created_at=datetime.now(),
            last_activity=datetime.now(),
            command_count=5,
            pending_command_markers={},
        )

        ssh_service._sessions["session-1"] = session_info

        results = await ssh_service.list_sessions("agent-1")

        assert len(results) == 1
        assert results[0].session_id == "session-1"
        assert results[0].agent_id == "agent-1"
        assert results[0].host == "example.com"
        assert results[0].username == "testuser"
        assert results[0].status == "active"
        assert results[0].command_count == 5
        assert results[0].message_count == 0

    async def test_get_session_history(self, ssh_service):
        """Test retrieving session history."""
        session = SessionInfo(
            session_id="test-session",
            agent_id="test-agent",
            connection_info=ConnectionInfo(
                connection=MagicMock(),
                host="example.com",
                username="testuser",
                agent_id="test-agent",
                metadata={},
            ),
            process=MagicMock(),
            buffer="",
            markers=set(),
            reader_task=None,
            lock=asyncio.Lock(),
            condition=asyncio.Condition(),
            status="active",
            history=[
                Message(
                    id="msg-1",
                    timestamp=datetime.now(),
                    direction="input",
                    content="pwd",
                )
            ],
            history_config=HistoryConfig(),
            created_at=datetime.now(),
            last_activity=datetime.now(),
            command_count=1,
            pending_command_markers={},
        )
        ssh_service._sessions[session.session_id] = session

        history = await ssh_service.get_session_history(session.session_id)

        assert isinstance(history, SessionHistory)
        assert history.session_id == session.session_id
        assert history.total_count == 1
        assert history.truncated is False

    async def test_get_session_history_invalid_direction(self, ssh_service):
        """Test invalid direction handling in history retrieval."""
        session = SessionInfo(
            session_id="test-session",
            agent_id="test-agent",
            connection_info=ConnectionInfo(
                connection=MagicMock(),
                host="example.com",
                username="testuser",
                agent_id="test-agent",
                metadata={},
            ),
            process=MagicMock(),
            buffer="",
            markers=set(),
            reader_task=None,
            lock=asyncio.Lock(),
            condition=asyncio.Condition(),
            status="active",
            history=[],
            history_config=HistoryConfig(),
            created_at=datetime.now(),
            last_activity=datetime.now(),
            command_count=0,
            pending_command_markers={},
        )
        ssh_service._sessions[session.session_id] = session

        with pytest.raises(SSHServiceError, match="Invalid direction"):
            await ssh_service.get_session_history(session.session_id, direction="bad")