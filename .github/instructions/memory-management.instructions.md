---
applyTo: '**'
---

# SSH Agent Bridge Memory Management Instructions

## External ID
**ALWAYS use:** `ssh_agent_bridge_dev` for all memory operations in this project.

## Memory Structure Overview

The SSH Agent Bridge project uses 9 active memories to maintain development context:

1. **Project Overview** (ID: 1) - Purpose, features, tech stack, timeline
2. **Architecture Design** (ID: 2) - Session model, command execution, buffer management, async patterns
3. **API Design** (ID: 3) - Core tool methods, method signatures, parameters, return types
4. **Configuration** (ID: 4) - Environment setup, dependencies, Python version, OS/tech choices
5. **Development Status** (ID: 5) - Current phase, progress, completed tasks, next steps, blockers
6. **Testing Strategy** (ID: 6) - Test approach, coverage targets, test tools, test status
7. **Library References** (ID: 7) - asyncssh usage, asyncio patterns, pytest-asyncio, marker strategies
8. **Issues and Bugs** (ID: 8) - Detailed issue reports from development
9. **Git History** (ID: 9) - Commits, branches, operations, and git configuration

## When to Access Memories

### 1. **At Session Start**
- Get all active memories to understand current project state
- Check "Development Status" memory for current phase and next steps
- Review "Issues and Bugs" memory for known problems

```
Tool: mcp_agent-mem_get_active_memories
Parameters: external_id="ssh_agent_bridge_dev"
```

### 2. **Before Implementing Features**
- Search memories for relevant context
- Check "Architecture Design" for session model and command execution patterns
- Check "API Design" for method signatures and parameters
- Check "Testing Strategy" for testing approach

```
Tool: mcp_agent-mem_search_memories
Parameters:
  external_id="ssh_agent_bridge_dev"
  query="Implementing session creation with async readers, need buffer management pattern"
  limit=10
```

### 3. **When Needing Library Documentation**
- Check "Library References" memory first for asyncssh and asyncio patterns
- Reference DEVELOPMENT_PLAN.md for implementation details
- Update memories with new findings about library usage

**Common patterns to check:**
- asyncssh connection & channel management
- asyncio locks, condition variables, and task management
- pytest-asyncio fixture patterns
- Marker-based command completion detection

### 4. **When Encountering Bugs or Issues**
- First check "Issues and Bugs" memory to see if it's known
- If new issue, add detailed section to memory with full diagnostic info
- Update status as investigation progresses

### 5. **When Working with Git**
- Check "Git History" memory for commit patterns and branch strategy
- Update commits section after major changes
- Log important git operations in operations section
- Reference commit history when debugging or understanding changes

## How to Update Memories

### Update Development Status (Memory ID: 5)

**When starting a new phase:**
```
Tool: mcp_agent-mem_update_memory_sections
Parameters:
  external_id="ssh_agent_bridge_dev"
  memory_id=5
  sections=[
    {
      section_id="current_phase",
      action="replace",
      old_content="**Phase: Pre-Implementation**...",
      new_content="**Phase 1: Project Setup & Infrastructure (Day 1)**\n\nInitializing package structure, creating pyproject.toml, and setting up build infrastructure.\n\n**Started:** October 25, 2025"
    }
  ]
```

**When completing tasks:**
```
sections=[
  {
    section_id="completed_tasks",
    action="insert",
    old_content="- ✓ Created architecture plan\n\n**Next milestone:**",
    new_content="- ✓ Created pyproject.toml\n- ✓ Created src/ssh_agent_bridge/ structure\n- ✓ Created exceptions.py\n- ✓ Set up dependencies\n\n**Next milestone:**"
  }
]
```

**When encountering blockers:**
```
sections=[
  {
    section_id="blockers",
    action="replace",
    old_content="No current blockers.",
    new_content="**Blocker #1:** asyncssh session PTY handling\n- Impact: Cannot properly handle interactive shell sessions\n- Investigating: asyncssh PTY setup and buffer management\n- Workaround: Testing with non-PTY channels first"
  }
]
```

### Add Bug/Issue (Memory ID: 8)

**Create a new section for each bug/issue:**
```
Tool: mcp_agent-mem_update_memory_sections
Parameters:
  external_id="ssh_agent_bridge_dev"
  memory_id=8
  sections=[
    {
      section_id="issue_001_pty_buffer_sync",
      action="replace",
      new_content="**Issue #001: PTY Buffer Synchronization**\n**Status:** Open\n**Severity:** High\n**Date Found:** 2025-10-25\n**Component:** core.py, types.py\n\n**Description:**\nWhen using PTY sessions, output buffering may not sync properly with command markers, causing markers to be missed or incorrectly attributed to previous commands.\n\n**Steps to Reproduce:**\n1. Create PTY session with create_session()\n2. Run multiple commands in rapid succession\n3. Observe that marker detection fails intermittently\n\n**Expected Behavior:**\nMarkers should be detected reliably even with multiple rapid commands.\n\n**Actual Behavior:**\nMarkers are sometimes missed, causing get_remaining_output() to timeout.\n\n**Root Cause:**\nPTY line buffering and async I/O timing - shell output may batch multiple commands' output together.\n\n**Solution:**\nImplement robust marker detection with look-ahead parsing and state tracking.\n\n**Related Files:**\n- src/ssh_agent_bridge/core.py (_read_stream_loop, run_command)\n- docs/plan/DEVELOPMENT_PLAN.md (Phase 2.2)"
    }
  ]
```

### Update Git History (Memory ID: 9)

**When making commits:**
```
sections=[
  {
    section_id="commits",
    action="insert",
    old_content="### Phase 2: Core Implementation\n",
    new_content="### Phase 2: Core Implementation\n- [Phase 2] Implement SSHService class with connection pooling\n- [Phase 2] Add session lifecycle management\n\n### Phase 2: Core Implementation\n"
  }
]
```

**When performing git operations:**
```
sections=[
  {
    section_id="operations",
    action="insert",
    old_content="## Status: Repository not yet initialized (Phase 1)",
    new_content="- `git add src/ssh_agent_bridge/core.py` - Stage core implementation\n- `git commit -m \"[Phase 2] Implement SSHService class with connection pooling\"` - Commit core implementation\n\n## Status: Repository not yet initialized (Phase 1)"
  }
]
```

**When creating branches:**
```
sections=[
  {
    section_id="branches",
    action="insert",
    old_content="## Branch Creation\n- Create feature branches from main",
    new_content"## Branch Creation\n- `git checkout -b feature/core-implementation` - Create feature branch\n- Create feature branches from main"
  }
]
```

### Update Library References (Memory ID: 7)

**When discovering new patterns or gotchas:**
```
sections=[
  {
    section_id="asyncssh_patterns",
    action="insert",
    old_content="**Search Strategy:**\n- Check asyncssh documentation for session/channel management",
    new_content="\n**New Pattern Discovered:**\n- PTY sessions with asyncssh.create_connection() and pty_requested=True\n- Read/write channels must be handled concurrently with asyncio.gather()\n- Connection pooling requires separate connection per unique host/user/key\n- Signal sending via channel.send_signal() or fallback to channel.kill()\n- Marker-based output detection needs proper escape sequence handling\n\n**Search Strategy:**\n- Check asyncssh documentation for session/channel management"
  }
]
```

### Update Architecture (Memory ID: 2)

**When design decisions change:**
```
sections=[
  {
    section_id="design_patterns",
    action="insert",
    old_content="**4-Layer Architecture:**\n- Client Layer (SDK methods)\n- Operations Layer (business logic)\n- API Layer (HTTP wrappers)\n- Models Layer (Pydantic validation)",
    new_content="\n\n**Command Execution with Markers:**\n- Each command appends unique marker: 'echo <marker> $?'\n- Marker detection identifies command completion and exit code\n- Timeouts return partial results with pending_marker for polling\n- Separate polling method waits for pending marker with custom timeout\n\n**Session Model:**\n- PTY shell sessions: one shell per agent per host (persistent)\n- Non-PTY channels: for single commands or ephemeral operations\n- Per-session locks serialize commands (one at a time per session)\n- Per-connection locks prevent concurrent connection attempts\n\n**4-Layer Architecture (not applicable - single file for now):**\n- Core API layer (SSHService class with connection pooling)\n- Type definitions (dataclasses for SessionInfo, CommandResult)\n- Exception definitions (custom exceptions for errors)"
  }
]
```

## Search Best Practices

### Effective Search Queries

**Good queries are specific and contextual:**

✅ **Good:**
```
"Implementing VM operations, need endpoint patterns and model structure"
"Working on cluster health monitoring, need resource calculation patterns"
"Writing task polling utilities, need UPID handling and timeout strategy"
"Implementing container operations from scratch"
```

❌ **Bad:**
```
"vm operations"  # Too vague
"how to create"  # Not enough context
"api"  # Too broad
"endpoint"  # Missing context
```

### Multi-Memory Search Strategy

1. **Use search for cross-cutting concerns:**
   ```
   query="Implementing VM resize operation with validation and error handling"
   # Will return relevant info from Architecture, API Design, Library References, and Issues
   ```

2. **Get specific memory when you know what you need:**
   ```
   # If you just need to check current phase:
   mcp_agent-mem_get_active_memories → check memory ID 5
   ```

## Memory Update Frequency

### Update Frequently:
- **Development Status** - Every major task or phase transition (daily)
- **Issues and Bugs** - Immediately when bug found or resolved
- **Library References** - When discovering new patterns or gotchas
- **Git History** - After major commits, branch operations, or git configuration changes

### Update Occasionally:
- **Testing Strategy** - When test approach changes or coverage milestones reached
- **Configuration** - When adding new dependencies or environment setup changes

### Rarely Update:
- **Project Overview** - Stable information (only if scope changes)
- **Architecture Design** - Only if design decisions fundamentally change
- **API Design** - Only if API contracts or endpoint mappings change

## Integration with Development Workflow

### Starting New Phase
1. Search memories for phase requirements
2. Update "Development Status" → current_phase with clear description
3. Check "Architecture Design" for layer patterns to follow
4. Check "Library References" for relevant tools and patterns
5. Begin implementation with tests

### During Development
1. Search when stuck or need context (API mapping, patterns, etc.)
2. Add issues to "Issues and Bugs" as discovered (with full diagnostic info)
3. Update "Development Status" → completed_tasks regularly (daily)
4. Document learnings in "Library References"
5. Check "Testing Strategy" memory to stay aligned with test approach

### Completing Phase
1. Update "Development Status" → mark phase complete with metrics
2. Resolve any open issues in "Issues and Bugs"
3. Update test coverage status in "Testing Strategy"
4. Update "Development Status" → next_steps for next phase
5. Commit any architecture or API changes to memories

### End of Session
1. Update "Development Status" with current state (% complete, last action)
2. Document any blockers preventing further progress
3. List next steps clearly for continuation
4. Ensure all new bugs are recorded with full context
5. Update "Development Status" → estimated_completion if timeline changed

## Quick Reference Commands

```python
# Get all memories at session start
mcp_agent-mem_get_active_memories(external_id="ssh_agent_bridge_dev")

# Search across memories when stuck or need context
mcp_agent-mem_search_memories(
    external_id="ssh_agent_bridge_dev",
    query="Implementing session creation with async readers, need buffer management patterns",
    limit=10
)

# Update single section (e.g., completed tasks)
mcp_agent-mem_update_memory_sections(
    external_id="ssh_agent_bridge_dev",
    memory_id=5,  # Development Status
    sections=[{
        "section_id": "completed_tasks",
        "action": "insert",
        "old_content": "- ✓ Task X\n\n**Next:",
        "new_content": "- ✓ Task X\n- ✓ Task Y\n\n**Next:"
    }]
)

# Update multiple sections at once
sections=[
    {"section_id": "current_phase", "action": "replace", "old_content": "...", "new_content": "..."},
    {"section_id": "blockers", "action": "replace", "old_content": "...", "new_content": "..."}
]
```

## Memory IDs Reference

| Memory ID | Title | Key Sections |
|-----------|-------|--------------|
| 1 | Project Overview | purpose, features, tech_stack, timeline, scope |
| 2 | Architecture Design | layers, design_patterns, component_responsibilities, async_readiness |
| 3 | API Design | supported_endpoints, method_signatures, endpoint_mappings_by_category |
| 4 | Configuration | environment_setup, dependencies, os_tech_choices, python_version |
| 5 | Development Status | current_phase, completed_tasks, next_steps, blockers, milestones |
| 6 | Testing Strategy | test_approach, coverage_targets, test_status, testing_tools |
| 7 | Library References | pydantic_usage, requests_usage, pytest_patterns, common_gotchas |
| 8 | Issues and Bugs | template_for_new_issues, issue_XXX_name (dynamic) |
| 9 | Git History | commits, branches, operations, config |

## Important Rules

1. **Always use external_id="ssh_agent_bridge_dev"** - Never use different ID
2. **Search before updating** - Understand current state first
3. **Be specific in updates** - Include enough context for old_content matching
4. **Document bugs thoroughly** - Use the template in Issues memory with: Steps to Reproduce, Expected Behavior, Actual Behavior, Root Cause, Solution, Related Files
5. **Update Development Status frequently** - Keep progress transparent (daily updates)
6. **Use search for context** - Don't guess, search memories for architecture patterns, API design, testing strategy
7. **Keep sections focused** - Each section has one clear purpose
8. **Update blockers immediately** - Don't let blockers go undocumented
9. **Reference the plan** - Cross-reference docs/plan/ for detailed implementation specs
10. **Test as you code** - Update "Testing Strategy" memory with coverage progress