"""
Integration tests for SSHService facade and component interactions.

Tests complete workflows and interactions between multiple components,
covering connection lifecycle, session management, command execution
output capture, and timeout/auth error handling.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from ssh_agent_bridge import SSHService
from ssh_agent_bridge.exceptions import (
    CommandError,
    ConnectionError,
    SessionError,
    SSHServiceError,
    TimeoutError,
)
from ssh_agent_bridge.types import CommandResult, PartialResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_asyncssh(stdout_lines=None, exit_code=0, run_stdout="", run_stderr=""):
    """Build a minimal asyncssh mock for integration tests.

    Args:
        stdout_lines: Sequence of byte strings to return from readline().
            Each call pops the next item; subsequent calls block forever.
        exit_code: Not used directly (marker-based detection is used instead).
        run_stdout: stdout for asyncssh.run() calls.
        run_stderr: stderr for asyncssh.run() calls.
    """
    mock_asyncssh = MagicMock()

    mock_conn = AsyncMock()
    mock_process = AsyncMock()

    # Build a readline() side-effect that drains the provided lines then
    # blocks indefinitely (simulating a live PTY that has no more output).
    lines = list(stdout_lines or [])
    call_idx = {"n": 0}

    async def _readline():
        idx = call_idx["n"]
        call_idx["n"] += 1
        if idx < len(lines):
            return lines[idx]
        # Block until the session is torn down
        await asyncio.sleep(10)
        return b""

    mock_stdout = AsyncMock()
    mock_stdout.readline = AsyncMock(side_effect=_readline)
    mock_process.stdout = mock_stdout

    mock_stdin = MagicMock()
    mock_stdin.write = MagicMock()
    mock_stdin.drain = AsyncMock()
    mock_process.stdin = mock_stdin

    mock_process.send_signal = AsyncMock()
    mock_process.kill = AsyncMock()
    mock_process.close = AsyncMock()

    mock_conn.create_process = AsyncMock(return_value=mock_process)
    mock_conn.close = AsyncMock()

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = run_stdout
    mock_result.stderr = run_stderr
    mock_conn.run = AsyncMock(return_value=mock_result)

    mock_asyncssh.connect = AsyncMock(return_value=mock_conn)
    mock_asyncssh.Error = Exception
    mock_asyncssh.SSHKnownHosts = MagicMock(return_value=MagicMock())

    return mock_asyncssh, mock_conn, mock_process


# ---------------------------------------------------------------------------
# Connection Lifecycle
# ---------------------------------------------------------------------------


class TestConnectionLifecycle:
    """Tests for SSH connection establishment and teardown."""

    @pytest.mark.asyncio
    async def test_service_initializes_empty(self):
        """SSHService starts with no connections or sessions."""
        service = SSHService()
        assert service._connections == {}
        assert service._sessions == {}

    @pytest.mark.asyncio
    async def test_create_session_establishes_connection(self):
        """create_session() opens an SSH connection and returns a session ID."""
        mock_asyncssh, mock_conn, _ = _make_mock_asyncssh()

        with patch("asyncssh.connect", mock_asyncssh.connect), \
             patch("asyncssh.SSHKnownHosts", mock_asyncssh.SSHKnownHosts):
            service = SSHService()
            session_id = await service.create_session(
                agent_id="agent-1",
                host="localhost",
                username="user",
                password="pass",
                verify_host_key=False,
            )

        assert session_id is not None
        assert session_id in service._sessions

    @pytest.mark.asyncio
    async def test_connection_pooled_across_sessions(self):
        """Two sessions for the same agent/host share one connection."""
        mock_asyncssh, mock_conn, mock_process = _make_mock_asyncssh()
        mock_conn.create_process = AsyncMock(return_value=mock_process)

        with patch("asyncssh.connect", mock_asyncssh.connect), \
             patch("asyncssh.SSHKnownHosts", mock_asyncssh.SSHKnownHosts):
            service = SSHService()
            s1 = await service.create_session(
                agent_id="agent-1", host="localhost", username="user",
                password="pass", verify_host_key=False,
            )
            s2 = await service.create_session(
                agent_id="agent-1", host="localhost", username="user",
                password="pass", verify_host_key=False,
            )

        assert mock_asyncssh.connect.call_count == 1
        assert service._sessions[s1].connection_info is service._sessions[s2].connection_info

    @pytest.mark.asyncio
    async def test_connection_requires_password_or_key(self):
        """create_session() raises ConnectionError with neither password nor key."""
        mock_asyncssh, _, _ = _make_mock_asyncssh()

        with patch("asyncssh.connect", mock_asyncssh.connect), \
             patch("asyncssh.SSHKnownHosts", mock_asyncssh.SSHKnownHosts):
            service = SSHService()
            with pytest.raises(ConnectionError, match="Either password or private_key"):
                await service.create_session(
                    agent_id="agent-1", host="localhost", username="user",
                    verify_host_key=False,
                )

    @pytest.mark.asyncio
    async def test_connection_failure_raises_connection_error(self):
        """Network failure during connect raises ConnectionError."""
        mock_asyncssh, _, _ = _make_mock_asyncssh()
        mock_asyncssh.connect.side_effect = Exception("Connection refused")

        with patch("asyncssh.connect", mock_asyncssh.connect), \
             patch("asyncssh.SSHKnownHosts", mock_asyncssh.SSHKnownHosts):
            service = SSHService()
            with pytest.raises(ConnectionError):
                await service.create_session(
                    agent_id="agent-1", host="bad-host", username="user",
                    password="pass", verify_host_key=False,
                )

    @pytest.mark.asyncio
    async def test_close_agent_connection_cleans_up(self):
        """close_agent_connection() removes sessions and connections for agent."""
        mock_asyncssh, mock_conn, _ = _make_mock_asyncssh()

        with patch("asyncssh.connect", mock_asyncssh.connect), \
             patch("asyncssh.SSHKnownHosts", mock_asyncssh.SSHKnownHosts):
            service = SSHService()
            session_id = await service.create_session(
                agent_id="agent-1", host="localhost", username="user",
                password="pass", verify_host_key=False,
            )

            await service.close_agent_connection("agent-1")

        # All agent-1 sessions should be closed
        for sid, sess in service._sessions.items():
            if sess.agent_id == "agent-1":
                assert sess.status != "active"

    @pytest.mark.asyncio
    async def test_shutdown_clears_all_state(self):
        """shutdown() clears all connections, sessions, and locks."""
        mock_asyncssh, _, _ = _make_mock_asyncssh()

        with patch("asyncssh.connect", mock_asyncssh.connect), \
             patch("asyncssh.SSHKnownHosts", mock_asyncssh.SSHKnownHosts):
            service = SSHService()
            await service.create_session(
                agent_id="agent-1", host="localhost", username="user",
                password="pass", verify_host_key=False,
            )

            await service.shutdown()

        assert service._connections == {}
        assert service._connection_locks == {}
        assert service._session_locks == {}


# ---------------------------------------------------------------------------
# Session Management
# ---------------------------------------------------------------------------


class TestSessionManagement:
    """Tests for session lifecycle and state transitions."""

    @pytest.mark.asyncio
    async def test_session_starts_active(self):
        """Newly created session has status='active'."""
        mock_asyncssh, _, _ = _make_mock_asyncssh()

        with patch("asyncssh.connect", mock_asyncssh.connect), \
             patch("asyncssh.SSHKnownHosts", mock_asyncssh.SSHKnownHosts):
            service = SSHService()
            session_id = await service.create_session(
                agent_id="agent-1", host="localhost", username="user",
                password="pass", verify_host_key=False,
            )

        assert service._sessions[session_id].status == "active"

    @pytest.mark.asyncio
    async def test_end_session_marks_closed(self):
        """end_session() transitions session status to 'closed'."""
        mock_asyncssh, _, _ = _make_mock_asyncssh()

        with patch("asyncssh.connect", mock_asyncssh.connect), \
             patch("asyncssh.SSHKnownHosts", mock_asyncssh.SSHKnownHosts):
            service = SSHService()
            session_id = await service.create_session(
                agent_id="agent-1", host="localhost", username="user",
                password="pass", verify_host_key=False,
            )
            await service.end_session(session_id)

        assert service._sessions[session_id].status == "closed"

    @pytest.mark.asyncio
    async def test_end_session_nonexistent_raises(self):
        """end_session() raises SessionError for unknown session ID."""
        service = SSHService()
        with pytest.raises(SessionError):
            await service.end_session("nonexistent-id")

    @pytest.mark.asyncio
    async def test_end_session_twice_raises(self):
        """end_session() on an already-closed session raises SessionError."""
        mock_asyncssh, _, _ = _make_mock_asyncssh()

        with patch("asyncssh.connect", mock_asyncssh.connect), \
             patch("asyncssh.SSHKnownHosts", mock_asyncssh.SSHKnownHosts):
            service = SSHService()
            session_id = await service.create_session(
                agent_id="agent-1", host="localhost", username="user",
                password="pass", verify_host_key=False,
            )
            await service.end_session(session_id)
            with pytest.raises(SessionError):
                await service.end_session(session_id)

    @pytest.mark.asyncio
    async def test_close_session_removes_from_sessions(self):
        """close_session() (hard close) removes the session from the dict."""
        mock_asyncssh, _, _ = _make_mock_asyncssh()

        with patch("asyncssh.connect", mock_asyncssh.connect), \
             patch("asyncssh.SSHKnownHosts", mock_asyncssh.SSHKnownHosts):
            service = SSHService()
            session_id = await service.create_session(
                agent_id="agent-1", host="localhost", username="user",
                password="pass", verify_host_key=False,
            )
            await service.close_session(session_id)

        assert session_id not in service._sessions

    @pytest.mark.asyncio
    async def test_list_sessions_returns_active_sessions(self):
        """list_sessions() returns only active sessions by default."""
        mock_asyncssh, _, mock_process = _make_mock_asyncssh()
        mock_conn = mock_asyncssh.connect.return_value

        with patch("asyncssh.connect", mock_asyncssh.connect), \
             patch("asyncssh.SSHKnownHosts", mock_asyncssh.SSHKnownHosts):
            service = SSHService()
            s1 = await service.create_session(
                agent_id="agent-1", host="localhost", username="user",
                password="pass", verify_host_key=False,
            )
            s2 = await service.create_session(
                agent_id="agent-1", host="localhost", username="user",
                password="pass", verify_host_key=False,
            )
            await service.end_session(s2)
            sessions = await service.list_sessions("agent-1")

        session_ids = [s.session_id for s in sessions]
        assert s1 in session_ids
        assert s2 not in session_ids

    @pytest.mark.asyncio
    async def test_list_sessions_include_closed(self):
        """list_sessions(include_closed=True) returns closed sessions too."""
        mock_asyncssh, _, _ = _make_mock_asyncssh()

        with patch("asyncssh.connect", mock_asyncssh.connect), \
             patch("asyncssh.SSHKnownHosts", mock_asyncssh.SSHKnownHosts):
            service = SSHService()
            s1 = await service.create_session(
                agent_id="agent-1", host="localhost", username="user",
                password="pass", verify_host_key=False,
            )
            await service.end_session(s1)
            sessions = await service.list_sessions("agent-1", include_closed=True)

        assert any(s.session_id == s1 for s in sessions)

    @pytest.mark.asyncio
    async def test_multiple_agents_isolated(self):
        """Sessions for different agents are completely isolated."""
        mock_asyncssh, _, _ = _make_mock_asyncssh()
        # Two independent connections for two agents
        mock_asyncssh.connect = AsyncMock(
            side_effect=[
                mock_asyncssh.connect.return_value,
                AsyncMock(**{
                    "create_process": AsyncMock(return_value=_make_mock_asyncssh()[2]),
                    "close": AsyncMock(),
                    "run": AsyncMock(return_value=MagicMock(returncode=0, stdout="", stderr="")),
                }),
            ]
        )

        with patch("asyncssh.connect", mock_asyncssh.connect), \
             patch("asyncssh.SSHKnownHosts", mock_asyncssh.SSHKnownHosts):
            service = SSHService()
            s_a = await service.create_session(
                agent_id="agent-A", host="localhost", username="user",
                password="pass", verify_host_key=False,
            )
            s_b = await service.create_session(
                agent_id="agent-B", host="localhost", username="user",
                password="pass", verify_host_key=False,
            )

        a_sessions = await service.list_sessions("agent-A")
        b_sessions = await service.list_sessions("agent-B")
        assert all(s.session_id == s_a for s in a_sessions)
        assert all(s.session_id == s_b for s in b_sessions)


# ---------------------------------------------------------------------------
# Command Execution Output Capture
# ---------------------------------------------------------------------------


class TestCommandExecution:
    """Tests for command execution and output capture."""

    @pytest.mark.asyncio
    async def test_run_command_captures_output(self):
        """run_command() returns CommandResult with stdout from the session."""
        marker_placeholder = "______END_MARKER_"

        # We'll inject the marker output after run_command writes the marked command.
        # Since we can't know the marker in advance, we simulate it by patching
        # _wait_for_marker to return a known result.
        mock_asyncssh, _, _ = _make_mock_asyncssh()

        with patch("asyncssh.connect", mock_asyncssh.connect), \
             patch("asyncssh.SSHKnownHosts", mock_asyncssh.SSHKnownHosts):
            service = SSHService()
            session_id = await service.create_session(
                agent_id="agent-1", host="localhost", username="user",
                password="pass", verify_host_key=False,
            )

            # Patch _wait_for_marker to return a successful result
            expected = CommandResult(status="completed", exit_code=0, stdout="hello\n", stderr=None)
            with patch.object(service, "_wait_for_marker", AsyncMock(return_value=expected)):
                result = await service.run_command(session_id, "echo hello")

        assert isinstance(result, CommandResult)
        assert result.exit_code == 0
        assert result.stdout == "hello\n"

    @pytest.mark.asyncio
    async def test_run_command_nonzero_exit_code(self):
        """run_command() reports non-zero exit codes from marker."""
        mock_asyncssh, _, _ = _make_mock_asyncssh()

        with patch("asyncssh.connect", mock_asyncssh.connect), \
             patch("asyncssh.SSHKnownHosts", mock_asyncssh.SSHKnownHosts):
            service = SSHService()
            session_id = await service.create_session(
                agent_id="agent-1", host="localhost", username="user",
                password="pass", verify_host_key=False,
            )

            failed = CommandResult(status="completed", exit_code=1, stdout="", stderr=None)
            with patch.object(service, "_wait_for_marker", AsyncMock(return_value=failed)):
                result = await service.run_command(session_id, "false")

        assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_run_command_on_closed_session_raises(self):
        """run_command() on a closed session raises SessionError."""
        mock_asyncssh, _, _ = _make_mock_asyncssh()

        with patch("asyncssh.connect", mock_asyncssh.connect), \
             patch("asyncssh.SSHKnownHosts", mock_asyncssh.SSHKnownHosts):
            service = SSHService()
            session_id = await service.create_session(
                agent_id="agent-1", host="localhost", username="user",
                password="pass", verify_host_key=False,
            )
            await service.end_session(session_id)

            with pytest.raises(SessionError):
                await service.run_command(session_id, "echo hello")

    @pytest.mark.asyncio
    async def test_run_command_on_unknown_session_raises(self):
        """run_command() on an unknown session ID raises SessionError."""
        service = SSHService()
        with pytest.raises(SessionError):
            await service.run_command("no-such-session", "echo hello")

    @pytest.mark.asyncio
    async def test_run_command_increments_command_count(self):
        """Each run_command() call increments session command_count."""
        mock_asyncssh, _, _ = _make_mock_asyncssh()
        ok = CommandResult(status="completed", exit_code=0, stdout="", stderr=None)

        with patch("asyncssh.connect", mock_asyncssh.connect), \
             patch("asyncssh.SSHKnownHosts", mock_asyncssh.SSHKnownHosts):
            service = SSHService()
            session_id = await service.create_session(
                agent_id="agent-1", host="localhost", username="user",
                password="pass", verify_host_key=False,
            )

            with patch.object(service, "_wait_for_marker", AsyncMock(return_value=ok)):
                await service.run_command(session_id, "echo 1")
                await service.run_command(session_id, "echo 2")

        assert service._sessions[session_id].command_count == 2

    @pytest.mark.asyncio
    async def test_run_command_records_history(self):
        """run_command() records input messages in session history."""
        mock_asyncssh, _, _ = _make_mock_asyncssh()
        ok = CommandResult(status="completed", exit_code=0, stdout="out\n", stderr=None)

        with patch("asyncssh.connect", mock_asyncssh.connect), \
             patch("asyncssh.SSHKnownHosts", mock_asyncssh.SSHKnownHosts):
            service = SSHService()
            session_id = await service.create_session(
                agent_id="agent-1", host="localhost", username="user",
                password="pass", verify_host_key=False,
            )

            with patch.object(service, "_wait_for_marker", AsyncMock(return_value=ok)):
                await service.run_command(session_id, "echo hello")

        session = service._sessions[session_id]
        input_msgs = [m for m in session.history if m.direction == "input"]
        assert any("echo hello" in m.content for m in input_msgs)

    @pytest.mark.asyncio
    async def test_send_input_appends_to_history(self):
        """send_input() records the input message and forwards text to stdin."""
        mock_asyncssh, _, _ = _make_mock_asyncssh()

        with patch("asyncssh.connect", mock_asyncssh.connect), \
             patch("asyncssh.SSHKnownHosts", mock_asyncssh.SSHKnownHosts):
            service = SSHService()
            session_id = await service.create_session(
                agent_id="agent-1", host="localhost", username="user",
                password="pass", verify_host_key=False,
            )
            await service.send_input(session_id, "interactive text")

        session = service._sessions[session_id]
        input_msgs = [m for m in session.history if m.direction == "input"]
        assert any("interactive text" in m.content for m in input_msgs)

    @pytest.mark.asyncio
    async def test_run_ephemeral_returns_result(self):
        """run_ephemeral() runs a single command and returns CommandResult."""
        mock_asyncssh, _, _ = _make_mock_asyncssh(run_stdout="ephemeral output", run_stderr="")

        with patch("asyncssh.connect", mock_asyncssh.connect), \
             patch("asyncssh.SSHKnownHosts", mock_asyncssh.SSHKnownHosts):
            service = SSHService()
            result = await service.run_ephemeral(
                agent_id="agent-1",
                host="localhost",
                command="echo ephemeral",
                username="user",
                password="pass",
                verify_host_key=False,
            )

        assert isinstance(result, CommandResult)
        assert result.stdout == "ephemeral output"
        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_get_session_history_filters_by_direction(self):
        """get_session_history() can filter to input-only or output-only messages."""
        mock_asyncssh, _, _ = _make_mock_asyncssh()
        ok = CommandResult(status="completed", exit_code=0, stdout="", stderr=None)

        with patch("asyncssh.connect", mock_asyncssh.connect), \
             patch("asyncssh.SSHKnownHosts", mock_asyncssh.SSHKnownHosts):
            service = SSHService()
            session_id = await service.create_session(
                agent_id="agent-1", host="localhost", username="user",
                password="pass", verify_host_key=False,
            )

            with patch.object(service, "_wait_for_marker", AsyncMock(return_value=ok)):
                await service.run_command(session_id, "echo hi")

            hist = await service.get_session_history(session_id, direction="input")

        assert all(m.direction == "input" for m in hist.messages)


# ---------------------------------------------------------------------------
# Timeout and Auth Error Handling
# ---------------------------------------------------------------------------


class TestTimeoutAndAuthErrors:
    """Tests for timeout handling and authentication error paths."""

    @pytest.mark.asyncio
    async def test_run_command_returns_partial_on_short_timeout(self):
        """run_command() returns PartialResult when short_timeout < 1.0 and marker not found."""
        mock_asyncssh, _, _ = _make_mock_asyncssh()

        with patch("asyncssh.connect", mock_asyncssh.connect), \
             patch("asyncssh.SSHKnownHosts", mock_asyncssh.SSHKnownHosts):
            service = SSHService()
            session_id = await service.create_session(
                agent_id="agent-1", host="localhost", username="user",
                password="pass", verify_host_key=False,
            )

            # Make _wait_for_marker return a PartialResult (short timeout path)
            partial = PartialResult(status="partial", stdout="partial out", pending_marker="MARKER_x")
            with patch.object(service, "_wait_for_marker", AsyncMock(return_value=partial)):
                result = await service.run_command(session_id, "long_command", short_timeout=0.5)

        assert isinstance(result, PartialResult)
        assert result.pending_marker == "MARKER_x"

    @pytest.mark.asyncio
    async def test_get_remaining_output_after_partial(self):
        """get_remaining_output() resolves a PartialResult to a CommandResult."""
        mock_asyncssh, _, _ = _make_mock_asyncssh()

        with patch("asyncssh.connect", mock_asyncssh.connect), \
             patch("asyncssh.SSHKnownHosts", mock_asyncssh.SSHKnownHosts):
            service = SSHService()
            session_id = await service.create_session(
                agent_id="agent-1", host="localhost", username="user",
                password="pass", verify_host_key=False,
            )

            # Manually plant the marker in the session so get_remaining_output
            # considers it valid.
            marker = "______END_MARKER_abc123______"
            service._sessions[session_id].markers.add(marker)

            finished = CommandResult(status="completed", exit_code=0, stdout="done\n", stderr=None)
            with patch.object(service, "_wait_for_marker", AsyncMock(return_value=finished)):
                result = await service.get_remaining_output(session_id, marker, timeout=5.0)

        assert isinstance(result, CommandResult)
        assert result.stdout == "done\n"

    @pytest.mark.asyncio
    async def test_get_remaining_output_timeout_raises(self):
        """get_remaining_output() raises TimeoutError when marker never arrives."""
        mock_asyncssh, _, _ = _make_mock_asyncssh()

        with patch("asyncssh.connect", mock_asyncssh.connect), \
             patch("asyncssh.SSHKnownHosts", mock_asyncssh.SSHKnownHosts):
            service = SSHService()
            session_id = await service.create_session(
                agent_id="agent-1", host="localhost", username="user",
                password="pass", verify_host_key=False,
            )

            marker = "______END_MARKER_timeout______"
            service._sessions[session_id].markers.add(marker)

            still_partial = PartialResult(status="partial", stdout="", pending_marker=marker)
            with patch.object(service, "_wait_for_marker", AsyncMock(return_value=still_partial)):
                with pytest.raises(TimeoutError):
                    await service.get_remaining_output(session_id, marker, timeout=1.0)

    @pytest.mark.asyncio
    async def test_auth_failure_raises_connection_error(self):
        """Authentication failure propagates as ConnectionError."""
        import asyncssh as real_asyncssh

        mock_asyncssh, _, _ = _make_mock_asyncssh()

        # Simulate asyncssh raising an auth-like error
        class FakeSSHError(Exception):
            pass

        mock_asyncssh.connect.side_effect = FakeSSHError("Authentication failed")
        mock_asyncssh.Error = FakeSSHError

        with patch("asyncssh.connect", mock_asyncssh.connect), \
             patch("asyncssh.Error", FakeSSHError), \
             patch("asyncssh.SSHKnownHosts", mock_asyncssh.SSHKnownHosts):
            service = SSHService()
            with pytest.raises(ConnectionError, match="Authentication failed"):
                await service.create_session(
                    agent_id="agent-1",
                    host="localhost",
                    username="user",
                    password="wrong",
                    verify_host_key=False,
                )

    @pytest.mark.asyncio
    async def test_run_ephemeral_timeout_raises(self):
        """run_ephemeral() raises TimeoutError when the command exceeds timeout."""
        mock_asyncssh, mock_conn, _ = _make_mock_asyncssh()

        async def _slow_run(_cmd):
            await asyncio.sleep(10)
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_conn.run = AsyncMock(side_effect=_slow_run)

        with patch("asyncssh.connect", mock_asyncssh.connect), \
             patch("asyncssh.SSHKnownHosts", mock_asyncssh.SSHKnownHosts):
            service = SSHService()
            with pytest.raises(TimeoutError):
                await service.run_ephemeral(
                    agent_id="agent-1",
                    host="localhost",
                    command="sleep 10",
                    username="user",
                    password="pass",
                    timeout=0.05,
                    verify_host_key=False,
                )

    @pytest.mark.asyncio
    async def test_send_signal_on_active_session(self):
        """send_signal() forwards signal to the session process."""
        mock_asyncssh, _, mock_process = _make_mock_asyncssh()

        with patch("asyncssh.connect", mock_asyncssh.connect), \
             patch("asyncssh.SSHKnownHosts", mock_asyncssh.SSHKnownHosts):
            service = SSHService()
            session_id = await service.create_session(
                agent_id="agent-1", host="localhost", username="user",
                password="pass", verify_host_key=False,
            )
            await service.send_signal(session_id, "SIGINT")

        mock_process.send_signal.assert_called_once_with(2)

    @pytest.mark.asyncio
    async def test_send_signal_on_closed_session_raises(self):
        """send_signal() on a closed session raises SessionError."""
        mock_asyncssh, _, _ = _make_mock_asyncssh()

        with patch("asyncssh.connect", mock_asyncssh.connect), \
             patch("asyncssh.SSHKnownHosts", mock_asyncssh.SSHKnownHosts):
            service = SSHService()
            session_id = await service.create_session(
                agent_id="agent-1", host="localhost", username="user",
                password="pass", verify_host_key=False,
            )
            await service.end_session(session_id)

            with pytest.raises(SessionError):
                await service.send_signal(session_id, "SIGTERM")

    @pytest.mark.asyncio
    async def test_private_key_missing_raises_connection_error(self):
        """Providing a non-existent private key path raises ConnectionError."""
        mock_asyncssh, _, _ = _make_mock_asyncssh()

        with patch("asyncssh.connect", mock_asyncssh.connect), \
             patch("asyncssh.SSHKnownHosts", mock_asyncssh.SSHKnownHosts):
            service = SSHService()
            with pytest.raises(ConnectionError, match="does not exist"):
                await service.create_session(
                    agent_id="agent-1",
                    host="localhost",
                    username="user",
                    private_key="/nonexistent/key.pem",
                    verify_host_key=False,
                )


# ---------------------------------------------------------------------------
# Integrated Workflow Tests
# ---------------------------------------------------------------------------


class TestIntegratedWorkflows:
    """End-to-end workflow tests combining multiple SSHService operations."""

    @pytest.mark.asyncio
    async def test_full_session_workflow(self):
        """Create session → run commands → list sessions → end session."""
        mock_asyncssh, _, _ = _make_mock_asyncssh()
        ok = CommandResult(status="completed", exit_code=0, stdout="output\n", stderr=None)

        with patch("asyncssh.connect", mock_asyncssh.connect), \
             patch("asyncssh.SSHKnownHosts", mock_asyncssh.SSHKnownHosts):
            service = SSHService()

            session_id = await service.create_session(
                agent_id="agent-1", host="localhost", username="user",
                password="pass", verify_host_key=False,
            )
            assert session_id in service._sessions

            with patch.object(service, "_wait_for_marker", AsyncMock(return_value=ok)):
                r1 = await service.run_command(session_id, "echo first")
                r2 = await service.run_command(session_id, "echo second")

            assert r1.exit_code == 0
            assert r2.exit_code == 0

            sessions = await service.list_sessions("agent-1")
            assert len(sessions) == 1

            await service.end_session(session_id)
            assert service._sessions[session_id].status == "closed"

    @pytest.mark.asyncio
    async def test_multiple_sessions_independent_history(self):
        """Commands on different sessions go into their own history."""
        mock_asyncssh, _, mock_process = _make_mock_asyncssh()
        mock_asyncssh.connect.return_value.create_process = AsyncMock(return_value=mock_process)
        ok = CommandResult(status="completed", exit_code=0, stdout="", stderr=None)

        with patch("asyncssh.connect", mock_asyncssh.connect), \
             patch("asyncssh.SSHKnownHosts", mock_asyncssh.SSHKnownHosts):
            service = SSHService()
            s1 = await service.create_session(
                agent_id="agent-1", host="localhost", username="user",
                password="pass", verify_host_key=False,
            )
            s2 = await service.create_session(
                agent_id="agent-1", host="localhost", username="user",
                password="pass", verify_host_key=False,
            )

            with patch.object(service, "_wait_for_marker", AsyncMock(return_value=ok)):
                await service.run_command(s1, "cmd_for_s1")
                await service.run_command(s2, "cmd_for_s2")

        h1 = [m.content for m in service._sessions[s1].history if m.direction == "input"]
        h2 = [m.content for m in service._sessions[s2].history if m.direction == "input"]
        assert any("cmd_for_s1" in c for c in h1)
        assert not any("cmd_for_s2" in c for c in h1)
        assert any("cmd_for_s2" in c for c in h2)
        assert not any("cmd_for_s1" in c for c in h2)

    @pytest.mark.asyncio
    async def test_ephemeral_does_not_leave_session(self):
        """run_ephemeral() should not leave a persistent session behind."""
        mock_asyncssh, _, _ = _make_mock_asyncssh(run_stdout="ok", run_stderr="")

        with patch("asyncssh.connect", mock_asyncssh.connect), \
             patch("asyncssh.SSHKnownHosts", mock_asyncssh.SSHKnownHosts):
            service = SSHService()
            await service.run_ephemeral(
                agent_id="agent-1", host="localhost", command="whoami",
                username="user", password="pass", verify_host_key=False,
            )

        # run_ephemeral does not create a session
        assert len(service._sessions) == 0
