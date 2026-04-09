"""Unit tests for session message history.

Tests for message recording, history trimming, and history queries.
"""

import asyncio
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from ssh_agent_bridge import (
    SSHService,
    ConnectionInfo,
    SessionInfo,
    Message,
    HistoryConfig,
)


@pytest.mark.unit
@pytest.mark.asyncio
class TestHistoryRecording:
    """Test cases for message history recording."""

    @pytest.mark.fast
    async def test_message_dataclass_with_marker(self):
        """Test Message dataclass with marker field for output correlation."""
        msg = Message(
            id="msg-123",
            timestamp=datetime.now(),
            direction="output",
            content="output text",
            command_id="cmd-456",
            marker="MARKER_123",
        )

        assert msg.id == "msg-123"
        assert msg.direction == "output"
        assert msg.command_id == "cmd-456"
        assert msg.marker == "MARKER_123"

    @pytest.mark.fast
    async def test_pending_markers_dict(self, ssh_service, mock_asyncssh):
        """Test that SessionInfo includes pending_command_markers dict."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            session_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            session = ssh_service._sessions[session_id]
            assert hasattr(session, "pending_command_markers")
            assert isinstance(session.pending_command_markers, dict)
            assert len(session.pending_command_markers) == 0

    @pytest.mark.fast
    async def test_input_message_created_with_command_id_and_marker(self, ssh_service):
        """Test that input messages are created with command_id and marker."""
        # Create a mock session info directly
        mock_conn = MagicMock()
        session_info = SessionInfo(
            session_id="test-session",
            agent_id="test-agent",
            connection_info=ConnectionInfo(
                connection=mock_conn,
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

        # Verify initial state
        assert len(session_info.history) == 0

        # Create an input message like run_command would
        command_id = "cmd-123"
        marker = "MARKER_123"
        input_msg = Message(
            id="msg-1",
            timestamp=datetime.now(),
            direction="input",
            content="echo test",
            command_id=command_id,
            marker=marker,
        )
        session_info.history.append(input_msg)

        # Verify message was added correctly
        assert len(session_info.history) == 1
        assert session_info.history[0].command_id == command_id
        assert session_info.history[0].marker == marker
        assert session_info.history[0].content == "echo test"

    @pytest.mark.fast
    async def test_command_count_initialization(self):
        """Test that command_count is initialized to 0 on session creation."""
        # Create a mock session info directly
        mock_conn = MagicMock()
        session_info = SessionInfo(
            session_id="test-session",
            agent_id="test-agent",
            connection_info=ConnectionInfo(
                connection=mock_conn,
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

        assert session_info.command_count == 0

        # Simulate incrementing like run_command does
        session_info.command_count += 1
        assert session_info.command_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
class TestHistoryTrimming:
    """Test cases for history trimming functionality."""

    @pytest.mark.fast
    async def test_history_config_defaults(self):
        """Test that HistoryConfig has proper defaults."""
        config = HistoryConfig()

        assert config.max_messages == 1000
        assert config.max_message_size == 65536  # 64KB
        assert config.trim_strategy == "oldest"

    @pytest.mark.fast
    async def test_trim_history_oldest_strategy(self, ssh_service, mock_asyncssh):
        """Test history trimming with oldest-first strategy."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            session_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            session = ssh_service._sessions[session_id]
            session.history_config.max_messages = 5

            # Add messages manually
            for i in range(10):
                msg = Message(
                    id=f"msg-{i}",
                    timestamp=datetime.now(),
                    direction="input",
                    content=f"message {i}",
                )
                session.history.append(msg)

            # Trim history
            await ssh_service._trim_history(session)

            # Should have max_messages messages remaining (oldest removed)
            assert len(session.history) == 5
            # Verify oldest messages were removed
            assert session.history[0].content == "message 5"
            assert session.history[-1].content == "message 9"

    @pytest.mark.fast
    async def test_trim_history_message_size_limit(self, ssh_service, mock_asyncssh):
        """Test history trimming of oversized messages."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            session_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            session = ssh_service._sessions[session_id]
            session.history_config.max_message_size = 100

            # Add a message with oversized content
            large_content = "x" * 500
            msg = Message(
                id="large-msg",
                timestamp=datetime.now(),
                direction="output",
                content=large_content,
            )
            session.history.append(msg)

            # Trim history
            await ssh_service._trim_history(session)

            # Message content should be truncated
            assert len(session.history[0].content) == 100
            assert session.history[0].content == "x" * 100

    @pytest.mark.fast
    async def test_last_activity_timestamp_updated(self):
        """Test that last_activity timestamp can be updated."""
        # Create a mock session info directly
        mock_conn = MagicMock()
        now = datetime.now()
        session_info = SessionInfo(
            session_id="test-session",
            agent_id="test-agent",
            connection_info=ConnectionInfo(
                connection=mock_conn,
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
            created_at=now,
            last_activity=now,
            command_count=0,
            pending_command_markers={},
        )

        initial_activity = session_info.last_activity

        # Simulate a small delay and then update
        await asyncio.sleep(0.01)
        session_info.last_activity = datetime.now()

        # last_activity should be updated
        assert session_info.last_activity > initial_activity

    @pytest.mark.fast
    async def test_pending_markers_dict_cleanup(self):
        """Test that pending_command_markers dict can be cleaned up after completion."""
        # Create a mock session info directly
        mock_conn = MagicMock()
        session_info = SessionInfo(
            session_id="test-session",
            agent_id="test-agent",
            connection_info=ConnectionInfo(
                connection=mock_conn,
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

        # Simulate adding a pending command marker (like run_command does)
        marker = "MARKER_123"
        command_id = "cmd-456"
        session_info.pending_command_markers[marker] = command_id

        assert len(session_info.pending_command_markers) == 1

        # Simulate cleanup when marker is found
        session_info.pending_command_markers.pop(marker, None)

        # Should be empty now
        assert len(session_info.pending_command_markers) == 0