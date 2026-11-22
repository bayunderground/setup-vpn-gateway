#!/usr/bin/env python3
"""Build the nftables ruleset that routes client traffic through the Pi. Pure, no host changes.

The ruleset lives in one project-owned table, `ip vpn_gateway`. It never touches the
global ruleset, never flushes other tables, and never enables nftables.service.

Modes come from gateway_mode.py:
  VPN_EXIT  Clients may only leave through Happ (happ-xray). Everything else is dropped.
  ORDINARY  Clients may only leave through the router path (eth0). Everything else is dropped.
  BLOCK     Clients may not leave at all. Also used for any unknown mode (fail closed).

IPv4 only. IPv6 is not forwarded or NATed (see CLAUDE.md rule 4).

Usage:
  forward_policy.py MODE [CLIENT_IP ...]     print the ruleset (does not apply it)
"""
import ipaddress
import sys

# Project-owned nftables table. Only this table is ever written.
TABLE = "vpn_gateway"
# Happ's tunnel interface on the Pi. It exists only while Happ is running.
TUNNEL = "happ-xray"
# The Pi's normal, router-facing interface (the "ORDINARY" path).
ROUTER_IF = "eth0"
# Client addresses the rules cover. Dell's live address is .105 (VERIFIED 2026-11-22).
DEFAULT_CLIENTS = ("192.168.0.105", "192.168.0.185")  # dell, android


def validate_clients(clients):
    """Return the clients as normalized IPv4 strings. Anything else is refused, so a bad
    address can never be interpolated into the ruleset text."""
    if not clients:
        raise ValueError("no client addresses given")
    out = []
    for c in clients:
        try:
            addr = ipaddress.IPv4Address(c)
        except (ValueError, ipaddress.AddressValueError) as exc:
            raise ValueError(f"not an IPv4 address: {c!r}") from exc
        out.append(str(addr))
    return out


def build_ruleset(mode, clients):
    """Return the full nft script for `mode` as one string.

    The script starts with `add table` and `flush table` for our table only. Those two
    lines make the script safe to re-run: the table is created if missing and emptied
    before the new rules go in. Nothing outside the table is touched."""
    addrs = validate_clients(clients)
    # nft set syntax: "{ 192.168.0.105, 192.168.0.185 }" matches any listed client.
    match = "{ " + ", ".join(addrs) + " }"

    if mode == "VPN_EXIT":
        # Accept forwarded client traffic only if it leaves through the tunnel.
        # The drop rule after it catches everything else from the clients, so a client
        # cannot leak out of eth0 while Happ is on.
        forward_rules = [
            f'ip saddr {match} oifname "{TUNNEL}" accept',
            f"ip saddr {match} drop",
        ]
        # Rewrite the source to the Pi's tunnel address so the return traffic comes back.
        nat_rules = [f'ip saddr {match} oifname "{TUNNEL}" masquerade']
    elif mode == "ORDINARY":
        # Same shape as VPN_EXIT, but the only allowed exit is the router path.
        forward_rules = [
            f'ip saddr {match} oifname "{ROUTER_IF}" accept',
            f"ip saddr {match} drop",
        ]
        nat_rules = [f'ip saddr {match} oifname "{ROUTER_IF}" masquerade']
    else:
        # BLOCK, or any unknown mode: fail closed. No accept rule and no NAT.
        forward_rules = [f"ip saddr {match} drop"]
        nat_rules = []

    lines = [
        f"add table ip {TABLE}",
        f"flush table ip {TABLE}",
        f"table ip {TABLE} {{",
        # The forward chain uses policy accept so that traffic from other hosts (for
        # example the Pi's own traffic) is not affected. Only the client rules above drop.
        "  chain forward {",
        "    type filter hook forward priority 0; policy accept;",
    ]
    lines += [f"    {r}" for r in forward_rules]
    lines.append("  }")
    if nat_rules:
        # The NAT chain only exists when there is something to masquerade.
        lines += [
            "  chain postrouting {",
            "    type nat hook postrouting priority srcnat; policy accept;",
        ]
        lines += [f"    {r}" for r in nat_rules]
        lines.append("  }")
    lines.append("}")
    return "\n".join(lines) + "\n"


def main(argv):
    """Print the ruleset for MODE. Used by hand to inspect the output; does not apply it."""
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    mode = argv[1]
    clients = argv[2:] or list(DEFAULT_CLIENTS)
    try:
        sys.stdout.write(build_ruleset(mode, clients))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
