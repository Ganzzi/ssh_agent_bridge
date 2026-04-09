# Phase 3 Testing - Recommended Test Patterns

This document provides recommended patterns for writing and running tests for SSH Agent Bridge Phase 3 and beyond.

## Test Categories & Markers

### 1. Fast Unit Tests (@pytest.mark.fast)
- No I/O operations
- No network access
- Complete in < 100ms
- Include: Data type tests, exception tests, simple function tests

**Example:**
```python
class TestDataTypes:
    @pytest.mark.fast
    def test_command_result_creation(self):
        """Pure Python object creation - no I/O."""
        result = CommandResult(
            status="completed", 
            exit_code=0, 
            stdout="Hello"
        )
        assert result.exit_code == 0

    @pytest.mark.fast
    def test_marker_generation(self, ssh_service):
        """Pure Python - generates unique markers."""
        marker1 = ssh_service._make_marker()
        marker2 = ssh_service._make_marker()
        assert marker1 != marker2
```

**Run:** `uv run pytest tests/test_core.py -m fast -v`

---

### 2. Async Unit Tests (@pytest.mark.asyncio)
- With mocked I/O (no real SSH)
- Test async logic flow
- Complete in < 500ms per test
- Include: Connection, session, command tests

**Example:**
```python
class TestConnectionManagement:
    @pytest.mark.asyncio
    async def test_connection_creation_success(self, ssh_service, mock_asyncssh):
        """Test connection creation with mocked SSH."""
        with patch("asyncssh.connect", mock_asyncssh.connect):
            conn_info = await ssh_service._ensure_connection(
                agent_id="test-agent",
                host="example.com",
                username="testuser",
                password="testpass",
            )
            assert conn_info.host == "example.com"
```

**Run:** `uv run pytest tests/test_core.py::TestConnectionManagement -v`

---

### 3. Integration Tests (@pytest.mark.asyncio, @pytest.mark.integration)
- Full end-to-end flows
- May use real or containerized SSH server
- Can take seconds per test
- Include: Full session workflows, multi-command sequences

**Example:**
```python
class TestIntegrationWorkflows:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_full_session_workflow(self, ssh_service):
        """Full session: create, run commands, end."""
        session_id = await ssh_service.create_session(
            agent_id="test-agent",
            host="localhost",  # Real or container
            username="testuser",
            password="testpass",
        )
        
        result = await ssh_service.run_command(session_id, "echo hello")
        assert result.status == "completed"
        assert "hello" in result.stdout
        
        await ssh_service.end_session(session_id)
```

**Run:** `uv run pytest tests/ -m integration -v`

---

## Fixture Patterns

### Safe Async Fixture Pattern
```python
@pytest.fixture
async def my_async_fixture(event_loop):
    """Async fixture - proper event loop context.
    
    Use this pattern for creating asyncio primitives or async resources.
    """
    # Setup in async context
    lock = asyncio.Lock()
    resource = await some_async_setup()
    
    yield resource  # Provide to test
    
    # Teardown/cleanup
    await some_async_cleanup(resource)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
```

### Mock SSH Connection Fixture
```python
@pytest.fixture
def mock_asyncssh():
    """Mock asyncssh module for testing without real SSH."""
    with patch.dict("sys.modules", {"asyncssh": MagicMock()}):
        mock_asyncssh = MagicMock()
        
        # Mock connection
        mock_conn = AsyncMock()
        mock_conn.create_process = AsyncMock()
        
        # Mock process  
        mock_process = AsyncMock()
        mock_process.stdout = AsyncMock()
        mock_process.stderr = AsyncMock()
        mock_process.stdin = AsyncMock()
        
        mock_conn.create_process.return_value = mock_process
        mock_asyncssh.connect = AsyncMock(return_value=mock_conn)
        
        yield mock_asyncssh
```

---

## Test Execution Strategies

### Strategy 1: Developer Workflow (During Development)
Run fast tests frequently to catch regressions:

```bash
# Quick feedback loop (< 1 second)
uv run pytest tests/test_core.py -m fast -v

# Test specific feature (< 2 seconds)
uv run pytest tests/test_core.py::TestConnectionManagement::test_connection_reuse -v

# Full test class when ready (< 5 seconds)
uv run pytest tests/test_core.py::TestSessionLifecycle -v
```

### Strategy 2: Pre-Commit Check
Run comprehensive tests before committing:

```bash
# Fast + async unit tests
uv run pytest tests/test_core.py -m "fast or asyncio" -v --tb=short

# With coverage
uv run pytest tests/test_core.py -m "fast or asyncio" --cov=src/ssh_agent_bridge --cov-report=term-missing
```

### Strategy 3: CI/CD Pipeline
```bash
# Phase 1: Fast tests (quick feedback)
pytest tests/ -m fast -v

# Phase 2: Async unit tests (thorough)  
pytest tests/ -m asyncio --cov=src/ssh_agent_bridge --cov-report=xml

# Phase 3: Integration tests (full validation)
pytest tests/ -m integration -v
```

---

## Common Patterns & Anti-Patterns

### ✅ GOOD Patterns

```python
# 1. Async test with mocking
@pytest.mark.asyncio
async def test_something(ssh_service, mock_asyncssh):
    with patch("asyncssh.connect", mock_asyncssh.connect):
        result = await ssh_service.some_method()
        assert result.success

# 2. Proper async fixture cleanup
@pytest.fixture
async def session_with_cleanup(event_loop):
    session = create_session()
    yield session
    await session.cleanup()  # Guaranteed cleanup

# 3. Timeout protection
@pytest.mark.asyncio
async def test_with_timeout():
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(long_operation(), timeout=1.0)

# 4. Use markers for organization
@pytest.mark.asyncio
@pytest.mark.fast
def test_quick_operation():
    # Automatically runs with fast marker
    pass
```

### ❌ ANTI-PATTERNS (Avoid)

```python
# 1. DON'T create async primitives in sync fixture
@pytest.fixture
def bad_fixture():
    lock = asyncio.Lock()  # ❌ Wrong context
    return lock

# 2. DON'T use session-scope event loop
@pytest.fixture(scope="session")
def event_loop():  # ❌ Causes deadlocks
    ...

# 3. DON'T create tasks without tracking for cleanup
async def test_bad():
    task = asyncio.create_task(background_work())  # ❌ No cleanup
    # Task might not finish before test ends

# 4. DON'T run full suite without markers
pytest tests/test_core.py  # ❌ May hang

# 5. DON'T mix sync and async in wrong context
@pytest.fixture
async def fixture():
    lock = asyncio.Lock()  # ✅ Correct
    sync_resource = SyncClass()  # ⚠️ Consider if needed async
    yield lock, sync_resource
```

---

## Running Tests Safely

### Quick Reference Table

| Goal | Command | Time | Risk |
|------|---------|------|------|
| Quick check | `uv run pytest -m fast -v` | < 1s | 🟢 Safe |
| Test one class | `uv run pytest tests/test_core.py::TestClass -v` | < 5s | 🟢 Safe |
| Test one method | `uv run pytest tests/test_core.py::TestClass::test_method -v` | < 1s | 🟢 Safe |
| Full async tests | `uv run pytest tests/test_core.py -m asyncio -v` | < 30s | 🟡 Check output |
| Full suite | `uv run pytest tests/test_core.py -v` | ⏱️ ? | 🔴 **RISKY** |
| All with coverage | `uv run pytest tests/ --cov` | < 60s | 🟡 Slower |

---

## Debugging Hanging Tests

If a test seems to hang:

1. **Check for infinite loops**
   ```python
   # Look for while True without proper exit
   while True:
       if done_condition:
           break  # ✅ Good
   ```

2. **Check for deadlocks**
   ```python
   # Multiple locks acquired in wrong order
   async with lock1:
       async with lock2:  # ❌ Bad order if lock2 tries to acquire lock1
           pass
   ```

3. **Check for pending tasks**
   ```python
   # Ensure all tasks are cancelled/awaited
   if task and not task.done():
       task.cancel()
       try:
           await task
       except asyncio.CancelledError:
           pass
   ```

4. **Use pytest timeout plugin**
   ```bash
   pip install pytest-timeout
   pytest --timeout=5 tests/test_core.py  # Kill tests after 5s
   ```

---

## Configuration Examples

### pytest.ini
```ini
[pytest]
asyncio_mode = auto
timeout = 10  # 10 second timeout per test
markers =
    fast: fast unit tests (no I/O)
    asyncio: async tests
    asyncio_io: async with I/O
    integration: integration tests
    slow: slow running tests
```

### pyproject.toml  
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
timeout = 10
markers = [
    "fast: fast unit tests (no I/O)",
    "asyncio: async tests", 
    "integration: integration tests",
]
```

---

## Next Steps for Phase 3

1. ✅ Fix pytest-asyncio configuration (DONE)
2. Add markers to all tests in test_core.py
3. Implement connection management tests with proper mocking
4. Implement session lifecycle tests
5. Implement command execution tests
6. Create integration test file (test_integration.py)
7. Achieve 80%+ coverage target

---

**Phase 3 Status:** Infrastructure fixed, ready for test implementation ✅
