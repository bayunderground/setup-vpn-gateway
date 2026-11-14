#!/usr/bin/env python3
"""Decide what the gateway should do for client traffic. Read-only.

Reads the watcher's state file and the tunnel interface, and prints one decision:

  ORDINARY  Happ is positively DISABLED. Clients use the normal router path.
  VPN_EXIT  Happ is ENABLED, the tunnel process is up, and the tunnel interface is up.
  BLOCK     Anything else. Client internet must not leave by the normal connection.

This program changes nothing. Applying the decision to nftables and routing is a
separate step that has not been approved yet.

Usage:
  gateway_mode.py [--state PATH]
"""
import json
import subprocess
import sys
import time
from datetime import datetime

STATE_PATH = "/run/vpn-gateway/state.json"
TUNNEL = "happ-xray"
STALE_AFTER = 15.0


def decide(intent, process, tunnel_up, fresh):
    if not fresh:
        return "BLOCK", "state missing, unreadable, or stale"
    if intent == "DISABLED":
        return "ORDINARY", "Happ positively disabled"
    if intent == "ENABLED" and process == "up" and tunnel_up:
        return "VPN_EXIT", "Happ enabled, process up, tunnel up"
    if intent == "ENABLED":
        return "BLOCK", "Happ enabled but tunnel not ready"
    return "BLOCK", f"intent {intent} is not a safe state"


def read_state(path, now):
    """Return (intent, process, fresh). Anything unreadable is UNKNOWN and not fresh."""
    try:
        with open(path) as f:
            doc = json.load(f)
        updated = datetime.fromisoformat(doc["updated"]).timestamp()
        fresh = 0 <= now - updated <= STALE_AFTER
        intent = doc.get("intent", "UNKNOWN")
        process = doc.get("process", "unknown")
        if intent not in ("ENABLED", "DISABLED", "TRANSITION", "UNKNOWN"):
            return "UNKNOWN", "unknown", False
        return intent, process, fresh
    except (OSError, ValueError, KeyError, TypeError):
        return "UNKNOWN", "unknown", False


def tunnel_up():
    result = subprocess.run(
        ["ip", "-j", "link", "show", "dev", TUNNEL],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        return False
    try:
        links = json.loads(result.stdout)
    except ValueError:
        return False
    return bool(links) and "UP" in links[0].get("flags", [])


def main(argv):
    path = STATE_PATH
    if len(argv) == 3 and argv[1] == "--state":
        path = argv[2]
    elif len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    now = time.time()
    intent, process, fresh = read_state(path, now)
    up = tunnel_up()
    mode, reason = decide(intent, process, up, fresh)
    print(json.dumps({"mode": mode, "reason": reason, "intent": intent,
                      "process": process, "tunnel_up": up, "fresh": fresh}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
