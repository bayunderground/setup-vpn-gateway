import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "gateway"))

import forward_policy as fp  # noqa: E402

DELL = "192.168.0.103"
ANDROID = "192.168.0.185"


class BuildRulesetTests(unittest.TestCase):
    def test_vpn_exit_sends_clients_only_into_happ(self):
        text = fp.build_ruleset("VPN_EXIT", [DELL, ANDROID])
        self.assertIn('oifname "happ-xray" accept', text)
        self.assertIn('oifname "happ-xray" masquerade', text)
        self.assertNotIn('oifname "eth0" accept', text)
        self.assertIn("drop", text)

    def test_ordinary_sends_clients_only_to_router(self):
        text = fp.build_ruleset("ORDINARY", [DELL, ANDROID])
        self.assertIn('oifname "eth0" accept', text)
        self.assertIn('oifname "eth0" masquerade', text)
        self.assertNotIn('oifname "happ-xray" accept', text)

    def test_block_drops_all_client_forwarding(self):
        text = fp.build_ruleset("BLOCK", [DELL, ANDROID])
        self.assertIn("drop", text)
        rules = [ln.strip() for ln in text.splitlines() if "accept" in ln and "policy" not in ln]
        self.assertEqual(rules, [], "BLOCK must not accept client traffic")
        self.assertNotIn("masquerade", text)

    def test_unknown_mode_fails_closed(self):
        text = fp.build_ruleset("WHATEVER", [DELL])
        self.assertIn("drop", text)
        self.assertNotIn("masquerade", text)

    def test_only_project_table_is_touched(self):
        for mode in ("VPN_EXIT", "ORDINARY", "BLOCK"):
            text = fp.build_ruleset(mode, [DELL])
            self.assertIn("table ip vpn_gateway", text)
            self.assertNotIn("flush ruleset", text)
            self.assertNotIn("delete table inet", text)

    def test_clients_are_listed_in_the_match(self):
        text = fp.build_ruleset("VPN_EXIT", [DELL, ANDROID])
        self.assertIn(f"{{ {DELL}, {ANDROID} }}", text)

    def test_only_ipv4_addresses_accepted(self):
        with self.assertRaises(ValueError):
            fp.build_ruleset("VPN_EXIT", ["fd00::1"])

    def test_invalid_client_rejected(self):
        for bad in ("", "192.168.0.300", "192.168.0.1; flush ruleset"):
            with self.assertRaises(ValueError):
                fp.build_ruleset("VPN_EXIT", [bad])

    def test_empty_client_list_rejected(self):
        with self.assertRaises(ValueError):
            fp.build_ruleset("VPN_EXIT", [])

    def test_default_clients_are_dell_and_android(self):
        self.assertEqual(fp.DEFAULT_CLIENTS, (DELL, ANDROID))


if __name__ == "__main__":
    unittest.main()
