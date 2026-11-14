import json
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "gateway"))

import gateway_mode as gm  # noqa: E402


def stamp(seconds_ago):
    return (datetime.now().astimezone() - timedelta(seconds=seconds_ago)).isoformat(timespec="seconds")


class DecideTests(unittest.TestCase):
    def test_disabled_uses_ordinary_path(self):
        self.assertEqual(gm.decide("DISABLED", "down", False, True)[0], "ORDINARY")
        self.assertEqual(gm.decide("DISABLED", "down", True, True)[0], "ORDINARY")

    def test_enabled_with_tunnel_exits_via_vpn(self):
        self.assertEqual(gm.decide("ENABLED", "up", True, True)[0], "VPN_EXIT")

    def test_enabled_without_tunnel_blocks(self):
        self.assertEqual(gm.decide("ENABLED", "up", False, True)[0], "BLOCK")
        self.assertEqual(gm.decide("ENABLED", "down", True, True)[0], "BLOCK")

    def test_transition_and_unknown_block(self):
        self.assertEqual(gm.decide("TRANSITION", "up", True, True)[0], "BLOCK")
        self.assertEqual(gm.decide("UNKNOWN", "unknown", True, True)[0], "BLOCK")

    def test_stale_or_missing_state_blocks_even_if_disabled(self):
        self.assertEqual(gm.decide("DISABLED", "down", False, False)[0], "BLOCK")
        self.assertEqual(gm.decide("ENABLED", "up", True, False)[0], "BLOCK")

    def test_only_disabled_or_vpn_exit_allow_traffic(self):
        allowed = {"ORDINARY", "VPN_EXIT"}
        for intent in ("ENABLED", "DISABLED", "TRANSITION", "UNKNOWN", "garbage"):
            for process in ("up", "down", "unknown"):
                for tun in (True, False):
                    for fresh in (True, False):
                        mode, _ = gm.decide(intent, process, tun, fresh)
                        if mode in allowed:
                            self.assertTrue(
                                (intent == "DISABLED" and fresh)
                                or (intent == "ENABLED" and process == "up" and tun and fresh),
                                (intent, process, tun, fresh),
                            )


class ReadStateTests(unittest.TestCase):
    def write(self, doc):
        fd, path = tempfile.mkstemp()
        with os.fdopen(fd, "w") as f:
            f.write(doc if isinstance(doc, str) else json.dumps(doc))
        self.addCleanup(os.unlink, path)
        return path

    def test_fresh_state_is_read(self):
        path = self.write({"intent": "DISABLED", "process": "down", "updated": stamp(1)})
        self.assertEqual(gm.read_state(path, time.time()), ("DISABLED", "down", True))

    def test_old_state_is_not_fresh(self):
        path = self.write({"intent": "DISABLED", "process": "down", "updated": stamp(gm.STALE_AFTER + 60)})
        self.assertEqual(gm.read_state(path, time.time())[2], False)

    def test_missing_file_is_unknown(self):
        self.assertEqual(gm.read_state("/nonexistent/state.json", time.time()), ("UNKNOWN", "unknown", False))

    def test_garbage_is_unknown(self):
        path = self.write("not json")
        self.assertEqual(gm.read_state(path, time.time())[0], "UNKNOWN")

    def test_unknown_intent_value_is_unknown(self):
        path = self.write({"intent": "MAYBE", "process": "up", "updated": stamp(0)})
        self.assertEqual(gm.read_state(path, time.time())[0], "UNKNOWN")

    def test_future_timestamp_is_not_fresh(self):
        path = self.write({"intent": "DISABLED", "process": "down", "updated": stamp(-600)})
        self.assertEqual(gm.read_state(path, time.time())[2], False)


if __name__ == "__main__":
    unittest.main()
