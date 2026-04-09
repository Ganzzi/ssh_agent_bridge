"""Custom exceptions for SSH Agent Bridge.

This module defines the exception hierarchy used throughout
the SSH Agent Bridge package.
"""


class SSHServiceError(Exception):
    """Base exception for all SSH Agent Bridge errors.

    This is the root exception that all other SSH-related errors inherit from.
    """

    pass


class ConnectionError(SSHServiceError):
    """Raised when SSH connection operations fail.

    This includes connection establishment, authentication failures,
    and connection drops during operation.
    """

    pass


class SessionError(SSHServiceError):
    """Raised when session operations fail.

    This includes invalid session IDs, closed sessions, and session
    lifecycle management errors.
    """

    pass


class CommandError(SSHServiceError):
    """Raised when command execution fails.

    This includes command syntax errors, permission issues, and
    other command-level execution problems.
    """

    pass


class TimeoutError(SSHServiceError):
    """Raised when operations timeout.

    This includes command execution timeouts, connection timeouts,
    and polling timeouts for partial results.
    """

    pass
