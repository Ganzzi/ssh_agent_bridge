#!/usr/bin/env python3
"""Multi-agent multi-session example.

This example demonstrates how multiple AI agents can work simultaneously on the
same host, each maintaining their own sessions and connection pooling.
"""

import asyncio
import sys
from ssh_agent_bridge import SSHService


class Agent:
    """Represents an AI agent with its own session management."""

    def __init__(self, agent_id, service):
        self.agent_id = agent_id
        self.service = service
        self.session_id = None

    async def initialize_session(self, host, username, password):
        """Initialize agent's session."""
        print(f"[{self.agent_id}] Initializing session...")
        self.session_id = await self.service.create_session(
            self.agent_id, host, username, password
        )
        print(f"[{self.agent_id}] Session created: {self.session_id}")

    async def run_task(self, task_name, command):
        """Run a task for this agent."""
        if not self.session_id:
            raise RuntimeError(f"Agent {self.agent_id} session not initialized")

        print(f"[{self.agent_id}] Starting task: {task_name}")
        result = await self.service.run_command(self.session_id, command)

        if result.status == "completed":
            print(
                f"[{self.agent_id}] Task '{task_name}' completed (exit code: {result.exit_code})"
            )
            return result
        else:
            print(f"[{self.agent_id}] Task '{task_name}' is running in background")
            return result

    async def cleanup(self):
        """Clean up agent's resources."""
        if self.session_id:
            print(f"[{self.agent_id}] Cleaning up session...")
            await self.service.end_session(self.session_id)
            self.session_id = None


async def agent_monitor_task(service, agent_id, session_id):
    """Background task to monitor an agent's session."""
    print(f"[MONITOR-{agent_id}] Starting to monitor session {session_id}")

    try:
        while True:
            # Check if session still exists
            # In a real implementation, you might check session health
            await asyncio.sleep(10)
            print(f"[MONITOR-{agent_id}] Session {session_id} is healthy")
    except asyncio.CancelledError:
        print(f"[MONITOR-{agent_id}] Monitor task cancelled")
        raise


async def run_parallel_agents(service, host, username, password):
    """Run multiple agents working in parallel."""
    print("Creating multiple agents...")

    # Create agents
    agents = [
        Agent("web-scraper-agent", service),
        Agent("log-analyzer-agent", service),
        Agent("backup-agent", service),
        Agent("health-check-agent", service),
    ]

    # Initialize all agent sessions
    init_tasks = []
    for agent in agents:
        task = agent.initialize_session(host, username, password)
        init_tasks.append(task)

    await asyncio.gather(*init_tasks)
    print("All agents initialized")

    # Start background monitoring tasks
    monitor_tasks = []
    for agent in agents:
        task = asyncio.create_task(
            agent_monitor_task(service, agent.agent_id, agent.session_id)
        )
        monitor_tasks.append(task)

    try:
        # Define agent tasks
        tasks = [
            # Web scraper agent
            agents[0].run_task(
                "scrape-website", "curl -s https://httpbin.org/get | head -20"
            ),
            # Log analyzer agent
            agents[1].run_task(
                "analyze-logs", "tail -50 /var/log/syslog | grep -i error | wc -l"
            ),
            # Backup agent
            agents[2].run_task(
                "create-backup",
                "echo 'Backup started at $(date)' && sleep 2 && echo 'Backup completed'",
            ),
            # Health check agent
            agents[3].run_task("health-check", "uptime && df -h / | tail -1"),
        ]

        # Run all tasks concurrently
        print("Running all agent tasks concurrently...")
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        for i, result in enumerate(results):
            agent = agents[i]
            if isinstance(result, Exception):
                print(f"[{agent.agent_id}] Task failed: {result}")
            else:
                print(f"[{agent.agent_id}] Task result: exit_code={result.exit_code}")

        # Simulate some follow-up work
        print("Running follow-up tasks...")

        followup_tasks = [
            agents[0].run_task(
                "process-data", "echo 'Processing scraped data...' && sleep 1"
            ),
            agents[1].run_task(
                "generate-report", "echo 'Generating log analysis report...' && sleep 1"
            ),
            agents[2].run_task(
                "verify-backup", "echo 'Verifying backup integrity...' && sleep 1"
            ),
            agents[3].run_task("alert-if-needed", "echo 'System health OK'"),
        ]

        followup_results = await asyncio.gather(*followup_tasks, return_exceptions=True)

        for i, result in enumerate(followup_results):
            agent = agents[i]
            if isinstance(result, Exception):
                print(f"[{agent.agent_id}] Follow-up failed: {result}")
            else:
                print(f"[{agent.agent_id}] Follow-up completed")

    finally:
        # Cancel monitor tasks
        print("Stopping monitor tasks...")
        for task in monitor_tasks:
            task.cancel()

        try:
            await asyncio.gather(*monitor_tasks, return_exceptions=True)
        except:
            pass

        # Clean up all agents
        print("Cleaning up all agents...")
        cleanup_tasks = [agent.cleanup() for agent in agents]
        await asyncio.gather(*cleanup_tasks, return_exceptions=True)


async def demonstrate_connection_pooling(service, host, username, password):
    """Demonstrate connection pooling across multiple agents."""
    print("Demonstrating connection pooling...")

    # Create multiple agents that will share connections
    agents = []
    for i in range(5):
        agent = Agent(f"pool-test-agent-{i}", service)
        await agent.initialize_session(host, username, password)
        agents.append(agent)

    print(f"Created {len(agents)} agents - they share connection pooling")

    # Run quick tasks
    tasks = []
    for agent in agents:
        task = agent.run_task(
            f"quick-task-{agent.agent_id}", "echo 'Hello from agent' && date"
        )
        tasks.append(task)

    results = await asyncio.gather(*tasks)

    for agent, result in zip(agents, results):
        print(f"[{agent.agent_id}] Result: {result.stdout.strip()}")

    # Clean up
    cleanup_tasks = [agent.cleanup() for agent in agents]
    await asyncio.gather(*cleanup_tasks)


async def main():
    """Run multi-agent examples."""
    if len(sys.argv) != 4:
        print("Usage: python multi_agent_multi_session.py <host> <username> <password>")
        sys.exit(1)

    host, username, password = sys.argv[1:]

    service = SSHService()

    try:
        print(f"Running multi-agent examples on {host}")

        # Example 1: Parallel agent execution
        print("\n=== Example 1: Parallel Agent Execution ===")
        await run_parallel_agents(service, host, username, password)

        # Example 2: Connection pooling
        print("\n=== Example 2: Connection Pooling ===")
        await demonstrate_connection_pooling(service, host, username, password)

        print("\nAll multi-agent examples completed successfully!")

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    finally:
        await service.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
