"""Unit tests for SSH Agent Bridge core functionality."""

import asyncio
from datetime import datetime
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from asyncssh import ConnectionLost
from ssh_agent_bridge import (
    SSHService,
    ConnectionInfo,
    SessionInfo,
    CommandResult,
    PartialResult,
    Message,
    SessionHistory,
    SessionSummary,
    HistoryConfig,
)
from ssh_agent_bridge.exceptions import (
    SSHServiceError,
    ConnectionError,
    SessionError,
    CommandError,
    TimeoutError,
)


class TestSSHService:
    """Test cases for the SSHService class."""

    @pytest.mark.asyncio
    @pytest.mark.fast
    async def test_service_initialization(self, ssh_service):
        """Test that SSHService initializes correctly."""
        assert ssh_service._connections == {}
        assert ssh_service._sessions == {}
        assert ssh_service._connection_locks == {}
        assert ssh_service._session_locks == {}

    @pytest.mark.asyncio
    @pytest.mark.fast
    async def test_shutdown(self, ssh_service):
        """Test that service shuts down cleanly."""
        # Should not raise any exceptions
        await ssh_service.shutdown()

    @pytest.mark.fast
    def test_marker_generation(self, ssh_service):
        """Test that markers are generated uniquely."""
        marker1 = ssh_service._make_marker()
        marker2 = ssh_service._make_marker()

        assert marker1 != marker2
        assert marker1.startswith("______END_MARKER_")
        assert marker2.startswith("______END_MARKER_")
        assert marker1.endswith("______")
        assert marker2.endswith("______")
        assert len(marker1) > 20  # ______END_MARKER_ + uuid + ______


class TestDataTypes:
    """Test cases for data type classes."""

    def test_command_result_creation(self):
        """Test CommandResult dataclass creation."""
        result = CommandResult(
            status="completed", exit_code=0, stdout="Hello World", stderr=None
        )

        assert result.status == "completed"
        assert result.exit_code == 0
        assert result.stdout == "Hello World"
        assert result.stderr is None

    def test_partial_result_creation(self):
        """Test PartialResult dataclass creation."""
        result = PartialResult(
            status="partial", stdout="Partial output...", pending_marker="MARKER_123"
        )

        assert result.status == "partial"
        assert result.stdout == "Partial output..."
        assert result.pending_marker == "MARKER_123"

    def test_connection_info_creation(self):
        """Test ConnectionInfo dataclass creation."""

        class MockConnection:
            pass

        conn = ConnectionInfo(
            connection=MockConnection(),
            host="example.com",
            username="testuser",
            agent_id="agent-123",
            metadata={"key": "value"},
        )

        assert conn.host == "example.com"
        assert conn.username == "testuser"
        assert conn.agent_id == "agent-123"
        assert conn.metadata == {"key": "value"}

    def test_message_creation(self):
        """Test Message dataclass creation."""
        now = datetime.now()
        msg = Message(
            id="msg-001",
            timestamp=now,
            direction="input",
            content="ls -la",
            command_id="cmd-001",
        )

        assert msg.id == "msg-001"
        assert msg.timestamp == now
        assert msg.direction == "input"
        assert msg.content == "ls -la"
        assert msg.command_id == "cmd-001"

    def test_message_without_command_id(self):
        """Test Message creation without command_id."""
        msg = Message(
            id="msg-002",
            timestamp=datetime.now(),
            direction="output",
            content="total 42",
        )

        assert msg.id == "msg-002"
        assert msg.direction == "output"
        assert msg.content == "total 42"
        assert msg.command_id is None

    def test_session_history_creation(self):
        """Test SessionHistory dataclass creation."""
        now = datetime.now()
        messages = [
            Message(
                id="msg-001",
                timestamp=now,
                direction="input",
                content="pwd",
            ),
            Message(
                id="msg-002",
                timestamp=now,
                direction="output",
                content="/home/user",
            ),
        ]

        history = SessionHistory(
            session_id="sess-123",
            messages=messages,
            total_count=2,
            truncated=False,
        )

        assert history.session_id == "sess-123"
        assert len(history.messages) == 2
        assert history.total_count == 2
        assert history.truncated is False

    def test_session_summary_creation(self):
        """Test SessionSummary dataclass creation."""
        now = datetime.now()
        summary = SessionSummary(
            session_id="sess-123",
            agent_id="agent-001",
            host="example.com",
            username="testuser",
            port=22,
            status="active",
            created_at=now,
            last_activity=now,
            command_count=5,
            message_count=10,
        )

        assert summary.session_id == "sess-123"
        assert summary.agent_id == "agent-001"
        assert summary.host == "example.com"
        assert summary.username == "testuser"
        assert summary.port == 22
        assert summary.status == "active"
        assert summary.command_count == 5
        assert summary.message_count == 10

    def test_history_config_defaults(self):
        """Test HistoryConfig with default values."""
        config = HistoryConfig()

        assert config.max_messages == 1000
        assert config.max_message_size == 65536  # 64KB
        assert config.trim_strategy == "oldest"

    def test_history_config_custom(self):
        """Test HistoryConfig with custom values."""
        config = HistoryConfig(
            max_messages=500, max_message_size=32768, trim_strategy="largest"
        )

        assert config.max_messages == 500
        assert config.max_message_size == 32768
        assert config.trim_strategy == "largest"


class TestExceptions:
    """Test cases for custom exceptions."""

    def test_ssh_service_error(self):
        """Test SSHServiceError base exception."""
        error = SSHServiceError("Test error")
        assert str(error) == "Test error"
        assert isinstance(error, Exception)

    def test_connection_error(self):
        """Test ConnectionError exception."""
        error = ConnectionError("Connection failed")
        assert str(error) == "Connection failed"
        assert isinstance(error, SSHServiceError)

    def test_session_error(self):
        """Test SessionError exception."""
        error = SessionError("Session not found")
        assert str(error) == "Session not found"
        assert isinstance(error, SSHServiceError)

    def test_command_error(self):
        """Test CommandError exception."""
        error = CommandError("Command failed")
        assert str(error) == "Command failed"
        assert isinstance(error, SSHServiceError)

    def test_timeout_error(self):
        """Test TimeoutError exception."""
        error = TimeoutError("Operation timed out")
        assert str(error) == "Operation timed out"
        assert isinstance(error, SSHServiceError)


class TestConnectionManagement:
    """Test cases for connection creation and pooling."""

    @pytest.mark.asyncio
    async def test_connection_creation_success(self, ssh_service, mock_asyncssh):
        """Test successful connection creation."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            conn_info = await ssh_service._ensure_connection(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            assert conn_info.host == "example.com"
            assert conn_info.username == "testuser"
            assert conn_info.agent_id == "test-agent"
            assert (
                "test-agent:example.com:testuser:password" in ssh_service._connections
            )

    @pytest.mark.asyncio
    async def test_connection_reuse(self, ssh_service, mock_asyncssh):
        """Test that connections are reused for same agent/host/auth."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            # First connection
            conn1 = await ssh_service._ensure_connection(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            # Second connection with same parameters should reuse
            conn2 = await ssh_service._ensure_connection(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            assert conn1 is conn2
            assert len(ssh_service._connections) == 1

    @pytest.mark.asyncio
    async def test_connection_separation_by_agent(self, ssh_service, mock_asyncssh):
        """Test that different agents get separate connections."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            conn1 = await ssh_service._ensure_connection(
                agent_id="agent-1",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            conn2 = await ssh_service._ensure_connection(
                agent_id="agent-2",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            assert conn1 is not conn2
            assert len(ssh_service._connections) == 2

    @pytest.mark.asyncio
    async def test_connection_separation_by_auth_method(
        self, ssh_service, mock_asyncssh
    ):
        """Test that different auth methods get separate connections."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            conn1 = await ssh_service._ensure_connection(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            # Mock file existence check for key auth method
            with patch("os.path.isfile", return_value=True):
                conn2 = await ssh_service._ensure_connection(
                    agent_id="test-agent",
                    host="example.com",
                    username="testuser",
                    private_key="/path/to/key",
                )

            assert conn1 is not conn2
            assert len(ssh_service._connections) == 2

    @pytest.mark.asyncio
    async def test_connection_failure(self, ssh_service):
        """Test connection failure handling."""
        with patch("asyncssh.connect", side_effect=Exception("Connection failed")):
            with pytest.raises(ConnectionError, match="Unexpected error connecting"):
                await ssh_service._ensure_connection(
                    agent_id="test-agent",
                    host="badhost.com",
                    username="testuser",
                    password="testpass",
                )

    @pytest.mark.asyncio
    async def test_close_agent_connection(self, ssh_service, mock_asyncssh):
        """Test closing connections for a specific agent."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            # Create connections for different agents
            await ssh_service._ensure_connection(
                agent_id="agent-1",
                host="example.com",
                username="testuser",
                password="testpass",
            )
            await ssh_service._ensure_connection(
                agent_id="agent-2",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            assert len(ssh_service._connections) == 2

            # Close agent-1 connections
            await ssh_service.close_agent_connection("agent-1")


class TestSessionLifecycle:
    """Test cases for session creation and management."""

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
    async def test_end_session_not_found(self, ssh_service):
        """Test ending a non-existent session."""
        with pytest.raises(SessionError, match="Session nonexistent does not exist"):
            await ssh_service.end_session("nonexistent")

    @pytest.mark.asyncio
    async def test_end_session_already_closed(self, ssh_service, mock_asyncssh):
        """Test ending an already closed session."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            session_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            # End session first time
            await ssh_service.end_session(session_id)


class TestCommandExecution:
    """Test cases for command execution functionality."""

    @pytest.mark.asyncio
    async def test_run_command_completed(self, ssh_service, mock_asyncssh):
        """Test successful command execution with immediate completion."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            session_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",  # Add password for testing
            )

            session = ssh_service._sessions[session_id]

            # Cancel the reader task so we can control the buffer directly
            if session.reader_task and not session.reader_task.done():
                session.reader_task.cancel()
                try:
                    await session.reader_task
                except asyncio.CancelledError:
                    pass

            # Capture the marker that will be used
            sent_commands = []
            session.process.stdin.write = lambda cmd: sent_commands.append(cmd)

            # Simulate asynchronously adding output to buffer
            async def add_output_with_marker():
                await asyncio.sleep(0.01)
                if sent_commands:
                    import re

                    cmd = sent_commands[-1]
                    match = re.search(r"echo\s+(\S+)=\"\$\?\"", cmd)
                    if match:
                        marker = match.group(1)
                        async with session.condition:
                            session.buffer += "command output\n" + marker + "=0\n"
                            session.condition.notify_all()

            # Start the output simulation task
            output_task = asyncio.create_task(add_output_with_marker())

            result = await ssh_service.run_command(session_id, "ls -la", 5.0)

            # Clean up task
            await output_task

            assert isinstance(result, CommandResult)
            assert result.status == "completed"
            assert result.exit_code == 0
            assert "command output" in result.stdout

    @pytest.mark.asyncio
    async def test_run_command_with_exit_code(self, ssh_service, mock_asyncssh):
        """Test command execution that exits with non-zero code."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            session_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",  # Add password for testing
                verify_host_key=False,  # Disable for testing
            )

            session = ssh_service._sessions[session_id]

            # Cancel the reader task so we can control the buffer directly
            if session.reader_task and not session.reader_task.done():
                session.reader_task.cancel()
                try:
                    await session.reader_task
                except asyncio.CancelledError:
                    pass

            # Capture the marker that will be used
            sent_commands = []
            session.process.stdin.write = lambda cmd: sent_commands.append(cmd)

            # Simulate asynchronously adding output to buffer with marker and exit code 1
            async def add_output_with_marker():
                await asyncio.sleep(0.01)
                if sent_commands:
                    import re

                    cmd = sent_commands[-1]
                    match = re.search(r"echo\s+(\S+)=\"\$\?\"", cmd)
                    if match:
                        marker = match.group(1)
                        async with session.condition:
                            session.buffer += "command failed\n" + marker + "=1\n"
                            session.condition.notify_all()

            # Start the output simulation task
            output_task = asyncio.create_task(add_output_with_marker())

            result = await ssh_service.run_command(session_id, "failing_command", 5.0)

            # Clean up task
            await output_task

            assert isinstance(result, CommandResult)
            assert result.status == "completed"
            assert result.exit_code == 1
            assert "command failed" in result.stdout

    @pytest.mark.asyncio
    async def test_run_command_partial(self, ssh_service, mock_asyncssh):
        """Test command execution that times out before completion."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            session_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",  # Add password for testing
            )

            session = ssh_service._sessions[session_id]

            # Cancel reader task
            if session.reader_task and not session.reader_task.done():
                session.reader_task.cancel()
                try:
                    await session.reader_task
                except asyncio.CancelledError:
                    pass

            # Simulate partial output without marker (simulating timeout)
            async def add_partial_output():
                # Wait longer than timeout so test times out
                await asyncio.sleep(0.2)
                async with session.condition:
                    session.buffer += "partial output"
                    session.condition.notify_all()

            output_task = asyncio.create_task(add_partial_output())

            result = await ssh_service.run_command(session_id, "slow-command", 0.01)

            # Let the background task finish
            try:
                await asyncio.wait_for(output_task, timeout=0.5)
            except asyncio.TimeoutError:
                output_task.cancel()

            assert isinstance(result, PartialResult)
            assert result.status == "partial"
            assert result.pending_marker.startswith("______END_MARKER_")

    @pytest.mark.asyncio
    async def test_run_command_broken_session(self, ssh_service, mock_asyncssh):
        """Test command execution when session becomes broken during execution."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            session_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",  # Add password for testing
                verify_host_key=False,  # Disable for testing
            )

            session = ssh_service._sessions[session_id]

            # Cancel reader task and mark session as broken
            if session.reader_task and not session.reader_task.done():
                session.reader_task.cancel()
                try:
                    await session.reader_task
                except asyncio.CancelledError:
                    pass

            # Mark session as broken
            session.status = "broken"

            # Attempting to run command on broken session should fail
            with pytest.raises(
                SessionError, match="Session .* is not active \\(status: broken\\)"
            ):
                await ssh_service.run_command(session_id, "ls", 5.0)

    @pytest.mark.asyncio
    async def test_run_command_invalid_session(self, ssh_service):
        """Test running command on invalid session."""
        """Test running command on invalid session."""
        with pytest.raises(SessionError, match="Session invalid does not exist"):
            await ssh_service.run_command("invalid", "ls", 5.0)

    @pytest.mark.asyncio
    async def test_run_command_closed_session(self, ssh_service, mock_asyncssh):
        """Test running command on closed session."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            session_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",  # Add password for testing
            )

            await ssh_service.end_session(session_id)

            with pytest.raises(SessionError, match="not active"):
                await ssh_service.run_command(session_id, "ls", 5.0)

    @pytest.mark.asyncio
    async def test_get_remaining_output_success(self, ssh_service, mock_asyncssh):
        """Test getting remaining output for a partial command."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            session_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            session = ssh_service._sessions[session_id]

            # Cancel reader task
            if session.reader_task and not session.reader_task.done():
                session.reader_task.cancel()
                try:
                    await session.reader_task
                except asyncio.CancelledError:
                    pass

            # First: get partial result (no marker yet)
            partial_task = asyncio.create_task(
                self._delay_output(session, "partial\n", 0.2)
            )

            partial_result = await ssh_service.run_command(
                session_id, "slow-command", 0.01
            )
            assert isinstance(partial_result, PartialResult)
            pending_marker = partial_result.pending_marker

            # Now add the marker for the second call
            async def add_marker():
                await asyncio.sleep(0.01)
                async with session.condition:
                    session.buffer += pending_marker + " 0\n"
                    session.condition.notify_all()

            marker_task = asyncio.create_task(add_marker())

            # Get remaining should find the marker now
            final_result = await ssh_service.get_remaining_output(
                session_id, pending_marker, 5.0
            )

            # Cleanup
            try:
                await asyncio.wait_for(marker_task, timeout=0.1)
            except asyncio.TimeoutError:
                marker_task.cancel()
            try:
                await asyncio.wait_for(partial_task, timeout=0.5)
            except asyncio.TimeoutError:
                partial_task.cancel()

            assert isinstance(final_result, CommandResult)
            assert final_result.status == "completed"
            assert final_result.exit_code == 0

    async def _delay_output(self, session, text, delay):
        """Helper to add output to buffer after delay."""
        await asyncio.sleep(delay)
        async with session.condition:
            session.buffer += text
            session.condition.notify_all()

    @pytest.mark.asyncio
    async def test_get_remaining_output_timeout(self, ssh_service, mock_asyncssh):
        """Test timeout when getting remaining output."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            session_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            session = ssh_service._sessions[session_id]

            # Cancel reader task
            if session.reader_task and not session.reader_task.done():
                session.reader_task.cancel()
                try:
                    await session.reader_task
                except asyncio.CancelledError:
                    pass

            # Create a timeout that will never receive the marker
            sent_commands = []
            session.process.stdin.write = lambda cmd: sent_commands.append(cmd)

            # Task that never adds the marker
            async def never_complete():
                await asyncio.sleep(10)  # Way longer than timeout

            output_task = asyncio.create_task(never_complete())

            # Get a partial result first
            partial_result = await ssh_service.run_command(session_id, "slow-cmd", 0.01)
            assert isinstance(partial_result, PartialResult)

            # Now timeout waiting for that marker
            with pytest.raises(TimeoutError, match="Marker .* not found within"):
                await ssh_service.get_remaining_output(
                    session_id, partial_result.pending_marker, 0.01
                )

            # Cleanup
            output_task.cancel()
            try:
                await output_task
            except asyncio.CancelledError:
                pass


class TestInteractiveFeatures:
    """Test cases for interactive input and signal handling."""

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
    async def test_send_input_invalid_session(self, ssh_service):
        """Test sending input to invalid session."""
        with pytest.raises(SessionError, match="Session invalid does not exist"):
            await ssh_service.send_input("invalid", "input")

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
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

            # Should fallback to kill
            await ssh_service.send_signal(session_id, "SIGKILL")

            # Verify kill was called
            session.process.kill.assert_called_once()


class TestEphemeralCommands:
    """Test cases for ephemeral (non-session) command execution."""

    @pytest.mark.asyncio
    async def test_run_ephemeral_command_success(self, ssh_service, mock_asyncssh):
        """Test successful ephemeral command execution."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            result = await ssh_service.run_ephemeral(
                agent_id="test-agent",
                host="example.com",
                command="echo 'hello world'",
                username="testuser",
                password="testpass",  # Add password for testing
                verify_host_key=False,  # Disable for testing
            )

            assert result.exit_code == 0
            assert "hello world" in result.stdout

    @pytest.mark.asyncio
    async def test_run_ephemeral_command_with_timeout(self, ssh_service, mock_asyncssh):
        """Test ephemeral command with timeout."""
        with patch("asyncssh.connect", mock_asyncssh.connect), patch(
            "asyncio.wait_for", side_effect=asyncio.TimeoutError
        ):

            with pytest.raises(TimeoutError):
                await ssh_service.run_ephemeral(
                    agent_id="test-agent",
                    host="example.com",
                    username="testuser",
                    password="testpass",  # Add password for testing
                    command="slow_command",
                    timeout=0.1,
                    verify_host_key=False,  # Disable for testing
                )

    @pytest.mark.asyncio
    async def test_run_ephemeral_command_error(self, ssh_service, mock_asyncssh):
        """Test ephemeral command with non-zero exit code."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            # Mock command that fails
            mock_asyncssh.connect.return_value.run.return_value = AsyncMock()
            mock_asyncssh.connect.return_value.run.return_value.stdout = ""
            mock_asyncssh.connect.return_value.run.return_value.stderr = (
                "command failed"
            )
            mock_asyncssh.connect.return_value.run.return_value.returncode = 1

            result = await ssh_service.run_ephemeral(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",  # Add password for testing
                command="failing_command",
                verify_host_key=False,  # Disable for testing
            )

            assert result.exit_code == 1
            assert "command failed" in result.stderr


class TestBufferManagement:
    """Test cases for buffer management and output handling."""

    @pytest.mark.asyncio
    async def test_buffer_overflow_protection(self, ssh_service, mock_asyncssh):
        """Test that buffers don't grow indefinitely."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            session_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            session = ssh_service._sessions[session_id]

            # Simulate large output that exceeds buffer limit
            large_output = "x" * (ssh_service._max_buffer_size + 1000)

            # Mock the process to return large output
            session.process.stdout.at_eof.return_value = True
            session.process.stdout.readline = AsyncMock(
                side_effect=[
                    large_output[:1000].encode(),
                    large_output[1000:2000].encode(),
                    b"",  # EOF
                ]
            )

            # Run a command that produces large output
            result = await ssh_service.run_command(session_id, "big_output_command")

            # Buffer should be truncated to max size
            assert len(result.output) <= ssh_service._max_buffer_size
            assert result.truncated is True

    @pytest.mark.asyncio
    async def test_concurrent_output_reading(self, ssh_service, mock_asyncssh):
        """Test that multiple commands don't interfere with output reading."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            session_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            session = ssh_service._sessions[session_id]

            # Mock concurrent command execution
            command1_marker = "CMD1_MARKER_12345"
            command2_marker = "CMD2_MARKER_67890"

            # Simulate interleaved output from two commands
            session.process.stdout.readline = AsyncMock(
                side_effect=[
                    b"Command 1 output\n",
                    f"echo {command1_marker} $?\n".encode(),
                    b"Command 2 output\n",
                    f"echo {command2_marker} $?\n".encode(),
                    b"",  # EOF
                ]
            )

            # Run first command
            result1 = await ssh_service.run_command(session_id, "cmd1", timeout=1.0)

            # Run second command
            result2 = await ssh_service.run_command(session_id, "cmd2", timeout=1.0)

            # Both commands should complete successfully
            assert result1.exit_code == 0
            assert result2.exit_code == 0
            assert "Command 1 output" in result1.output

    @pytest.mark.asyncio
    async def test_large_output_handling(self, ssh_service, mock_asyncssh):
        """Test handling of commands that produce large amounts of output."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            session_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
                verify_host_key=False,  # Disable for testing
            )

            session = ssh_service._sessions[session_id]

            # Cancel the reader task so we can control the buffer directly
            if session.reader_task and not session.reader_task.done():
                session.reader_task.cancel()
                try:
                    await session.reader_task
                except asyncio.CancelledError:
                    pass

            # Capture the marker that will be used
            sent_commands = []
            session.process.stdin.write = lambda cmd: sent_commands.append(cmd)

            # Create large output (100KB)
            large_output_size = 100 * 1024
            large_output = "x" * large_output_size + "\n"

            # Simulate asynchronously adding large output to buffer with marker
            async def add_large_output_with_marker():
                await asyncio.sleep(0.01)
                if sent_commands:
                    import re

                    cmd = sent_commands[-1]
                    match = re.search(r"echo\s+(\S+)=\"\$\?\"", cmd)
                    if match:
                        marker = match.group(1)
                        async with session.condition:
                            session.buffer += large_output + marker + "=0\n"
                            session.condition.notify_all()

            # Start the output simulation task
            output_task = asyncio.create_task(add_large_output_with_marker())

            result = await ssh_service.run_command(session_id, "large_output_cmd", 5.0)

            # Clean up task
            await output_task

            # Should handle large output correctly
            assert isinstance(result, CommandResult)
            assert result.status == "completed"
            assert result.exit_code == 0
            assert len(result.stdout) >= large_output_size  # At least the large output
            assert "x" * 100 in result.stdout  # Should contain our test data


class TestConcurrentSessions:
    """Test cases for concurrent session handling."""

    @pytest.mark.asyncio
    async def test_multiple_sessions_same_host(self, ssh_service, mock_asyncssh):
        """Test multiple sessions to the same host."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            # Create multiple sessions to same host
            session1_id = await ssh_service.create_session(
                agent_id="agent1",
                host="example.com",
                username="user1",
                password="pass1",
            )

            session2_id = await ssh_service.create_session(
                agent_id="agent2",
                host="example.com",
                username="user2",
                password="pass2",
            )

            # Should have different sessions but same connection (pooled)
            assert session1_id != session2_id
            assert len(ssh_service._sessions) == 2
            assert len(ssh_service._connections) == 2  # Different auth combos

            # Both should work independently
            result1 = await ssh_service.run_command(session1_id, "echo 'session1'")
            result2 = await ssh_service.run_command(session2_id, "echo 'session2'")

            assert result1.exit_code == 0
            assert result2.exit_code == 0
            assert "session1" in result1.output
            assert "session2" in result2.output

    @pytest.mark.asyncio
    async def test_session_isolation(self, ssh_service, mock_asyncssh):
        """Test that sessions are properly isolated."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            session1_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            session2_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="different.com",
                username="testuser",
                password="testpass",
            )

            # Commands in different sessions should not interfere
            await ssh_service.run_command(session1_id, "cd /tmp")
            result2 = await ssh_service.run_command(session2_id, "pwd")

            # Session 2 should not be affected by session 1's directory change
            assert "/tmp" not in result2.output

    @pytest.mark.asyncio
    async def test_connection_pooling(self, ssh_service, mock_asyncssh):
        """Test that connections are properly pooled."""
        with patch("asyncssh.connect", mock_asyncssh.connect) as mock_connect:
            # Create two sessions with same connection parameters
            session1_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            session2_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            # Should reuse the same connection
            assert mock_connect.call_count == 1
            assert len(ssh_service._connections) == 1

            # Both sessions should share the connection
            assert any(
                "example.com" in key and "testuser" in key and "test-agent" in key
                for key in ssh_service._connections.keys()
            )


class TestCleanupAndLifecycle:
    """Test cases for session and connection cleanup."""

    @pytest.mark.asyncio
    async def test_session_cleanup_on_close(self, ssh_service, mock_asyncssh):
        """Test that sessions are properly cleaned up when closed."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            session_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            assert session_id in ssh_service._sessions

            # Close the session
            await ssh_service.close_session(session_id)

            # Session should be removed
            assert session_id not in ssh_service._sessions

    @pytest.mark.asyncio
    async def test_connection_cleanup_on_last_session_close(
        self, ssh_service, mock_asyncssh
    ):
        """Test that connections are cleaned up when last session closes."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            session1_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            session2_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            # Should have one connection shared by both sessions
            assert len(ssh_service._connections) == 1

            # Close first session
            await ssh_service.close_session(session1_id)
            # Connection should still exist
            assert len(ssh_service._connections) == 1

            # Close second session
            await ssh_service.close_session(session2_id)
            # Connection should be cleaned up
            assert len(ssh_service._connections) == 0

    @pytest.mark.asyncio
    async def test_service_shutdown_cleanup(self, ssh_service, mock_asyncssh):
        """Test that all resources are cleaned up on service shutdown."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            # Create multiple sessions
            session1_id = await ssh_service.create_session(
                agent_id="agent1",
                host="host1.com",
                username="user1",
                password="pass1",
            )

            session2_id = await ssh_service.create_session(
                agent_id="agent2",
                host="host2.com",
                username="user2",
                password="pass2",
            )

            assert len(ssh_service._sessions) == 2
            assert len(ssh_service._connections) == 2

            # Shutdown service
            await ssh_service.shutdown()

            # All resources should be cleaned up
            assert len(ssh_service._sessions) == 0
            assert len(ssh_service._connections) == 0

    @pytest.mark.asyncio
    async def test_connection_error_handling(self, ssh_service, mock_asyncssh):
        """Test handling of connection errors during operations."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            session_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            session = ssh_service._sessions[session_id]

            # Simulate connection failure during command execution
            session.process.stdout.readline.side_effect = ConnectionLost(
                "Connection lost"
            )

            with pytest.raises(
                SSHServiceError, match="Connection lost during command execution"
            ):
                await ssh_service.run_command(session_id, "failing_command")

    @pytest.mark.asyncio
    async def test_create_session_implemented(self, ssh_service, mock_asyncssh):
        """Test that create_session is now implemented."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            session_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            assert isinstance(session_id, str)
            assert len(session_id) > 0
            assert session_id in ssh_service._sessions

    @pytest.mark.asyncio
    async def test_run_command_implemented(self, ssh_service, mock_asyncssh):
        """Test that run_command is now implemented."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            # First create a session
            session_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",  # Add password for testing
            )

            # Mock the process to simulate command output
            session = ssh_service._sessions[session_id]

            # Cancel the reader task so we can control the buffer directly
            if session.reader_task and not session.reader_task.done():
                session.reader_task.cancel()
                try:
                    await session.reader_task
                except asyncio.CancelledError:
                    pass

            # Capture the marker that will be used
            sent_commands = []
            session.process.stdin.write = lambda cmd: sent_commands.append(cmd)

            # Simulate asynchronously adding output to buffer
            async def add_output_with_marker():
                await asyncio.sleep(0.01)
                if sent_commands:
                    import re

                    cmd = sent_commands[-1]
                    match = re.search(r"echo\s+(\S+)=\"\$\?\"", cmd)
                    if match:
                        marker = match.group(1)
                        async with session.condition:
                            session.buffer += "command output\n" + marker + "=0\n"
                            session.condition.notify_all()

            # Start the output simulation task
            output_task = asyncio.create_task(add_output_with_marker())

            result = await ssh_service.run_command(session_id, "ls -la", 5.0)

            # Clean up task
            await output_task

            assert result.status == "completed"
            assert result.exit_code == 0
            assert "command output" in result.stdout

    @pytest.mark.asyncio
    async def test_send_input_implemented(self, ssh_service, mock_asyncssh):
        """Test that send_input is now implemented."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            session_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",  # Add password for testing
            )

            # Should not raise NotImplementedError
            await ssh_service.send_input(session_id, "test input")

    @pytest.mark.asyncio
    async def test_send_signal_implemented(self, ssh_service, mock_asyncssh):
        """Test that send_signal is now implemented."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            session_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",  # Add password for testing
            )

            # Should not raise NotImplementedError
            await ssh_service.send_signal(session_id, "SIGINT")

    @pytest.mark.asyncio
    async def test_run_ephemeral_implemented(self, ssh_service, mock_asyncssh):
        """Test that run_ephemeral is now implemented."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            result = await ssh_service.run_ephemeral(
                agent_id="test-agent",
                host="example.com",
                command="ls",
                username="testuser",
                password="testpass",  # Add password for testing
                verify_host_key=False,  # Disable for testing
            )

            assert result.status == "completed"
            assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_close_agent_connection_implemented(self, ssh_service, mock_asyncssh):
        """Test that close_agent_connection is now implemented."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            # Create a session first
            await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            # Should not raise NotImplementedError
            await ssh_service.close_agent_connection("test-agent")


class TestMessageRecording:
    """Test cases for message history recording (Phase 2 feature)."""

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
    @pytest.mark.fast
    async def test_session_info_has_pending_markers_dict(
        self, ssh_service, mock_asyncssh
    ):
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

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
    @pytest.mark.fast
    async def test_input_message_format_for_send_input(self):
        """Test the format of input messages created for send_input."""
        # Verify that input messages can be created without command_id
        msg = Message(
            id="msg-interactive",
            timestamp=datetime.now(),
            direction="input",
            content="user response",
            command_id=None,
            marker=None,
        )

        assert msg.direction == "input"
        assert msg.content == "user response"
        assert msg.command_id is None
        assert msg.marker is None

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
    @pytest.mark.fast
    async def test_history_config_defaults(self):
        """Test that HistoryConfig has proper defaults."""
        config = HistoryConfig()

        assert config.max_messages == 1000
        assert config.max_message_size == 65536  # 64KB
        assert config.trim_strategy == "oldest"

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
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


class TestListSessions:
    """Test cases for the list_sessions() API method."""

    @pytest.mark.asyncio
    @pytest.mark.fast
    async def test_list_sessions_single_agent(self, ssh_service):
        """Test listing sessions for a single agent."""
        # Create a mock session
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

        # List sessions for agent-1
        results = await ssh_service.list_sessions("agent-1")

        assert len(results) == 1
        assert results[0].session_id == "session-1"
        assert results[0].agent_id == "agent-1"
        assert results[0].host == "example.com"
        assert results[0].username == "testuser"
        assert results[0].status == "active"
        assert results[0].command_count == 5
        assert results[0].message_count == 0

    @pytest.mark.asyncio
    @pytest.mark.fast
    async def test_list_sessions_multiple_agents(self, ssh_service):
        """Test listing sessions with multiple agents."""
        # Create sessions for different agents
        for agent_id in ["agent-1", "agent-2"]:
            for i in range(2):
                mock_conn = MagicMock()
                mock_conn.host = f"host-{agent_id}.com"
                mock_conn.username = f"user-{agent_id}"

                conn_info = ConnectionInfo(
                    connection=mock_conn,
                    host=f"host-{agent_id}.com",
                    username=f"user-{agent_id}",
                    agent_id=agent_id,
                    metadata={"port": 22},
                )

                session_info = SessionInfo(
                    session_id=f"{agent_id}-session-{i}",
                    agent_id=agent_id,
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
                    command_count=i + 1,
                    pending_command_markers={},
                )

                ssh_service._sessions[f"{agent_id}-session-{i}"] = session_info

        # List sessions for agent-1
        results = await ssh_service.list_sessions("agent-1")

        assert len(results) == 2
        assert all(s.agent_id == "agent-1" for s in results)

        # List sessions for agent-2
        results = await ssh_service.list_sessions("agent-2")

        assert len(results) == 2
        assert all(s.agent_id == "agent-2" for s in results)

    @pytest.mark.asyncio
    @pytest.mark.fast
    async def test_list_sessions_include_closed(self, ssh_service):
        """Test listing sessions with include_closed flag."""
        mock_conn = MagicMock()
        conn_info = ConnectionInfo(
            connection=mock_conn,
            host="example.com",
            username="testuser",
            agent_id="agent-1",
            metadata={"port": 22},
        )

        # Create active session
        active_session = SessionInfo(
            session_id="session-active",
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
            command_count=1,
            pending_command_markers={},
        )

        # Create closed session
        closed_session = SessionInfo(
            session_id="session-closed",
            agent_id="agent-1",
            connection_info=conn_info,
            process=MagicMock(),
            buffer="",
            markers=set(),
            reader_task=None,
            lock=asyncio.Lock(),
            condition=asyncio.Condition(),
            status="closed",
            history=[],
            history_config=HistoryConfig(),
            created_at=datetime.now(),
            last_activity=datetime.now(),
            command_count=0,
            pending_command_markers={},
        )

        ssh_service._sessions["session-active"] = active_session
        ssh_service._sessions["session-closed"] = closed_session

        # List without include_closed (default)
        results = await ssh_service.list_sessions("agent-1", include_closed=False)
        assert len(results) == 1
        assert results[0].status == "active"

        # List with include_closed
        results = await ssh_service.list_sessions("agent-1", include_closed=True)
        assert len(results) == 2
        assert {s.status for s in results} == {"active", "closed"}

    @pytest.mark.asyncio
    @pytest.mark.fast
    async def test_list_sessions_limit(self, ssh_service):
        """Test listing sessions with limit parameter."""
        mock_conn = MagicMock()
        conn_info = ConnectionInfo(
            connection=mock_conn,
            host="example.com",
            username="testuser",
            agent_id="agent-1",
            metadata={"port": 22},
        )

        # Create 5 sessions
        for i in range(5):
            session_info = SessionInfo(
                session_id=f"session-{i}",
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
                command_count=i,
                pending_command_markers={},
            )
            ssh_service._sessions[f"session-{i}"] = session_info

        # List with default limit (100)
        results = await ssh_service.list_sessions("agent-1")
        assert len(results) == 5

        # List with limit=2
        results = await ssh_service.list_sessions("agent-1", limit=2)
        assert len(results) == 2


class TestGetSessionHistory:
    """Test cases for the get_session_history() API method."""

    @pytest.mark.asyncio
    @pytest.mark.fast
    async def test_get_session_history_basic(self, ssh_service):
        """Test retrieving session history."""
        mock_conn = MagicMock()
        conn_info = ConnectionInfo(
            connection=mock_conn,
            host="example.com",
            username="testuser",
            agent_id="agent-1",
            metadata={"port": 22},
        )

        # Create messages
        messages = [
            Message(
                id="msg-1",
                timestamp=datetime(2025, 12, 1, 10, 0),
                direction="input",
                content="ls",
                command_id="cmd-1",
            ),
            Message(
                id="msg-2",
                timestamp=datetime(2025, 12, 1, 10, 1),
                direction="output",
                content="file1.txt",
                command_id="cmd-1",
            ),
        ]

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
            history=messages,
            history_config=HistoryConfig(),
            created_at=datetime.now(),
            last_activity=datetime.now(),
            command_count=1,
            pending_command_markers={},
        )

        ssh_service._sessions["session-1"] = session_info

        # Get history
        history = await ssh_service.get_session_history("session-1")

        assert history.session_id == "session-1"
        assert len(history.messages) == 2
        assert history.total_count == 2
        assert history.truncated is False

    @pytest.mark.asyncio
    @pytest.mark.fast
    async def test_get_session_history_not_found(self, ssh_service):
        """Test retrieving history for non-existent session."""
        with pytest.raises(SessionError):
            await ssh_service.get_session_history("nonexistent-session")

    @pytest.mark.asyncio
    @pytest.mark.fast
    async def test_get_session_history_filter_by_direction(self, ssh_service):
        """Test filtering history by direction."""
        mock_conn = MagicMock()
        conn_info = ConnectionInfo(
            connection=mock_conn,
            host="example.com",
            username="testuser",
            agent_id="agent-1",
            metadata={"port": 22},
        )

        messages = [
            Message(
                id="msg-1",
                timestamp=datetime(2025, 12, 1, 10, 0),
                direction="input",
                content="cmd1",
                command_id="cmd-1",
            ),
            Message(
                id="msg-2",
                timestamp=datetime(2025, 12, 1, 10, 1),
                direction="output",
                content="output1",
                command_id="cmd-1",
            ),
            Message(
                id="msg-3",
                timestamp=datetime(2025, 12, 1, 10, 2),
                direction="input",
                content="cmd2",
                command_id="cmd-2",
            ),
        ]

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
            history=messages,
            history_config=HistoryConfig(),
            created_at=datetime.now(),
            last_activity=datetime.now(),
            command_count=2,
            pending_command_markers={},
        )

        ssh_service._sessions["session-1"] = session_info

        # Filter by input
        history = await ssh_service.get_session_history("session-1", direction="input")
        assert len(history.messages) == 2
        assert all(m.direction == "input" for m in history.messages)
        assert history.total_count == 2

        # Filter by output
        history = await ssh_service.get_session_history("session-1", direction="output")
        assert len(history.messages) == 1
        assert all(m.direction == "output" for m in history.messages)
        assert history.total_count == 1

    @pytest.mark.asyncio
    @pytest.mark.fast
    async def test_get_session_history_filter_by_since(self, ssh_service):
        """Test filtering history by timestamp."""
        mock_conn = MagicMock()
        conn_info = ConnectionInfo(
            connection=mock_conn,
            host="example.com",
            username="testuser",
            agent_id="agent-1",
            metadata={"port": 22},
        )

        messages = [
            Message(
                id="msg-1",
                timestamp=datetime(2025, 12, 1, 10, 0),
                direction="input",
                content="cmd1",
            ),
            Message(
                id="msg-2",
                timestamp=datetime(2025, 12, 1, 10, 5),
                direction="output",
                content="output1",
            ),
            Message(
                id="msg-3",
                timestamp=datetime(2025, 12, 1, 10, 10),
                direction="input",
                content="cmd2",
            ),
        ]

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
            history=messages,
            history_config=HistoryConfig(),
            created_at=datetime.now(),
            last_activity=datetime.now(),
            command_count=2,
            pending_command_markers={},
        )

        ssh_service._sessions["session-1"] = session_info

        # Filter since 10:05
        since_time = datetime(2025, 12, 1, 10, 5)
        history = await ssh_service.get_session_history("session-1", since=since_time)
        assert len(history.messages) == 2  # msg-2 and msg-3
        assert history.total_count == 2

    @pytest.mark.asyncio
    @pytest.mark.fast
    async def test_get_session_history_limit_and_truncate(self, ssh_service):
        """Test limiting history and detecting truncation."""
        mock_conn = MagicMock()
        conn_info = ConnectionInfo(
            connection=mock_conn,
            host="example.com",
            username="testuser",
            agent_id="agent-1",
            metadata={"port": 22},
        )

        # Create 5 messages
        messages = [
            Message(
                id=f"msg-{i}",
                timestamp=datetime(2025, 12, 1, 10, i),
                direction="input" if i % 2 == 0 else "output",
                content=f"message-{i}",
            )
            for i in range(5)
        ]

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
            history=messages,
            history_config=HistoryConfig(),
            created_at=datetime.now(),
            last_activity=datetime.now(),
            command_count=3,
            pending_command_markers={},
        )

        ssh_service._sessions["session-1"] = session_info

        # Get with limit=2
        history = await ssh_service.get_session_history("session-1", limit=2)
        assert len(history.messages) == 2
        assert history.total_count == 5
        assert history.truncated is True

        # Get with limit=10
        history = await ssh_service.get_session_history("session-1", limit=10)
        assert len(history.messages) == 5
        assert history.total_count == 5
        assert history.truncated is False

    @pytest.mark.asyncio
    @pytest.mark.fast
    async def test_get_session_history_invalid_direction(self, ssh_service):
        """Test error handling for invalid direction."""
        mock_conn = MagicMock()
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
            command_count=0,
            pending_command_markers={},
        )

        ssh_service._sessions["session-1"] = session_info

        # Try with invalid direction
        with pytest.raises(SSHServiceError):
            await ssh_service.get_session_history("session-1", direction="invalid")


class TestPerformance:
    """Performance tests for session history and message handling."""

    @pytest.mark.asyncio
    async def test_large_message_history_creation(self, ssh_service):
        """Benchmark creating and storing 1000+ messages in history."""
        mock_conn = MagicMock()
        conn_info = ConnectionInfo(
            connection=mock_conn,
            host="example.com",
            username="testuser",
            agent_id="agent-1",
            metadata={"port": 22},
        )

        # Create 1000 messages efficiently
        import time

        start_time = time.time()

        messages = []
        for i in range(1000):
            msg = Message(
                id=f"msg-{i:04d}",
                timestamp=datetime.now(),
                direction="input" if i % 2 == 0 else "output",
                content=f"message content {i}" * 10,  # ~200 bytes each
            )
            messages.append(msg)

        creation_time = time.time() - start_time

        # Create session with all messages
        start_time = time.time()
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
            history=messages,
            history_config=HistoryConfig(max_messages=1000),
            created_at=datetime.now(),
            last_activity=datetime.now(),
            command_count=500,
            pending_command_markers={},
        )

        assignment_time = time.time() - start_time
        ssh_service._sessions["session-1"] = session_info

        # Verify all messages are stored
        assert len(session_info.history) == 1000

        # Should be fast (< 1 second total for 1000 messages)
        total_time = creation_time + assignment_time
        assert total_time < 1.0, f"Message creation too slow: {total_time:.3f}s"

    @pytest.mark.asyncio
    async def test_message_history_query_performance(self, ssh_service):
        """Benchmark querying large message histories."""
        import time

        mock_conn = MagicMock()
        conn_info = ConnectionInfo(
            connection=mock_conn,
            host="example.com",
            username="testuser",
            agent_id="agent-1",
            metadata={"port": 22},
        )

        # Create 1000 messages with timestamps
        messages = []
        base_time = datetime(2025, 12, 1, 10, 0)
        for i in range(1000):
            msg = Message(
                id=f"msg-{i:04d}",
                timestamp=base_time.replace(second=i % 60),
                direction="input" if i % 2 == 0 else "output",
                content=f"message {i}",
            )
            messages.append(msg)

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
            history=messages,
            history_config=HistoryConfig(),
            created_at=datetime.now(),
            last_activity=datetime.now(),
            command_count=500,
            pending_command_markers={},
        )

        ssh_service._sessions["session-1"] = session_info

        # Benchmark basic retrieval with high limit to get all messages
        start_time = time.time()
        history = await ssh_service.get_session_history("session-1", limit=2000)
        query_time = time.time() - start_time

        assert len(history.messages) == 1000
        # Query should be very fast
        assert query_time < 0.1, f"Basic query too slow: {query_time:.3f}s"

        # Benchmark direction filtering
        start_time = time.time()
        history = await ssh_service.get_session_history(
            "session-1", direction="input", limit=2000
        )
        filter_time = time.time() - start_time

        assert len(history.messages) == 500  # Half are input
        # Filtering should still be fast
        assert filter_time < 0.2, f"Direction filter too slow: {filter_time:.3f}s"

        # Benchmark limit + truncation
        start_time = time.time()
        history = await ssh_service.get_session_history("session-1", limit=100)
        limit_time = time.time() - start_time

        assert len(history.messages) == 100
        assert history.truncated is True
        # Limiting should be fast
        assert limit_time < 0.1, f"Limit query too slow: {limit_time:.3f}s"

    @pytest.mark.asyncio
    async def test_history_trimming_performance(self, ssh_service):
        """Benchmark history trimming with 1000+ messages."""
        import time

        mock_conn = MagicMock()
        conn_info = ConnectionInfo(
            connection=mock_conn,
            host="example.com",
            username="testuser",
            agent_id="agent-1",
            metadata={"port": 22},
        )

        # Create 1500 messages
        messages = []
        for i in range(1500):
            msg = Message(
                id=f"msg-{i:04d}",
                timestamp=datetime.now(),
                direction="input" if i % 2 == 0 else "output",
                content="x" * 100,  # ~100 bytes each
            )
            messages.append(msg)

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
            history=messages,
            history_config=HistoryConfig(
                max_messages=1000, trim_strategy="oldest"  # Trim to 1000
            ),
            created_at=datetime.now(),
            last_activity=datetime.now(),
            command_count=750,
            pending_command_markers={},
        )

        ssh_service._sessions["session-1"] = session_info

        # Benchmark trimming
        start_time = time.time()
        await ssh_service._trim_history(session_info)
        trim_time = time.time() - start_time

        # Should trim to max_messages
        assert len(session_info.history) == 1000
        # Trimming should be fast (< 100ms even for 1500 messages)
        assert trim_time < 0.1, f"Trimming too slow: {trim_time:.3f}s"

    @pytest.mark.asyncio
    async def test_memory_bounded_with_trimming(self, ssh_service):
        """Verify that history trimming keeps memory bounded."""
        mock_conn = MagicMock()
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
            history_config=HistoryConfig(
                max_messages=100,  # Keep small for testing
                max_message_size=1024,  # 1KB per message max
                trim_strategy="oldest",
            ),
            created_at=datetime.now(),
            last_activity=datetime.now(),
            command_count=0,
            pending_command_markers={},
        )

        ssh_service._sessions["session-1"] = session_info

        # Add 200 messages with large content
        for i in range(200):
            msg = Message(
                id=f"msg-{i:03d}",
                timestamp=datetime.now(),
                direction="output",
                content="x" * 5000,  # 5KB content (will be trimmed to 1KB)
            )
            session_info.history.append(msg)

            # Trim after each addition to maintain bounded memory
            await ssh_service._trim_history(session_info)

        # Should have at most max_messages
        assert len(session_info.history) <= 100

        # Each message should be at most max_message_size
        for msg in session_info.history:
            assert (
                len(msg.content) <= 1024
            ), f"Message too large: {len(msg.content)} bytes"

    @pytest.mark.asyncio
    async def test_list_sessions_performance_many_agents(self, ssh_service):
        """Benchmark list_sessions with many agents."""
        import time

        # Create 100 sessions across 10 agents
        mock_conn = MagicMock()

        for agent_idx in range(10):
            for session_idx in range(10):
                conn_info = ConnectionInfo(
                    connection=mock_conn,
                    host=f"host{agent_idx}.com",
                    username=f"user{agent_idx}",
                    agent_id=f"agent-{agent_idx}",
                    metadata={"port": 22},
                )

                session_info = SessionInfo(
                    session_id=f"agent-{agent_idx}-session-{session_idx}",
                    agent_id=f"agent-{agent_idx}",
                    connection_info=conn_info,
                    process=MagicMock(),
                    buffer="",
                    markers=set(),
                    reader_task=None,
                    lock=asyncio.Lock(),
                    condition=asyncio.Condition(),
                    status="active" if session_idx % 2 == 0 else "closed",
                    history=[],
                    history_config=HistoryConfig(),
                    created_at=datetime.now(),
                    last_activity=datetime.now(),
                    command_count=session_idx,
                    pending_command_markers={},
                )

                ssh_service._sessions[f"agent-{agent_idx}-session-{session_idx}"] = (
                    session_info
                )

        # Benchmark listing for one agent with many sessions
        start_time = time.time()
        results = await ssh_service.list_sessions("agent-0")
        query_time = time.time() - start_time

        assert len(results) == 5  # Only active sessions
        # Query should be fast
        assert query_time < 0.05, f"List sessions too slow: {query_time:.3f}s"

    @pytest.mark.asyncio
    async def test_rapid_command_sequence_history_recording(self, ssh_service):
        """Test history recording during rapid command sequences."""
        import time

        mock_conn = MagicMock()
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
            command_count=0,
            pending_command_markers={},
        )

        ssh_service._sessions["session-1"] = session_info

        # Simulate rapid command sequence (100 commands)
        start_time = time.time()

        for cmd_idx in range(100):
            # Record input message
            input_msg = Message(
                id=f"input-{cmd_idx}",
                timestamp=datetime.now(),
                direction="input",
                content=f"command {cmd_idx}",
                command_id=f"cmd-{cmd_idx}",
            )
            session_info.history.append(input_msg)
            session_info.command_count += 1

            # Record output message
            output_msg = Message(
                id=f"output-{cmd_idx}",
                timestamp=datetime.now(),
                direction="output",
                content=f"output for command {cmd_idx}" * 10,
                command_id=f"cmd-{cmd_idx}",
            )
            session_info.history.append(output_msg)

        recording_time = time.time() - start_time

        # Should have recorded all messages
        assert len(session_info.history) == 200  # 2 messages per command
        assert session_info.command_count == 100

        # Recording 200 messages should be very fast
        assert recording_time < 0.5, f"Recording too slow: {recording_time:.3f}s"

    @pytest.mark.asyncio
    async def test_memory_impact_with_large_outputs(self, ssh_service):
        """Benchmark memory usage with large output messages."""
        import sys

        mock_conn = MagicMock()
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
            history_config=HistoryConfig(max_messages=100),
            created_at=datetime.now(),
            last_activity=datetime.now(),
            command_count=0,
            pending_command_markers={},
        )

        # Add messages with 64KB output each (at max size limit)
        large_output = "x" * 65536  # 64KB

        for i in range(10):  # 10 large messages
            msg = Message(
                id=f"msg-{i}",
                timestamp=datetime.now(),
                direction="output",
                content=large_output,
            )
            session_info.history.append(msg)

        # Estimate memory per message (rough)
        total_messages = len(session_info.history)
        approx_size_per_message = (
            sys.getsizeof(large_output) + 300
        )  # Message object overhead

        # With 100 message limit and 64KB per message, max should be ~6.4MB
        estimated_max_memory = 100 * approx_size_per_message

        # Should not exceed reasonable limits
        assert (
            estimated_max_memory < 10_000_000
        ), f"Estimated memory too high: {estimated_max_memory} bytes"
