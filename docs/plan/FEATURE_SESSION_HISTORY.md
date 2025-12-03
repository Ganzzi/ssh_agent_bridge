# Feature: Session Listing & Message History (v0.2)

## Overview

Add the ability to list all active sessions for an agent and retrieve message history (input/output) for each session. This enhances observability and debugging capabilities for AI agents.

---

## Problem Statement

**Current Limitations:**
1. **No session visibility**: Agents cannot list their active sessions
2. **Buffer-only storage**: Output is accumulated in a single `buffer` string with no structure
3. **No input tracking**: Commands sent to sessions are not recorded
4. **No history retrieval**: Cannot query past command/output pairs

**Agent Need:**
- List sessions to understand current state
- Review command history for context and debugging
- Correlate inputs with outputs for decision making

---

## Proposed Solution

### Design Recommendations

#### 1. **Structured Message History** (Recommended)

Replace the simple buffer string with a structured message history:

```python
@dataclass
class Message:
    """A single message in the session history."""
    timestamp: datetime
    direction: str  # "input" | "output"
    content: str
    command_id: Optional[str] = None  # Links output to input
    marker: Optional[str] = None  # For command outputs
```

**Benefits:**
- Correlate inputs with outputs
- Query by time range
- Support replay/debugging scenarios
- Memory-efficient with configurable limits

#### 2. **Session Summary for Listing**

New method to list sessions with summary info:

```python
@dataclass
class SessionSummary:
    """Summary of a session for listing."""
    session_id: str
    agent_id: str
    host: str
    username: str
    status: str  # "active" | "closed" | "broken"
    created_at: datetime
    last_activity: datetime
    command_count: int
    message_count: int
```

#### 3. **Configurable History Limits**

Prevent unbounded memory growth:

```python
@dataclass
class HistoryConfig:
    """Configuration for message history."""
    max_messages: int = 1000  # Max messages per session
    max_message_size: int = 65536  # Max size per message (64KB)
    trim_strategy: str = "oldest"  # "oldest" | "largest" | "none"
```

---

## API Design

### New Methods

#### `list_sessions(agent_id: str) -> List[SessionSummary]`
List all sessions (active and recently closed) for an agent.

```python
async def list_sessions(
    self,
    agent_id: str,
    include_closed: bool = False,
    limit: int = 100
) -> List[SessionSummary]:
    """List all sessions for the specified agent.
    
    Args:
        agent_id: Agent identifier
        include_closed: Include closed/broken sessions
        limit: Maximum sessions to return
    
    Returns:
        List of SessionSummary objects
    """
```

#### `get_session_history(session_id: str, ...) -> SessionHistory`
Get message history for a session.

```python
async def get_session_history(
    self,
    session_id: str,
    limit: int = 100,
    since: Optional[datetime] = None,
    direction: Optional[str] = None  # "input" | "output" | None for both
) -> SessionHistory:
    """Get message history for a session.
    
    Args:
        session_id: Session identifier
        limit: Maximum messages to return
        since: Only messages after this timestamp
        direction: Filter by direction
    
    Returns:
        SessionHistory with messages and metadata
    """
```

### New Data Types

```python
@dataclass
class Message:
    """A single message in session history."""
    id: str
    timestamp: datetime
    direction: str  # "input" | "output"
    content: str
    command_id: Optional[str] = None

@dataclass
class SessionHistory:
    """History of messages for a session."""
    session_id: str
    messages: List[Message]
    total_count: int  # Total messages (may be > len(messages) if limited)
    truncated: bool  # True if history was trimmed

@dataclass
class SessionSummary:
    """Summary information for a session."""
    session_id: str
    agent_id: str
    host: str
    username: str
    port: int
    status: str
    created_at: datetime
    last_activity: datetime
    command_count: int
    message_count: int
```

---

## Architecture Changes

### Current Buffer Model (v0.1)
```
SessionInfo:
  buffer: str  # All output concatenated
  markers: Set[str]  # Active markers
```

### New History Model (v0.2)
```
SessionInfo:
  buffer: str  # Keep for backward compatibility & marker detection
  history: List[Message]  # Structured message history
  history_config: HistoryConfig  # Limits and behavior
  created_at: datetime
  last_activity: datetime
  command_count: int
```

### Backward Compatibility

- Keep existing `buffer` field for marker detection (internal use)
- Add `history` field for structured tracking
- Existing code continues to work unchanged
- New methods are additive

---

## Implementation Phases

## Phase 1: Data Types & Session Tracking (Day 1)

### 1.1 Add New Data Types
- [ ] Add `Message` dataclass to `types.py`
- [ ] Add `SessionSummary` dataclass to `types.py`
- [ ] Add `SessionHistory` dataclass to `types.py`
- [ ] Add `HistoryConfig` dataclass to `types.py`
- [ ] Update `SessionInfo` with new fields:
  - `history: List[Message]`
  - `history_config: HistoryConfig`
  - `created_at: datetime`
  - `last_activity: datetime`
  - `command_count: int`

### 1.2 Update Session Creation
- [ ] Initialize history list on session creation
- [ ] Set `created_at` timestamp
- [ ] Initialize `command_count` to 0
- [ ] Add default `HistoryConfig`

### 1.3 Unit Tests for Data Types
- [ ] Test `Message` creation and serialization
- [ ] Test `SessionSummary` fields
- [ ] Test `SessionHistory` with messages
- [ ] Test `HistoryConfig` defaults and validation

---

## Phase 2: Message Recording (Day 2)

### 2.1 Record Input Messages
- [ ] In `run_command()`: Record command as input message
- [ ] In `send_input()`: Record input as input message
- [ ] Generate unique `command_id` for correlation

### 2.2 Record Output Messages
- [ ] In `_read_stream_loop()`: Record output chunks as messages
- [ ] Link output to command via `command_id` when marker detected
- [ ] Update `last_activity` timestamp on each message

### 2.3 History Trimming
- [ ] Implement `_trim_history()` method
- [ ] Enforce `max_messages` limit
- [ ] Enforce `max_message_size` limit
- [ ] Call trim after each message addition

### 2.4 Unit Tests for Recording
- [ ] Test input message recording
- [ ] Test output message recording
- [ ] Test message correlation via command_id
- [ ] Test history trimming

---

## Phase 3: API Methods (Day 3)

### 3.1 Implement `list_sessions()`
- [ ] Filter sessions by agent_id
- [ ] Create `SessionSummary` for each session
- [ ] Support `include_closed` flag
- [ ] Support `limit` parameter

### 3.2 Implement `get_session_history()`
- [ ] Validate session exists
- [ ] Filter messages by `since` timestamp
- [ ] Filter messages by `direction`
- [ ] Apply `limit` and set `truncated` flag

### 3.3 Update Package Exports
- [ ] Export new types from `__init__.py`
- [ ] Export new methods

### 3.4 Unit Tests for API
- [ ] Test `list_sessions()` with multiple agents
- [ ] Test `list_sessions()` with include_closed
- [ ] Test `get_session_history()` basic case
- [ ] Test `get_session_history()` with filters
- [ ] Test `get_session_history()` with limits

---

## Phase 4: Documentation & Examples (Day 4)

### 4.1 API Documentation
- [ ] Update `docs/API.md` with new methods
- [ ] Document new data types
- [ ] Add usage examples

### 4.2 Example Scripts
- [ ] Create `examples/session_listing.py`
- [ ] Create `examples/history_analysis.py`
- [ ] Update existing examples if needed

### 4.3 Architecture Documentation
- [ ] Update `docs/ARCHITECTURE.md` with history model
- [ ] Document memory management strategy
- [ ] Document backward compatibility

### 4.4 User Guide Update
- [ ] Add session management section to `docs/GUIDE.md`
- [ ] Add debugging with history section

---

## Phase 5: Testing & QA (Day 5)

### 5.1 Integration Tests
- [ ] Test full workflow with real SSH
- [ ] Test history across multiple commands
- [ ] Test memory limits under load

### 5.2 Performance Testing
- [ ] Benchmark with 1000+ messages
- [ ] Measure memory impact
- [ ] Test trim strategy efficiency

### 5.3 Edge Cases
- [ ] Test with very large outputs (>64KB per message)
- [ ] Test with rapid command sequences
- [ ] Test history after session close

### 5.4 Code Quality
- [ ] Type hints on all new methods
- [ ] Docstrings for all new classes/methods
- [ ] Run black, isort, flake8, mypy

---

## Phase 6: Release v0.2 (Day 6)

### 6.1 Version Update
- [ ] Update version to 0.2.0 in `pyproject.toml`
- [ ] Update version in `__init__.py`

### 6.2 Changelog
- [ ] Update `CHANGELOG.md` with v0.2.0 features
- [ ] Document breaking changes (if any)
- [ ] Document new API methods

### 6.3 Release
- [ ] Build package
- [ ] Upload to PyPI
- [ ] Tag v0.2.0 in git
- [ ] Verify installation

---

## Alternative Approaches Considered

### Option A: Keep Buffer Only (Minimal Change)
**Pros:** Simple, no breaking changes
**Cons:** No structure, no input tracking, no correlation

### Option B: Replace Buffer with History (Breaking Change)
**Pros:** Clean design, no duplication
**Cons:** Breaking change, marker detection needs rewrite

### Option C: Dual Storage (Recommended - Selected)
**Pros:** Backward compatible, best of both worlds
**Cons:** Slight memory overhead (buffer + history)

**Recommendation:** Option C provides the best balance of features and compatibility.

---

## Memory Considerations

### Estimated Memory Usage

| Scenario | Messages | Memory Est. |
|----------|----------|-------------|
| Light usage | 100 msgs | ~100KB |
| Normal usage | 1000 msgs | ~1MB |
| Heavy usage | 10000 msgs | ~10MB |
| With limits | 1000 max | ~1MB cap |

### Mitigation Strategies

1. **Default limits**: 1000 messages max per session
2. **Message size limits**: 64KB max per message
3. **Trim strategy**: Remove oldest messages first
4. **Optional disable**: Allow `history_enabled=False` for memory-sensitive use

---

## Configuration Options

```python
# Default configuration
service = SSHService(
    history_config=HistoryConfig(
        max_messages=1000,
        max_message_size=65536,
        trim_strategy="oldest"
    )
)

# High-memory mode for debugging
service = SSHService(
    history_config=HistoryConfig(
        max_messages=10000,
        max_message_size=131072,
        trim_strategy="none"
    )
)

# Minimal memory mode
service = SSHService(
    history_config=HistoryConfig(
        max_messages=100,
        max_message_size=4096,
        trim_strategy="oldest"
    )
)
```

---

## Success Criteria

- [ ] `list_sessions()` returns accurate session list
- [ ] `get_session_history()` returns correlated input/output
- [ ] Memory usage stays bounded with configured limits
- [ ] Existing tests continue to pass (backward compatible)
- [ ] New tests achieve ≥80% coverage on new code
- [ ] All documentation updated
- [ ] v0.2.0 published to PyPI

---

## Timeline Summary

| Phase | Duration | Tasks |
|-------|----------|-------|
| Phase 1: Data Types | 1 day | 6 tasks |
| Phase 2: Recording | 1 day | 8 tasks |
| Phase 3: API | 1 day | 9 tasks |
| Phase 4: Docs | 1 day | 8 tasks |
| Phase 5: Testing | 1 day | 8 tasks |
| Phase 6: Release | 0.5 day | 6 tasks |
| **Total** | **5.5 days** | **45 tasks** |

---

## References

- Current buffer implementation: `src/ssh_agent_bridge/core.py` (lines 673-723)
- Session model: `src/ssh_agent_bridge/types.py` (SessionInfo dataclass)
- API documentation: `docs/API.md`
- Architecture: `docs/ARCHITECTURE.md`
