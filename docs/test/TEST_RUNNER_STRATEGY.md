# Test Runner Strategy for SSH Agent Bridge

## Problem
Running `pytest tests/test_core.py` hangs indefinitely due to several issues:
1. Event loop fixture with session scope reusing event loop across tests
2. Async primitives (Lock, Condition) created in non-async fixture context
3. Reader tasks not properly cleaned up after session tests

## Solution: Selective Test Running

Instead of running the full test file at once, use pytest markers to run tests in groups:

### Run Individual Test Classes

```bash
# Test data types and exceptions (fast, no async I/O)
uv run pytest tests/test_core.py::TestDataTypes -v
uv run pytest tests/test_core.py::TestExceptions -v

# Test connection management (async but quick)
uv run pytest tests/test_core.py::TestConnectionManagement -v

# Test session lifecycle (careful - can hang if not fixed)
uv run pytest tests/test_core.py::TestSessionLifecycle -v

# Test command execution (prone to hanging)
uv run pytest tests/test_core.py::TestCommandExecution -v
```

### Run Individual Tests

```bash
# Test a specific test function
uv run pytest tests/test_core.py::TestSSHService::test_service_initialization -v
uv run pytest tests/test_core.py::TestSSHService::test_marker_generation -v
uv run pytest tests/test_core.py::TestConnectionManagement::test_connection_creation_success -v
```

### Recommended Test Order (For Development)

1. **Basic Types & Exceptions** (No async, always fast):
   ```bash
   uv run pytest tests/test_core.py::TestDataTypes tests/test_core.py::TestExceptions -v
   ```

2. **Service Initialization** (Minimal async):
   ```bash
   uv run pytest tests/test_core.py::TestSSHService -v
   ```

3. **Connection Management** (Async with mocks):
   ```bash
   uv run pytest tests/test_core.py::TestConnectionManagement -v
   ```

4. **Session Lifecycle** (Medium complexity):
   ```bash
   uv run pytest tests/test_core.py::TestSessionLifecycle::test_create_session_success -v
   ```

### Pytest Markers (Future Enhancement)

Add markers to test_core.py for better organization:

```python
@pytest.mark.fast        # No I/O, runs instantly
@pytest.mark.asyncio
def test_marker_generation(self):
    ...

@pytest.mark.asyncio_io  # Async with I/O, may take longer
def test_command_execution(self):
    ...

@pytest.mark.slow       # Integration tests, takes longest
def test_end_to_end(self):
    ...
```

Then run:
```bash
uv run pytest tests/test_core.py -m fast -v         # Only fast tests
uv run pytest tests/test_core.py -m asyncio_io -v   # Medium tests
uv run pytest tests/test_core.py -m slow -v         # Integration tests
```

## Fixes Applied

### Fix 1: Event Loop Fixture (conftest.py)
- **Before**: `scope="session"` - single loop reused for all tests
- **After**: `scope="function"` (default) - fresh loop per test
- **Impact**: Prevents event loop reuse issues and hangs

### Fix 2: Async Fixture (conftest.py)
- **Before**: `sample_session_info` created Lock/Condition in non-async context
- **After**: Made fixture async, creates primitives in proper event loop context
- **Impact**: Proper asyncio resource management

## Current Status

- ✅ Conftest configuration fixed
- ✅ Async fixture converted to async
- ⏳ Individual tests verified (in progress)
- ⏳ Full test suite validation (next step)

## Next Steps

1. Run individual test classes to verify fixes
2. Add pytest markers for test categorization
3. Create CI/CD configuration to run tests safely
4. Document any remaining hanging tests
5. Implement workarounds or fixes for problematic tests

## Troubleshooting

If a test still hangs:

1. **Check for infinite loops**: Look for `while True:` without proper break conditions
2. **Check for deadlocks**: Multiple async locks acquired in wrong order
3. **Check for pending tasks**: Reader tasks not being cancelled properly
4. **Increase timeout**: Add `timeout` parameter to pytest config if tests are legitimately slow

```python
# In pytest.ini or pyproject.toml
[tool:pytest]
asyncio_mode = auto
timeout = 5  # 5 second timeout per test
```

## Additional Resources

- pytest-asyncio docs: https://pytest-asyncio.readthedocs.io/
- Event loop scoping: https://docs.pytest.org/en/7.1.x/fixture.html#scope
- asyncio debugging: https://docs.python.org/3/library/asyncio-dev.html
