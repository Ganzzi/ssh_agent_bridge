# SSH Agent Bridge Architecture

This document describes the architecture, design decisions, and technical details of the SSH Agent Bridge package.

## Overview

SSH Agent Bridge provides high-level SSH session management for AI agents. Unlike traditional SSH libraries that stream output in real-time, this package uses structured parameters and returns, making it suitable for non-interactive agent use cases.

## Core Concepts

### Agent-Centric Design

The package is designed around AI agents as first-class citizens:

- **Agent Identity**: Each agent has a unique ID for connection pooling
- **Session Isolation**: Commands from different agents never interfere
- **Connection Reuse**: Agents can maintain persistent connections across sessions
- **Resource Management**: Automatic cleanup when agents disconnect

### Structured Communication

Instead of streaming output, the package provides:

- **Command Results**: Structured objects with exit codes and output
- **Partial Results**: Support for long-running commands with polling
- **Timeout Handling**: Configurable timeouts with graceful degradation
- **Marker-Based Completion**: Reliable command completion detection

## Architecture Layers

### 1. Client Layer (Public API)

The `SSHService` class provides the main interface:

```python
class SSHService:
    # Session management
    async def create_session(...) -> str
    async def end_session(...)

    # Command execution
    async def run_command(...) -> Union[CommandResult, PartialResult]
    async def get_remaining_output(...) -> CommandResult

    # Interactive features
    async def send_input(...) -> None
    async def send_signal(...) -> None

    # Utilities
    async def run_ephemeral(...) -> CommandResult
```

### 2. Connection Layer

Manages SSH connections with pooling:

- **Connection Pooling**: `Dict[str, ConnectionInfo]` keyed by agent ID
- **Lazy Creation**: Connections created on first use
- **Authentication**: Support for password and key-based auth
- **Health Checks**: Automatic reconnection on failures

### 3. Session Layer

Handles PTY shell sessions:

- **Session Registry**: `Dict[str, SessionInfo]` for active sessions
- **PTY Sessions**: Full terminal emulation with `asyncssh.create_connection(pty_requested=True)`
- **Buffer Management**: Accumulates all session output
- **Reader Tasks**: Background tasks reading stdout/stderr streams

### 4. Command Layer

Implements marker-based command execution:

- **Unique Markers**: Generated per command for reliable completion detection
- **Command Injection**: `command && echo <marker> $?`
- **Buffer Scanning**: Searches for marker lines in accumulated output
- **Timeout Handling**: Returns partial results when markers not found

## Key Design Decisions

### PTY vs Non-PTY Sessions

**Decision**: Use PTY (pseudo-terminal) sessions for all persistent sessions.

**Rationale**:
- PTY provides full shell environment (environment variables, job control)
- Interactive commands work correctly (sudo, ssh, editors)
- Consistent behavior across different shell types
- Better compatibility with complex commands

**Trade-offs**:
- Slightly higher resource usage
- Output buffering may differ from non-PTY
- Signal handling more complex

### Marker-Based Completion Detection

**Decision**: Append unique markers to commands to detect completion.

**Pattern**: `original_command && echo "MARKER_abc123def456 $?"`

**Rationale**:
- Reliable completion detection without parsing shell prompts
- Works across different shell types (bash, zsh, sh)
- Captures exit codes accurately
- Handles multi-line output correctly

**Implementation**:
- Markers are unique per command (UUID-based)
- Buffer searched for marker lines
- Exit code extracted from marker output
- Supports partial result polling

### Connection Pooling Strategy

**Decision**: Pool connections per (agent_id, host, username, auth_method) tuple.

**Rationale**:
- Reduces connection overhead for multiple sessions
- Maintains security boundaries between agents
- Supports concurrent sessions on same connection
- Automatic cleanup on agent disconnection

**Key Features**:
- Lazy connection creation
- Per-agent connection locks
- Health checking and reconnection
- Graceful degradation on connection loss

### Async-First Design

**Decision**: All operations are async with asyncio.

**Rationale**:
- Non-blocking I/O for high concurrency
- Suitable for async agent frameworks
- Efficient resource utilization
- Future-proof for async ecosystems

**Patterns Used**:
- `asyncio.Lock` for synchronization
- `asyncio.Condition` for buffer notifications
- `asyncio.gather` for concurrent operations
- Background reader tasks

## Concurrency Model

### Session-Level Serialization

Commands within a session are serialized:

```python
# Per-session lock ensures one command at a time
async with session.lock:
    result = await self._execute_command(session, command)
```

**Rationale**:
- Simplifies buffer management
- Prevents command interleaving
- Maintains deterministic output ordering
- Reduces race conditions

### Connection-Level Parallelism

Multiple sessions can run concurrently on the same connection:

```python
# Different sessions on same connection run in parallel
session1_task = asyncio.create_task(run_commands(session1))
session2_task = asyncio.create_task(run_commands(session2))
await asyncio.gather(session1_task, session2_task)
```

**Benefits**:
- Efficient use of single SSH connection
- Supports multiple concurrent agents
- Better resource utilization

### Buffer Synchronization

Buffer changes notify waiting tasks:

```python
# Reader task notifies on new output
async with session.condition:
    session.buffer += data
    session.condition.notify_all()

# Command execution waits for marker
async with session.condition:
    await session.condition.wait_for(
        lambda: marker in session.buffer,
        timeout=timeout
    )
```

## Data Flow

### Command Execution Flow

1. **Command Submission**:
   - Generate unique marker
   - Append marker to command: `cmd && echo <marker> $?`
   - Send to session stdin

2. **Output Accumulation**:
   - Background reader task reads stdout/stderr
   - Appends to session buffer
   - Notifies waiting tasks

3. **Completion Detection**:
   - Search buffer for marker line
   - Extract exit code from marker
   - Return complete or partial result

4. **Polling Support**:
   - Partial results include pending_marker
   - `get_remaining_output()` waits for same marker
   - Supports long-running command workflows

### Session Lifecycle

1. **Creation** (`create_session`):
   - Ensure connection exists
   - Create PTY channel
   - Start background reader task
   - Register session

2. **Usage**:
   - Commands serialized per session
   - Buffer accumulates all output
   - Signals sent to current process group

3. **Cleanup** (`end_session`):
   - Cancel reader task
   - Close channel
   - Remove from registry

## Error Handling

### Exception Hierarchy

```
SSHServiceError (base)
├── ConnectionError     # Connection failures
├── SessionError        # Invalid sessions
├── CommandError        # Command execution failures
└── TimeoutError        # Operation timeouts
```

### Failure Modes

- **Connection Drops**: Automatic reconnection attempts
- **Session Corruption**: Session marked as broken, requires recreation
- **Command Failures**: Detailed error messages with context
- **Timeout Exceeded**: Partial results with polling capability

## Performance Considerations

### Buffer Management

**Current Strategy**: Unlimited buffer growth
- Simple and safe for typical usage
- Memory usage scales with session lifetime
- Suitable for short-to-medium sessions

**Future Optimization**: Circular buffer with trimming
- Configurable maximum buffer size
- Automatic trimming of old output
- Memory-bounded operation

### Connection Efficiency

- **Pooling**: Reduces connection overhead
- **Multiplexing**: Multiple sessions per connection
- **Keep-Alive**: Persistent connections reduce latency
- **Lazy Cleanup**: Connections closed on demand

### Scaling Limits

**Per-Session**:
- Commands serialized (by design)
- Buffer growth linear with output
- Single reader task per session

**Per-Connection**:
- Multiple concurrent sessions
- Shared connection bandwidth
- SSH protocol limits apply

## Security Considerations

### Authentication

- **Key-Based Preferred**: Private keys more secure than passwords
- **Key File Handling**: Proper file permissions required
- **Password Security**: Not logged or stored in memory

### Connection Security

- **Known Hosts**: SSH host verification enabled
- **Certificate Validation**: Standard SSH security
- **Agent Isolation**: Separate connections per agent

### Data Handling

- **Credential Logging**: Passwords never logged
- **Buffer Security**: Sensitive data may remain in buffers
- **Cleanup**: Explicit resource cleanup required

## Limitations

### By Design

1. **Serialized Commands**: One command per session at a time
   - Simplifies implementation
   - Prevents output interleaving
   - May limit throughput for some use cases

2. **Buffer Growth**: Unlimited accumulation
   - Memory usage increases over time
   - Suitable for bounded session lifetimes

3. **Signal Support**: Varies by SSH server
   - `SIGKILL` most reliable
   - `SIGINT` may not work on all servers

### Technical Limitations

1. **SSH Server Compatibility**: Tested with OpenSSH
   - Other SSH servers may have different behavior
   - PTY support required

2. **Shell Variability**: Works with POSIX shells
   - Command markers assume standard shell behavior
   - Complex shell configurations may interfere

3. **Network Reliability**: Assumes stable connections
   - Connection drops require manual reconnection
   - No automatic retry logic

## Future Enhancements

### Phase 7+ Features

- **Connection Multiplexing**: Parallel commands per session
- **Buffer Rotation**: Automatic trimming for long sessions
- **Advanced Prompt Detection**: Regex-based interactive handling
- **Web API**: FastAPI/gRPC wrapper
- **CLI Tool**: Human debugging interface
- **SFTP Support**: File operations integration

### Optimization Opportunities

- **Binary Marker Search**: Faster completion detection
- **Compressed Buffers**: Memory-efficient storage
- **Connection Pool Tuning**: Configurable pool sizes
- **Async Iterator API**: Streaming result support

## Testing Strategy

### Unit Testing
- Mock SSH connections for isolated testing
- Test all error paths and edge cases
- Validate marker generation and parsing
- Test concurrent session behavior

### Integration Testing
- Real SSH server testing (local or containerized)
- End-to-end session workflows
- Interactive prompt handling
- Long-running command scenarios

### Coverage Goals
- **Core Methods**: 100% coverage
- **Error Handling**: All exception paths tested
- **Concurrency**: Race condition testing
- **Overall Target**: ≥80% code coverage