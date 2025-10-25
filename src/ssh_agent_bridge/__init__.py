"""SSH Agent Bridge - High-level SSH session management for AI agents.

This package provides a tool-based interface for AI agents to execute commands
on remote SSH hosts with structured parameters and returns, supporting long-running
commands, interactive prompts, and signal handling.
"""

from .core import SSHService
from .exceptions import (
    SSHServiceError,
    ConnectionError,
    SessionError,
    CommandError,
    TimeoutError,
)
from .types import (
    ConnectionInfo,
    SessionInfo,
    CommandResult,
    PartialResult,
)

__version__ = "0.1.0"
__all__ = [
    "SSHService",
    "SSHServiceError",
    "ConnectionError",
    "SessionError",
    "CommandError",
    "TimeoutError",
    "ConnectionInfo",
    "SessionInfo",
    "CommandResult",
    "PartialResult",
]
