# AsyncSSH quick API recap — short & practical

* `await asyncssh.connect(host, username=..., client_keys=[...])` → returns an `SSHClientConnection`. This is the authenticated SSH *connection* (TCP + crypto). You can open many channels on it.
* `await conn.run(cmd)` → one-off execution. Opens a short channel, runs the command, returns `SSHCompletedProcess` (`exit_status`, `stdout`, `stderr`).
* `proc = await conn.create_process(command=..., term_type='xterm')` → creates a `SSHClientProcess` (a channel). If `term_type` provided you get a PTY-like shell session (interactive). `proc.stdin`, `proc.stdout`, `proc.stderr` are async streams. `proc.kill()` kills; `proc.send_signal(sig)` can send signals (platform dependent).
* `proc.stdin.write(...)` + `await proc.stdin.drain()` → send data to the remote process.
* Reading: `await proc.stdout.read(n)` or `await proc.stdout.read()` to get data.

---

# What you asked for

You asked for a simplified model:

* `run_command(session_id, command, short_timeout, completion_timeout)` that:

  * writes the command plus a unique marker,
  * reads for a *short* time (`short_timeout`) to check if the marker is present (command finished) or not,
  * if finished → return `completed` with full output,
  * if not finished within `short_timeout` → return `partial` with current output and leave the session running, so the agent can:

    * call `send_input(session_id, text)` to paste input for a prompt,
    * call `send_signal(session_id, sig)` (e.g., ctrl-c),
    * call `get_remaining_output(session_id, timeout)` to wait for the command’s completion (marker).
* multiple sessions per agent, one connection per agent.

Below is a **complete, ready-to-use** `async` Python service file implementing exactly that behavior using `asyncssh`. Save as e.g. `ssh_service_simple.py`.

---

```py
# ssh_service_simple.py
"""
Async SSH service using asyncssh.

Main features:
- One connection per agent (agent_id -> SSHClientConnection).
- Many sessions per connection (session = persistent shell / PTY).
- run_command(session_id, command, short_timeout): append marker and read short time.
    - returns {"status": "completed", "exit_code": int, "stdout": str}
    - or {"status": "partial", "stdout": str, "pending_marker": str}
- get_remaining_output(session_id, pending_marker, timeout): wait until marker (or timeout)
- send_input(session_id, input_text): write to session stdin
- send_signal(session_id, sig): send signal (SIGINT etc.) or kill
- run_ephemeral for one-off non-interactive commands (conn.run)
"""

import asyncio
import asyncssh
import logging
import signal as _signal
from dataclasses import dataclass, field
from typing import Dict, Optional, List
from uuid import uuid4

logger = logging.getLogger("ssh_service_simple")
logging.basicConfig(level=logging.INFO)


@dataclass
class ConnectionInfo:
    conn: asyncssh.SSHClientConnection
    host: str
    username: str


@dataclass
class SessionInfo:
    id: str
    agent_id: str
    conn: asyncssh.SSHClientConnection
    process: asyncssh.SSHClientProcess
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    buffer: str = ""                       # aggregated stdout+stderr
    buffer_cond: asyncio.Condition = field(default_factory=asyncio.Condition)
    reader_tasks: List[asyncio.Task] = field(default_factory=list)
    closed: bool = False
    # track the latest pending marker when a command is outstanding
    pending_marker: Optional[str] = None
    pending_start_index: int = 0


class SSHService:
    def __init__(self, known_hosts: Optional[str] = None):
        # agent_id -> ConnectionInfo
        self._connections: Dict[str, ConnectionInfo] = {}
        # session_id -> SessionInfo
        self._sessions: Dict[str, SessionInfo] = {}
        # per-agent connection lock to avoid concurrent connect
        self._conn_locks: Dict[str, asyncio.Lock] = {}
        self._known_hosts = known_hosts

    # ---------------------------
    # Connection management
    # ---------------------------
    async def _ensure_connection(self,
                                 agent_id: str,
                                 host: str,
                                 username: str,
                                 client_keys: Optional[List[str]] = None,
                                 password: Optional[str] = None,
                                 port: int = 22,
                                 keepalive_interval: Optional[int] = 30) -> asyncssh.SSHClientConnection:
        if agent_id not in self._conn_locks:
            self._conn_locks[agent_id] = asyncio.Lock()

        async with self._conn_locks[agent_id]:
            ci = self._connections.get(agent_id)
            if ci:
                conn = ci.conn
                try:
                    if conn.is_connected():
                        return conn
                except Exception:
                    # fallback to reconnect
                    pass

            conn = await asyncssh.connect(
                host,
                port=port,
                username=username,
                client_keys=client_keys,
                password=password,
                known_hosts=self._known_hosts,
                keepalive_interval=keepalive_interval,
            )
            self._connections[agent_id] = ConnectionInfo(conn=conn, host=host, username=username)
            logger.info("Connected agent=%s -> %s", agent_id, host)
            return conn

    async def close_agent_connection(self, agent_id: str):
        # close sessions for agent
        to_close = [s_id for s_id, s in self._sessions.items() if s.agent_id == agent_id]
        for s_id in to_close:
            await self.end_session(s_id)

        ci = self._connections.pop(agent_id, None)
        if ci:
            try:
                ci.conn.close()
                await ci.conn.wait_closed()
            except Exception:
                logger.exception("Error closing connection for %s", agent_id)
        self._conn_locks.pop(agent_id, None)
        logger.info("Closed agent connection %s", agent_id)

    # ---------------------------
    # Session lifecycle
    # ---------------------------
    async def create_session(self,
                             agent_id: str,
                             host: str,
                             username: str,
                             client_keys: Optional[List[str]] = None,
                             password: Optional[str] = None,
                             port: int = 22,
                             pty: bool = True,
                             term_type: str = "xterm",
                             term_size=(24, 80),
                             shell_cmd: str = "/bin/bash -l"):
        """
        Create a persistent shell session (PTY by default).
        Returns session_id.
        """
        conn = await self._ensure_connection(agent_id, host, username, client_keys, password, port)

        if pty:
            process = await conn.create_process(term_type=term_type, term_size=term_size, command=shell_cmd)
        else:
            process = await conn.create_process(command=shell_cmd)

        session_id = str(uuid4().hex)
        sinfo = SessionInfo(
            id=session_id,
            agent_id=agent_id,
            conn=conn,
            process=process,
        )

        # spawn reader tasks for stdout and stderr
        t1 = asyncio.create_task(self._read_stream_loop(session_id, process.stdout))
        t2 = asyncio.create_task(self._read_stream_loop(session_id, process.stderr))
        sinfo.reader_tasks.extend([t1, t2])

        self._sessions[session_id] = sinfo

        # small delay to let shell initialize
        await asyncio.sleep(0.05)
        logger.info("Created session %s for agent %s", session_id, agent_id)
        return session_id

    async def _read_stream_loop(self, session_id: str, stream):
        """
        Continuously read a stream (stdout or stderr) and append into session.buffer,
        notifying waiters via buffer_cond.
        """
        sinfo = self._sessions.get(session_id)
        if not sinfo:
            return

        try:
            while True:
                chunk = await stream.read(4096)
                if not chunk:
                    break
                # append to buffer and notify
                sinfo.buffer += chunk
                async with sinfo.buffer_cond:
                    sinfo.buffer_cond.notify_all()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Reader stream error for session %s", session_id)

    # ---------------------------
    # Command execution model
    # ---------------------------
    def _make_marker(self) -> str:
        return "__CMD_END__" + uuid4().hex

    async def run_command(self,
                          session_id: str,
                          command: str,
                          short_timeout: float = 0.8,
                          completion_timeout: float = 30.0):
        """
        Run a command inside a persistent session shell.
        - Appends a unique marker: `echo <marker> $?`
        - Waits up to short_timeout for the marker to appear.
            - If marker found -> returns {"status":"completed", "exit_code":int, "stdout": str}
            - If marker not found within short_timeout -> returns {"status":"partial", "stdout": str, "pending_marker": marker}
              and leaves session running. Agent can then call send_input, send_signal, or get_remaining_output.
        Note: completion_timeout is used by helper get_remaining_output to wait longer if the agent asks.
        """
        sinfo = self._sessions.get(session_id)
        if not sinfo or sinfo.closed:
            raise ValueError("invalid or closed session")

        async with sinfo.lock:
            # Prepare marker and remember start index
            marker = self._make_marker()
            wrapped = f"{command}\necho {marker} $?\n"
            start_index = len(sinfo.buffer)

            # write command
            try:
                sinfo.process.stdin.write(wrapped)
                await sinfo.process.stdin.drain()
            except Exception as e:
                raise RuntimeError("failed to write to session stdin") from e

            sinfo.pending_marker = marker
            sinfo.pending_start_index = start_index

            # Wait short time for the marker
            try:
                async with sinfo.buffer_cond:
                    await asyncio.wait_for(sinfo.buffer_cond.wait_for(
                        lambda: marker in sinfo.buffer[start_index:]), timeout=short_timeout)
            except asyncio.TimeoutError:
                # not completed yet -> return partial with current output
                current_out = sinfo.buffer[start_index:]
                return {"status": "partial", "stdout": current_out, "pending_marker": marker}

            # marker found within short_timeout => parse exit code and return completed
            full_segment = sinfo.buffer[start_index:]
            idx = full_segment.find(marker)
            before = full_segment[:idx]
            after = full_segment[idx + len(marker):].strip()
            exit_code = None
            if after:
                # after usually contains " <exitcode>\n" — parse first token
                try:
                    exit_code = int(after.split(None, 1)[0])
                except Exception:
                    exit_code = None

            # clear pending marker
            sinfo.pending_marker = None
            sinfo.pending_start_index = 0
            return {"status": "completed", "exit_code": exit_code if exit_code is not None else 0, "stdout": before}

    async def get_remaining_output(self, session_id: str, pending_marker: str, timeout: float = 30.0):
        """
        Wait until the previously returned pending_marker appears in the session buffer or timeout.
        Returns {"status":"completed", "stdout":..., "exit_code":...} or {"status":"timeout", "stdout": ...}
        """
        sinfo = self._sessions.get(session_id)
        if not sinfo:
            raise ValueError("invalid session")

        # ensure the pending marker matches stored one if present
        if sinfo.pending_marker and sinfo.pending_marker != pending_marker:
            # caller provided different marker; still allow it but use buffer indexing from 0
            start_index = 0
        else:
            start_index = sinfo.pending_start_index if sinfo.pending_start_index else 0

        try:
            async with sinfo.buffer_cond:
                await asyncio.wait_for(sinfo.buffer_cond.wait_for(
                    lambda: pending_marker in sinfo.buffer[start_index:]), timeout=timeout)
        except asyncio.TimeoutError:
            # return whatever is available now
            out = sinfo.buffer[start_index:]
            return {"status": "timeout", "stdout": out}

        # marker found
        full_segment = sinfo.buffer[start_index:]
        idx = full_segment.find(pending_marker)
        before = full_segment[:idx]
        after = full_segment[idx + len(pending_marker):].strip()
        exit_code = None
        if after:
            try:
                exit_code = int(after.split(None, 1)[0])
            except Exception:
                exit_code = None

        # clear pending marker if it was ours
        if sinfo.pending_marker == pending_marker:
            sinfo.pending_marker = None
            sinfo.pending_start_index = 0

        return {"status": "completed", "exit_code": exit_code if exit_code is not None else 0, "stdout": before}

    async def send_input(self, session_id: str, input_text: str):
        """
        Write input into session's stdin (e.g., password, or 'yes' answer).
        Does not wait for completion. Use get_remaining_output() to wait for completion marker.
        """
        sinfo = self._sessions.get(session_id)
        if not sinfo or sinfo.closed:
            raise ValueError("invalid or closed session")
        if not input_text.endswith("\n"):
            input_text = input_text + "\n"
        try:
            sinfo.process.stdin.write(input_text)
            await sinfo.process.stdin.drain()
            return {"status": "ok"}
        except Exception as e:
            raise RuntimeError("failed to write input") from e

    async def send_signal(self, session_id: str, sig):
        """
        Send a signal to the remote process.
        sig can be:
           - integer (e.g., signal.SIGINT)
           - string like "SIGINT" or "INT" or "KILL"
        If signal sending is not supported, we fallback to killing the process.
        """
        sinfo = self._sessions.get(session_id)
        if not sinfo or sinfo.closed:
            raise ValueError("invalid or closed session")

        proc = sinfo.process
        try:
            # normalize
            if isinstance(sig, str):
                name = sig.upper()
                if name.startswith("SIG"):
                    name = name[3:]
                sig_obj = getattr(_signal, "SIG" + name, None)
                if sig_obj is None and name == "KILL":
                    # fallback to kill
                    proc.kill()
                    return {"status": "killed"}
                else:
                    proc.send_signal(sig_obj)
                    return {"status": "sent", "signal": name}
            else:
                # assume int signal
                proc.send_signal(sig)
                return {"status": "sent", "signal": sig}
        except Exception:
            # send_signal might not be supported; fallback to kill
            try:
                proc.kill()
                return {"status": "killed"}
            except Exception:
                raise

    # ---------------------------
    # One-off ephemeral exec
    # ---------------------------
    async def run_ephemeral(self,
                            agent_id: str,
                            host: str,
                            username: str,
                            command: str,
                            client_keys: Optional[List[str]] = None,
                            password: Optional[str] = None,
                            port: int = 22,
                            timeout: Optional[float] = 30.0):
        """
        One-off command (conn.run). Good for non-interactive commands.
        """
        conn = await self._ensure_connection(agent_id, host, username, client_keys, password, port)
        result = await conn.run(command, check=False, timeout=timeout)
        return {"exit_code": result.exit_status, "stdout": result.stdout, "stderr": result.stderr}

    # ---------------------------
    # Session termination and cleanup
    # ---------------------------
    async def end_session(self, session_id: str):
        sinfo = self._sessions.pop(session_id, None)
        if not sinfo:
            return
        sinfo.closed = True

        # cancel readers
        for t in sinfo.reader_tasks:
            if not t.done():
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass
                except Exception:
                    logger.exception("Error waiting for reader task")

        # attempt to close stdin nicely then close process
        try:
            sinfo.process.stdin.write_eof()
        except Exception:
            pass
        try:
            sinfo.process.kill()
        except Exception:
            pass
        try:
            await sinfo.process.wait_closed()
        except Exception:
            pass

        logger.info("Ended session %s", session_id)

    async def shutdown(self):
        session_ids = list(self._sessions.keys())
        for sid in session_ids:
            await self.end_session(sid)
        agent_ids = list(self._connections.keys())
        for aid in agent_ids:
            await self.close_agent_connection(aid)
        logger.info("SSHService shutdown complete.")
```

---

# How the new API behaves (short examples)

1. Create two sessions on the same VM (both PTY):

```py
svc = SSHService(known_hosts=None)
s1 = await svc.create_session("agentA", "192.168.56.101", "ubuntu", client_keys=["~/.ssh/id_ed25519"])
s2 = await svc.create_session("agentA", "192.168.56.101", "ubuntu", client_keys=["~/.ssh/id_ed25519"])
```

2. Run a command that prompts (session A), with short timeout:

```py
res = await svc.run_command(s1, 'read -p "Confirm (yes/no): " ANS; echo "GOT:$ANS"', short_timeout=0.8)
# res might be:
# {"status":"partial", "stdout":"Confirm (yes/no): ", "pending_marker":"__CMD_END__..."}
```

3. Agent decides answer and sends input:

```py
await svc.send_input(s1, "yes")
# Now wait for completion:
done = await svc.get_remaining_output(s1, res["pending_marker"], timeout=10.0)
# done => {"status":"completed","exit_code":0,"stdout":"Confirm (yes/no): GOT:yes\n"}
```

4. Run a non-interactive command on session B:

```py
resB = await svc.run_command(s2, "echo hello && uname -n", short_timeout=0.8)
# likely returns {"status":"completed", "exit_code":0, "stdout":"hello\nvm-hostname\n"}
```

5. Send Ctrl-C to a long running process:

```py
await svc.send_signal(s1, "INT")   # or await svc.send_signal(s1, signal.SIGINT)
# Then get remaining output / or treat as aborted
```

---

# Notes, limitations & tips

* **PTY**: interactive prompts often only appear on a PTY. Use `pty=True` in `create_session`.
* **Markers**: we append `echo <marker> $?` after each command. That makes detection reliable.
* **Buffer growth**: current implementation accumulates session buffer indefinitely. For long-lived sessions handling huge outputs, add trimming: e.g., keep only last N bytes and adjust `pending_start_index` accordingly.
* **Multiple concurrent commands on same session**: this service **serializes** commands on each session (via `sinfo.lock`). If you need concurrency in same shell, you'll need a different multiplexing strategy (hard!).
* **Prompt detection heuristics**: this implementation *does not* attempt to detect prompts via regex — it simply returns partial output quickly if marker absent. That lets your agent decide the next step (send input, signal, or wait longer).
* **Security**: keep private keys safe. Prefer key-based auth for bots. Use `known_hosts` or verify host fingerprints in production.
* **Signals**: `proc.send_signal(sig)` may not be supported by all servers/asyncssh versions; in those cases the code falls back to `proc.kill()`.

---

If you want, next I can:

* add per-session buffer trimming and retention policy, or
* wrap this into a FastAPI microservice with `POST /sessions`, `POST /sessions/{id}/run`, `POST /sessions/{id}/input`, `POST /sessions/{id}/signal`, `GET /sessions/{id}/remaining?marker=...`, or
* provide a small example client that exercises the two-session flow end-to-end.

Which one should I produce next?
