# SSH Agent Bridge API Reference

This document provides detailed API reference for the SSH Agent Bridge package.

## SSHService Class

The main class for SSH session management and command execution.

### Constructor

```python
SSHService()
```

Initialize a new SSH service instance.

### Session Management

#### create_session

```python
async def create_session(
    agent_id: str,
    host: str,
    username: str,
    password: Optional[str] = None,
    private_key: Optional[str] = None,
    port: int = 22,
    term_type: str = "xterm"
) -> str
```

Create a new persistent SSH session for the specified agent and host.

**Parameters:**
- `agent_id` (str): Unique identifier for the agent
- `host` (str): SSH host to connect to
- `username` (str): SSH username
- `password` (Optional[str]): SSH password (optional if using key auth)
- `private_key` (Optional[str]): Path to private key file (optional if using password auth)
- `port` (int): SSH port (default: 22)
- `term_type` (str): Terminal type for PTY (default: "xterm")

**Returns:** Session ID (str) for subsequent operations

**Raises:**
- `ConnectionError`: If connection fails
- `SSHServiceError`: For other SSH-related errors

#### end_session

```python
async def end_session(session_id: str) -> None
```

End the specified SSH session and clean up resources.

**Parameters:**
- `session_id` (str): Session ID to end

**Raises:**
- `SessionError`: If session doesn't exist or is already closed

### Command Execution

#### run_command

```python
async def run_command(
    session_id: str,
    command: str,
    short_timeout: float = 10.0
) -> Union[CommandResult, PartialResult]
```

Execute a command in the specified session with marker-based completion detection.

**Parameters:**
- `session_id` (str): Session ID to run command in
- `command` (str): Command to execute
- `short_timeout` (float): Timeout in seconds to wait for completion (default: 10.0)

**Returns:**
- `CommandResult`: If command completes within timeout
- `PartialResult`: If command times out (with pending_marker for polling)

**Raises:**
- `SessionError`: If session doesn't exist or is closed
- `CommandError`: If command execution fails
- `TimeoutError`: If operation times out

#### get_remaining_output

```python
async def get_remaining_output(
    session_id: str,
    pending_marker: str,
    timeout: float = 30.0
) -> CommandResult
```

Wait for remaining output from a previously timed-out command.

**Parameters:**
- `session_id` (str): Session ID to check
- `pending_marker` (str): Marker from partial result
- `timeout` (float): Timeout in seconds to wait (default: 30.0)

**Returns:** `CommandResult` with final exit code and complete output

**Raises:**
- `SessionError`: If session doesn't exist or is closed
- `TimeoutError`: If marker not found within timeout

### Interactive Operations

#### send_input

```python
async def send_input(session_id: str, input_text: str) -> None
```

Send input text to the stdin of the specified session.

**Parameters:**
- `session_id` (str): Session ID to send input to
- `input_text` (str): Text to send (will be followed by newline)

**Raises:**
- `SessionError`: If session doesn't exist or is closed

#### send_signal

```python
async def send_signal(session_id: str, signal: Union[str, int]) -> None
```

Send a signal to the process in the specified session.

**Parameters:**
- `session_id` (str): Session ID to send signal to
- `signal` (Union[str, int]): Signal name (e.g., 'SIGINT') or number

**Raises:**
- `SessionError`: If session doesn't exist or is closed
- `SSHServiceError`: If signal sending fails

### Ephemeral Commands

#### run_ephemeral

```python
async def run_ephemeral(
    agent_id: str,
    host: str,
    command: str,
    username: str,
    password: Optional[str] = None,
    private_key: Optional[str] = None,
    port: int = 22,
    timeout: float = 10.0
) -> CommandResult
```

Run a single command without creating a persistent session.

**Parameters:**
- `agent_id` (str): Unique identifier for the agent
- `host` (str): SSH host to connect to
- `command` (str): Command to execute
- `username` (str): SSH username
- `password` (Optional[str]): SSH password (optional)
- `private_key` (Optional[str]): Path to private key file (optional)
- `port` (int): SSH port (default: 22)
- `timeout` (float): Timeout in seconds (default: 10.0)

**Returns:** `CommandResult` with exit code, stdout, and stderr

**Raises:**
- `ConnectionError`: If connection fails
- `CommandError`: If command execution fails
- `TimeoutError`: If operation times out

### Lifecycle Management

#### close_agent_connection

```python
async def close_agent_connection(agent_id: str) -> None
```

Close all connections and sessions for the specified agent.

**Parameters:**
- `agent_id` (str): Agent ID to close connections for

#### shutdown

```python
async def shutdown() -> None
```

Shutdown the service and clean up all resources.

### Session Listing & History

#### list_sessions

```python
async def list_sessions(
    agent_id: str,
    include_closed: bool = False,
    limit: int = 100
) -> List[SessionSummary]
```

List all sessions for the specified agent.

**Parameters:**
- `agent_id` (str): Agent identifier
- `include_closed` (bool): Include closed/broken sessions (default: False)
- `limit` (int): Maximum sessions to return (default: 100)

**Returns:** List of `SessionSummary` objects sorted by newest first

**Raises:**
- `SSHServiceError`: If service not initialized

#### get_session_history

```python
async def get_session_history(
    session_id: str,
    limit: int = 100,
    since: Optional[datetime] = None,
    direction: Optional[str] = None
) -> SessionHistory
```

Get message history for a session.

**Parameters:**
- `session_id` (str): Session identifier
- `limit` (int): Maximum messages to return (default: 100)
- `since` (Optional[datetime]): Only messages after this timestamp (default: None)
- `direction` (Optional[str]): Filter by direction - "input", "output", or None for both (default: None)

**Returns:** `SessionHistory` with messages and metadata

**Raises:**
- `SessionError`: If session doesn't exist

## Data Types

### CommandResult

```python
@dataclass
class CommandResult:
    status: str = "completed"  # Always "completed"
    exit_code: int = 0         # Command exit code
    stdout: str = ""           # Standard output
    stderr: Optional[str] = None  # Standard error (optional)
```

### PartialResult

```python
@dataclass
class PartialResult:
    status: str = "partial"    # Always "partial"
    stdout: str = ""           # Output received so far
    pending_marker: str = ""   # Marker for polling completion
```

### Message

```python
@dataclass
class Message:
    id: str                         # Unique message identifier
    timestamp: datetime             # When message was recorded
    direction: str                  # "input" or "output"
    content: str                    # Message content
    command_id: Optional[str] = None  # Correlation ID for command pairs
    marker: Optional[str] = None    # Command completion marker (output only)
```

Represents a single message in the session history. Each command input and its corresponding output messages are correlated via `command_id`.

### SessionHistory

```python
@dataclass
class SessionHistory:
    session_id: str              # Session identifier
    messages: List[Message]      # Messages (may be filtered/limited)
    total_count: int             # Total messages in history
    truncated: bool              # True if messages were truncated
```

Contains the message history for a session. When `truncated` is True, `total_count` indicates how many more messages exist beyond the returned `messages` list.

### SessionSummary

```python
@dataclass
class SessionSummary:
    session_id: str      # Unique session identifier
    agent_id: str        # Agent that created this session
    host: str            # SSH host
    username: str        # SSH username
    port: int            # SSH port
    status: str          # "active", "closed", or "broken"
    created_at: datetime # When session was created
    last_activity: datetime  # Last activity timestamp
    command_count: int   # Number of commands executed
    message_count: int   # Total messages in history
```

Summary information for a session, useful for listing and monitoring sessions.

### HistoryConfig

```python
@dataclass
class HistoryConfig:
    max_messages: int = 1000       # Maximum messages per session
    max_message_size: int = 65536  # Maximum size per message (64KB)
    trim_strategy: str = "oldest"  # "oldest", "largest", or "none"
```

Configuration for message history limits and behavior. Prevents unbounded memory growth in long-lived sessions.

## Exceptions

All exceptions inherit from `SSHServiceError`.

- `ConnectionError`: SSH connection failures
- `SessionError`: Invalid or closed sessions
- `CommandError`: Command execution failures
- `TimeoutError`: Operation timeouts

## Usage Patterns

### Basic Session Workflow

```python
service = SSHService()

# Create session
session_id = await service.create_session(
    agent_id="agent-123",
    host="example.com",
    username="user",
    password="secret"
)

# Run command
result = await service.run_command(session_id, "ls -la")
if result.status == "completed":
    print(f"Exit code: {result.exit_code}")
    print(f"Output: {result.stdout}")
else:
    # Handle partial result
    final_result = await service.get_remaining_output(
        session_id, result.pending_marker
    )

# Clean up
await service.end_session(session_id)
```

### Ephemeral Command

```python
result = await service.run_ephemeral(
    agent_id="agent-123",
    host="example.com",
    command="uptime",
    username="user",
    password="secret"
)
print(f"Server uptime: {result.stdout.strip()}")
```