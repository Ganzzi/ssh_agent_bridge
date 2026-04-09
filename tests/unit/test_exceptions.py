"""Unit tests for SSH Agent Bridge custom exceptions.

Tests for SSHServiceError, ConnectionError, SessionError, CommandError,
and TimeoutError exception classes.
"""

import pytest
from ssh_agent_bridge.exceptions import (
    SSHServiceError,
    ConnectionError,
    SessionError,
    CommandError,
    TimeoutError,
)


@pytest.mark.unit
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