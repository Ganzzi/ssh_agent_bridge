# Development Guide

## Prerequisites

- Python >=3.8
- [uv](https://github.com/astral-sh/uv) (recommended package manager)

## Setup

```bash
# Install development dependencies
uv sync --all-groups --all-extras

# Or with pip
pip install -e ".[dev]"
```

## Unit Tests (PR Gate)

```bash
# Run unit tests only (no integration/e2e tests)
uv run pytest -m "not integration and not e2e" -q

# Run specific test module
uv run pytest tests/unit/test_connection_pool.py -m "unit" -v
```

## Integration / E2E Tests

```bash
# Run all tests
uv run pytest -q

# Run integration tests only
uv run pytest -m integration -v

# Run E2E tests only
uv run pytest -m e2e -v
```

## Coverage

```bash
# Run coverage for unit tests
uv run pytest -m "not integration and not e2e" --cov=src/ssh_agent_bridge --cov-report=term-missing

# Generate HTML coverage report
uv run pytest -m "not integration and not e2e" --cov=src/ssh_agent_bridge --cov-report=html
```

## Type Checking

```bash
# Run mypy type checking
uv run mypy src/
```

## Formatting

```bash
# Format code with black
uv run black src/

# Check formatting
uv run black --check src/
```

## CI Behavior

The CI pipeline runs:

```bash
uv sync --all-groups --all-extras
uv run pytest -m "not integration and not e2e" -q
```

Only unit tests are run in CI to ensure fast feedback. Integration and E2E tests require SSH server infrastructure and are run manually or in specialized test environments.

## Test Structure

```
tests/
├── unit/          # Unit tests (no external dependencies, PR-gated)
│   ├── test_types.py
│   ├── test_exceptions.py
│   ├── test_connection_pool.py
│   ├── test_session_lifecycle.py
│   ├── test_command_execution.py
│   ├── test_markers.py
│   ├── test_prompt_handling.py
│   ├── test_signal_handling.py
│   └── test_history.py
├── integration/   # Integration tests (require SSH server)
│   └── test_ssh_integration.py
├── e2e/          # E2E tests (full workflow tests)
│   └── test_session_workflow.py
├── conftest.py   # Shared fixtures
└── legacy/       # Archived monolithic test file
    └── test_core_archive.py
```

## Known Issues

- Integration tests require a real SSH server or comprehensive mock setup
- Some async tests may produce RuntimeWarnings about unawaited coroutines (harmless)
- The legacy test_core_archive.py is kept for reference but not run by default
