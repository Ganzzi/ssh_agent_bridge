#!/usr/bin/env python3
"""Interactive prompt handling example.

This example demonstrates how to handle interactive commands that prompt for
input, such as password prompts, confirmation dialogs, and multi-step interactions.
"""

import asyncio
import sys
from ssh_agent_bridge import SSHService


async def handle_password_prompt(service, session_id):
    """Example: Handle sudo password prompt."""
    print("Running sudo command that requires password...")

    # Start the command
    result = await service.run_command(session_id, "sudo apt update", short_timeout=3.0)

    if result.status == "partial" and "password" in result.stdout.lower():
        print("Password prompt detected, sending password...")
        await service.send_input(session_id, "mypassword")

        # Wait for command completion
        final_result = await service.get_remaining_output(
            session_id, result.pending_marker, timeout=30.0
        )

        print(f"Command completed with exit code: {final_result.exit_code}")
        print(f"Output length: {len(final_result.stdout)} characters")
    else:
        print("No password prompt detected or command completed quickly")


async def handle_confirmation_prompt(service, session_id):
    """Example: Handle yes/no confirmation."""
    print("Running command that asks for confirmation...")

    # Start the command
    result = await service.run_command(
        session_id, "rm -i important_file.txt", short_timeout=2.0
    )

    if result.status == "partial":
        # Check for common confirmation patterns
        output_lower = result.stdout.lower()
        if any(
            word in output_lower for word in ["yes/no", "y/n", "confirm", "proceed"]
        ):
            print("Confirmation prompt detected, answering 'yes'...")
            await service.send_input(session_id, "yes")

            # Wait for completion
            final_result = await service.get_remaining_output(
                session_id, result.pending_marker, timeout=10.0
            )

            print(f"Command completed with exit code: {final_result.exit_code}")
        else:
            print("No confirmation prompt detected")
    else:
        print("Command completed without prompting")


async def handle_multi_step_interaction(service, session_id):
    """Example: Handle multi-step interactive process."""
    print("Running multi-step interactive process...")

    # Step 1: Start the process
    result = await service.run_command(
        session_id, "mysql_secure_installation", short_timeout=2.0
    )

    interactions = [
        ("enter current password", ""),
        ("change root password?", "y"),
        ("new password:", "new_secure_password"),
        ("repeat password:", "new_secure_password"),
        ("remove anonymous users?", "y"),
        ("disallow root login remotely?", "y"),
        ("remove test database?", "y"),
        ("reload privilege tables?", "y"),
    ]

    for prompt_pattern, response in interactions:
        if (
            result.status == "partial"
            and prompt_pattern.lower() in result.stdout.lower()
        ):
            print(f"Responding to: {prompt_pattern}")
            await service.send_input(session_id, response)

            # Wait for next prompt
            result = await service.get_remaining_output(
                session_id, result.pending_marker, timeout=10.0
            )
        else:
            break

    print(f"Multi-step process completed with exit code: {result.exit_code}")


async def handle_signal_interruption(service, session_id):
    """Example: Handle long-running command with signal interruption."""
    print("Starting long-running command...")

    # Start a command that runs indefinitely
    result = await service.run_command(
        session_id, "tail -f /var/log/syslog", short_timeout=2.0
    )

    if result.status == "partial":
        print("Command is running, waiting 5 seconds then interrupting...")
        await asyncio.sleep(5)

        # Send SIGINT (Ctrl+C)
        print("Sending SIGINT...")
        await service.send_signal(session_id, "SIGINT")

        # Wait for cleanup
        final_result = await service.get_remaining_output(
            session_id, result.pending_marker, timeout=5.0
        )

        print(f"Command interrupted with exit code: {final_result.exit_code}")


async def main():
    """Run interactive prompt examples."""
    if len(sys.argv) != 4:
        print("Usage: python interactive_prompt.py <host> <username> <password>")
        sys.exit(1)

    host, username, password = sys.argv[1:]

    service = SSHService()

    try:
        print(f"Connecting to {host} as {username}...")

        # Create session
        session_id = await service.create_session(
            agent_id="interactive-example",
            host=host,
            username=username,
            password=password,
        )

        print("Session created, running examples...")

        # Example 1: Password prompt
        try:
            await handle_password_prompt(service, session_id)
        except Exception as e:
            print(f"Password prompt example failed: {e}")

        # Reset session for next example
        await service.end_session(session_id)
        session_id = await service.create_session(
            agent_id="interactive-example",
            host=host,
            username=username,
            password=password,
        )

        # Example 2: Confirmation prompt
        try:
            await handle_confirmation_prompt(service, session_id)
        except Exception as e:
            print(f"Confirmation prompt example failed: {e}")

        # Example 3: Multi-step interaction (commented out - requires mysql)
        # try:
        #     await handle_multi_step_interaction(service, session_id)
        # except Exception as e:
        #     print(f"Multi-step example failed: {e}")

        # Example 4: Signal interruption
        try:
            await handle_signal_interruption(service, session_id)
        except Exception as e:
            print(f"Signal interruption example failed: {e}")

        print("All examples completed!")

    except Exception as e:
        print(f"Error: {e}")
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
