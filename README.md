# SSH Agent Bridge

[![PyPI version](https://badge.fury.io/py/ssh-agent-bridge.svg)](https://pypi.org/project/ssh-agent-bridge/)
[![Python versions](https://img.shields.io/pypi/pyversions/ssh-agent-bridge.svg)](https://pypi.org/project/ssh-agent-bridge/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Python package that provides high-level SSH session management for AI agents. Enables non-interactive agents to communicate with remote VMs over SSH using a tool-based interface with structured parameters and returns.

## Key Features

- **Agent-Centric Design**: Connection pooling per agent with session isolation
- **Structured Communication**: No CLI streaming - structured parameters and returns
- **Marker-Based Execution**: Reliable command completion detection with exit codes
- **Interactive Support**: Handle prompts, passwords, and confirmations
- **Signal Handling**: Send SIGINT, SIGKILL, and other signals to processes
- **Async First**: Built on asyncio for high concurrency and performance
- **Timeout Management**: Configurable timeouts with graceful degradation

## Installation

```bash
pip install ssh-agent-bridge
```

For development:

```bash
git clone https://github.com/Ganzzi/ssh-agent-bridge.git
cd ssh_agent_bridge
pip install -e .[dev]
```

## Quick Start

### Simple Ephemeral Command

```python
import asyncio
from ssh_agent_bridge import SSHService

async def main():
    service = SSHService()

    try:
        result = await service.run_ephemeral(
            agent_id="my-agent",
            host="example.com",
            command="echo 'Hello, World!'",
            username="myuser",
            password="mypassword"
        )

        print(f"Exit code: {result.exit_code}")
        print(f"Output: {result.stdout}")

    finally:
        await service.shutdown()

asyncio.run(main())
```

### Persistent Session

```python
import asyncio
from ssh_agent_bridge import SSHService

async def main():
    service = SSHService()

    try:
        # Create session
        session_id = await service.create_session(
            agent_id="my-agent",
            host="example.com",
            username="myuser",
            password="mypassword"
        )

        # Run multiple commands
        commands = ["pwd", "ls -la", "whoami"]
        for cmd in commands:
            result = await service.run_command(session_id, cmd)
            print(f"$ {cmd}")
            print(result.stdout)

        # Clean up
        await service.end_session(session_id)

    finally:
        await service.shutdown()

asyncio.run(main())
```

## Documentation

- **[API Reference](docs/API.md)** - Complete method signatures and parameters
- **[User Guide](docs/GUIDE.md)** - Installation, usage patterns, and best practices
- **[Architecture](docs/ARCHITECTURE.md)** - Design decisions and technical details
- **[Development Plan](docs/plan/DEVELOPMENT_PLAN.md)** - Project roadmap and implementation status

## Requirements

- Python 3.8+
- SSH server access (OpenSSH recommended)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Development

### Setup

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Run tests
pytest

# Run type checking
mypy src/

# Format code
black src/
```

### Testing

```bash
# Run all tests (55/55 core tests PASS - 100% pass rate)
uv run pytest tests/test_core.py -v

# Run with coverage (86% coverage, exceeds 80% target)
uv run pytest tests/test_core.py --cov=src/ssh_agent_bridge --cov-report=html

# Run core unit tests
uv run pytest tests/test_core.py::TestDataTypes tests/test_core.py::TestExceptions tests/test_core.py::TestSSHService tests/test_core.py::TestConnectionManagement tests/test_core.py::TestSessionLifecycle tests/test_core.py::TestCommandExecution -v
```

For detailed testing information, see:
- **[TEST_RUNNER_STRATEGY.md](tests/TEST_RUNNER_STRATEGY.md)** - Safe test execution guide
- **[TESTING_PATTERNS.md](tests/TESTING_PATTERNS.md)** - Patterns and anti-patterns

## Project Status

**Phase 6 Complete ✅ | Released on PyPI 🚀**

### Current Phase: Phase 6 - Packaging & Release (COMPLETE)

#### Phase 6 Completion
- ✅ **Build System:** PEP 517 build configured, wheel & sdist generation tested
- ✅ **PyPI Preparation:** Package metadata, classifiers, and documentation uploaded
- ✅ **Release Process:** Version 0.1.1 tagged and released to PyPI
- ✅ **Package Available:** https://pypi.org/project/ssh-agent-bridge/

#### Final Test Status
- ✅ **55/55 core tests PASS** (100% pass rate)
- ✅ **86% Code Coverage** (exceeded 80% target)
- ✅ **7/7 Example Scripts** (all working successfully)
- ✅ **100% Core Functionality** (production ready)

#### Next Phase: Phase 7 - Maintenance & Enhancements
- � **User Feedback:** Collect issues and feature requests
- 🔧 **Maintenance:** Bug fixes and security updates
- ✨ **Future Features:** Connection multiplexing, advanced prompt detection, SFTP support
- 🌐 **Community:** Documentation improvements, contribution guidelines

## Support

If you find this project helpful, please consider:

- ⭐ Starring the repository
- 🐛 Reporting bugs or issues
- 💡 Suggesting features or improvements
- 📖 Contributing documentation

## Related Projects

- [asyncssh](https://github.com/ronf/asyncssh) - Underlying SSH protocol implementation
- [paramiko](https://github.com/paramiko/paramiko) - Alternative SSH library for Python