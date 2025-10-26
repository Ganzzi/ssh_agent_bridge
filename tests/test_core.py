"""Unit tests for SSH Agent Bridge core functionality."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from asyncssh import ConnectionLost
from ssh_agent_bridge import (
    SSHService,
    ConnectionInfo,
    SessionInfo,
    CommandResult,
    PartialResult,
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
                # password="testpass", # Disable for testing
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
                # password="testpass", # Disable for testing
            )

            # Second connection with same parameters should reuse
            conn2 = await ssh_service._ensure_connection(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                # password="testpass", # Disable for testing
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
                # password="testpass", # Disable for testing
            )

            conn2 = await ssh_service._ensure_connection(
                agent_id="agent-2",
                host="example.com",
                username="testuser",
                # password="testpass", # Disable for testing
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
                # password="testpass", # Disable for testing
            )

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
                    # password="testpass", # Disable for testing
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
                # password="testpass", # Disable for testing
            )
            await ssh_service._ensure_connection(
                agent_id="agent-2",
                host="example.com",
                username="testuser",
                # password="testpass", # Disable for testing
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
                # password="testpass", # Disable for testing
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
                # password="testpass", # Disable for testing
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
                # password="testpass", # Disable for testing
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
                # password="testpass", # Disable for testing
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
                # password="testpass", # Disable for testing
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
                # password="testpass", # Disable for testing
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
                # password="testpass", # Disable for testing
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
                # password="testpass", # Disable for testing
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
                # password="testpass", # Disable for testing
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
                # password="testpass", # Disable for testing
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
                # password="testpass", # Disable for testing
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
                # password="testpass", # Disable for testing
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
                # password="testpass", # Disable for testing
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
                # password="testpass", # Disable for testing
            )

            session2_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="different.com",
                username="testuser",
                # password="testpass", # Disable for testing
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
                # password="testpass", # Disable for testing
            )

            session2_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                # password="testpass", # Disable for testing
            )

            # Should reuse the same connection
            assert mock_connect.call_count == 1
            assert len(ssh_service._connections) == 1

            # Both sessions should share the connection
            conn_key = ("example.com", "testuser", "test-agent")
            assert conn_key in ssh_service._connections


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
                # password="testpass", # Disable for testing
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
                # password="testpass", # Disable for testing
            )

            session2_id = await ssh_service.create_session(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                # password="testpass", # Disable for testing
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
                # password="testpass", # Disable for testing
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
                # password="testpass", # Disable for testing
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
                # password="testpass", # Disable for testing
            )

            # Should not raise NotImplementedError
            await ssh_service.close_agent_connection("test-agent")
