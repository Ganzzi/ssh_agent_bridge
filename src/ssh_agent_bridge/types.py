"""Type definitions for SSH Agent Bridge.

This module contains dataclasses and type definitions used throughout
the SSH Agent Bridge package.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

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
        buffer: Accumulated output buffer (for marker detection)
        markers: Set of active markers being waited on
        reader_task: Background task reading output
        lock: Lock for serializing commands on this session
        condition: Condition for notifying buffer changes
        status: Session status ('active', 'closed', 'broken')
        history: List of structured messages (input/output)
        history_config: Configuration for history limits
        created_at: When session was created
        last_activity: Last time session had activity
        command_count: Number of commands executed
        pending_command_markers: Dict mapping marker -> command_id for output correlation
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
    history: List["Message"]
    history_config: "HistoryConfig"
    created_at: datetime
    last_activity: datetime
    command_count: int
    pending_command_markers: Dict[str, Optional[str]] = None  # marker -> command_id


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


@dataclass
class Message:
    """A single message in session history.

    Attributes:
        id: Unique message identifier
        timestamp: When the message was recorded
        direction: "input" or "output"
        content: The message content
        command_id: Optional correlation ID for command input/output pairs
        marker: Optional marker for output messages (command completion marker)
    """

    id: str
    timestamp: datetime
    direction: str  # "input" | "output"
    content: str
    command_id: Optional[str] = None
    marker: Optional[str] = None


@dataclass
class SessionHistory:
    """History of messages for a session.

    Attributes:
        session_id: Session identifier
        messages: List of messages (may be filtered/limited)
        total_count: Total messages in history (before filtering)
        truncated: True if messages were truncated due to limits
    """

    session_id: str
    messages: List[Message]
    total_count: int
    truncated: bool


@dataclass
class SessionSummary:
    """Summary information for a session.

    Attributes:
        session_id: Unique session identifier
        agent_id: Agent that owns this session
        host: SSH host
        username: SSH username
        port: SSH port
        status: Session status ("active", "closed", "broken")
        created_at: When session was created
        last_activity: Last time session had activity
        command_count: Number of commands executed
        message_count: Number of messages in history
    """

    session_id: str
    agent_id: str
    host: str
    username: str
    port: int
    status: str
    created_at: datetime
    last_activity: datetime
    command_count: int
    message_count: int


@dataclass
class HistoryConfig:
    """Configuration for message history limits.

    Attributes:
        max_messages: Maximum messages per session (default: 1000)
        max_message_size: Maximum size per message in bytes (default: 64KB)
        trim_strategy: How to trim when limits exceeded ("oldest", "largest", "none")
    """

    max_messages: int = 1000
    max_message_size: int = 65536  # 64KB
    trim_strategy: str = "oldest"
