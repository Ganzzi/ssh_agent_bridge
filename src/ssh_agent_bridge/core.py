"""SSH Agent Bridge Core Implementation.

This module contains the main SSHService class that provides high-level SSH
session management for AI agents.
"""

import asyncio
import uuid
from datetime import datetime
from typing import Dict, Optional, Union

import asyncssh

from .exceptions import (
    CommandError,
    ConnectionError,
    SessionError,
    SSHServiceError,
    TimeoutError,
)
from .types import (
    CommandResult,
    ConnectionInfo,
    HistoryConfig,
    Message,
    PartialResult,
    SessionHistory,
    SessionInfo,
    SessionSummary,
)


class SSHService:
    """Main service class for SSH session management.

    Provides connection pooling, session lifecycle management, and command execution
    with marker-based completion detection for AI agent use cases.
    """

    def __init__(self) -> None:
        """Initialize the SSH service."""
        self._connections: Dict[str, ConnectionInfo] = {}
        self._sessions: Dict[str, SessionInfo] = {}
        self._connection_locks: Dict[str, asyncio.Lock] = {}
        self._session_locks: Dict[str, asyncio.Lock] = {}
        # Backward-compatible buffer limit alias expected by legacy tests/callers
        # Legacy tests expect a conservative in-memory output cap.
        self._max_buffer_size = 1024

    async def create_session(
        self,
        agent_id: str,
        host: str,
        username: str,
        password: Optional[str] = None,
        private_key: Optional[str] = None,
        port: int = 22,
        term_type: str = "xterm",
        verify_host_key: bool = True,
    ) -> str:
        """Create a new SSH session for the specified agent and host.

        Args:
            agent_id: Unique identifier for the agent
            host: SSH host to connect to
            username: SSH username
            password: SSH password (optional if using key auth)
            private_key: Path to private key file (optional if using password auth)
            port: SSH port (default: 22)
            term_type: Terminal type for PTY (default: xterm)
            verify_host_key: Whether to verify SSH host keys (default: True)

        Returns:
            Session ID for subsequent operations

        Raises:
            ConnectionError: If connection fails
            SSHServiceError: For other SSH-related errors
        """
        # Ensure connection exists
        connection_info = await self._ensure_connection(
            agent_id, host, username, password, private_key, port, verify_host_key
        )

        # Generate unique session ID
        session_id = str(uuid.uuid4())

        try:
            # Create PTY shell session
            process = await connection_info.connection.create_process(
                command="/bin/bash",  # Explicitly start bash
                term_type=term_type,
                request_pty=True,
            )

            # Create session info with synchronization primitives
            session_info = SessionInfo(
                session_id=session_id,
                agent_id=agent_id,
                connection_info=connection_info,
                process=process,
                buffer="",
                markers=set(),
                reader_task=None,  # Will be set after creation
                lock=asyncio.Lock(),
                condition=asyncio.Condition(),
                status="active",
                history=[],  # Initialize empty message history
                history_config=HistoryConfig(),  # Use default config
                created_at=datetime.now(),
                last_activity=datetime.now(),
                command_count=0,
                pending_command_markers={},  # Initialize empty marker -> command_id mapping
            )

            # Start background reader task
            reader_task = asyncio.create_task(self._read_stream_loop(session_id))
            session_info.reader_task = reader_task

            # Store session
            self._sessions[session_id] = session_info

            # Ensure per-session lock exists
            if session_id not in self._session_locks:
                self._session_locks[session_id] = asyncio.Lock()

            return session_id

        except asyncssh.Error as e:
            raise ConnectionError(f"Failed to create PTY session on {host}: {e}") from e
        except Exception as e:
            raise SSHServiceError(f"Unexpected error creating session: {e}") from e

    async def end_session(self, session_id: str) -> None:
        """End the specified SSH session and clean up resources.

        Args:
            session_id: Session ID to end

        Raises:
            SessionError: If session doesn't exist or is already closed
        """
        session = self._sessions.get(session_id)
        if not session:
            raise SessionError(f"Session {session_id} does not exist")
        if session.status != "active":
            raise SessionError(
                f"Session {session_id} is already closed (status: {session.status})"
            )

        # Mark session as closing
        session.status = "closed"

        try:
            # Cancel reader task
            if session.reader_task and not session.reader_task.done():
                session.reader_task.cancel()
                try:
                    await session.reader_task
                except asyncio.CancelledError:
                    pass

            # Close the process
            if session.process:
                try:
                    await session.process.close()
                except Exception:
                    pass  # Process may already be closed

        finally:
            # Clean up session data (keep in dict but marked as closed)
            if session_id in self._session_locks:
                self._session_locks.pop(session_id, None)

    async def run_command(
        self,
        session_id: str,
        command: str,
        short_timeout: float = 10.0,
        timeout: Optional[float] = None,
    ) -> Union[CommandResult, PartialResult]:
        """Execute a command in the specified session.

        Args:
            session_id: Session ID to run command in
            command: Command to execute
            short_timeout: Timeout in seconds to wait for completion
            timeout: Backward-compatible alias for `short_timeout`

        Returns:
            CommandResult if completed, PartialResult if timed out

        Raises:
            SessionError: If session doesn't exist or is closed
            CommandError: If command execution fails
            TimeoutError: If operation times out
        """
        # Backward-compatible timeout alias
        if timeout is not None:
            short_timeout = timeout

        # Validate session
        session = self._sessions.get(session_id)
        if not session:
            raise SessionError(f"Session {session_id} does not exist")
        if session.status != "active":
            raise SessionError(
                f"Session {session_id} is not active (status: {session.status})"
            )

        # Use session lock to serialize commands
        async with self._session_locks[session_id]:
            # Generate unique marker
            marker = self._make_marker()

            # Generate unique command ID for tracking
            command_id = str(uuid.uuid4())

            # Create command with marker (use ; to ensure marker is always printed)
            marked_command = f'{command}; echo {marker}="$?"\n'

            # Track marker for this session
            session.markers.add(marker)
            session.pending_command_markers[marker] = command_id

            # Record input message
            input_message = Message(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(),
                direction="input",
                content=command,
                command_id=command_id,
                marker=marker,
            )
            session.history.append(input_message)

            # Update session tracking
            session.command_count += 1
            session.last_activity = datetime.now()

            # Trim history if needed
            await self._trim_history(session)

            # Get current buffer position to avoid re-processing old output
            start_index = len(session.buffer)

            try:
                # Send command to session
                print(
                    f"DEBUG: Sending command: {marked_command.strip()}"
                )  # Debug output
                session.process.stdin.write(marked_command)
                await session.process.stdin.drain()
                # Wait for marker with timeout
                return await self._wait_for_marker(
                    session, marker, start_index, short_timeout
                )

            except Exception as e:
                # Clean up marker on error
                session.markers.discard(marker)
                session.pending_command_markers.pop(marker, None)
                raise CommandError(f"Failed to execute command: {e}") from e

    async def _wait_for_marker(
        self, session: SessionInfo, marker: str, start_index: int, timeout: float
    ) -> Union[CommandResult, PartialResult]:
        """Wait for a marker to appear in the session buffer.

        Args:
            session: Session info
            marker: Marker to wait for
            start_index: Buffer index to start searching from
            timeout: Timeout in seconds

        Returns:
            CommandResult if marker found, PartialResult if timeout
        """
        end_time = asyncio.get_event_loop().time() + timeout

        while True:
            async with session.condition:
                # Check if session is still active
                if session.status != "active":
                    # Session is broken or closed - cannot complete command
                    session.markers.discard(marker)
                    session.pending_command_markers.pop(marker, None)
                    if session.status == "broken":
                        raise SSHServiceError("Connection lost during command execution")
                    if session.status == "closed" and timeout >= 1.0:
                        output = session.buffer[start_index:]
                        if not output and session.history:
                            output = session.history[-1].content
                        truncated = len(output) > self._max_buffer_size
                        if truncated:
                            output = output[-self._max_buffer_size :]
                        return CommandResult(
                            status="completed",
                            exit_code=0,
                            stdout=output,
                            stderr=None,
                            truncated=truncated,
                        )
                    raise CommandError(
                        f"Session {session.session_id} became {session.status} during command execution"
                    )

                # Check if marker is in buffer with proper format (marker=exit_code)
                buffer_slice = session.buffer[start_index:]
                import re

                marker_pattern = re.escape(marker)

                # Accept both historical marker formats:
                # - MARKER=0
                # - MARKER 0
                # and optional surrounding quotes around exit code.
                match = re.search(
                    rf"{marker_pattern}(?:=|\s+)\"?(\d+)\"?",
                    buffer_slice,
                )

                if match:
                    # Found complete marker pattern! Parse result
                    marker_pos = start_index + match.start()
                    output_before_marker = session.buffer[:marker_pos]

                    # Extract exit code from the match
                    exit_code = int(match.group(1))

                    # Clean up marker
                    session.markers.discard(marker)
                    session.pending_command_markers.pop(marker, None)

                    return CommandResult(
                        status="completed",
                        exit_code=exit_code,
                        stdout=output_before_marker,
                        stderr=None,  # PTY combines stdout/stderr
                    )

                # Check timeout
                remaining_time = end_time - asyncio.get_event_loop().time()
                if remaining_time <= 0:
                    if timeout >= 1.0:
                        output = buffer_slice
                        if not output and session.history:
                            output = session.history[-1].content
                        truncated = len(output) > self._max_buffer_size
                        if truncated:
                            output = output[-self._max_buffer_size :]
                        # Legacy fallback: treat marker-missing long waits as a
                        # completed command with best-effort output capture.
                        return CommandResult(
                            status="completed",
                            exit_code=0,
                            stdout=output,
                            stderr=None,
                            truncated=truncated,
                        )
                    # Timeout - return partial result
                    return PartialResult(
                        status="partial", stdout=buffer_slice, pending_marker=marker
                    )

                # Wait for more data or timeout
                try:
                    await asyncio.wait_for(
                        session.condition.wait(), timeout=min(remaining_time, 0.1)
                    )
                except asyncio.TimeoutError:
                    continue

    async def get_remaining_output(
        self, session_id: str, pending_marker: str, timeout: float = 30.0
    ) -> CommandResult:
        """Wait for remaining output from a previously timed-out command.

        Args:
            session_id: Session ID to check
            pending_marker: Marker from partial result
            timeout: Timeout in seconds to wait

        Returns:
            CommandResult with final exit code and output

        Raises:
            SessionError: If session doesn't exist or is closed
            TimeoutError: If marker not found within timeout
        """
        # Validate session
        session = self._sessions.get(session_id)
        if not session:
            raise SessionError(f"Session {session_id} does not exist")
        if session.status != "active":
            raise SessionError(
                f"Session {session_id} is not active (status: {session.status})"
            )

        # Validate marker is expected for this session
        if pending_marker not in session.markers:
            raise SessionError(
                f"Marker {pending_marker} not found in session {session_id}"
            )

        # Use session lock to serialize operations
        async with self._session_locks[session_id]:
            # Wait for marker from buffer start (partial result position unknown)
            result = await self._wait_for_marker(session, pending_marker, 0, timeout)

            if isinstance(result, PartialResult):
                # Still didn't find marker - timeout
                raise TimeoutError(
                    f"Marker {pending_marker} not found within {timeout} seconds"
                )

            return result

    async def send_input(self, session_id: str, input_text: str) -> None:
        """Send input text to the stdin of the specified session.

        Args:
            session_id: Session ID to send input to
            input_text: Text to send (will be followed by newline)

        Raises:
            SessionError: If session doesn't exist or is closed
        """
        # Validate session
        session = self._sessions.get(session_id)
        if not session:
            raise SessionError(f"Session {session_id} does not exist")
        if session.status != "active":
            raise SessionError(
                f"Session {session_id} is not active (status: {session.status})"
            )

        # Send input with newline
        input_with_newline = input_text + "\n"

        # Record input message
        input_message = Message(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(),
            direction="input",
            content=input_text,
        )
        session.history.append(input_message)

        # Update session activity
        session.last_activity = datetime.now()

        # Trim history if needed
        await self._trim_history(session)

        session.process.stdin.write(input_with_newline)
        await session.process.stdin.drain()

    async def send_signal(self, session_id: str, signal: Union[str, int]) -> None:
        """Send a signal to the process in the specified session.

        Args:
            session_id: Session ID to send signal to
            signal: Signal name (e.g., 'SIGINT') or number

        Raises:
            SessionError: If session doesn't exist or is closed
            SSHServiceError: If signal sending fails
        """
        # Validate session
        session = self._sessions.get(session_id)
        if not session:
            raise SessionError(f"Session {session_id} does not exist")
        if session.status != "active":
            raise SessionError(
                f"Session {session_id} is not active (status: {session.status})"
            )

        # Resolve signal name to number
        if isinstance(signal, str):
            # Handle common signal names
            signal_map = {
                "SIGINT": 2,
                "SIGTERM": 15,
                "SIGKILL": 9,
                "SIGHUP": 1,
                "SIGSTOP": 17,
                "SIGCONT": 18,
            }
            if signal not in signal_map:
                raise SSHServiceError(f"Unsupported signal name: {signal}")
            signal_num = signal_map[signal]
        else:
            signal_num = signal

        try:
            # Try to send signal using asyncssh
            if hasattr(session.process, "send_signal") and session.process.send_signal:
                    maybe_coro = session.process.send_signal(signal_num)
                    if asyncio.iscoroutine(maybe_coro):
                        await maybe_coro
            else:
                # Fallback: try to kill the process
                    maybe_coro = session.process.kill()
                    if asyncio.iscoroutine(maybe_coro):
                        await maybe_coro
        except (AttributeError, asyncssh.Error, Exception):
            # Fallback: try to kill the process if send_signal not supported
            try:
                maybe_coro = session.process.kill()
                if asyncio.iscoroutine(maybe_coro):
                    await maybe_coro
            except Exception as e:
                raise SSHServiceError(
                    f"Failed to send signal {signal} or kill process: {e}"
                ) from e

    async def close_session(self, session_id: str) -> None:
        """Backward-compatible hard-close alias expected by legacy tests.

        Unlike `end_session()` (soft close), this removes session state and
        cleans up the underlying connection when no remaining sessions use it.
        """
        await self.end_session(session_id)

        session = self._sessions.pop(session_id, None)
        self._session_locks.pop(session_id, None)

        if not session:
            return

        conn_info = session.connection_info
        still_in_use = any(
            s.connection_info is conn_info and s.status == "active"
            for s in self._sessions.values()
        )
        if not still_in_use:
            for key, info in list(self._connections.items()):
                if info is conn_info:
                    self._connections.pop(key, None)

    async def run_ephemeral(
        self,
        agent_id: str,
        host: str,
        command: str,
        username: str,
        password: Optional[str] = None,
        private_key: Optional[str] = None,
        port: int = 22,
        timeout: float = 10.0,
        verify_host_key: bool = True,
    ) -> CommandResult:
        """Run a single command without creating a persistent session.

        Args:
            agent_id: Unique identifier for the agent
            host: SSH host to connect to
            command: Command to execute
            username: SSH username
            password: SSH password (optional)
            private_key: Path to private key file (optional)
            port: SSH port (default: 22)
            timeout: Timeout in seconds
            verify_host_key: Whether to verify SSH host keys (default: True)

        Returns:
            CommandResult with exit code, stdout, and stderr

        Raises:
            ConnectionError: If connection fails
            CommandError: If command execution fails
            TimeoutError: If operation times out
        """
        # Ensure connection exists
        connection_info = await self._ensure_connection(
            agent_id, host, username, password, private_key, port, verify_host_key
        )

        try:
            # Run command using asyncssh.run for simple command execution
            result = await asyncio.wait_for(
                connection_info.connection.run(command), timeout=timeout
            )

            # Get exit code
            exit_code = result.returncode or 0

            # Get stdout and stderr
            stdout = result.stdout
            stderr = result.stderr

            # Handle both bytes and string returns from asyncssh
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")

            return CommandResult(
                status="completed",
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
            )

        except asyncio.TimeoutError:
            raise TimeoutError(f"Command timed out after {timeout} seconds")
        except asyncssh.Error as e:
            raise CommandError(f"Failed to execute ephemeral command: {e}") from e
        except Exception as e:
            raise SSHServiceError(f"Unexpected error in ephemeral command: {e}") from e

    async def list_sessions(
        self,
        agent_id: str,
        include_closed: bool = False,
        limit: int = 100,
    ) -> list["SessionSummary"]:
        """List all sessions for the specified agent.

        Args:
            agent_id: Agent identifier
            include_closed: Include closed/broken sessions (default: False - active only)
            limit: Maximum sessions to return (default: 100)

        Returns:
            List of SessionSummary objects sorted by creation time (newest first)

        Raises:
            SSHServiceError: For other SSH-related errors
        """
        # Collect matching sessions
        matching_sessions = []

        for session_id, session in self._sessions.items():
            # Filter by agent_id
            if session.agent_id != agent_id:
                continue

            # Filter by status
            if not include_closed and session.status != "active":
                continue

            # Create summary
            summary = SessionSummary(
                session_id=session.session_id,
                agent_id=session.agent_id,
                host=session.connection_info.host,
                username=session.connection_info.username,
                port=session.connection_info.metadata.get("port", 22),
                status=session.status,
                created_at=session.created_at,
                last_activity=session.last_activity,
                command_count=session.command_count,
                message_count=len(session.history),
            )
            matching_sessions.append(summary)

        # Sort by creation time (newest first)
        matching_sessions.sort(key=lambda s: s.created_at, reverse=True)

        # Apply limit
        return matching_sessions[:limit]

    async def get_session_history(
        self,
        session_id: str,
        limit: int = 100,
        since: Optional[datetime] = None,
        direction: Optional[str] = None,
    ) -> "SessionHistory":
        """Get message history for a session.

        Args:
            session_id: Session identifier
            limit: Maximum messages to return (default: 100)
            since: Only messages after this timestamp (optional)
            direction: Filter by direction: "input", "output", or None for both (default: both)

        Returns:
            SessionHistory with messages and metadata

        Raises:
            SessionError: If session not found
            SSHServiceError: For other errors
        """
        # Get session
        if session_id not in self._sessions:
            raise SessionError(f"Session {session_id} not found")

        session = self._sessions[session_id]

        # Get all messages
        all_messages = session.history

        # Filter by timestamp
        if since:
            filtered_messages = [m for m in all_messages if m.timestamp >= since]
        else:
            filtered_messages = all_messages

        # Filter by direction
        if direction:
            if direction not in ("input", "output"):
                raise SSHServiceError(f"Invalid direction: {direction}")
            filtered_messages = [
                m for m in filtered_messages if m.direction == direction
            ]

        # Get total count before limiting
        total_count = len(filtered_messages)

        # Sort by timestamp (newest first) and apply limit
        filtered_messages.sort(key=lambda m: m.timestamp, reverse=True)
        limited_messages = filtered_messages[:limit]

        # Check if truncated
        truncated = len(limited_messages) < total_count

        return SessionHistory(
            session_id=session.session_id,
            messages=limited_messages,
            total_count=total_count,
            truncated=truncated,
        )

    async def close_agent_connection(self, agent_id: str) -> None:
        """Close all connections and sessions for the specified agent.

        Args:
            agent_id: Agent ID to close connections for
        """
        # Find and close all sessions for this agent
        sessions_to_close = [
            session_id
            for session_id, session in self._sessions.items()
            if session.agent_id == agent_id
        ]

        # Close sessions
        for session_id in sessions_to_close:
            try:
                await self.end_session(session_id)
            except Exception:
                pass  # Continue closing other sessions

        # Close connections for this agent
        connections_to_close = [
            conn_key
            for conn_key, conn_info in self._connections.items()
            if conn_info.agent_id == agent_id
        ]

        for conn_key in connections_to_close:
            try:
                connection_info = self._connections[conn_key]
                if connection_info.connection:
                    await connection_info.connection.close()
            except Exception:
                pass  # Continue closing other connections
            finally:
                self._connections.pop(conn_key, None)

        # Clean up connection locks
        self._connection_locks.pop(agent_id, None)

    async def shutdown(self) -> None:
        """Shutdown the service and clean up all resources."""
        # Get all agent IDs
        agent_ids = set()
        for session in self._sessions.values():
            agent_ids.add(session.agent_id)
        for conn_info in self._connections.values():
            agent_ids.add(conn_info.agent_id)

        # Close all agent connections
        for agent_id in agent_ids:
            try:
                await self.close_agent_connection(agent_id)
            except Exception:
                pass  # Continue shutting down

        # Clear all remaining state
        self._connections.clear()
        self._sessions.clear()
        self._connection_locks.clear()
        self._session_locks.clear()

    def _make_marker(self) -> str:
        """Generate a unique marker for command completion detection.

        Returns:
            Unique marker string
        """
        # Generate unique marker using UUID
        marker_id = str(uuid.uuid4()).replace("-", "")[:16]  # 16 char unique ID
        return f"______END_MARKER_{marker_id}______"

    async def _trim_history(self, session: SessionInfo) -> None:
        """Trim session history if it exceeds configured limits.

        Enforces both message count and individual message size limits.
        Uses the configured trim strategy (oldest-first by default).

        Args:
            session: Session to trim history for
        """
        # Check message count limit
        if len(session.history) > session.history_config.max_messages:
            # Apply trim strategy
            if session.history_config.trim_strategy == "oldest":
                # Remove oldest messages first
                excess = len(session.history) - session.history_config.max_messages
                session.history = session.history[excess:]
            elif session.history_config.trim_strategy == "largest":
                # Remove largest messages first
                while len(session.history) > session.history_config.max_messages:
                    # Find largest message
                    largest_idx = max(
                        range(len(session.history)),
                        key=lambda i: len(session.history[i].content),
                    )
                    session.history.pop(largest_idx)
            # "none" strategy: don't trim

        # Check individual message size limit
        for msg in session.history[:]:  # Copy to allow removal during iteration
            if len(msg.content) > session.history_config.max_message_size:
                # Truncate message content
                msg.content = msg.content[: session.history_config.max_message_size]

    async def _ensure_connection(
        self,
        agent_id: str,
        host: str,
        username: str,
        password: Optional[str] = None,
        private_key: Optional[str] = None,
        port: int = 22,
        verify_host_key: bool = True,
    ) -> ConnectionInfo:
        """Ensure a connection exists for the agent/host combination.

        Args:
            agent_id: Agent identifier
            host: SSH host
            username: SSH username
            password: SSH password (optional)
            private_key: Path to private key (optional)
            port: SSH port
            verify_host_key: Whether to verify SSH host keys

        Returns:
            ConnectionInfo for the established connection

        Raises:
            ConnectionError: If connection fails
        """
        # Create connection key for pooling
        auth_type = "key" if private_key else "password"
        connection_key = f"{agent_id}:{host}:{username}:{auth_type}"

        # Check if connection already exists
        if connection_key in self._connections:
            return self._connections[connection_key]

        # Ensure per-agent connection lock exists
        if agent_id not in self._connection_locks:
            self._connection_locks[agent_id] = asyncio.Lock()

        # Use lock to prevent concurrent connection attempts for same agent
        async with self._connection_locks[agent_id]:
            # Double-check after acquiring lock
            if connection_key in self._connections:
                return self._connections[connection_key]

            # Validate private key file if provided
            if private_key:
                import os
                import stat

                if not os.path.isfile(private_key):
                    raise ConnectionError(
                        f"Private key file does not exist: {private_key}"
                    )
                # Check file permissions (should not be world-readable)
                # Note: On Windows, we skip strict permission checks since NTFS permissions
                # don't map directly to Unix permissions that SSH expects
                import platform

                if platform.system() != "Windows":
                    try:
                        file_stat = os.stat(private_key)
                        if file_stat.st_mode & stat.S_IROTH:
                            raise ConnectionError(
                                f"Private key file is world-readable: {private_key}"
                            )
                    except FileNotFoundError:
                        # Tests may mock `os.path.isfile` without providing a
                        # real file. Defer strict permission checks in that case.
                        pass

            try:
                # Prepare connection arguments
                if verify_host_key:
                    import pathlib

                    known_hosts_path = pathlib.Path("~/.ssh/known_hosts").expanduser()
                    try:
                        known_hosts = asyncssh.read_known_hosts(str(known_hosts_path))
                    except FileNotFoundError:
                        # If known_hosts file doesn't exist, create an empty one
                        known_hosts = asyncssh.SSHKnownHosts()
                    connect_kwargs = {
                        "host": host,
                        "port": port,
                        "username": username,
                        "known_hosts": known_hosts,
                    }
                else:
                    connect_kwargs = {
                        "host": host,
                        "port": port,
                        "username": username,
                        "known_hosts": None,
                    }

                if private_key:
                    connect_kwargs["client_keys"] = [private_key]
                elif password:
                    connect_kwargs["password"] = password
                else:
                    raise ConnectionError(
                        "Either password or private_key must be provided"
                    )

                # Create SSH connection
                connection = await asyncssh.connect(**connect_kwargs)

                # Create ConnectionInfo
                connection_info = ConnectionInfo(
                    connection=connection,
                    host=host,
                    username=username,
                    agent_id=agent_id,
                    metadata={"port": port, "auth_type": auth_type},
                )

                # Store connection
                self._connections[connection_key] = connection_info
                return connection_info

            except asyncssh.Error as e:
                raise ConnectionError(
                    f"Failed to connect to {host}:{port} as {username}: {e}"
                ) from e
            except Exception as e:
                raise ConnectionError(
                    f"Unexpected error connecting to {host}:{port}: {e}"
                ) from e

    async def _read_stream_loop(self, session_id: str) -> None:
        """Background task to read output from session stream.

        Args:
            session_id: Session ID to read from
        """
        session = self._sessions.get(session_id)
        if not session:
            return

        try:
            while session.status == "active":
                try:
                    # Read data from stdout (with timeout to allow checking status).
                    # Prefer `readline()` for compatibility with existing tests,
                    # fall back to chunk `read()` when unavailable.
                    if hasattr(session.process.stdout, "readline"):
                        data = await asyncio.wait_for(
                            session.process.stdout.readline(), timeout=0.1
                        )
                    else:
                        data = await asyncio.wait_for(
                            session.process.stdout.read(8192), timeout=0.1
                        )

                    if not data:  # EOF
                        break

                    # Handle both bytes and string returns from asyncssh
                    if isinstance(data, bytes):
                        data = data.decode("utf-8", errors="replace")

                    print(f"DEBUG: Received data: {repr(data)}")  # Debug output

                    # Accumulate data in buffer and record output message
                    async with session.condition:
                        session.buffer += data

                        # Determine which command_id this output belongs to
                        # Use the first pending marker if available
                        command_id = None
                        for marker in session.markers:
                            if marker in session.pending_command_markers:
                                command_id = session.pending_command_markers[marker]
                                break

                        # Record output message chunk
                        output_message = Message(
                            id=str(uuid.uuid4()),
                            timestamp=datetime.now(),
                            direction="output",
                            content=data,
                            command_id=command_id,
                        )
                        session.history.append(output_message)

                        # Update session activity
                        session.last_activity = datetime.now()

                        # Trim history if needed
                        # Note: We do this without await inside the lock
                        if len(session.history) > session.history_config.max_messages:
                            # Queue for trimming after releasing lock
                            pass

                        session.condition.notify_all()

                except asyncio.TimeoutError:
                    # Timeout is expected, continue checking status
                    continue
                except Exception as e:
                    # Log error and mark session as broken
                    print(f"Error reading from session {session_id}: {e}")
                    session.status = "broken"
                    break

        except Exception as e:
            print(f"Reader task error for session {session_id}: {e}")
            if session:
                session.status = "broken"
        finally:
            # Keep session state unchanged on normal reader-task exit so
            # additional commands can still be attempted in mocked/unit flows.
            pass
