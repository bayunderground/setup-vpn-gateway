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

STATE_PATH = "/run/vpn-gateway/state.json"
HAPPD_SOCK = "/tmp/happd.sock"
PROCESS_ID = "xray-core"
PUBLISH_EVERY = 5.0
RETRY_AFTER = 2.0
NO_DAEMON_RETRY = 5.0

EVENT_LINE = re.compile(r"(read|write|sendmsg|recvmsg)\((\d+), ")
TIME_PREFIX = re.compile(r"(\d\d:\d\d:\d\d\.\d+)")

REQUEST_PATTERNS = [
    (re.compile(r'\\"action\\":\\"stop\\",\\"process-id\\":\\"xray-core\\"'), ("stop_request",)),
    (re.compile(r'\\"action\\":\\"start\\"'), ("start_request",)),
]
EVENT_PATTERNS = [
    (re.compile(r'\\"event\\":\\"started\\",\\"process-id\\":\\"xray-core\\"'), ("started",)),
    (re.compile(r'\\"data\\":\\"(-?\d+)\\",\\"event\\":\\"finished\\",\\"process-id\\":\\"xray-core\\"'), None),
    (re.compile(r'\\"data\\":\\"Process crashed\\"'), ("crashed",)),
    (re.compile(r'\\"error\\":\\"Process not found: xray-core\\"'), ("not_found",)),
]
REQUEST_DIRECTIONS = ("read", "recvmsg")
EVENT_DIRECTIONS = ("write", "sendmsg")


def parse_line(line):
    """Return the control events found in one strace line. Never keeps the line."""
    m = EVENT_LINE.search(line)
    if not m:
        return []
    direction, fd = m.group(1), int(m.group(2))
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
                events.append(("finished", found.group(1)))
            else:
                events.append(event)
    return events


class State:
    def __init__(self):
        self.intent = "UNKNOWN"
        self.process = "unknown"
        self.reason = "watcher started"
        self.pending_stop = False

    def set(self, intent, process, reason):
        changed = (intent, process) != (self.intent, self.process)
        self.intent, self.process, self.reason = intent, process, reason
        return changed

    def apply(self, event):
        kind = event[0]
        if kind == "start_request":
            return self.set("TRANSITION", "unknown", "start requested")
        if kind == "started":
            self.pending_stop = False
            return self.set("ENABLED", "up", "started event")
        if kind == "stop_request":
            if self.process == "down":
                return False
            self.pending_stop = True
            return self.set("TRANSITION", "up", "stop requested")
        if kind == "finished":
            code = event[1]
            stopped_by_user = self.pending_stop and code == "0"
            self.pending_stop = False
            if stopped_by_user:
                return self.set("DISABLED", "down", "stopped by user")
            return self.set("ENABLED", "down", f"process exited with code {code}")
        if kind == "crashed":
            self.pending_stop = False
            return self.set("ENABLED", "down", "process crashed")
        if kind == "not_found":
            if self.pending_stop:
                self.pending_stop = False
                return self.set("DISABLED", "down", "stopped by user (process gone)")
            if self.intent == "ENABLED":
                return self.set("ENABLED", "down", "process not found")
            return False
        return False

    def unknown(self, reason):
        self.pending_stop = False
        return self.set("UNKNOWN", "unknown", reason)


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def publish(state, happd_pid):
    doc = {
        "intent": state.intent,
        "process": state.process,
        "reason": state.reason,
        "updated": now_iso(),
        "happd_pid": happd_pid,
    }
    directory = os.path.dirname(STATE_PATH)
    os.makedirs(directory, mode=0o755, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".state-")
    with os.fdopen(fd, "w") as f:
        json.dump(doc, f)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp, 0o644)
    os.replace(tmp, STATE_PATH)


def log(message):
    print(f"{now_iso()} {message}", flush=True)


def replay(path):
    state = State()
    with open(path, errors="replace") as f:
        for line in f:
            events = parse_line(line)
            for event in events:
                if state.apply(event):
                    stamp = TIME_PREFIX.search(line)
                    print(f"{stamp.group(1) if stamp else '-'} {state.intent} {state.process} ({state.reason})")


def happd_pid():
    out = subprocess.run(
        ["systemctl", "show", "-p", "MainPID", "--value", "happd.service"],
        capture_output=True, text=True, check=False,
    ).stdout.strip()
    return int(out) if out.isdigit() else 0


def frame(obj):
    data = json.dumps(obj, separators=(",", ":")).encode()
    return struct.pack(">I", len(data)) + data


def probe_status():
    """One read-only status request. Returns 'running', 'not-running', or None."""
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
            while len(buf) >= 4:
                size = struct.unpack(">I", buf[:4])[0]
                if len(buf) < 4 + size:
                    break
                text = buf[4:4 + size].decode(errors="replace")
                buf = buf[4 + size:]
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
            ready, _, _ = select.select([fd], [], [], PUBLISH_EVERY)
            if ready:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                buf += chunk
                *lines, buf = buf.split(b"\n")
                for raw in lines:
                    for event in parse_line(raw.decode(errors="replace")):
                        if state.apply(event):
                            log(f"intent={state.intent} process={state.process} ({state.reason})")
                            publish(state, pid)
                            last_publish = time.time()
            if time.time() - last_publish >= PUBLISH_EVERY:
                publish(state, pid)
                last_publish = time.time()
    finally:
        proc.kill()
        proc.wait()


def run_service():
    state = State()
    publish(state, 0)
    log("watcher started; state UNKNOWN until the GUI is observed")
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
        if probe_status() == "running" and state.intent == "UNKNOWN":
            state.set("ENABLED", "up", "xray running when the watcher attached")
            log("intent=ENABLED process=up (xray running at attach)")
        publish(state, pid)
        try:
            watch(pid, state)
        except OSError as err:
            log(f"strace failed: {err}")
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
