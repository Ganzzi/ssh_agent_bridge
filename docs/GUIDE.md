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
- [Best Practices](#best-practices)
- [Advanced Patterns](#advanced-patterns)

## Installation

### From PyPI (Recommended)

```bash
pip install ssh-agent-bridge
```

### From Source

```bash
git clone https://github.com/your-org/ssh-agent-bridge.git
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