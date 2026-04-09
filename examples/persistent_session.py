#!/usr/bin/env python3
"""Persistent session example.

This example shows how to create a persistent SSH session and run multiple commands.
"""

import asyncio
import sys
import os
from ssh_agent_bridge import SSHService


async def main():
    """Create a session and run multiple commands."""
    if len(sys.argv) != 4:
        print("Usage: python persistent_session.py <host> <username> <password>")
        sys.exit(1)

    host, username, password = sys.argv[1:]

    service = SSHService()

    try:
        print(f"Connecting to {host}...")

        # Create session
        print("Creating session...")
        session_id = await service.create_session(
            agent_id="persistent-example",
            host=host,
            username=username,
            password=password,  # Use password instead of private_key for testing
            # private_key=os.path.expanduser("~/.ssh/id_rsa"),
            # term_type="xterm",  # Remove for compatibility
            verify_host_key=False,  # Disable for testing
        )
        print(f"Session created: {session_id}")

        # Run multiple commands
        commands = ["pwd", "whoami"]  # Simplified for testing

        for command in commands:
            print(f"\n$ {command}")

            result = await service.run_command(session_id, command)

            if result.status == "completed":
                print(result.stdout.strip())
            else:
                print(f"Command still running, output so far: {result.stdout}")
                # In a real scenario, you might call get_remaining_output here

        print(f"\nEnding session: {session_id}")
        await service.end_session(session_id)

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

    finally:
        await service.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
