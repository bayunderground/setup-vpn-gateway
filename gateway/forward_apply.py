#!/usr/bin/env python3
"""Keep the client forwarding ruleset in step with the Happ state. Runs as root.

Every few seconds it reads the watcher state and the tunnel (gateway_mode.py),
builds the matching ruleset (forward_policy.py), and applies it only when the
mode changes. Each ruleset is checked with `nft -c -f` before it is applied.

Rules (CLAUDE.md, user decision 2026-11-14):
  Happ ON  (VPN_EXIT): clients leave through Happ.
  Happ OFF (ORDINARY): clients leave through the router path.
  Unknown or stale:    BLOCK.

Fail closed: if the wanted ruleset cannot be applied, the controller tries to
apply BLOCK instead. Keeping the previous ORDINARY ruleset after a failed
switch to VPN_EXIT would send client traffic out of the normal connection while
Happ is on, so that is never done. If even BLOCK cannot be applied, the last
working ruleset is kept, the error is reported, and the loop keeps running.

Only the project table `ip vpn_gateway` is written. The global ruleset is never
flushed, and nftables.service is never enabled.

Usage:
  forward_apply.py            run as the systemd service (root)
  forward_apply.py --once     run one tick; print the mode; exit 1 on failure
"""
import os
import subprocess
import sys
import tempfile
import time

import forward_policy as fp
import gateway_mode as gm

# How often the controller re-reads the state and the tunnel.
TICK_SECONDS = 5.0
# Scratch directory for the ruleset files handed to nft. It is on tmpfs (/run).
WORK_DIR = "/run/vpn-gateway"
MODES = ("VPN_EXIT", "ORDINARY", "BLOCK")
SAFE_MODE = "BLOCK"


def _run(argv):
    """Run a command and return only its exit code. Output is captured and discarded."""
    return subprocess.run(argv, capture_output=True, text=True, check=False).returncode


class Controller:
    """Holds the last applied ruleset. `runner(argv) -> returncode` is injectable so the
    tests can replace nft with a fake and check the sequence of commands."""

    def __init__(self, runner=_run, clients=fp.DEFAULT_CLIENTS, work_dir=WORK_DIR):
        self.runner = runner
        self.clients = list(clients)
        self.work_dir = work_dir
        # The exact ruleset text that is currently live, or None if unknown.
        self.applied = None
        # The mode that is currently live.
        self.mode = None
        # A short reason when the last apply failed, otherwise None.
        self.last_error = None

    def tick(self, mode):
        """Make the ruleset match `mode`. Returns the mode now in effect."""
        if mode not in MODES:
            # An unexpected value from the decision code is treated as unsafe.
            mode = SAFE_MODE
        self._verify()
        # Nothing to do when the live ruleset already matches. Without this check the
        # table would be flushed and reloaded on every tick.
        if self.applied == fp.build_ruleset(mode, self.clients):
            return self.mode
        if self._apply(mode):
            return mode
        # Fail closed: never leave ORDINARY in place when VPN_EXIT was wanted.
        if mode != SAFE_MODE and self._apply(SAFE_MODE):
            return SAFE_MODE
        return self.mode

    def _apply(self, mode):
        """Check and apply one ruleset. Returns True only when it is live."""
        text = fp.build_ruleset(mode, self.clients)
        path = self._write(text)
        try:
            # Step 1: check the syntax without changing anything.
            if self.runner(["nft", "-c", "-f", path]) != 0:
                self.last_error = f"{mode} ruleset failed nft -c; not applied"
                return False
            # Step 2: load it. The script itself flushes only the project table.
            if self.runner(["nft", "-f", path]) != 0:
                self.last_error = f"{mode} ruleset failed nft -f; not applied"
                return False
        finally:
            # The file is removed whether or not the apply worked.
            try:
                os.unlink(path)
            except OSError:
                pass
        self.applied = text
        self.mode = mode
        self.last_error = None
        return True

    def _verify(self):
        """Forget the cached ruleset if the table was removed or flushed by someone else.
        The next tick then re-applies it, so a removed table is restored within one tick."""
        if self.applied is not None and not self._table_present():
            self.applied = None

    def _table_present(self):
        return self.runner(["nft", "list", "table", "ip", fp.TABLE]) == 0

    def _write(self, text):
        """Write the ruleset to a fresh temporary file and return its path."""
        os.makedirs(self.work_dir, exist_ok=True)
        fd, path = tempfile.mkstemp(prefix="forward-", suffix=".nft", dir=self.work_dir)
        with os.fdopen(fd, "w") as f:
            f.write(text)
        return path


def decide_now(state_path=gm.STATE_PATH):
    """Read the state file and the tunnel, and return the mode they imply right now."""
    now = time.time()
    intent, process, fresh = gm.read_state(state_path, now)
    last_choice = gm.read_last_choice(state_path)
    up = gm.tunnel_up()
    mode, _reason = gm.decide(intent, process, up, fresh, last_choice)
    return mode


def main(argv):
    if "--once" in argv:
        # One tick, for manual checks. Exit 1 when the mode could not be applied.
        c = Controller()
        mode = c.tick(decide_now())
        print(mode)
        if c.last_error:
            print(f"forward_apply: {c.last_error}", file=sys.stderr, flush=True)
            return 1
        return 0
    c = Controller()
    last_status = None
    while True:
        try:
            mode = c.tick(decide_now())
        except Exception as exc:  # fail closed: try to block, then keep running
            print(f"forward_apply: error {exc!r}; trying BLOCK", file=sys.stderr, flush=True)
            try:
                mode = c.tick(SAFE_MODE)
            except Exception as block_exc:
                print(f"forward_apply: BLOCK also failed: {block_exc!r}",
                      file=sys.stderr, flush=True)
                mode = c.mode
        # Log only when the mode or the error changes, so the journal stays short.
        status = (mode, c.last_error)
        if status != last_status:
            detail = f" ({c.last_error})" if c.last_error else ""
            print(f"forward_apply: mode={mode}{detail}", flush=True)
            last_status = status
        time.sleep(TICK_SECONDS)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
