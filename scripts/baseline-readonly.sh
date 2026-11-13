#!/usr/bin/env bash
# Read-only baseline for the VPN gateway project. Changes nothing.
# Uses sudo only when already passwordless (sudo -n); otherwise marks root-only items as SKIPPED.
set -uo pipefail

SUDO=""
if sudo -n true 2>/dev/null; then SUDO="sudo -n"; fi

section() { printf '\n## %s\n' "$1"; }
run() { "$@" 2>&1 || echo "(exit $?)"; }

echo "# baseline $(date -Iseconds) host=$(hostname) user=$(whoami) root_helper=${SUDO:-none}"

section "os"
run uname -a
run sh -c 'grep -E "^(PRETTY_NAME)=" /etc/os-release'

section "identity and addresses"
run sh -c 'hostnamectl --static 2>/dev/null || hostname'
run ip -br addr
run sh -c 'ip -4 route show; echo "--- v6 default:"; ip -6 route show default'

section "policy rules"
run ip rule show

section "routing tables in use"
for t in $(ip rule show | grep -oE 'lookup [A-Za-z0-9_]+' | awk '{print $2}' | sort -u); do
  echo "-- table $t"
  run ip route show table "$t"
done

section "forwarding sysctls"
run sh -c 'echo "ip_forward=$(cat /proc/sys/net/ipv4/ip_forward)  ipv6_forwarding=$(cat /proc/sys/net/ipv6/conf/all/forwarding 2>/dev/null)"'

section "services"
run sh -c 'for s in happd ssh NetworkManager nftables; do printf "%s: enabled=%s active=%s\n" "$s" "$(systemctl is-enabled $s.service 2>/dev/null)" "$(systemctl is-active $s.service 2>/dev/null)"; done'

section "nftables"
if [ -n "$SUDO" ]; then
  run $SUDO nft list ruleset
else
  echo "SKIPPED (needs root): nft list ruleset"
fi

section "happ (names and socket only, no config values)"
run sh -c 'ls -l /tmp/happd.sock 2>/dev/null || echo "no /tmp/happd.sock"'
run sh -c 'happd_v=$(/opt/happ/bin/happd --version 2>/dev/null | head -1); echo "happd: ${happd_v:-unknown}"'
if [ -n "$SUDO" ]; then
  run $SUDO /opt/happ/bin/happ-diag
else
  echo "SKIPPED (needs root): happ-diag"
fi
