#!/usr/bin/env python3
"""Passive observer for the happd control socket.

Connects to /tmp/happd.sock and records every frame the daemon sends.
It sends only get-privilege and heartbeat requests. It never sends start or stop.

Frame format (observed 2026-11-14): 4-byte big-endian length, then UTF-8 JSON.

Usage: python3 happd-observe.py [seconds] [logfile]
"""
import json
import select
import socket
import struct
import sys
import time

SOCK_PATH = "/tmp/happd.sock"
DURATION = int(sys.argv[1]) if len(sys.argv) > 1 else 120
LOG_PATH = sys.argv[2] if len(sys.argv) > 2 else "/tmp/opencode/happd-observer.log"
HEARTBEAT_EVERY = 2.0


def frame(obj):
    data = json.dumps(obj, separators=(",", ":")).encode()
    return struct.pack(">I", len(data)) + data


def split_frames(buf):
    out = []
    while len(buf) >= 4:
        size = struct.unpack(">I", buf[:4])[0]
        if len(buf) < 4 + size:
            break
        out.append(buf[4:4 + size].decode(errors="replace"))
        buf = buf[4 + size:]
    return out, buf


def log(logf, text):
    line = f"{time.strftime('%H:%M:%S')} {text}"
    print(line, flush=True)
    logf.write(line + "\n")
    logf.flush()


def main():
    with open(LOG_PATH, "a") as logf:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(SOCK_PATH)
        s.sendall(frame({"action": "get-privilege", "request-id": "obs-priv"}))
        log(logf, f"connected {SOCK_PATH}, observing {DURATION}s")

        end = time.time() + DURATION
        next_hb = time.time()
        hb = 0
        buf = b""
        while time.time() < end:
            if time.time() >= next_hb:
                hb += 1
                s.sendall(frame({"action": "heartbeat", "request-id": f"obs-hb-{hb}"}))
                next_hb += HEARTBEAT_EVERY
            ready, _, _ = select.select([s], [], [], 0.5)
            if not ready:
                continue
            chunk = s.recv(65536)
            if not chunk:
                log(logf, "daemon closed the connection")
                break
            buf += chunk
            frames, buf = split_frames(buf)
            for text in frames:
                if '"heartbeat' in text or '"request-id":"obs-hb' in text:
                    continue
                if '"push-token"' in text:
                    text = '{"event":"push-token","token":"<redacted>"}'
                log(logf, text[:400])
        s.close()
        log(logf, "done")


if __name__ == "__main__":
    main()
