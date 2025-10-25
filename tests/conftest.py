"""Pytest configuration and fixtures for SSH Agent Bridge tests."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


@pytest.fixture
def event_loop():
    """Create an instance of the default event loop for each test function.

    Using 'function' scope instead of 'session' to ensure proper test isolation
    and prevent event loop reuse issues that cause tests to hang.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture
def ssh_service():
    """Provide a fresh SSHService instance for each test."""
    from ssh_agent_bridge import SSHService

    service = SSHService()
    yield service
    # Note: shutdown is async, but for simplicity in tests we'll skip it
    # In real usage, proper async cleanup would be needed


@pytest.fixture
def mock_asyncssh():
    """Mock the asyncssh module for testing (non-async fixture).

    Returns a properly configured mock for asyncssh.connect that can be patched
    into tests. Use with: patch("asyncssh.connect", mock_asyncssh.connect)
    """
    mock_asyncssh = MagicMock()

    # Mock connection
    mock_conn = AsyncMock()
    mock_conn.create_process = AsyncMock()
    mock_conn.close = AsyncMock()  # Make close() async

    # Mock process with properly configured stdout/stderr
    mock_process = AsyncMock()

    # Setup stdout.read() to return empty (EOF) to avoid hanging
    mock_stdout = AsyncMock()
    mock_stdout.read = AsyncMock(return_value=b"")  # Return empty bytes for EOF
    mock_process.stdout = mock_stdout

    # Setup stderr similarly
    mock_stderr = AsyncMock()
    mock_stderr.read = AsyncMock(return_value=b"")
    mock_process.stderr = mock_stderr

    # Setup stdin
    mock_stdin = AsyncMock()
    mock_process.stdin = mock_stdin

    # Other process methods
    mock_process.returncode = 0
    mock_process.wait = AsyncMock()
    mock_process.send_signal = AsyncMock()
    mock_process.kill = AsyncMock()
    mock_process.close = AsyncMock()

    # Setup create_process to return the mock process
    mock_conn.create_process.return_value = mock_process

    # Mock connect function
    mock_asyncssh.connect = AsyncMock(return_value=mock_conn)
    mock_asyncssh.Error = Exception

    return mock_asyncssh


@pytest.fixture
def sample_connection_info():
    """Provide sample connection information for testing."""
    from ssh_agent_bridge import ConnectionInfo

    # Mock connection
    mock_conn = MagicMock()
    mock_conn.create_process = AsyncMock()

    return ConnectionInfo(
        connection=mock_conn,
        host="example.com",
        username="testuser",
        agent_id="test-agent",
        metadata={"test": True},
    )


@pytest.fixture
async def sample_session_info(sample_connection_info, event_loop):
    """Provide sample session information for testing (async fixture).

    This must be async to properly create asyncio primitives like Lock and Condition.
    """
    from ssh_agent_bridge import SessionInfo

    # Mock process
    mock_process = AsyncMock()
    mock_process.stdout = AsyncMock()
    mock_process.stderr = AsyncMock()
    mock_process.stdin = AsyncMock()
    mock_process.returncode = 0

    # Mock task
    mock_task = AsyncMock()

    session = SessionInfo(
        session_id="test-session-123",
        agent_id="test-agent",
        connection_info=sample_connection_info,
        process=mock_process,
        buffer="",
        markers=set(),
        reader_task=mock_task,
        lock=asyncio.Lock(),
        condition=asyncio.Condition(),
        status="active",
    )

    yield session

    # Cleanup: cancel reader task if it's still running
    if session.reader_task and not session.reader_task.done():
        session.reader_task.cancel()
        try:
            await session.reader_task
        except asyncio.CancelledError:
            pass
