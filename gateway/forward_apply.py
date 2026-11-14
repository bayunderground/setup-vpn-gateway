#!/usr/bin/env python3
"""Keep the client forwarding ruleset in step with the Happ state. Runs as root.

Every few seconds it reads the watcher state and the tunnel (gateway_mode.py),
builds the matching ruleset (forward_policy.py), and applies it only when the
mode changes. Each ruleset is checked with `nft -c -f` before it is applied.

Rules (CLAUDE.md, user decision 2026-11-14):
  Happ ON  (VPN_EXIT): clients leave through Happ.
  Happ OFF (ORDINARY): clients leave through the router path.
  Unknown or stale:    BLOCK. A failed check never replaces the working ruleset.

Only the project table `ip vpn_gateway` is written. The global ruleset is never
flushed, and nftables.service is never enabled.

Usage:
  forward_apply.py            run as the systemd service (root)
  forward_apply.py --once     run one tick and print the mode
"""
import os
import subprocess
import sys
import tempfile
import time

import forward_policy as fp
import gateway_mode as gm

TICK_SECONDS = 5.0
WORK_DIR = "/run/vpn-gateway"


def _run(argv):
    return subprocess.run(argv, capture_output=True, text=True, check=False).returncode


class Controller:
    """Holds the last applied ruleset. `runner(argv) -> returncode` is injectable."""

    def __init__(self, runner=_run, clients=fp.DEFAULT_CLIENTS, work_dir=WORK_DIR):
        self.runner = runner
        self.clients = list(clients)
        self.work_dir = work_dir
        self.applied = None
        self.mode = None

    def tick(self, mode):
        """Make the ruleset match `mode`. Returns the mode now in effect."""
        if mode not in ("VPN_EXIT", "ORDINARY", "BLOCK"):
            mode = "BLOCK"
        text = fp.build_ruleset(mode, self.clients)
        if text == self.applied:
            return self.mode
        path = self._write(text)
        try:
            if self.runner(["nft", "-c", "-f", path]) != 0:
                return self.mode
            if self.runner(["nft", "-f", path]) != 0:
                return self.mode
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
        self.applied = text
        self.mode = mode
        return mode

    def _write(self, text):
        os.makedirs(self.work_dir, exist_ok=True)
        fd, path = tempfile.mkstemp(prefix="forward-", suffix=".nft", dir=self.work_dir)
        with os.fdopen(fd, "w") as f:
            f.write(text)
        return path


def decide_now(state_path=gm.STATE_PATH):
    now = time.time()
    intent, process, fresh = gm.read_state(state_path, now)
    up = gm.tunnel_up()
    mode, _reason = gm.decide(intent, process, up, fresh)
    return mode


def main(argv):
    if "--once" in argv:
        c = Controller()
        print(c.tick(decide_now()))
        return 0
    c = Controller()
    last_printed = None
    while True:
        try:
            mode = c.tick(decide_now())
        except Exception as exc:  # fail closed: try to block, then keep running
            print(f"forward_apply: error {exc!r}; trying BLOCK", file=sys.stderr, flush=True)
            mode = c.tick("BLOCK")
        if mode != last_printed:
            print(f"forward_apply: mode={mode}", flush=True)
            last_printed = mode
        time.sleep(TICK_SECONDS)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
