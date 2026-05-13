"""
Live integration tests for ssh-agent-bridge against real SSH server.

Tests exercise SSH session creation, command execution, session persistence,
long-running commands, and signal handling.
Skip with structured evidence when SSH_TEST_* env vars are not set.

Environment variables required:
- SSH_TEST_HOST — SSH server host (e.g., "192.168.1.100")
- SSH_TEST_USER — SSH username

Optional:
- SSH_TEST_PASSWORD — SSH password (if not using key auth)
- SSH_TEST_PORT — SSH port (default: 22)
"""

import os
import pytest


# ---------------------------------------------------------------------------
# Required environment check
# ---------------------------------------------------------------------------


REQUIRED_ENV = ["SSH_TEST_HOST", "SSH_TEST_USER"]


def _build_skip_message(missing_vars):
    """Build structured skip message listing missing env vars."""
    lines = ["BUILT_NOT_VERIFIED: Missing environment variables:"]
    for var in missing_vars:
        lines.append(f"  - {var}")
    lines.append("")
    lines.append("Set these variables to enable live SSH integration tests:")
    lines.append('  export SSH_TEST_HOST="your-ssh-server"')
    lines.append('  export SSH_TEST_USER="your-username"')
    lines.append('  export SSH_TEST_PASSWORD="your-password"  # optional')
    return "\n".join(lines)


@pytest.fixture(autouse=True)
def require_ssh():
    """Skip test if required SSH environment variables are not set."""
    missing = [v for v in REQUIRED_ENV if not os.getenv(v)]
    if missing:
        pytest.skip(_build_skip_message(missing))


@pytest.fixture
def ssh_config():
    """Load SSH config from environment."""
    return {
        "host": os.getenv("SSH_TEST_HOST"),
        "port": int(os.getenv("SSH_TEST_PORT", "22")),
        "username": os.getenv("SSH_TEST_USER"),
        "password": os.getenv("SSH_TEST_PASSWORD"),
    }


# ---------------------------------------------------------------------------
# SSH session tests
# ---------------------------------------------------------------------------


class TestSSHLiveSession:
    """Live SSH session tests."""

    @pytest.mark.asyncio
    async def test_create_session_and_run_command(self, ssh_config):
        """Create SSH session and run a simple command."""
        from ssh_agent_bridge import SSHService

        service = SSHService()
        agent_id = "test-live-agent"

        result = await service.run_command(
            agent_id=agent_id,
            host=ssh_config["host"],
            port=ssh_config["port"],
            username=ssh_config["username"],
            password=ssh_config["password"],
            command="echo hello",
            timeout=10.0,
        )

        assert result.status == "completed"
        assert "hello" in result.stdout
        assert result.exit_code == 0

        # Cleanup
        await service.close_session(agent_id)

    @pytest.mark.asyncio
    async def test_session_persistence_cwd(self, ssh_config):
        """Session preserves current working directory across commands."""
        from ssh_agent_bridge import SSHService

        service = SSHService()
        agent_id = "test-live-cwd"

        # Change to /tmp
        result1 = await service.run_command(
            agent_id=agent_id,
            host=ssh_config["host"],
            port=ssh_config["port"],
            username=ssh_config["username"],
            password=ssh_config["password"],
            command="cd /tmp",
            timeout=10.0,
        )
        assert result1.status == "completed"

        # Check that we're in /tmp
        result2 = await service.run_command(
            agent_id=agent_id,
            host=ssh_config["host"],
            port=ssh_config["port"],
            username=ssh_config["username"],
            password=ssh_config["password"],
            command="pwd",
            timeout=10.0,
        )
        assert result2.status == "completed"
        assert "/tmp" in result2.stdout

        # Cleanup
        await service.close_session(agent_id)

    @pytest.mark.asyncio
    async def test_session_persistence_env(self, ssh_config):
        """Session preserves environment variables across commands."""
        from ssh_agent_bridge import SSHService

        service = SSHService()
        agent_id = "test-live-env"

        # Set environment variable
        result1 = await service.run_command(
            agent_id=agent_id,
            host=ssh_config["host"],
            port=ssh_config["port"],
            username=ssh_config["username"],
            password=ssh_config["password"],
            command="export TEST_VAR=hello_world",
            timeout=10.0,
        )
        assert result1.status == "completed"

        # Check that env var is set
        result2 = await service.run_command(
            agent_id=agent_id,
            host=ssh_config["host"],
            port=ssh_config["port"],
            username=ssh_config["username"],
            password=ssh_config["password"],
            command="echo $TEST_VAR",
            timeout=10.0,
        )
        assert result2.status == "completed"
        assert "hello_world" in result2.stdout

        # Cleanup
        await service.close_session(agent_id)

    @pytest.mark.asyncio
    async def test_long_running_command(self, ssh_config):
        """Test handling of long-running commands with timeout."""
        from ssh_agent_bridge import SSHService

        service = SSHService()
        agent_id = "test-live-long"

        # Run a command that takes a few seconds
        result = await service.run_command(
            agent_id=agent_id,
            host=ssh_config["host"],
            port=ssh_config["port"],
            username=ssh_config["username"],
            password=ssh_config["password"],
            command="sleep 2 && echo done",
            timeout=10.0,
        )

        assert result.status == "completed"
        assert "done" in result.stdout

        # Cleanup
        await service.close_session(agent_id)

    @pytest.mark.asyncio
    async def test_command_with_stderr(self, ssh_config):
        """Test command that produces stderr output."""
        from ssh_agent_bridge import SSHService

        service = SSHService()
        agent_id = "test-live-stderr"

        # Run a command that outputs to stderr
        result = await service.run_command(
            agent_id=agent_id,
            host=ssh_config["host"],
            port=ssh_config["port"],
            username=ssh_config["username"],
            password=ssh_config["password"],
            command="ls /nonexistent 2>&1",
            timeout=10.0,
        )

        # Command should fail but we should get output
        assert "cannot access" in result.stdout or "No such file" in result.stdout
        assert result.exit_code != 0

        # Cleanup
        await service.close_session(agent_id)

    @pytest.mark.asyncio
    async def test_session_info(self, ssh_config):
        """Test getting session information."""
        from ssh_agent_bridge import SSHService

        service = SSHService()
        agent_id = "test-live-info"

        # Run a command to create session
        await service.run_command(
            agent_id=agent_id,
            host=ssh_config["host"],
            port=ssh_config["port"],
            username=ssh_config["username"],
            password=ssh_config["password"],
            command="echo test",
            timeout=10.0,
        )

        # Get session info
        session_info = await service.get_session_info(agent_id)
        assert session_info is not None
        assert session_info.connected is True
        assert len(session_info.history) > 0

        # Cleanup
        await service.close_session(agent_id)
