import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "gateway"))

import forward_apply as fa  # noqa: E402
import forward_policy as fp  # noqa: E402


def make(runner):
    return fa.Controller(runner, work_dir=tempfile.mkdtemp())


class FakeRunner:
    def __init__(self, fail_on=()):
        self.calls = []
        self.fail_on = set(fail_on)

    def __call__(self, argv):
        self.calls.append(list(argv))
        if argv[0] == "nft" and argv[1] in self.fail_on:
            return 1
        return 0


class TickTests(unittest.TestCase):
    def test_first_tick_applies_mode(self):
        r = FakeRunner()
        state = make(r)
        mode = state.tick("VPN_EXIT")
        self.assertEqual(mode, "VPN_EXIT")
        self.assertEqual(len(r.calls), 2)  # check, then apply
        self.assertEqual(r.calls[0][:2], ["nft", "-c"])
        self.assertEqual(r.calls[1][:2], ["nft", "-f"])

    def test_unchanged_mode_does_not_reapply(self):
        r = FakeRunner()
        c = make(r)
        c.tick("VPN_EXIT")
        n = len(r.calls)
        c.tick("VPN_EXIT")
        self.assertEqual(len(r.calls), n)

    def test_mode_change_reapplies(self):
        r = FakeRunner()
        c = make(r)
        c.tick("VPN_EXIT")
        n = len(r.calls)
        c.tick("ORDINARY")
        self.assertEqual(len(r.calls), n + 2)

    def test_failed_check_keeps_previous_ruleset(self):
        r = FakeRunner(fail_on=("-c",))
        c = make(r)
        c.tick("VPN_EXIT")
        self.assertIsNone(c.applied)
        # a failed check must never be followed by an apply
        self.assertFalse(any(call[1] == "-f" for call in r.calls))

    def test_unknown_mode_applies_block(self):
        r = FakeRunner()
        c = make(r)
        mode = c.tick("SOMETHING")
        self.assertEqual(mode, "BLOCK")

    def test_never_touches_global_ruleset(self):
        r = FakeRunner()
        c = make(r)
        for m in ("VPN_EXIT", "ORDINARY", "BLOCK", "UNKNOWN"):
            c.tick(m)
        for call in r.calls:
            joined = " ".join(call)
            self.assertNotIn("flush ruleset", joined)
            self.assertNotIn("nftables.service", joined)
            self.assertNotIn("delete table inet", joined)


class ApplyTextTests(unittest.TestCase):
    def test_ruleset_text_matches_policy_module(self):
        c = make(FakeRunner())
        c.tick("ORDINARY")
        self.assertEqual(c.applied, fp.build_ruleset("ORDINARY", list(fp.DEFAULT_CLIENTS)))


if __name__ == "__main__":
    unittest.main()
