#!/usr/bin/env python3
"""Example: Session Listing and History Analysis

This example demonstrates how to use the session listing and history
retrieval features to monitor and analyze SSH session activity.

Features:
- List all active sessions for an agent
- Retrieve session message history
- Filter history by direction (input/output)
- Correlate command inputs with outputs
- Monitor session health and activity
"""

import asyncio
from datetime import datetime, timedelta
from ssh_agent_bridge import SSHService


async def example_session_listing():
    """Example 1: List all active sessions for an agent."""
    print("=" * 60)
    print("Example 1: List Active Sessions")
    print("=" * 60)

    service = SSHService()

    try:
        # Note: In a real scenario, you would have created sessions first.
        # For this example, we'll demonstrate the API pattern.

        # List only active sessions
        active_sessions = await service.list_sessions(
            agent_id="example-agent", include_closed=False, limit=10
        )

        print(f"\nFound {len(active_sessions)} active session(s):\n")

        for session in active_sessions:
            print(f"Session ID: {session.session_id}")
            print(f"  Host: {session.host} (port {session.port})")
            print(f"  Username: {session.username}")
            print(f"  Status: {session.status}")
            print(f"  Created: {session.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
            print(
                f"  Last Activity: {session.last_activity.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            print(f"  Commands Executed: {session.command_count}")
            print(f"  Total Messages: {session.message_count}")
            print()

        # Include closed sessions to see full history
        all_sessions = await service.list_sessions(
            agent_id="example-agent", include_closed=True, limit=50
        )
        print(f"Total sessions (active + closed): {len(all_sessions)}")

    finally:
        await service.shutdown()


async def example_session_history():
    """Example 2: Retrieve and display session history."""
    print("\n" + "=" * 60)
    print("Example 2: View Session Message History")
    print("=" * 60)

    service = SSHService()

    try:
        # Get full history for a session
        # In a real scenario, session_id would come from create_session()
        session_id = "example-session-id"

        history = await service.get_session_history(session_id, limit=100)

        print(f"\nSession: {history.session_id}")
        print(f"Messages: {len(history.messages)} (of {history.total_count} total)")
        if history.truncated:
            print("Note: History was truncated to fit limit")

        print("\nMessage Timeline:")
        print("-" * 60)

        for message in history.messages:
            timestamp = message.timestamp.strftime("%H:%M:%S")
            direction = "→ INPUT" if message.direction == "input" else "← OUTPUT"

            # Show command_id if present (helps correlate input/output)
            correlation = f" (cmd: {message.command_id})" if message.command_id else ""

            # Truncate long messages for display
            content_preview = message.content.replace("\n", " ")[:50]

            print(f"[{timestamp}] {direction}{correlation}")
            print(f"        {content_preview}")
            print()

    finally:
        await service.shutdown()


async def example_history_filtering():
    """Example 3: Filter history by direction and time range."""
    print("\n" + "=" * 60)
    print("Example 3: Filter History by Direction and Time")
    print("=" * 60)

    service = SSHService()

    try:
        session_id = "example-session-id"

        # Get input commands from the last hour
        one_hour_ago = datetime.now() - timedelta(hours=1)

        input_history = await service.get_session_history(
            session_id, since=one_hour_ago, direction="input", limit=50
        )

        print(f"\nInput commands from last hour: {len(input_history.messages)}")
        print("-" * 60)

        for message in input_history.messages:
            timestamp = message.timestamp.strftime("%H:%M:%S")
            print(f"[{timestamp}] $ {message.content}")

        # Get recent output separately
        output_history = await service.get_session_history(
            session_id, since=one_hour_ago, direction="output", limit=50
        )

        print(f"\n\nOutput messages from last hour: {len(output_history.messages)}")
        print("-" * 60)

        for message in output_history.messages[-10:]:  # Last 10 outputs
            timestamp = message.timestamp.strftime("%H:%M:%S")
            # Show first line of output
            first_line = message.content.split("\n")[0][:70]
            print(f"[{timestamp}] {first_line}")

    finally:
        await service.shutdown()


async def example_command_correlation():
    """Example 4: Correlate commands with their outputs."""
    print("\n" + "=" * 60)
    print("Example 4: Correlate Input Commands with Outputs")
    print("=" * 60)

    service = SSHService()

    try:
        session_id = "example-session-id"

        # Get all messages
        history = await service.get_session_history(session_id, limit=500)

        # Group messages by command_id
        from collections import defaultdict

        command_logs = defaultdict(list)

        for message in history.messages:
            if message.command_id:
                command_logs[message.command_id].append(message)

        print(f"\nFound {len(command_logs)} commands with tracked output\n")

        # Show first 5 command/output pairs
        for i, (command_id, messages) in enumerate(list(command_logs.items())[:5]):
            print(f"Command {i+1} (ID: {command_id[:8]}...)")
            print("-" * 60)

            for msg in messages:
                if msg.direction == "input":
                    print(f"INPUT:  {msg.content[:70]}")
                else:
                    lines = msg.content.split("\n")
                    for line in lines[:3]:  # Show first 3 lines of output
                        print(f"OUTPUT: {line[:70]}")
                    if len(lines) > 3:
                        print(f"OUTPUT: ... ({len(lines) - 3} more lines)")

            print()

    finally:
        await service.shutdown()


async def example_session_monitoring():
    """Example 5: Monitor session health and recent activity."""
    print("\n" + "=" * 60)
    print("Example 5: Monitor Session Health and Activity")
    print("=" * 60)

    service = SSHService()

    try:
        agent_id = "example-agent"
        session_id = "example-session-id"

        # Get current session status
        sessions = await service.list_sessions(agent_id, include_closed=True, limit=100)

        session_info = next((s for s in sessions if s.session_id == session_id), None)

        if session_info:
            print(f"\nSession Status Report: {session_info.session_id}")
            print("-" * 60)
            print(f"Status: {session_info.status}")
            print(
                f"Host: {session_info.host} ({session_info.username}@{session_info.host})"
            )
            print(f"Created: {session_info.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
            print(
                f"Last Activity: {session_info.last_activity.strftime('%Y-%m-%d %H:%M:%S')}"
            )

            # Calculate age and inactivity
            age = datetime.now() - session_info.created_at
            inactivity = datetime.now() - session_info.last_activity

            print(f"Age: {age}")
            print(f"Inactivity: {inactivity}")
            print(f"Commands Executed: {session_info.command_count}")
            print(f"Total Messages: {session_info.message_count}")

            # Get recent output for health check
            history = await service.get_session_history(
                session_id, limit=20, direction="output"
            )

            print(f"\nRecent Activity: {len(history.messages)} recent output messages")
            if history.messages:
                print("Last 3 messages:")
                for message in history.messages[-3:]:
                    first_line = message.content.split("\n")[0][:60]
                    timestamp = message.timestamp.strftime("%H:%M:%S")
                    print(f"  [{timestamp}] {first_line}")
        else:
            print(f"\nSession {session_id} not found")

    finally:
        await service.shutdown()


async def main():
    """Run all examples."""
    print("\n" + "=" * 60)
    print("SSH Agent Bridge - Session Listing & History Examples")
    print("=" * 60)

    # Note: These examples demonstrate the API patterns.
    # In a real scenario, you would:
    # 1. Create sessions with create_session()
    # 2. Execute commands with run_command()
    # 3. Then use these examples to query history

    print("\nNote: These examples show API patterns.")
    print("In a real scenario, first create sessions and run commands,")
    print("then use these methods to list and query history.\n")

    try:
        # Run all examples (they handle missing sessions gracefully)
        await example_session_listing()
        await example_session_history()
        await example_history_filtering()
        await example_command_correlation()
        await example_session_monitoring()

    except Exception as e:
        print(f"Error: {e}")
        print("\nNote: These examples require active sessions.")
        print(
            "Create sessions first with create_session() and run commands with run_command()."
        )


if __name__ == "__main__":
    asyncio.run(main())
