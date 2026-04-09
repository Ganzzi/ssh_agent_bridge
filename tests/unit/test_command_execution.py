"""Unit tests for SSH command execution.

Tests for run_command, get_remaining_output, run_ephemeral, and
related command execution functionality.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from ssh_agent_bridge import SSHService
from ssh_agent_bridge.exceptions import SessionError, CommandError, TimeoutError


@pytest.mark.unit
@pytest.mark.asyncio
class TestCommandExecution:
    """Test cases for command execution functionality."""

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

            assert result.status == "completed"
            assert result.exit_code == 0
            assert "command output" in result.stdout

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

            assert result.status == "completed"
            assert result.exit_code == 1
            assert "command failed" in result.stdout

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

            assert result.status == "partial"
            assert result.pending_marker.startswith("______END_MARKER_")

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

    async def test_run_command_invalid_session(self, ssh_service):
        """Test running command on invalid session."""
        with pytest.raises(SessionError, match="Session invalid does not exist"):
            await ssh_service.run_command("invalid", "ls", 5.0)

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
            assert partial_result.status == "partial"
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

            assert final_result.status == "completed"
            assert final_result.exit_code == 0

    async def _delay_output(self, session, text, delay):
        """Helper to add output to buffer after delay."""
        await asyncio.sleep(delay)
        async with session.condition:
            session.buffer += text
            session.condition.notify_all()

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
            assert partial_result.status == "partial"

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

    async def test_run_ephemeral_command_error(self, ssh_service, mock_asyncssh):
        """Test ephemeral command with non-zero exit code."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            # Mock command that fails
            mock_result = MagicMock()
            mock_result.stdout = "command failed"
            mock_result.stderr = "error occurred"
            mock_result.returncode = 1
            mock_asyncssh.connect.return_value.run.return_value = mock_result

            result = await ssh_service.run_ephemeral(
                agent_id="test-agent",
                host="example.com",
                command="failing_command",
                username="testuser",
                password="testpass",  # Add password for testing
                verify_host_key=False,  # Disable for testing
            )

            assert result.exit_code == 1
            assert "command failed" in result.stdout
            assert "error occurred" in result.stderr
            mock_asyncssh.connect.return_value.run.assert_called_once_with(
                "failing_command"
            )