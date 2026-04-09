# SSH Agent Bridge User Guide

This guide provides comprehensive instructions for using the SSH Agent Bridge package to manage SSH sessions and execute commands from AI agents.

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Core Concepts](#core-concepts)
- [Session Management](#session-management)
- [Command Execution](#command-execution)
- [Interactive Operations](#interactive-operations)
- [Error Handling](#error-handling)
- [Security Considerations](#security-considerations)
- [Best Practices](#best-practices)
- [Advanced Patterns](#advanced-patterns)

## Installation

### From PyPI (Recommended)

```bash
pip install ssh-agent-bridge
```

### From Source

```bash
git clone https://github.com/Ganzzi/ssh-agent-bridge.git
cd ssh-agent-bridge
pip install -e .
```

### Requirements

- Python 3.8+
- SSH access to target hosts
- Either password authentication or SSH key pairs

## Quick Start

### Single Command (Ephemeral)

The simplest way to run a command without maintaining state:

```python
import asyncio
from ssh_agent_bridge import SSHService

async def main():
    service = SSHService()

    try:
        result = await service.run_ephemeral(
            agent_id="my-agent",
            host="example.com",
            command="uptime",
            username="user",
            password="secret"
        )

        print(f"Exit code: {result.exit_code}")
        print(f"Output: {result.stdout}")

    finally:
        await service.shutdown()

asyncio.run(main())
```

### Persistent Session

For multiple commands on the same host:

```python
import asyncio
from ssh_agent_bridge import SSHService

async def main():
    service = SSHService()

    try:
        # Create session
        session_id = await service.create_session(
            agent_id="my-agent",
            host="example.com",
            username="user",
            password="secret"
        )

        # Run multiple commands
        result1 = await service.run_command(session_id, "pwd")
        result2 = await service.run_command(session_id, "ls -la")

        print(f"Current directory: {result1.stdout.strip()}")
        print(f"Files: {result2.stdout}")

        # Clean up
        await service.end_session(session_id)

    finally:
        await service.shutdown()

asyncio.run(main())
```

## Core Concepts

### Agent Identity

Each agent should have a unique `agent_id`. This enables:

- Connection pooling (reuse connections across sessions)
- Resource isolation (different agents don't interfere)
- Proper cleanup (resources cleaned up per agent)

```python
# Good: Unique agent IDs
agent_id = "web-scraper-agent-001"
agent_id = "database-admin-bot"

# Bad: Generic or reused IDs
agent_id = "agent"  # Too generic
agent_id = "default"  # Conflicts between agents
```

### Session Lifecycle

Sessions represent persistent SSH shell connections:

- **Created**: `create_session()` starts a PTY shell
- **Active**: Commands can be executed via `run_command()`
- **Ended**: `end_session()` closes the shell and cleans up

```python
# Session workflow
session_id = await service.create_session(agent_id, host, username, password)
# ... use session ...
await service.end_session(session_id)
```

### Command Execution Model

Unlike traditional SSH clients, this package uses **marker-based completion**:

1. Command is sent: `ls -la && echo MARKER_123 $?`
2. Output is buffered until marker appears
3. Exit code is parsed from marker line
4. Result returned with complete output

This enables reliable completion detection even with complex output.

## Session Management

### Creating Sessions

```python
session_id = await service.create_session(
    agent_id="my-agent",
    host="example.com",
    username="user",
    password="secret",           # Optional: for password auth
    private_key="/path/to/key",  # Optional: for key auth
    port=22,                     # Optional: default 22
    term_type="xterm"           # Optional: default "xterm"
)
```

### Authentication Options

**Password Authentication:**
```python
session_id = await service.create_session(
    agent_id="agent-1",
    host="server.com",
    username="admin",
    password="mypassword"
)
```

**SSH Key Authentication:**
```python
session_id = await service.create_session(
    agent_id="agent-1",
    host="server.com",
    username="admin",
    private_key="/home/user/.ssh/id_rsa"
)
```

### Session Cleanup

Always clean up sessions when done:

```python
# Individual session
await service.end_session(session_id)

# All sessions for an agent
await service.close_agent_connection(agent_id)

# Complete shutdown
await service.shutdown()
```

## Command Execution

### Basic Command Execution

```python
result = await service.run_command(session_id, "ls -la")

if result.status == "completed":
    print(f"Success! Exit code: {result.exit_code}")
    print(f"Output: {result.stdout}")
else:
    print("Command is still running...")
```

### Handling Long-Running Commands

For commands that take time, use partial results:

```python
result = await service.run_command(session_id, "sleep 30", short_timeout=5.0)

if result.status == "partial":
    print(f"Partial output: {result.stdout}")

    # Wait for completion
    final_result = await service.get_remaining_output(
        session_id,
        result.pending_marker,
        timeout=60.0  # Wait up to 1 minute more
    )

    print(f"Final result: {final_result.stdout}")
```

### Timeout Behavior

- `short_timeout` (default: 10s): How long to wait initially
- `timeout` (default: 30s): How long to wait when polling

```python
# Fast command with short timeout
result = await service.run_command(session_id, "echo hello", short_timeout=1.0)

# Long command with longer initial wait
result = await service.run_command(session_id, "compile-project", short_timeout=60.0)

# Extended polling for very long commands
final = await service.get_remaining_output(session_id, marker, timeout=300.0)
```

## Interactive Operations

### Sending Input

For commands that prompt for input:

```python
# Run command that prompts
result = await service.run_command(session_id, "sudo apt update")

if "password" in result.stdout.lower():
    # Send password
    await service.send_input(session_id, "mypassword")

    # Get result after input
    final_result = await service.get_remaining_output(session_id, result.pending_marker)
```

### Signal Handling

Interrupt running commands:

```python
# Start long-running command
result = await service.run_command(session_id, "tail -f /var/log/syslog", short_timeout=2.0)

if result.status == "partial":
    # Interrupt with Ctrl+C
    await service.send_signal(session_id, "SIGINT")

    # Or kill the process
    await service.send_signal(session_id, "SIGKILL")
```

## Error Handling

### Connection Errors

```python
try:
    session_id = await service.create_session(agent_id, host, username, password)
except ConnectionError as e:
    print(f"Failed to connect: {e}")
    # Handle: retry, different credentials, etc.
```

### Session Errors

```python
try:
    result = await service.run_command(session_id, "invalid-command")
except SessionError as e:
    print(f"Session error: {e}")
    # Handle: recreate session, check if session still exists
```

### Timeout Errors

```python
try:
    result = await service.run_command(session_id, "slow-command", short_timeout=1.0)
except TimeoutError as e:
    print(f"Command timed out: {e}")
    # Handle: increase timeout, check command status
```

### Command Errors

```python
result = await service.run_command(session_id, "false")  # Command that fails

if result.exit_code != 0:
    print(f"Command failed with exit code: {result.exit_code}")
    if result.stderr:
        print(f"Error output: {result.stderr}")
```

### Best Practices

#### Error Handling Pattern

```python
async def safe_run_command(service, session_id, command, max_retries=3):
    """Run command with retry logic."""
    for attempt in range(max_retries):
        try:
            result = await service.run_command(session_id, command)
            return result
        except (ConnectionError, SessionError) as e:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff
            # Recreate session if needed
            # session_id = await service.create_session(...)
```

#### Resource Management

```python
async def with_session(service, agent_id, host, username, password):
    """Context manager pattern for sessions."""
    session_id = None
    try:
        session_id = await service.create_session(agent_id, host, username, password)
        yield session_id
    finally:
        if session_id:
            await service.end_session(session_id)
```

## Security Considerations

### Host Key Verification

SSH Agent Bridge enables host key verification by default for security. This prevents man-in-the-middle attacks by ensuring you're connecting to the expected host.

```python
# Secure (default): Verify host keys
session_id = await service.create_session(
    agent_id="agent1",
    host="example.com",
    username="user",
    password="secret",
    verify_host_key=True  # Default: True
)

# Less secure (not recommended): Skip verification
session_id = await service.create_session(
    agent_id="agent1",
    host="example.com",
    username="user",
    password="secret",
    verify_host_key=False  # Only for testing/trusted networks
)
```

**Security Warning**: Only disable host key verification in trusted environments or for testing. In production, always verify host keys.

### Private Key Security

When using SSH key authentication:

1. **File Permissions**: Private key files should not be world-readable
2. **Secure Storage**: Store keys securely and rotate regularly
3. **Key Validation**: The library validates key file existence and permissions

```python
# The library automatically validates private key security
session_id = await service.create_session(
    agent_id="agent1",
    host="example.com",
    username="user",
    private_key="/path/to/private/key"  # Must not be world-readable
)
```

### Credential Handling

- **No Logging**: Passwords and key paths are never logged in error messages
- **Memory Management**: Credentials are passed directly to SSH library
- **No Persistence**: Credentials are not stored beyond connection establishment

### Buffer Security

Session buffers accumulate all command output in memory. For sessions that handle sensitive data:

- **Session Scope**: Use focused sessions for sensitive operations
- **Cleanup**: End sessions promptly after sensitive operations
- **Memory Awareness**: Be aware that output remains in memory until session ends

```python
# For sensitive operations, use dedicated sessions
async def run_sensitive_command(service, host, username, password):
    session_id = await service.create_session(
        agent_id="sensitive-agent",
        host=host,
        username=username,
        password=password
    )

    try:
        result = await service.run_command(session_id, "cat /etc/shadow")
        # Process sensitive result
        return result
    finally:
        # Immediately clean up to clear buffer from memory
        await service.end_session(session_id)
```

### Network Security

- **SSH Protocol**: Uses secure SSH protocol with encryption
- **Connection Pooling**: Reuses authenticated connections securely
- **Session Isolation**: Commands from different agents are isolated

## Best Practices

### Agent Design

1. **Unique Agent IDs**: Use descriptive, unique identifiers
2. **Resource Limits**: Limit concurrent sessions per agent
3. **Connection Reuse**: Let the service manage connection pooling
4. **Cleanup**: Always clean up resources in finally blocks

### Command Design

1. **Idempotent Commands**: Design commands that can be safely retried
2. **Timeout Planning**: Set appropriate timeouts based on command duration
3. **Output Handling**: Commands should produce parseable output
4. **Error Checking**: Check exit codes and handle failures gracefully

### Session Management

1. **Session Scope**: Keep sessions focused on related operations
2. **Concurrent Commands**: Use separate sessions for parallel operations
3. **Long-Running Sessions**: Monitor and refresh long-lived sessions
4. **State Awareness**: Track session state to avoid invalid operations

## Session Management & History

### Listing Active Sessions

View all active sessions for an agent to understand current connections:

```python
# List only active sessions
active_sessions = await service.list_sessions(
    agent_id="my-agent",
    include_closed=False
)

for session in active_sessions:
    print(f"Session: {session.session_id}")
    print(f"  Host: {session.host}")
    print(f"  Commands executed: {session.command_count}")
    print(f"  Last activity: {session.last_activity}")
```

### Retrieving Session History

Access the message history for debugging and auditing:

```python
# Get all messages from a session
history = await service.get_session_history(session_id)

for message in history.messages:
    timestamp = message.timestamp.strftime("%H:%M:%S")
    direction = "→" if message.direction == "input" else "←"
    print(f"[{timestamp}] {direction} {message.content[:60]}")

if history.truncated:
    print(f"... ({history.total_count - len(history.messages)} more messages)")
```

### Filtering History

Query history with time ranges and direction filters:

```python
from datetime import datetime, timedelta

# Get input commands from the last hour
one_hour_ago = datetime.now() - timedelta(hours=1)

history = await service.get_session_history(
    session_id,
    since=one_hour_ago,
    direction="input",
    limit=50
)

print(f"Commands executed in last hour: {len(history.messages)}")
for message in history.messages:
    print(f"  $ {message.content}")
```

### Session Monitoring & Debugging

Track session health and command correlation:

```python
async def monitor_session(service, agent_id, session_id):
    """Get current session status and recent activity."""
    
    # Get session summary
    sessions = await service.list_sessions(agent_id, include_closed=True)
    session_info = next(
        (s for s in sessions if s.session_id == session_id), 
        None
    )
    
    if not session_info:
        print(f"Session {session_id} not found")
        return
    
    print(f"Session Status: {session_info.status}")
    print(f"Commands executed: {session_info.command_count}")
    print(f"Total messages: {session_info.message_count}")
    
    # Get recent output
    history = await service.get_session_history(
        session_id,
        limit=20,
        direction="output"
    )
    
    print(f"\nRecent output ({len(history.messages)} messages):")
    for message in history.messages[-5:]:  # Last 5 messages
        lines = message.content.split('\n')
        preview = lines[0][:70] if lines else ""
        print(f"  {preview}")
```

### Command Correlation

Link input commands with their outputs using message history:

```python
# Get full history including both inputs and outputs
history = await service.get_session_history(session_id, limit=200)

# Group messages by command_id to see input/output pairs
from collections import defaultdict

command_logs = defaultdict(list)
for message in history.messages:
    if message.command_id:
        command_logs[message.command_id].append(message)

for command_id, messages in list(command_logs.items())[:5]:
    print(f"\nCommand {command_id}:")
    for msg in messages:
        if msg.direction == "input":
            print(f"  INPUT: {msg.content}")
        else:
            preview = msg.content.split('\n')[0][:50]
            print(f"  OUTPUT: {preview}")
```

## Advanced Patterns

### Multi-Agent Coordination

```python
class MultiAgentManager:
    def __init__(self):
        self.service = SSHService()
        self.agent_sessions = {}  # agent_id -> session_id

    async def get_session(self, agent_id, host, username, password):
        """Get or create session for agent."""
        if agent_id not in self.agent_sessions:
            session_id = await self.service.create_session(
                agent_id, host, username, password
            )
            self.agent_sessions[agent_id] = session_id
        return self.agent_sessions[agent_id]

    async def cleanup_agent(self, agent_id):
        """Clean up all resources for an agent."""
        if agent_id in self.agent_sessions:
            await self.service.end_session(self.agent_sessions[agent_id])
            del self.agent_sessions[agent_id]
        await self.service.close_agent_connection(agent_id)
```

### Command Pipelines

```python
async def run_pipeline(service, session_id, commands):
    """Run a series of commands, stopping on failure."""
    results = []

    for command in commands:
        result = await service.run_command(session_id, command)

        if result.exit_code != 0:
            raise CommandError(f"Pipeline failed on: {command}")

        results.append(result)

    return results

# Usage
commands = [
    "cd /tmp",
    "wget https://example.com/file.tar.gz",
    "tar xzf file.tar.gz",
    "./configure",
    "make",
    "make install"
]

results = await run_pipeline(service, session_id, commands)
```

### Interactive Command Automation

```python
async def run_interactive_command(service, session_id, command, inputs):
    """Run command with automated responses to prompts."""
    result = await service.run_command(session_id, command, short_timeout=2.0)

    for expected_prompt, response in inputs:
        if expected_prompt.lower() in result.stdout.lower():
            await service.send_input(session_id, response)

            # Wait for next prompt or completion
            result = await service.get_remaining_output(
                session_id, result.pending_marker, timeout=10.0
            )

    return result

# Usage
inputs = [
    ("password:", "secret123"),
    ("continue?", "yes"),
    ("filename:", "output.txt")
]

result = await run_interactive_command(
    service, session_id, "sudo apt install package", inputs
)
```

This guide covers the essential patterns for using SSH Agent Bridge effectively. For detailed API reference, see the [API Documentation](API.md).</content>
<parameter name="filePath">z:\code\ssh_agent_bridge\docs\GUIDE.md