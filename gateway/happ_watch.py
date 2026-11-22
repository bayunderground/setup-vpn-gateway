#!/usr/bin/env python3
"""Happ GUI intent watcher for the VPN gateway. Read-only.

Attaches strace to the main thread of happd and reads the control messages that
the Happ GUI sends and receives over /tmp/happd.sock. It derives the user's intent
(ENABLED, DISABLED, TRANSITION, UNKNOWN) and publishes it to STATE_PATH.

Stop detection: the daemon does not always send a "finished" event after a user
stop (observed on 2026-11-14). A stop request followed by a "Process not found"
reply is also treated as a user stop.

After a crash the GUI sends its own stop request about 0.3 s later (observed
2026-11-14). A stop request while the process is already down is ignored, so
a crash never looks like a user OFF. Known limit: a user OFF clicked after a
crash cannot be told apart from that cleanup, so the gateway stays blocked
until Happ is started again.

Remembered choice (2026-11-22): every explicit user ON or OFF is also saved to
CHOICE_PATH on disk. After a reboot the watcher starts UNKNOWN, but the saved
choice is published in the state file, so gateway_mode.py can use an OFF when
the tunnel is down.

Privacy and safety rules:
  - Raw trace lines are never written to disk or printed. Only derived state
    changes are printed (to the systemd journal).
  - start requests carry the xray configuration. They are parsed in memory and
    only the fact that a start was requested is kept.
  - Only messages for process "xray-core" are considered.
  - The watcher never sends start or stop. It sends one read-only status request
    when it attaches.
  - Anything it cannot see is UNKNOWN, which the controller treats as blocked.

Usage:
  happ_watch.py               run as the systemd service (root)
  happ_watch.py --replay FILE print state changes found in a saved strace file
"""
import json
import os
import re
import select
import socket
import struct
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

# Live state for the controllers. /run is tmpfs, so it is rebuilt after every boot.
STATE_PATH = "/run/vpn-gateway/state.json"
# The user's last explicit ON or OFF. Kept on disk so it survives a reboot.
CHOICE_PATH = "/var/lib/vpn-gateway/last_choice.json"
# Happd's control socket. The watcher only sends one read-only status request on it.
HAPPD_SOCK = "/tmp/happd.sock"
# The only Happ process the watcher cares about. Other processes are ignored.
PROCESS_ID = "xray-core"
# How often the state file is rewritten even when nothing changed (seconds).
PUBLISH_EVERY = 5.0
# Wait before re-attaching strace after it stopped (seconds).
RETRY_AFTER = 2.0
# Wait before looking for happd again when it is not running (seconds).
NO_DAEMON_RETRY = 5.0

# Pulls the file descriptor out of an strace line such as: read(12, "...", 512) = 512
EVENT_LINE = re.compile(r"(read|write|sendmsg|recvmsg)\((\d+), ")
# Pulls the timestamp (hh:mm:ss.micro) from the start of an strace line.
TIME_PREFIX = re.compile(r"(\d\d:\d\d:\d\d\.\d+)")

# Requests from the GUI to happd. Patterns are matched against the escaped JSON text
# inside the strace line, so the backslashes are part of the pattern.
REQUEST_PATTERNS = [
    # The user (or the GUI's cleanup after a crash) asked xray-core to stop.
    (re.compile(r'\\"action\\":\\"stop\\",\\"process-id\\":\\"xray-core\\"'), ("stop_request",)),
    # The user asked xray-core to start. The payload is not kept (it carries the config).
    (re.compile(r'\\"action\\":\\"start\\"'), ("start_request",)),
]
# Messages from happd to the GUI. These patterns are matched only on write/sendmsg.
EVENT_PATTERNS = [
    # xray-core reports that it is running.
    (re.compile(r'\\"event\\":\\"started\\",\\"process-id\\":\\"xray-core\\"'), ("started",)),
    # xray-core exited. The capture group is the exit code; "0" means a clean exit.
    (re.compile(r'\\"data\\":\\"(-?\d+)\\",\\"event\\":\\"finished\\",\\"process-id\\":\\"xray-core\\"'), None),
    # xray-core died unexpectedly.
    (re.compile(r'\\"data\\":\\"Process crashed\\"'), ("crashed",)),
    # happd says there is no xray-core process to stop or query.
    (re.compile(r'\\"error\\":\\"Process not found: xray-core\\"'), ("not_found",)),
]
# Requests are read by happd, so they show up as read/recvmsg on the connection.
REQUEST_DIRECTIONS = ("read", "recvmsg")
# Replies and events are written by happd, so they show up as write/sendmsg.
EVENT_DIRECTIONS = ("write", "sendmsg")


def parse_line(line):
    """Return the control events found in one strace line. Never keeps the line."""
    m = EVENT_LINE.search(line)
    if not m:
        return []
    direction, fd = m.group(1), int(m.group(2))
    # fd 0, 1, 2 are stdin, stdout, stderr. Control traffic is on the socket, not there.
    if fd <= 2:
        return []
    events = []
    if direction in REQUEST_DIRECTIONS:
        for pattern, event in REQUEST_PATTERNS:
            if pattern.search(line):
                events.append(event)
    elif direction in EVENT_DIRECTIONS:
        for pattern, event in EVENT_PATTERNS:
            found = pattern.search(line)
            if not found:
                continue
            if event is None:
                # "finished" carries the exit code, so it is returned with the code.
                events.append(("finished", found.group(1)))
            else:
                events.append(event)
    return events


class State:
    """The watcher's view of Happ. apply() turns one event into a state change and
    returns True when the visible state (intent or process) actually changed."""

    def __init__(self):
        # What the watcher believes right now. UNKNOWN until it sees something.
        self.intent = "UNKNOWN"
        self.process = "unknown"
        self.reason = "watcher started"
        # True between a stop request and its outcome, so the next "finished" or
        # "not found" can be attributed to the user.
        self.pending_stop = False
        # The last explicit ON or OFF this watcher has seen (or loaded from disk).
        self.last_choice = None

    def set(self, intent, process, reason):
        changed = (intent, process) != (self.intent, self.process)
        self.intent, self.process, self.reason = intent, process, reason
        return changed

    def apply(self, event):
        kind = event[0]
        if kind == "start_request":
            # A start was asked for but not yet confirmed. Clients stay blocked meanwhile.
            return self.set("TRANSITION", "unknown", "start requested")
        if kind == "started":
            self.pending_stop = False
            return self.set("ENABLED", "up", "started event")
        if kind == "stop_request":
            # A stop after a crash is GUI cleanup, not a user choice, so it is ignored.
            if self.process == "down":
                return False
            self.pending_stop = True
            return self.set("TRANSITION", "up", "stop requested")
        if kind == "finished":
            code = event[1]
            # Only a clean exit (code 0) that follows a stop request counts as a user OFF.
            stopped_by_user = self.pending_stop and code == "0"
            self.pending_stop = False
            if stopped_by_user:
                return self.set("DISABLED", "down", "stopped by user")
            # Any other exit is treated as ENABLED-but-down, which blocks clients.
            return self.set("ENABLED", "down", f"process exited with code {code}")
        if kind == "crashed":
            self.pending_stop = False
            return self.set("ENABLED", "down", "process crashed")
        if kind == "not_found":
            # happd has no process. After a stop request this is the reliable user-OFF
            # signal, because happd often sends no "finished" event.
            if self.pending_stop:
                self.pending_stop = False
                return self.set("DISABLED", "down", "stopped by user (process gone)")
            # Not found while we think it is on: the process vanished without a stop.
            if self.intent == "ENABLED":
                return self.set("ENABLED", "down", "process not found")
            return False
        return False

    def unknown(self, reason):
        """Forget what was observed. Used when the trace is lost or happd restarts.
        The saved last_choice is kept, because it is not a live observation."""
        self.pending_stop = False
        return self.set("UNKNOWN", "unknown", reason)


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def write_json_atomic(path, doc):
    """Write JSON to a temporary file in the same directory, then rename it over `path`.
    A reader never sees a half-written file."""
    directory = os.path.dirname(path)
    os.makedirs(directory, mode=0o755, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp-")
    with os.fdopen(fd, "w") as f:
        json.dump(doc, f)
        f.flush()
        # Force the data to disk before the rename, so a power cut cannot leave an empty file.
        os.fsync(f.fileno())
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def publish(state, happd_pid):
    """Write the current state for the controllers to read."""
    doc = {
        "intent": state.intent,
        "process": state.process,
        "reason": state.reason,
        "updated": now_iso(),
        "happd_pid": happd_pid,
        "last_choice": state.last_choice,
    }
    write_json_atomic(STATE_PATH, doc)


def load_last_choice(path=CHOICE_PATH):
    """The user's last explicit choice from disk, or None. Survives reboots."""
    try:
        with open(path) as f:
            choice = json.load(f).get("choice")
    except (OSError, ValueError, AttributeError):
        return None
    return choice if choice in ("ENABLED", "DISABLED") else None


def record_choice(state, path=CHOICE_PATH):
    """Remember an explicit ON or OFF. UNKNOWN and TRANSITION are never remembered."""
    if state.intent not in ("ENABLED", "DISABLED") or state.intent == state.last_choice:
        return
    try:
        write_json_atomic(path, {"choice": state.intent, "updated": now_iso()})
    except OSError as err:
        # Not saving is safe: the controller then blocks instead of guessing.
        log(f"could not save the choice to {path}: {err}")
        return
    state.last_choice = state.intent


def log(message):
    print(f"{now_iso()} {message}", flush=True)


def replay(path):
    """Print the state changes found in a saved strace file. For tests and analysis."""
    state = State()
    with open(path, errors="replace") as f:
        for line in f:
            events = parse_line(line)
            for event in events:
                if state.apply(event):
                    stamp = TIME_PREFIX.search(line)
                    print(f"{stamp.group(1) if stamp else '-'} {state.intent} {state.process} ({state.reason})")


def happd_pid():
    """Return the PID of happd.service, or 0 when it is not running."""
    out = subprocess.run(
        ["systemctl", "show", "-p", "MainPID", "--value", "happd.service"],
        capture_output=True, text=True, check=False,
    ).stdout.strip()
    return int(out) if out.isdigit() else 0


def frame(obj):
    """Encode one message in happd's wire format: a 4-byte big-endian length, then JSON."""
    data = json.dumps(obj, separators=(",", ":")).encode()
    return struct.pack(">I", len(data)) + data


def probe_status():
    """One read-only status request. Returns 'running', 'not-running', or None.

    Used once at attach time, so a Happ that is already running is recognized
    without waiting for a start event."""
    request_id = "watch-status"
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(3)
    try:
        sock.connect(HAPPD_SOCK)
        sock.sendall(frame({"action": "status", "process-id": PROCESS_ID, "request-id": request_id}))
        buf = b""
        deadline = time.time() + 3
        while time.time() < deadline:
            chunk = sock.recv(65536)
            if not chunk:
                break
            buf += chunk
            # Replies are length-prefixed. Read as many complete messages as are buffered.
            while len(buf) >= 4:
                size = struct.unpack(">I", buf[:4])[0]
                if len(buf) < 4 + size:
                    break
                text = buf[4:4 + size].decode(errors="replace")
                buf = buf[4 + size:]
                # Ignore messages for other requests (happd may send unrelated events).
                if request_id not in text:
                    continue
                if '"running":true' in text:
                    return "running"
                return "not-running"
    except OSError:
        return None
    finally:
        sock.close()
    return None


def watch(pid, state):
    """Run strace on happd until it exits, updating `state` from the control messages."""
    # -tt adds timestamps, -e limits the trace to read/write, -s 512 keeps enough of each
    # message to match the patterns. Stdout is discarded so no raw trace is kept.
    proc = subprocess.Popen(
        ["strace", "-tt", "-p", str(pid), "-e", "trace=read,write", "-s", "512"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    fd = proc.stderr.fileno()
    buf = b""
    last_publish = 0.0
    try:
        while True:
            # Wait up to PUBLISH_EVERY seconds for trace output. The timeout lets the
            # state file be refreshed even when Happ is silent.
            ready, _, _ = select.select([fd], [], [], PUBLISH_EVERY)
            if ready:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                buf += chunk
                # Keep the last, possibly incomplete, line in the buffer for the next read.
                *lines, buf = buf.split(b"\n")
                for raw in lines:
                    for event in parse_line(raw.decode(errors="replace")):
                        if state.apply(event):
                            log(f"intent={state.intent} process={state.process} ({state.reason})")
                            record_choice(state)
                            publish(state, pid)
                            last_publish = time.time()
            if time.time() - last_publish >= PUBLISH_EVERY:
                publish(state, pid)
                last_publish = time.time()
    finally:
        proc.kill()
        proc.wait()


def run_service():
    """Main loop for the systemd service. Re-attaches whenever happd or strace goes away."""
    state = State()
    # Load the saved choice first, so the very first state file already carries it.
    state.last_choice = load_last_choice()
    publish(state, 0)
    log(f"watcher started; state UNKNOWN until the GUI is observed (last saved choice: {state.last_choice})")
    while True:
        pid = happd_pid()
        if not pid:
            if state.unknown("happd is not running"):
                log("intent=UNKNOWN (happd is not running)")
            publish(state, 0)
            time.sleep(NO_DAEMON_RETRY)
            continue
        state.unknown(f"attaching to happd pid {pid}")
        publish(state, pid)
        # If xray is already running when we attach, the GUI's start event was missed.
        # Treat it as ENABLED, but only while the state is still UNKNOWN.
        if probe_status() == "running" and state.intent == "UNKNOWN":
            state.set("ENABLED", "up", "xray running when the watcher attached")
            log("intent=ENABLED process=up (xray running at attach)")
            record_choice(state)
        publish(state, pid)
        try:
            watch(pid, state)
        except OSError as err:
            log(f"strace failed: {err}")
        # The trace stopped, so the watcher no longer sees Happ. Go back to UNKNOWN.
        state.unknown("tracer stopped; happd may have restarted")
        publish(state, 0)
        log("intent=UNKNOWN (tracer stopped)")
        time.sleep(RETRY_AFTER)


def main(argv):
    if len(argv) == 3 and argv[1] == "--replay":
        replay(argv[2])
        return 0
    if len(argv) == 1:
        run_service()
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
