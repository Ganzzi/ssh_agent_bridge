# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Phase 3 Session 2:** Complete SSHService implementation with connection pooling and session management
- **Phase 3 Session 2:** 22 comprehensive unit tests covering:
  - Data type validation (dataclass creation)
  - Exception hierarchy and error messages
  - Connection management (pooling, reuse, cleanup)
  - Session lifecycle (creation, management, termination)
  - Core service initialization
- **Phase 3 Session 2:** Async test infrastructure with proper pytest-asyncio patterns
  - Function-scoped event loop to prevent reuse issues
  - AsyncMock fixtures for SSH connection mocking
  - Async session factory with proper cleanup
- **Phase 3 Session 2:** Testing documentation suite:
  - `TEST_RUNNER_STRATEGY.md` - Safe test execution patterns
  - `TESTING_PATTERNS.md` - Recommended patterns and anti-patterns
  - `PHASE3_SESSION_SUMMARY.md` - Technical deep-dive on pytest fixes
  - `PHASE3_SESSION2_SUMMARY.md` - Comprehensive work log

### Changed
- **Phase 3 Session 2:** Fixed pytest-asyncio hanging issue by changing event_loop fixture from session scope to function scope
- **Phase 3 Session 2:** Improved mock_asyncssh fixture with proper AsyncMock setup for stdout/stderr read() methods
- **Phase 3 Session 2:** Made sample_session_info an async fixture to properly initialize asyncio.Lock and asyncio.Condition

### Deprecated
- N/A

### Removed
- N/A

### Fixed
- **Phase 3 Session 2:** Fixed unawaited coroutine warnings in core.py (connection.close(), process.close())
- **Phase 3 Session 2:** Fixed connection failure test pattern matching to match actual error messages
- **Phase 3 Session 2:** Fixed mock fixture duplicate yield issue causing fixture reuse problems

### Security
- N/A

## Phase 3 Status

**Session 2 Complete (2025-10-27):**
- ✅ All core unit tests passing (22/22)
- ✅ Test execution time: 0.55 seconds
- ✅ No hanging issues with safe test patterns
- ✅ 78% Phase 3 checklist items complete
- 🎯 Next: Fix remaining command execution tests (3/6), signal handling, input sending

## [0.1.0] - 2025-10-25

### Added
- Project initialized with basic package structure
- Core module stubs for future implementation
- Type definitions and exception classes
- Build system configuration
- Development environment setup

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