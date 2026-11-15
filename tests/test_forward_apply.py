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
    """Return code for nft calls. `fail_check`/`fail_apply` match ruleset text."""

    def __init__(self, fail_all=False, table_present=True):
        self.calls = []
        self.texts = []
        self.fail_all = fail_all
        self.table_present = table_present
        self.fail_check = None
        self.fail_apply = None

    def __call__(self, argv):
        self.calls.append(list(argv))
        text = ""
        if argv[0] == "nft" and argv[1] in ("-c", "-f"):
            try:
                with open(argv[-1]) as f:
                    text = f.read()
            except OSError:
                text = ""
        self.texts.append(text)
        if argv[0] != "nft":
            return 0
        if argv[1:3] == ["list", "table"]:
            return 0 if self.table_present else 1
        if self.fail_all:
            return 1
        if argv[1] == "-c" and self.fail_check and self.fail_check in text:
            return 1
        if argv[1] == "-f" and self.fail_apply and self.fail_apply in text:
            return 1
        return 0


def applies_with(runner, needle):
    """The nft -f calls whose ruleset text contains `needle`."""
    return [call for call, text in zip(runner.calls, runner.texts)
            if call[1] == "-f" and needle in text]


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
        self.assertFalse([call for call in r.calls[n:] if call[1] == "-f"])

    def test_mode_change_reapplies(self):
        r = FakeRunner()
        c = make(r)
        c.tick("VPN_EXIT")
        n = len(r.calls)
        c.tick("ORDINARY")
        self.assertEqual(len([call for call in r.calls[n:] if call[1] == "-f"]), 1)

    def test_failed_check_falls_back_to_block(self):
        r = FakeRunner()
        c = make(r)
        c.tick("ORDINARY")
        r.fail_check = "happ-xray"
        mode = c.tick("VPN_EXIT")
        self.assertEqual(mode, "BLOCK")
        self.assertEqual(c.applied, fp.build_ruleset("BLOCK", list(fp.DEFAULT_CLIENTS)))
        self.assertFalse(applies_with(r, "happ-xray"))

    def test_failed_apply_falls_back_to_block(self):
        r = FakeRunner()
        c = make(r)
        c.tick("ORDINARY")
        r.fail_apply = "happ-xray"
        mode = c.tick("VPN_EXIT")
        self.assertEqual(mode, "BLOCK")
        self.assertEqual(c.applied, fp.build_ruleset("BLOCK", list(fp.DEFAULT_CLIENTS)))

    def test_failed_block_keeps_previous_ruleset_and_reports_error(self):
        r = FakeRunner()
        c = make(r)
        c.tick("ORDINARY")
        before = c.applied
        r.fail_all = True
        mode = c.tick("VPN_EXIT")
        self.assertEqual(mode, "ORDINARY")
        self.assertEqual(c.applied, before)
        self.assertIn("not applied", c.last_error)
        self.assertFalse(applies_with(r, "happ-xray"))

    def test_startup_failure_returns_none(self):
        r = FakeRunner(fail_all=True)
        c = make(r)
        self.assertIsNone(c.tick("VPN_EXIT"))
        self.assertIsNone(c.applied)
        self.assertIsNotNone(c.last_error)

    def test_flushed_table_is_reapplied(self):
        r = FakeRunner()
        c = make(r)
        c.tick("VPN_EXIT")
        r.table_present = False
        c.tick("VPN_EXIT")
        self.assertTrue(applies_with(r, "happ-xray"))

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
