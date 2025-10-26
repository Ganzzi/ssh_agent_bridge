"""Type definitions for SSH Agent Bridge.

This module contains dataclasses and type definitions used throughout
the SSH Agent Bridge package.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, Optional, Set

if TYPE_CHECKING:
    import asyncssh
else:
    asyncssh = None


@dataclass
class ConnectionInfo:
    """Information about an SSH connection.

    Attributes:
        connection: The asyncssh connection object
        host: SSH host
        username: SSH username
        agent_id: Agent that owns this connection
        metadata: Additional connection metadata
    """

    connection: "asyncssh.SSHClientConnection"
    host: str
    username: str
    agent_id: str
    metadata: Dict[str, Any]


@dataclass
class SessionInfo:
    """Information about an SSH session.

    Attributes:
        session_id: Unique session identifier
        agent_id: Agent that owns this session
        connection_info: Connection this session uses
        process: The asyncssh process/channel
        buffer: Accumulated output buffer
        markers: Set of active markers being waited on
        reader_task: Background task reading output
        lock: Lock for serializing commands on this session
        condition: Condition for notifying buffer changes
        status: Session status ('active', 'closed', 'broken')
    """

    session_id: str
    agent_id: str
    connection_info: ConnectionInfo
    process: "asyncssh.SSHClientProcess"
    buffer: str
    markers: Set[str]
    reader_task: Any  # asyncio.Task
    lock: Any  # asyncio.Lock
    condition: Any  # asyncio.Condition
    status: str


@dataclass
class CommandResult:
    """Result of a completed command execution.

    Attributes:
        status: Always 'completed' for completed commands
        exit_code: Command exit code (0 for success)
        stdout: Standard output from command
        stderr: Standard error from command (optional)
    """

    status: str = "completed"
    exit_code: int = 0
    stdout: str = ""
    stderr: Optional[str] = None


@dataclass
class PartialResult:
    """Result of a command that timed out before completion.

    Attributes:
        status: Always 'partial' for partial results
        stdout: Output received so far
        pending_marker: Marker to poll for completion
    """

    status: str = "partial"
    stdout: str = ""
    pending_marker: str = ""
