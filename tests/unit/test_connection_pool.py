"""Unit tests for SSH connection pool management.

Tests for connection creation, reuse, pooling, and cleanup.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ssh_agent_bridge import SSHService
from ssh_agent_bridge.exceptions import ConnectionError


@pytest.mark.unit
@pytest.mark.asyncio
class TestConnectionPool:
    """Test cases for connection pooling."""

    async def test_connection_creation_success(self, ssh_service, mock_asyncssh):
        """Test successful connection creation."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            conn_info = await ssh_service._ensure_connection(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            assert conn_info.host == "example.com"
            assert conn_info.username == "testuser"
            assert conn_info.agent_id == "test-agent"
            assert (
                "test-agent:example.com:testuser:password" in ssh_service._connections
            )

    async def test_connection_reuse(self, ssh_service, mock_asyncssh):
        """Test that connections are reused for same agent/host/auth."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            # First connection
            conn1 = await ssh_service._ensure_connection(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            # Second connection with same parameters should reuse
            conn2 = await ssh_service._ensure_connection(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            assert conn1 is conn2
            assert len(ssh_service._connections) == 1

    async def test_connection_separation_by_agent(self, ssh_service, mock_asyncssh):
        """Test that different agents get separate connections."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            conn1 = await ssh_service._ensure_connection(
                agent_id="agent-1",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            conn2 = await ssh_service._ensure_connection(
                agent_id="agent-2",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            assert conn1 is not conn2
            assert len(ssh_service._connections) == 2

    async def test_connection_separation_by_auth_method(
        self, ssh_service, mock_asyncssh
    ):
        """Test that different auth methods get separate connections."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            conn1 = await ssh_service._ensure_connection(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            # Mock file existence check for key auth method
            with patch("os.path.isfile", return_value=True):
                conn2 = await ssh_service._ensure_connection(
                    agent_id="test-agent",
                    host="example.com",
                    username="testuser",
                    private_key="/path/to/key",
                )

            assert conn1 is not conn2
            assert len(ssh_service._connections) == 2

    async def test_connection_failure(self, ssh_service):
        """Test connection failure handling."""
        with patch("asyncssh.connect", side_effect=Exception("Connection failed")):
            with pytest.raises(ConnectionError, match="Unexpected error connecting"):
                await ssh_service._ensure_connection(
                    agent_id="test-agent",
                    host="badhost.com",
                    username="testuser",
                    password="testpass",
                )

    async def test_close_agent_connection(self, ssh_service, mock_asyncssh):
        """Test closing connections for a specific agent."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            # Create connections for different agents
            await ssh_service._ensure_connection(
                agent_id="agent-1",
                host="example.com",
                username="testuser",
                password="testpass",
            )
            await ssh_service._ensure_connection(
                agent_id="agent-2",
                host="example.com",
                username="testuser",
                password="testpass",
            )

            assert len(ssh_service._connections) == 2

            # Close agent-1 connections
            await ssh_service.close_agent_connection("agent-1")

            # Verify agent-1 connection is gone, agent-2 remains
            assert len(ssh_service._connections) == 1
            assert any("agent-2" in key for key in ssh_service._connections.keys())