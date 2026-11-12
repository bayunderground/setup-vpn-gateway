#!/usr/bin/env bash
set -Eeuo pipefail

# Ubuntu VPN gateway for one Android device, using Happ's existing TUN route.
# Run from the Ubuntu desktop/console: sudo bash setup-android-vpn-gateway.sh

CONNECTION="TP-Link_42SN_5G"
LAN_IF="wlp8s0"
LAN_IP_CIDR="192.168.0.105/24"
LAN_IP="192.168.0.105"
LAN_GATEWAY="192.168.0.1"
ANDROID_IP="192.168.0.185"
ANDROID_MAC="f0:35:75:23:34:62"
VPN_IF="tun0"
VPN_TABLE="2022"
RULE_PRIORITY="8000"

INSTALLER="/usr/local/sbin/android-vpn-share"
DISPATCHER="/etc/NetworkManager/dispatcher.d/90-android-vpn-share"
SERVICE="/etc/systemd/system/android-vpn-share.service"
TIMER="/etc/systemd/system/android-vpn-share.timer"
SYSCTL_CONF="/etc/sysctl.d/90-android-vpn-share.conf"

if [[ "${EUID}" -ne 0 ]]; then
    echo "Please run as root: sudo bash $0"
    exit 1
fi

if ! command -v nmcli >/dev/null 2>&1; then
    echo "NetworkManager/nmcli not found. This script expects NetworkManager."
    exit 1
fi

if ! nmcli -t -f NAME connection show | grep -Fxq "$CONNECTION"; then
    echo "Wi-Fi connection '$CONNECTION' was not found."
    echo "Available connections:"
    nmcli -t -f NAME,TYPE connection show
    exit 1
fi

echo "This will set $CONNECTION to $LAN_IP_CIDR, gateway $LAN_GATEWAY."
echo "Reactivating Wi-Fi may briefly disconnect the network and Happ VPN."
read -r -p "Continue? [y/N] " answer
[[ "$answer" =~ ^[Yy]$ ]] || exit 0

# Install the idempotent apply script.
install -d -m 0755 /usr/local/sbin
cat > "$INSTALLER" <<'APPLY_SCRIPT'
#!/usr/bin/env bash
set -Eeuo pipefail

LAN_IF="wlp8s0"
ANDROID_IP="192.168.0.185"
ANDROID_MAC="f0:35:75:23:34:62"
VPN_IF="tun0"
VPN_TABLE="2022"
RULE_PRIORITY="8000"
CHAIN="ANDROID_VPN_OUT"

# Serialize dispatcher, timer, and manual invocations.
exec 9>/run/lock/android-vpn-share.lock
flock 9

IPT="$(command -v iptables)"
IP6T="$(command -v ip6tables || true)"

vpn_up() { ip link show "$VPN_IF" >/dev/null 2>&1; }

# Insert a rule at the top of a chain only when it is missing. Live rules are
# never flushed, so the kill-switch is never left open between timer runs.
add_once() {
    local ipt="$1" chain="$2"
    shift 2
    "$ipt" -w -C "$chain" "$@" 2>/dev/null || "$ipt" -w -I "$chain" 1 "$@"
}

# Keep IPv4 forwarding enabled (also restored by sysctl.d at boot).
sysctl -w net.ipv4.ip_forward=1 >/dev/null

# The policy rule sends packets sourced by Android through Happ's table.
# Happ owns the routes inside table 2022; this script does not alter them.
if ! ip -4 rule show | grep -Eq "^${RULE_PRIORITY}:.*from ${ANDROID_IP}(/32)? lookup ${VPN_TABLE}([[:space:]]|$)"; then
    ip -4 rule add priority "$RULE_PRIORITY" from "${ANDROID_IP}/32" lookup "$VPN_TABLE"
fi

# Dedicated chain: Android may be forwarded only out through tun0.
# If routing falls back to Wi-Fi or another interface, the packet is dropped.
"$IPT" -w -N "$CHAIN" 2>/dev/null || true

# Dedicated chain: Android may be forwarded only out through tun0.
# If routing falls back to Wi-Fi or another interface, the packet is dropped.
# ACCEPT is inserted above DROP, so DROP stays last.
if vpn_up; then
    add_once "$IPT" "$CHAIN" -o "$VPN_IF" -j ACCEPT
else
    while "$IPT" -w -D "$CHAIN" -o "$VPN_IF" -j ACCEPT 2>/dev/null; do :; done
fi
if ! "$IPT" -w -C "$CHAIN" -j DROP 2>/dev/null; then
    "$IPT" -w -A "$CHAIN" -j DROP
fi

# Jump for Android-originated forwarded IPv4 packets.
add_once "$IPT" FORWARD -i "$LAN_IF" -s "${ANDROID_IP}/32" -j "$CHAIN"

# Allow only established return traffic from the VPN to Android.
RETURN_RULE=(-i "$VPN_IF" -o "$LAN_IF" -d "${ANDROID_IP}/32"
             -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT)
if vpn_up; then
    add_once "$IPT" FORWARD "${RETURN_RULE[@]}"
fi

# NAT Android IPv4 traffic as it leaves through the VPN.
if vpn_up; then
    NAT_RULE=(-s "${ANDROID_IP}/32" -o "$VPN_IF" -j MASQUERADE)
    if ! "$IPT" -w -t nat -C POSTROUTING "${NAT_RULE[@]}" 2>/dev/null; then
        "$IPT" -w -t nat -A POSTROUTING "${NAT_RULE[@]}"
    fi
fi

# If IPv6 packets are routed through this PC, drop them rather than forward
# them outside the IPv4-only VPN tunnel. This does NOT block IPv6 sent directly
# to the Wi-Fi router; see the Android instructions about router IPv6/RA.
if [[ -n "$IP6T" ]]; then
    IPV6_RULE=(-i "$LAN_IF" -m mac --mac-source "$ANDROID_MAC" -j DROP)
    if ! "$IP6T" -w -C FORWARD "${IPV6_RULE[@]}" 2>/dev/null; then
        "$IP6T" -w -I FORWARD 1 "${IPV6_RULE[@]}"
    fi
fi
APPLY_SCRIPT
chmod 0755 "$INSTALLER"

# Make IPv4 forwarding survive reboot.
cat > "$SYSCTL_CONF" <<'SYSCTL'
net.ipv4.ip_forward=1
SYSCTL
chmod 0644 "$SYSCTL_CONF"
sysctl --system >/dev/null

# Set Ubuntu's Wi-Fi address statically.
nmcli connection modify "$CONNECTION" \
    ipv4.method manual \
    ipv4.addresses "$LAN_IP_CIDR" \
    ipv4.gateway "$LAN_GATEWAY" \
    ipv4.dns "192.168.0.1 1.1.1.1" \
    ipv4.ignore-auto-dns yes \
    802-11-wireless.powersave 2

# Install a NetworkManager dispatcher hook for Wi-Fi/VPN link activation.
install -d -m 0755 /etc/NetworkManager/dispatcher.d
cat > "$DISPATCHER" <<'DISPATCHER_SCRIPT'
#!/bin/sh
IFACE="${1:-}"
ACTION="${2:-}"
case "$ACTION" in
    up|down|dhcp4-change)
        if [ "$IFACE" = "wlp8s0" ] || [ "$IFACE" = "tun0" ]; then
            /usr/local/sbin/android-vpn-share apply
        fi
        ;;
    vpn-up|vpn-down)
        /usr/local/sbin/android-vpn-share apply
        ;;
esac
exit 0
DISPATCHER_SCRIPT
chmod 0755 "$DISPATCHER"

# Systemd service: apply rules at boot.
cat > "$SERVICE" <<'UNIT'
[Unit]
Description=Share Happ VPN with Android over Wi-Fi
Wants=NetworkManager.service
After=NetworkManager.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/android-vpn-share apply
UNIT

# Timer periodically repairs rules if Happ or another network component flushes them.
cat > "$TIMER" <<'UNIT'
[Unit]
Description=Periodically ensure Android VPN sharing rules

[Timer]
OnBootSec=20s
OnUnitActiveSec=30s
AccuracySec=5s
Unit=android-vpn-share.service

[Install]
WantedBy=timers.target
UNIT

systemctl daemon-reload
systemctl enable --now android-vpn-share.timer

echo
echo "Applying static Wi-Fi configuration (this may briefly disconnect Wi-Fi)..."
nmcli connection up "$CONNECTION"

echo
echo "Applying VPN-sharing rules..."
"$INSTALLER" apply

echo
echo "Installation complete."
echo
echo "Ubuntu Wi-Fi:"
ip -br addr show "$LAN_IF"
echo
echo "Policy rule:"
ip -4 rule show | grep -E "^${RULE_PRIORITY}:|^"
echo
echo "Timer:"
systemctl --no-pager --full status android-vpn-share.timer || true
echo
echo "IMPORTANT:"
echo "  1. Reserve $LAN_IP for this PC in your router's DHCP settings."
echo "     Ubuntu Wi-Fi MAC: a4:34:d9:24:57:2f"
echo "  2. Reconnect Happ if it did not reconnect after Wi-Fi was reactivated."
echo "  3. Configure Android as described in the accompanying instructions."
echo "  4. The setup shares IPv4 only; Android IPv6 forwarding is blocked to prevent bypass."
