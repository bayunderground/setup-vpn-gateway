#!/usr/bin/env bash
set -Eeuo pipefail

# setup-vpn-gateway-alpha.sh
# Alpha 0.1: read-only Happ state probe for the Raspberry Pi gateway project.
# This deliberately does NOT change routes, firewall rules, sysctls, or services.
# Run on the Raspberry Pi as an ordinary user:
#   bash setup-vpn-gateway-alpha.sh [status]

VERSION="0.1.0-alpha"
VPN_IF="happ-xray"
HAPP_SERVICE="happd.service"

usage() {
    cat <<'EOF'
Usage: setup-vpn-gateway-alpha.sh [status|--help]

Read-only diagnostic for the Raspberry Pi Happ gateway.

It reports whether the observed Happ TUN is active. It does not install or
configure gateway forwarding, NAT, nftables, policy routing, or client routes.
EOF
}

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

[[ $# -le 1 ]] || { usage >&2; exit 2; }
case "${1:-status}" in
    --help|-h|help) usage; exit 0 ;;
    status) ;;
    *) usage >&2; exit 2 ;;
esac

for cmd in ip systemctl pgrep; do
    command -v "$cmd" >/dev/null 2>&1 || die "Required command not found: $cmd"
done

printf 'VPN gateway alpha diagnostic %s\n' "$VERSION"
printf 'Timestamp: %s\n' "$(date --iso-8601=seconds)"
printf 'Host: %s\n\n' "$(hostname)"

if systemctl is-active --quiet "$HAPP_SERVICE"; then
    SERVICE_STATE="active"
else
    SERVICE_STATE="$(systemctl is-active "$HAPP_SERVICE" 2>/dev/null || true)"
fi

if ip link show dev "$VPN_IF" >/dev/null 2>&1; then
    TUN_PRESENT=yes
else
    TUN_PRESENT=no
fi

if pgrep -x xray >/dev/null 2>&1; then
    XRAY_PRESENT=yes
else
    XRAY_PRESENT=no
fi

if ip -4 route show table main default 2>/dev/null | grep -Eq "^default dev ${VPN_IF}([[:space:]]|$)"; then
    VPN_DEFAULT=yes
else
    VPN_DEFAULT=no
fi

printf '%-22s %s\n' "Happ service:" "$SERVICE_STATE"
printf '%-22s %s\n' "TUN interface ($VPN_IF):" "$TUN_PRESENT"
printf '%-22s %s\n' "xray process:" "$XRAY_PRESENT"
printf '%-22s %s\n' "Main default via TUN:" "$VPN_DEFAULT"

if [[ "$TUN_PRESENT" == yes && "$XRAY_PRESENT" == yes && "$VPN_DEFAULT" == yes ]]; then
    OBSERVED_STATE="TUNNEL_ACTIVE"
    printf '\nObserved state: %s\n' "$OBSERVED_STATE"
    printf 'Meaning: Happ TUN is present and selected as the Pi main default route.\n'
elif [[ "$TUN_PRESENT" == no && "$XRAY_PRESENT" == no && "$VPN_DEFAULT" == no ]]; then
    OBSERVED_STATE="TUNNEL_ABSENT"
    printf '\nObserved state: %s\n' "$OBSERVED_STATE"
    printf 'Meaning: no active Happ TUN was observed. This does NOT prove Happ is disabled.\n'
else
    OBSERVED_STATE="INCONSISTENT_OR_TRANSITIONING"
    printf '\nObserved state: %s\n' "$OBSERVED_STATE"
    printf 'Meaning: interface, process, and route indicators do not agree.\n'
fi

printf '\nIPv4 interfaces:\n'
ip -br -4 addr
printf '\nMain IPv4 default routes:\n'
ip -4 route show table main default
printf '\nActive NetworkManager connections:\n'
if command -v nmcli >/dev/null 2>&1; then
    nmcli -t -f NAME,TYPE,DEVICE connection show --active 2>/dev/null || true
else
    echo "nmcli not installed"
fi

cat <<'EOF'

IMPORTANT:
- happd.service is a persistent control daemon; its running state is not the
  Happ VPN enabled/disabled signal.
- TUNNEL_ABSENT currently conflates "Happ disabled" with "Happ enabled but
  disconnected/failed". Do not use this alpha probe to control a client
  gateway or to claim that the kill switch is safe.
- This script is read-only. No network configuration has been modified.
EOF
