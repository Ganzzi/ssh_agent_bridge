#!/usr/bin/env python3
"""Signal handling example.

This example demonstrates how to send signals to interrupt or control
long-running commands in SSH sessions.
"""

import asyncio
import sys
from ssh_agent_bridge import SSHService


async def demonstrate_sigint(service, session_id):
    """Demonstrate SIGINT (Ctrl+C) handling."""
    print("=== SIGINT Example ===")
    print("Starting a command that can be interrupted with Ctrl+C...")

    # Start a command that runs for a while
    result = await service.run_command(
        session_id,
        "for i in {1..10}; do echo 'Iteration $i'; sleep 2; done",
        short_timeout=3.0,
    )

    if result.status == "partial":
        print("Command is running, waiting 5 seconds then sending SIGINT...")
        await asyncio.sleep(5)

        print("Sending SIGINT (Ctrl+C)...")
        await service.send_signal(session_id, "SIGINT")

        # Wait for the command to respond to the signal
        final_result = await service.get_remaining_output(
            session_id, result.pending_marker, timeout=10.0
        )

        print(f"Command interrupted with exit code: {final_result.exit_code}")
        print(f"Output received: {len(final_result.stdout)} characters")
    else:
        print("Command completed before we could interrupt it")


async def demonstrate_sigkill(service, session_id):
    """Demonstrate SIGKILL (force kill) handling."""
    print("\n=== SIGKILL Example ===")
    print("Starting a command that ignores SIGINT...")

    # Start a command that traps SIGINT
    result = await service.run_command(
        session_id,
        "trap 'echo Ignoring SIGINT' INT; for i in {1..20}; do echo 'Iteration $i'; sleep 1; done",
        short_timeout=2.0,
    )

    if result.status == "partial":
        print(
            "Command is running (with SIGINT trap), waiting 3 seconds then sending SIGKILL..."
        )
        await asyncio.sleep(3)

        print("Sending SIGKILL (force kill)...")
        await service.send_signal(session_id, "SIGKILL")

        # Wait for the command to be killed
        final_result = await service.get_remaining_output(
            session_id, result.pending_marker, timeout=5.0
        )

        print(f"Command killed with exit code: {final_result.exit_code}")
        print("Note: SIGKILL cannot be caught or ignored by processes")
    else:
        print("Command completed before we could kill it")


async def demonstrate_sighup(service, session_id):
    """Demonstrate SIGHUP handling."""
    print("\n=== SIGHUP Example ===")
    print("Starting a background process that responds to SIGHUP...")

    # Start a process that handles SIGHUP
    result = await service.run_command(
        session_id,
        "echo 'Process started, PID: $$'; trap 'echo Received SIGHUP, reloading config...' HUP; sleep 10",
        short_timeout=2.0,
    )

    if result.status == "partial":
        print("Process is running, waiting 3 seconds then sending SIGHUP...")
        await asyncio.sleep(3)

        print("Sending SIGHUP...")
        await service.send_signal(session_id, "SIGHUP")

        # Wait to see the SIGHUP handling
        final_result = await service.get_remaining_output(
            session_id, result.pending_marker, timeout=8.0
        )

        print(f"Process finished with exit code: {final_result.exit_code}")
        if "reloading config" in final_result.stdout:
            print("SIGHUP was properly handled by the process")
    else:
        print("Process completed before we could send SIGHUP")


async def demonstrate_signal_by_number(service, session_id):
    """Demonstrate sending signals by number."""
    print("\n=== Signal by Number Example ===")
    print("Signals can be sent by name or number...")

    # Start a command
    result = await service.run_command(
        session_id, "echo 'Starting process...'; sleep 10", short_timeout=2.0
    )

    if result.status == "partial":
        print("Process running, sending signal 15 (SIGTERM)...")
        await service.send_signal(session_id, 15)  # SIGTERM

        final_result = await service.get_remaining_output(
            session_id, result.pending_marker, timeout=5.0
        )

        print(f"Process terminated with exit code: {final_result.exit_code}")
        print("Note: Signal 15 is SIGTERM, which allows graceful shutdown")
    else:
        print("Process completed before signal")


async def demonstrate_process_group_signals(service, session_id):
    """Demonstrate signals affecting process groups."""
    print("\n=== Process Group Signals Example ===")
    print("Some signals affect the entire process group...")

    # Start a pipeline that creates multiple processes
    result = await service.run_command(
        session_id, "sleep 30 | sleep 30 | sleep 30", short_timeout=2.0
    )

    if result.status == "partial":
        print("Pipeline running (3 sleep processes), sending SIGTERM...")
        await service.send_signal(session_id, "SIGTERM")

        final_result = await service.get_remaining_output(
            session_id, result.pending_marker, timeout=5.0
        )

        print(f"Pipeline finished with exit code: {final_result.exit_code}")
        print("Note: The signal may affect the entire pipeline")
    else:
        print("Pipeline completed before signal")


async def demonstrate_signal_error_handling(service, session_id):
    """Demonstrate error handling when signals fail."""
    print("\n=== Signal Error Handling Example ===")
    print("Testing what happens when signal operations fail...")

    # Try to send signal to non-existent session
    try:
        await service.send_signal("non-existent-session", "SIGINT")
        print("ERROR: Should have failed!")
    except Exception as e:
        print(f"Correctly caught error for invalid session: {type(e).__name__}")

    # Try to send invalid signal
    try:
        result = await service.run_command(session_id, "sleep 5", short_timeout=1.0)
        if result.status == "partial":
            await service.send_signal(session_id, "INVALID_SIGNAL")
            print("ERROR: Should have failed!")
    except Exception as e:
        print(f"Correctly caught error for invalid signal: {type(e).__name__}")


async def main():
    """Run signal handling examples."""
    if len(sys.argv) != 4:
        print("Usage: python signal_handling.py <host> <username> <password>")
        sys.exit(1)

    host, username, password = sys.argv[1:]

    service = SSHService()

    try:
        print(f"Connecting to {host} as {username}...")

        # Create session
        session_id = await service.create_session(
            agent_id="signal-example", host=host, username=username, password=password
        )

        print("Session created, running signal examples...")

        # Run all examples
        await demonstrate_sigint(service, session_id)
        await demonstrate_sigkill(service, session_id)
        await demonstrate_sighup(service, session_id)
        await demonstrate_signal_by_number(service, session_id)
        await demonstrate_process_group_signals(service, session_id)
        await demonstrate_signal_error_handling(service, session_id)

        print("\n=== All Signal Examples Completed ===")

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    finally:
        # Clean up
        try:
            await service.end_session(session_id)
        except:
            pass
        await service.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
