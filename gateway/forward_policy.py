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

TABLE = "vpn_gateway"
TUNNEL = "happ-xray"
ROUTER_IF = "eth0"
DEFAULT_CLIENTS = ("192.168.0.103", "192.168.0.185")  # dell, android


def validate_clients(clients):
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
    addrs = validate_clients(clients)
    match = "{ " + ", ".join(addrs) + " }"

    if mode == "VPN_EXIT":
        forward_rules = [
            f'ip saddr {match} oifname "{TUNNEL}" accept',
            f"ip saddr {match} drop",
        ]
        nat_rules = [f'ip saddr {match} oifname "{TUNNEL}" masquerade']
    elif mode == "ORDINARY":
        forward_rules = [
            f'ip saddr {match} oifname "{ROUTER_IF}" accept',
            f"ip saddr {match} drop",
        ]
        nat_rules = [f'ip saddr {match} oifname "{ROUTER_IF}" masquerade']
    else:
        # BLOCK, or any unknown mode: fail closed.
        forward_rules = [f"ip saddr {match} drop"]
        nat_rules = []

    lines = [
        f"add table ip {TABLE}",
        f"flush table ip {TABLE}",
        f"table ip {TABLE} {{",
        "  chain forward {",
        "    type filter hook forward priority 0; policy accept;",
    ]
    lines += [f"    {r}" for r in forward_rules]
    lines.append("  }")
    if nat_rules:
        lines += [
            "  chain postrouting {",
            "    type nat hook postrouting priority srcnat; policy accept;",
        ]
        lines += [f"    {r}" for r in nat_rules]
        lines.append("  }")
    lines.append("}")
    return "\n".join(lines) + "\n"


def main(argv):
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
