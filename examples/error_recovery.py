#!/usr/bin/env python3
"""Error recovery and resilience patterns example.

This example demonstrates how to handle various error conditions and implement
robust recovery patterns for SSH operations.
"""

import asyncio
import sys
import time
from ssh_agent_bridge import (
    SSHService,
    ConnectionError,
    SessionError,
    TimeoutError,
    CommandError,
)


class ResilientAgent:
    """An agent that demonstrates error recovery patterns."""

    def __init__(self, agent_id, service, host, username, password):
        self.agent_id = agent_id
        self.service = service
        self.host = host
        self.username = username
        self.password = password
        self.session_id = None
        self.connection_attempts = 0
        self.max_connection_attempts = 3

    async def ensure_session(self):
        """Ensure we have a valid session, creating one if needed."""
        if self.session_id:
            # Quick check if session is still valid
            try:
                result = await self.service.run_command(
                    self.session_id, "echo 'ping'", short_timeout=2.0
                )
                if result.status == "completed" and result.exit_code == 0:
                    return  # Session is good
            except Exception:
                print(f"[{self.agent_id}] Session check failed, will recreate")
                self.session_id = None

        # Create new session with retry logic
        for attempt in range(self.max_connection_attempts):
            try:
                print(
                    f"[{self.agent_id}] Creating session (attempt {attempt + 1}/{self.max_connection_attempts})..."
                )
                self.session_id = await self.service.create_session(
                    self.agent_id, self.host, self.username, self.password
                )
                self.connection_attempts = 0  # Reset counter on success
                print(f"[{self.agent_id}] Session created successfully")
                return
            except ConnectionError as e:
                print(f"[{self.agent_id}] Connection attempt {attempt + 1} failed: {e}")
                if attempt < self.max_connection_attempts - 1:
                    wait_time = 2**attempt  # Exponential backoff
                    print(f"[{self.agent_id}] Waiting {wait_time}s before retry...")
                    await asyncio.sleep(wait_time)
                else:
                    raise Exception(
                        f"Failed to create session after {self.max_connection_attempts} attempts"
                    )

    async def run_command_resilient(self, command, description="", max_retries=2):
        """Run a command with automatic retry and session recovery."""
        for attempt in range(max_retries + 1):
            try:
                await self.ensure_session()

                print(f"[{self.agent_id}] Running: {description or command}")
                result = await self.service.run_command(self.session_id, command)

                if result.status == "completed":
                    print(
                        f"[{self.agent_id}] Command completed (exit code: {result.exit_code})"
                    )
                    return result
                else:
                    # Handle partial results
                    print(
                        f"[{self.agent_id}] Command running in background, waiting for completion..."
                    )
                    final_result = await self.service.get_remaining_output(
                        self.session_id, result.pending_marker, timeout=30.0
                    )
                    print(
                        f"[{self.agent_id}] Command finished (exit code: {final_result.exit_code})"
                    )
                    return final_result

            except (ConnectionError, SessionError) as e:
                print(f"[{self.agent_id}] Attempt {attempt + 1} failed: {e}")
                if attempt < max_retries:
                    print(f"[{self.agent_id}] Will retry...")
                    self.session_id = None  # Force session recreation
                    await asyncio.sleep(1)
                else:
                    raise Exception(
                        f"Command failed after {max_retries + 1} attempts: {e}"
                    )

            except TimeoutError as e:
                print(f"[{self.agent_id}] Command timed out: {e}")
                if attempt < max_retries:
                    print(f"[{self.agent_id}] Retrying with longer timeout...")
                else:
                    raise

    async def cleanup(self):
        """Clean up resources."""
        if self.session_id:
            try:
                await self.service.end_session(self.session_id)
            except Exception as e:
                print(f"[{self.agent_id}] Error during cleanup: {e}")
            finally:
                self.session_id = None


async def demonstrate_connection_recovery(service, host, username, password):
    """Demonstrate automatic connection recovery."""
    print("=== Connection Recovery Example ===")

    agent = ResilientAgent("recovery-agent", service, host, username, password)

    try:
        # Run some commands that should work
        await agent.run_command_resilient(
            "echo 'Connection test 1'", "Initial connection test"
        )
        await agent.run_command_resilient("uptime", "System uptime check")

        # Simulate connection issues by ending the session manually
        print("Simulating connection drop...")
        if agent.session_id:
            await service.end_session(agent.session_id)
            agent.session_id = None

        # Next command should automatically recover
        await agent.run_command_resilient(
            "echo 'Recovered connection'", "Post-recovery test"
        )

        print("Connection recovery successful!")

    finally:
        await agent.cleanup()


async def demonstrate_timeout_handling(service, host, username, password):
    """Demonstrate timeout handling and recovery."""
    print("\n=== Timeout Handling Example ===")

    agent = ResilientAgent("timeout-agent", service, host, username, password)

    try:
        # Test with very short timeout that should fail
        try:
            result = await agent.run_command_resilient(
                "sleep 10",
                "Long running command with short timeout",
                max_retries=0,  # Don't retry for this test
            )
            if result.status == "partial":
                print("Command correctly returned partial result due to timeout")
        except TimeoutError:
            print("Command correctly timed out")

        # Test recovery with longer timeout
        result = await agent.run_command_resilient(
            "sleep 3 && echo 'Completed after sleep'", "Recoverable command"
        )
        print(f"Recovery successful: {result.stdout.strip()}")

    finally:
        await agent.cleanup()


async def demonstrate_network_resilience(service, host, username, password):
    """Demonstrate handling of network-related errors."""
    print("\n=== Network Resilience Example ===")

    agent = ResilientAgent("network-agent", service, host, username, password)

    try:
        # Test with invalid host (will fail)
        print("Testing with invalid host (should fail gracefully)...")
        bad_agent = ResilientAgent(
            "bad-agent", service, "invalid.host.local", username, password
        )

        try:
            await bad_agent.run_command_resilient("echo 'test'", max_retries=1)
            print("ERROR: Should have failed!")
        except Exception as e:
            print(f"Correctly handled invalid host: {type(e).__name__}")

        # Continue with valid operations
        await agent.run_command_resilient(
            "echo 'Network test successful'", "Valid host test"
        )

    finally:
        await agent.cleanup()


async def demonstrate_circuit_breaker_pattern(service, host, username, password):
    """Demonstrate circuit breaker pattern for failing services."""
    print("\n=== Circuit Breaker Pattern Example ===")

    class CircuitBreakerAgent(ResilientAgent):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.failure_count = 0
            self.last_failure_time = 0
            self.circuit_open = False
            self.failure_threshold = 3
            self.recovery_timeout = 30  # seconds

        async def run_command_resilient(self, command, description="", max_retries=2):
            current_time = time.time()

            # Check if circuit should be closed
            if (
                self.circuit_open
                and (current_time - self.last_failure_time) > self.recovery_timeout
            ):
                print(f"[{self.agent_id}] Circuit breaker: attempting to close circuit")
                self.circuit_open = False
                self.failure_count = 0

            if self.circuit_open:
                raise Exception(f"Circuit breaker is OPEN (too many failures)")

            try:
                result = await super().run_command_resilient(
                    command, description, max_retries
                )
                self.failure_count = 0  # Reset on success
                return result
            except Exception as e:
                self.failure_count += 1
                self.last_failure_time = current_time

                if self.failure_count >= self.failure_threshold:
                    print(
                        f"[{self.agent_id}] Circuit breaker: OPENING (failure count: {self.failure_count})"
                    )
                    self.circuit_open = True

                raise

    agent = CircuitBreakerAgent("circuit-agent", service, host, username, password)

    try:
        # Run some successful commands
        await agent.run_command_resilient("echo 'Circuit test 1'")
        await agent.run_command_resilient("echo 'Circuit test 2'")

        # Simulate failures by using invalid commands
        print("Simulating failures to trigger circuit breaker...")
        for i in range(4):
            try:
                await agent.run_command_resilient(
                    "invalid_command_that_fails", max_retries=0
                )
            except Exception as e:
                print(f"Expected failure {i+1}: {type(e).__name__}")

        # Try one more time - should be blocked by circuit breaker
        try:
            await agent.run_command_resilient("echo 'Should be blocked'", max_retries=0)
            print("ERROR: Circuit breaker should have blocked this!")
        except Exception as e:
            print(f"Correctly blocked by circuit breaker: {e}")

        # Wait for circuit to close
        print("Waiting for circuit breaker recovery timeout...")
        await asyncio.sleep(35)

        # Should work again
        result = await agent.run_command_resilient("echo 'Circuit recovered'")
        print(f"Circuit breaker recovery successful: {result.stdout.strip()}")

    finally:
        await agent.cleanup()


async def main():
    """Run error recovery examples."""
    if len(sys.argv) != 4:
        print("Usage: python error_recovery.py <host> <username> <password>")
        sys.exit(1)

    host, username, password = sys.argv[1:]

    service = SSHService()

    try:
        print(f"Running error recovery examples on {host}")

        await demonstrate_connection_recovery(service, host, username, password)
        await demonstrate_timeout_handling(service, host, username, password)
        await demonstrate_network_resilience(service, host, username, password)
        await demonstrate_circuit_breaker_pattern(service, host, username, password)

        print("\n=== All Error Recovery Examples Completed ===")

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    finally:
        await service.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
