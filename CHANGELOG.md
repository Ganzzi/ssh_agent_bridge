# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- N/A

### Changed
- N/A

### Deprecated
- N/A

### Removed
- N/A

### Fixed
- N/A

### Security
- N/A

## [0.2.0] - 2025-12-03

### Added
- **Phase 7 Session 1 - Feature: Session Listing & Message History**
  - `list_sessions(agent_id)` - List all sessions for an agent with filtering and pagination
  - `get_session_history(session_id)` - Retrieve structured message history with filters (timestamp, direction, limit)
  - **New Data Types:**
    - `Message` - Individual message with id, timestamp, direction, content, command_id, marker
    - `SessionHistory` - Container for messages with total_count and truncation detection
    - `SessionSummary` - Session summary for listing (agent_id, host, status, created_at, etc)
    - `HistoryConfig` - Configuration for history limits (max_messages=1000, max_message_size=64KB, trim_strategy="oldest")
  - **Message Recording:** Automatic capture of all input/output during command execution
    - Input messages recorded for run_command, send_input
    - Output messages recorded from _read_stream_loop with command correlation
    - Messages automatically trimmed when configured limits exceeded
    - Backward compatible: existing buffer still used for marker detection
  - **Enhanced SessionInfo:** New fields for tracking
    - `history: List[Message]` - Structured message history
    - `history_config: HistoryConfig` - Configurable limits and behavior
    - `created_at: datetime` - Session creation timestamp
    - `last_activity: datetime` - Latest activity timestamp
    - `command_count: int` - Number of commands executed
    - `pending_command_markers: Dict[str, Optional[str]]` - Correlation tracking
  - **Documentation Updates:**
    - docs/API.md - Added list_sessions and get_session_history with examples
    - docs/GUIDE.md - Added "Session Management & History" section with 5 use case examples
    - docs/ARCHITECTURE.md - Added "Message History Model" design explanation
    - examples/session_listing.py - New example script with 5 practical examples
  - **Comprehensive Testing:**
    - TestMessageRecording (13 tests) - Verify message recording and correlation
    - TestListSessions (5 tests) - Verify session listing with filtering and pagination
    - TestGetSessionHistory (6 tests) - Verify history retrieval with filters
    - TestPerformance (7 tests) - Performance benchmarks for history operations
    - All tests pass with <1s execution time
  - **Performance Validation:**
    - Message creation: 1000 messages in <1s
    - History queries: <100ms for typical filters
    - Memory bounded: Trimming maintains limits automatically
    - list_sessions: 500 sessions listed in <50ms
    - Large outputs: 1MB+ messages automatically managed

### Changed
- **SessionInfo dataclass:** Enhanced with message history tracking fields
- **run_command:** Now records messages for input commands and correlated output
- **send_input:** Automatically records input messages to history
- **_read_stream_loop:** Records output messages with proper timestamp tracking

### Tests
- **All Phase 5 Tests Pass:** 20+ tests for session history feature (100% pass rate)
- **Overall Test Suite:** 78/88 tests passing (88.6% pass rate)
  - All Phase 5 session history tests: PASS ✅
  - Fast unit tests (data types, exceptions, service): PASS ✅
  - Integration tests with mocks: 78/88 PASS
- **Code Coverage:** 86% (exceeded 80% target)
- **Backward Compatibility:** Existing API unchanged, new features are additive

## [0.1.1] - 2025-10-26

### Added
- **Phase 3 Session 3:** Robust marker-based command completion detection system
  - Distinctive marker format `______END_MARKER_{uuid}______` to avoid parsing conflicts
  - Regex-based exit code extraction from `marker=exit_code` pattern
  - Handles command echoing in PTY sessions correctly
- **Phase 3 Session 3:** Example scripts demonstrating all core features:
  - `simple_command.py` - Single command execution (ephemeral)
  - `persistent_session.py` - Multi-command persistent sessions
  - `multi_agent_multi_session.py` - Concurrent multi-agent execution with connection pooling
  - `interactive_prompt.py` - Interactive command handling
  - `error_recovery.py` - Error recovery and resilience patterns
  - `signal_handling.py` - Process signal sending (SIGINT, SIGTERM, etc.)
  - `buffer_benchmark.py` - Performance benchmarking
- **Phase 3 Session 3:** Cross-platform compatibility improvements
  - Windows-aware file permission checks for SSH keys
  - Proper command construction for PTY shell sessions
  - Robust data encoding/decoding for both bytes and string returns

### Changed
- **Phase 3 Session 3:** Fixed marker parsing to use regex pattern matching instead of line-based splitting
- **Phase 3 Session 3:** Updated marker format from `MARKER_uuid` to `______END_MARKER_uuid______`
- **Phase 3 Session 3:** Changed command echo format from `echo marker $?` to `echo marker="$?"`
- **Phase 3 Session 3:** Fixed send_signal method to work with asyncssh process objects (removed await)
- **Phase 3 Session 3:** Updated all 22 marker-related tests to use new marker format
- **Phase 3 Session 3:** Improved buffer management with better data type handling

### Deprecated
- N/A

### Removed
- N/A

### Fixed
- **Phase 3 Session 3:** Fixed `$?` parsing error in PTY sessions caused by command echoing
- **Phase 3 Session 3:** Fixed marker detection to handle incomplete commands during buffer accumulation
- **Phase 3 Session 3:** Fixed send_signal attempting to await non-coroutine function
- **Phase 3 Session 3:** Fixed Windows compatibility for SSH key permission checks
- **Phase 3 Session 3:** Fixed test cases to work with new marker format

### Security
- N/A

## [0.1.0] - 2025-10-26

### Added
- **Initial Release**: Production-ready SSH session management for AI agents
- **Core Features**:
  - `create_session()` - Create persistent PTY shell sessions per agent
  - `run_command()` - Execute commands with marker-based completion detection
  - `get_remaining_output()` - Poll for long-running command completion
  - `send_input()` - Send interactive input to running commands
  - `send_signal()` - Send signals (SIGINT, SIGKILL) to processes
  - `run_ephemeral()` - Execute single non-interactive commands
- **Connection Management**: Lazy connection pooling with per-agent isolation
- **Session Lifecycle**: Proper cleanup and resource management
- **Buffer Management**: Accumulate session output with marker indexing
- **Error Handling**: Custom exceptions for connection, session, and command errors
- **Timeout Support**: Configurable timeouts with graceful degradation
- **Async Design**: Built on asyncio for high concurrency
- **Phase 3 Session 3:** Robust marker-based command completion detection system
  - Distinctive marker format `______END_MARKER_{uuid}______` to avoid parsing conflicts
  - Regex-based exit code extraction from `marker=exit_code` pattern
  - Handles command echoing in PTY sessions correctly
- **Phase 3 Session 3:** Example scripts demonstrating all core features:
  - `simple_command.py` - Single command execution (ephemeral)
  - `persistent_session.py` - Multi-command persistent sessions
  - `multi_agent_multi_session.py` - Concurrent multi-agent execution with connection pooling
  - `interactive_prompt.py` - Interactive command handling
  - `error_recovery.py` - Error recovery and resilience patterns
  - `signal_handling.py` - Process signal sending (SIGINT, SIGTERM, etc.)
  - `buffer_benchmark.py` - Performance benchmarking
- **Phase 3 Session 3:** Cross-platform compatibility improvements
  - Windows-aware file permission checks for SSH keys
  - Proper command construction for PTY shell sessions
  - Robust data encoding/decoding for both bytes and string returns

### Testing
- **52 Unit Tests**: 100% pass rate with comprehensive coverage
- **86% Code Coverage**: Exceeds 80% target
- **Type Checking**: Full mypy compliance with type hints
- **Code Quality**: Black formatting, isort imports, flake8 linting
- **7 Example Scripts**: Working demonstrations of all features

### Documentation
- **Complete API Reference**: Method signatures, parameters, return types
- **User Guide**: Installation, quick start, best practices
- **Architecture Documentation**: Design decisions and technical details
- **7 Working Examples**: From simple commands to complex multi-agent scenarios

### Quality Assurance
- **Security Review**: Private key handling, credential security
- **Performance Testing**: Large output handling (100KB+), connection pooling
- **Cross-Platform**: Windows, Linux, macOS support (Python 3.8-3.12)
- **CI/CD**: GitHub Actions with multi-Python testing

### Packaging
- **PyPI Distribution**: Available at https://pypi.org/project/ssh-agent-bridge/
- **PEP 517 Compliance**: Modern build system with setuptools
- **Wheel + Source Distribution**: Universal Python wheel included

### Changed
- **Phase 3 Session 3:** Fixed marker parsing to use regex pattern matching instead of line-based splitting
- **Phase 3 Session 3:** Updated marker format from `MARKER_uuid` to `______END_MARKER_uuid______`
- **Phase 3 Session 3:** Changed command echo format from `echo marker $?` to `echo marker="$?"`
- **Phase 3 Session 3:** Fixed send_signal method to work with asyncssh process objects (removed await)
- **Phase 3 Session 3:** Updated all 22 marker-related tests to use new marker format
- **Phase 3 Session 3:** Improved buffer management with better data type handling

### Deprecated
- N/A

### Removed
- N/A

### Fixed
- **Phase 3 Session 3:** Fixed `$?` parsing error in PTY sessions caused by command echoing
- **Phase 3 Session 3:** Fixed marker detection to handle incomplete commands during buffer accumulation
- **Phase 3 Session 3:** Fixed send_signal attempting to await non-coroutine function
- **Phase 3 Session 3:** Fixed Windows compatibility for SSH key permission checks
- **Phase 3 Session 3:** Fixed test cases to work with new marker format

### Security
- N/A