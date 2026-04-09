#!/usr/bin/env python3
"""
Buffer Performance Benchmark for SSH Agent Bridge.

This script benchmarks buffer operations under various load conditions
to help identify performance characteristics and potential bottlenecks.
"""

import asyncio
import time
import statistics
from typing import List
from ssh_agent_bridge import SSHService


async def benchmark_buffer_operations():
    """Benchmark buffer operations with simulated data."""
    print("SSH Agent Bridge - Buffer Performance Benchmark")
    print("=" * 50)

    service = SSHService()

    # Test different buffer sizes
    buffer_sizes = [1000, 10000, 100000, 1000000]  # characters
    marker_searches = 10  # searches per buffer size

    print(f"Testing with {marker_searches} marker searches per buffer size")
    print()

    for size in buffer_sizes:
        print(f"Buffer Size: {size:,} characters")

        # Create test buffer with marker at the end
        test_data = "x" * (size - 20) + "MARKER_test_123 0\n"
        marker = "MARKER_test_123"

        # Benchmark marker searches
        search_times: List[float] = []

        for _ in range(marker_searches):
            start_time = time.perf_counter()

            # Simulate marker search (simplified version of actual logic)
            marker_index = test_data.find(marker)
            if marker_index >= 0:
                # Extract exit code (simplified)
                marker_line_start = test_data.rfind("\n", 0, marker_index) + 1
                marker_line_end = test_data.find("\n", marker_index)
                if marker_line_end == -1:
                    marker_line_end = len(test_data)
                marker_line = test_data[marker_line_start:marker_line_end]
                parts = marker_line.strip().split()
                exit_code = int(parts[-1]) if len(parts) >= 2 else 1

            end_time = time.perf_counter()
            search_times.append(end_time - start_time)

        avg_time = statistics.mean(search_times)
        min_time = min(search_times)
        max_time = max(search_times)

        print(".4f")
        print(".4f")
        print(".4f")
        print()

    print("Benchmark completed.")


async def benchmark_session_creation():
    """Benchmark session creation overhead."""
    print("Session Creation Benchmark")
    print("=" * 30)

    service = SSHService()
    iterations = 100

    # Note: This would require actual SSH server for real benchmarking
    # For now, just measure the in-memory operations
    print(f"Simulated session creation ({iterations} iterations)")
    print("Note: Real benchmark requires SSH server connection")
    print()


if __name__ == "__main__":
    asyncio.run(benchmark_buffer_operations())
    asyncio.run(benchmark_session_creation())
