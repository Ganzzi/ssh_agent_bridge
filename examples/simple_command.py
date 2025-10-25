#!/usr/bin/env python3
"""Simple ephemeral command example.

This example shows how to run a single command without maintaining a session.
"""

import asyncio
import sys
from ssh_agent_bridge import SSHService


async def main():
    """Run a simple command on a remote host."""
    if len(sys.argv) != 5:
        print("Usage: python simple_command.py <host> <username> <password> <command>")
        sys.exit(1)

    host, username, password, command = sys.argv[1:]

    service = SSHService()

    try:
        print(f"Running command on {host}: {command}")

        result = await service.run_ephemeral(
            agent_id="simple-example",
            host=host,
            command=command,
            username=username,
            password=password,
        )

        print(f"Exit code: {result.exit_code}")
        print("Output:")
        print(result.stdout)

        if result.stderr:
            print("Errors:")
            print(result.stderr)

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

    finally:
        await service.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
