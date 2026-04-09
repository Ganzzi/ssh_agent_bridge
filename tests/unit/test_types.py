"""Unit tests for SSH Agent Bridge data types.

Tests for CommandResult, PartialResult, ConnectionInfo, Message,
SessionHistory, SessionSummary, and HistoryConfig dataclasses.
"""

import pytest
from datetime import datetime
from ssh_agent_bridge.types import (
    CommandResult,
    PartialResult,
    ConnectionInfo,
    Message,
    SessionHistory,
    SessionSummary,
    HistoryConfig,
)


@pytest.mark.unit
class TestCommandResult:
    """Test cases for CommandResult dataclass."""

    def test_command_result_creation(self):
        """Test CommandResult dataclass creation."""
        result = CommandResult(
            status="completed", exit_code=0, stdout="Hello World", stderr=None
        )

        assert result.status == "completed"
        assert result.exit_code == 0
        assert result.stdout == "Hello World"
        assert result.stderr is None

    def test_output_backward_compatibility_alias(self):
        """Test output property as backward-compatible alias for stdout."""
        result = CommandResult(
            status="completed", exit_code=0, stdout="Output text", stderr=None
        )

        assert result.output == "Output text"
        assert result.output == result.stdout

    def test_command_result_with_truncation(self):
        """Test CommandResult with truncated output."""
        result = CommandResult(
            status="completed",
            exit_code=0,
            stdout="Partial output...",
            stderr=None,
            truncated=True
        )

        assert result.truncated is True


@pytest.mark.unit
class TestPartialResult:
    """Test cases for PartialResult dataclass."""

    def test_partial_result_creation(self):
        """Test PartialResult dataclass creation."""
        result = PartialResult(
            status="partial", stdout="Partial output...", pending_marker="MARKER_123"
        )

        assert result.status == "partial"
        assert result.stdout == "Partial output..."
        assert result.pending_marker == "MARKER_123"

    def test_output_backward_compatibility_alias(self):
        """Test output property as backward-compatible alias for stdout."""
        result = PartialResult(
            status="partial", stdout="Partial output...", pending_marker="MARKER_123"
        )

        assert result.output == "Partial output..."
        assert result.output == result.stdout


@pytest.mark.unit
class TestConnectionInfo:
    """Test cases for ConnectionInfo dataclass."""

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


@pytest.mark.unit
class TestMessage:
    """Test cases for Message dataclass."""

    def test_message_creation_with_command_id(self):
        """Test Message creation with command_id."""
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

    def test_message_creation_without_command_id(self):
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

    def test_message_with_marker(self):
        """Test Message with marker for output correlation."""
        msg = Message(
            id="msg-123",
            timestamp=datetime.now(),
            direction="output",
            content="output text",
            command_id="cmd-456",
            marker="MARKER_123",
        )

        assert msg.marker == "MARKER_123"
        assert msg.command_id == "cmd-456"


@pytest.mark.unit
class TestSessionHistory:
    """Test cases for SessionHistory dataclass."""

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

    def test_session_history_truncated(self):
        """Test SessionHistory with truncated messages."""
        history = SessionHistory(
            session_id="sess-456",
            messages=[],
            total_count=1500,
            truncated=True,
        )

        assert history.truncated is True
        assert history.total_count == 1500


@pytest.mark.unit
class TestSessionSummary:
    """Test cases for SessionSummary dataclass."""

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


@pytest.mark.unit
class TestHistoryConfig:
    """Test cases for HistoryConfig dataclass."""

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
