#!/usr/bin/env python3
"""Decide what the gateway should do for client traffic. Read-only.

Reads the watcher's state file and the tunnel interface, and prints one decision:

  ORDINARY  Happ is positively DISABLED. Clients use the normal router path.
  VPN_EXIT  Happ is ENABLED, the tunnel process is up, and the tunnel interface is up.
  BLOCK     Anything else. Client internet must not leave by the normal connection.

After a Pi reboot the watcher may only know UNKNOWN. If the user's last explicit
choice (remembered by the watcher on disk) was OFF and the tunnel is down, the
decision is ORDINARY. A remembered ON, no remembered choice, or a live tunnel
still blocks.

This program changes nothing. forward_apply.py applies the decision.

Usage:
  gateway_mode.py [--state PATH]
"""
import json
import subprocess
import sys
import time
from datetime import datetime

# Written by happ_watch.py. /run is tmpfs, so this file is empty after a reboot.
STATE_PATH = "/run/vpn-gateway/state.json"
# Happ's tunnel interface on the Pi.
TUNNEL = "happ-xray"
# The state file must have been written this recently (seconds). The watcher rewrites
# it every 5 seconds, so 15 seconds means the watcher has stopped or is stuck.
STALE_AFTER = 15.0


def decide(intent, process, tunnel_up, fresh, last_choice=None):
    """Return (mode, reason). The order of the checks matters: each rule below is
    reached only when the ones above it did not match."""
    # Stale or unreadable state can never allow traffic, even if it says DISABLED.
    if not fresh:
        return "BLOCK", "state missing, unreadable, or stale"
    # The only way to get ORDINARY from a fresh observation: the user stopped Happ.
    if intent == "DISABLED":
        return "ORDINARY", "Happ positively disabled"
    # Happ is on and the tunnel is working: send clients through it.
    if intent == "ENABLED" and process == "up" and tunnel_up:
        return "VPN_EXIT", "Happ enabled, process up, tunnel up"
    # Happ says it is on, but the tunnel is missing. Do not fall back to the router path.
    if intent == "ENABLED":
        return "BLOCK", "Happ enabled but tunnel not ready"
    # The reboot case. The watcher does not know the current state, but the user's last
    # explicit choice was OFF. That is only trusted while there is no tunnel, because a
    # live tunnel means Happ is on now.
    if intent == "UNKNOWN" and last_choice == "DISABLED" and not tunnel_up and process != "up":
        return "ORDINARY", "watcher restarted; last explicit user choice was OFF and the tunnel is down"
    # Everything else, including TRANSITION and UNKNOWN, fails closed.
    return "BLOCK", f"intent {intent} is not a safe state"


def read_state(path, now):
    """Return (intent, process, fresh). Anything unreadable is UNKNOWN and not fresh."""
    try:
        with open(path) as f:
            doc = json.load(f)
        updated = datetime.fromisoformat(doc["updated"]).timestamp()
        # A timestamp in the future is treated as not fresh: the clock or the file is wrong.
        fresh = 0 <= now - updated <= STALE_AFTER
        intent = doc.get("intent", "UNKNOWN")
        process = doc.get("process", "unknown")
        # Only the four known values are accepted. Anything else is treated as UNKNOWN.
        if intent not in ("ENABLED", "DISABLED", "TRANSITION", "UNKNOWN"):
            return "UNKNOWN", "unknown", False
        return intent, process, fresh
    except (OSError, ValueError, KeyError, TypeError):
        return "UNKNOWN", "unknown", False


def read_last_choice(path):
    """Return the user's last explicit choice ("ENABLED" or "DISABLED") from the state file, or None."""
    try:
        with open(path) as f:
            choice = json.load(f).get("last_choice")
    except (OSError, ValueError, AttributeError):
        return None
    return choice if choice in ("ENABLED", "DISABLED") else None


def tunnel_up():
    """True only when the kernel reports the tunnel interface as UP. The interface being
    present is not enough."""
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
        # Used by the tests and for manual checks with a fake state file.
        path = argv[2]
    elif len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    now = time.time()
    intent, process, fresh = read_state(path, now)
    last_choice = read_last_choice(path)
    up = tunnel_up()
    mode, reason = decide(intent, process, up, fresh, last_choice)
    print(json.dumps({"mode": mode, "reason": reason, "intent": intent,
                      "process": process, "tunnel_up": up, "fresh": fresh,
                      "last_choice": last_choice}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
