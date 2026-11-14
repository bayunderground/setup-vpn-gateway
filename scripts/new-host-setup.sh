#!/usr/bin/env bash
# new-host-setup.sh: prepare a Raspberry Pi (Raspberry Pi OS / Debian) for this project.
#
# Run as your normal user (not root). It asks for your sudo password once:
#   bash scripts/new-host-setup.sh
#   PI_HOSTNAME=pi5home bash scripts/new-host-setup.sh     # also set the hostname
#   bash scripts/new-host-setup.sh --uninstall              # remove what this script added
#
# It DOES:
#   - install packages (including strace, used by the Happ watcher)
#   - keep nftables disabled (its stock config erases all firewall rules)
#   - check that Happ is installed (Happ is installed separately, not by this script)
#   - clone or update the project repo
#   - install a read-only sudo rule for diagnostics
#   - install and start the Happ GUI watcher at boot (read-only, publishes state)
#   - install a boot-time read-only baseline report
#
# It does NOT: change routing, firewall rules, IP forwarding, or Happ settings,
# and it does NOT start the gateway controller (its rules are not approved yet).
set -Eeuo pipefail

REPO_URL="https://github.com/bayunderground/setup-vpn-gateway.git"
REPO_DIR="${REPO_DIR:-$HOME/setup-vpn-gateway}"
LIB_DIR=/usr/local/lib/vpn-gateway
LOG_DIR=/var/log/vpn-gateway
SUDOERS=/etc/sudoers.d/vpn-gateway-readonly
WATCH_UNIT=vpn-gateway-watch.service
BASELINE_UNIT=vpn-gateway-boot-baseline.service
PACKAGES=(git nftables iproute2 python3 network-manager openssh-server curl strace)

say()  { printf '\n== %s\n' "$*"; }
info() { printf '   %s\n' "$*"; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

uninstall() {
    say "Uninstall (only files this script created)"
    for unit in "$WATCH_UNIT" "$BASELINE_UNIT"; do
        sudo systemctl disable --now "$unit" 2>/dev/null || true
        sudo rm -f "/etc/systemd/system/$unit"
    done
    sudo systemctl daemon-reload
    sudo rm -rf "$LIB_DIR"
    sudo rm -f "$SUDOERS"
    info "removed watcher and baseline units, $LIB_DIR, and $SUDOERS"
    info "kept logs in $LOG_DIR and the repo in $REPO_DIR"
}

[[ $EUID -ne 0 ]] || die "run as your normal user, not root. The script calls sudo where needed."
command -v sudo >/dev/null || die "sudo is required"
command -v systemctl >/dev/null || die "systemd is required"

if [[ "${1:-}" == "--uninstall" ]]; then
    uninstall
    exit 0
fi

sudo -v

say "1. Packages"
sudo apt-get update -qq --allow-releaseinfo-change ||
    info "WARNING: apt update reported errors (often an unrelated third-party repo). Continuing with the existing package lists."
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${PACKAGES[@]}"
info "installed: ${PACKAGES[*]}"

say "2. Hostname"
if [[ -n "${PI_HOSTNAME:-}" ]]; then
    sudo hostnamectl set-hostname "$PI_HOSTNAME"
    if grep -qE '^127\.0\.1\.1' /etc/hosts; then
        sudo sed -i -E "s/^127\.0\.1\.1.*/127.0.1.1\t$PI_HOSTNAME/" /etc/hosts
    else
        printf '127.0.1.1\t%s\n' "$PI_HOSTNAME" | sudo tee -a /etc/hosts >/dev/null
    fi
fi
info "hostname: $(hostnamectl --static)"

say "3. nftables stays disabled"
sudo systemctl disable nftables.service 2>/dev/null || true
if systemctl is-active --quiet nftables.service; then
    info "WARNING: nftables.service is running. Not stopping it here. Check: sudo nft list ruleset"
fi
info "enabled=$(systemctl is-enabled nftables.service 2>/dev/null || true) active=$(systemctl is-active nftables.service 2>/dev/null || true)"

say "4. Happ"
MISSING_HAPP=0
if systemctl cat happd.service >/dev/null 2>&1; then
    info "happd.service enabled=$(systemctl is-enabled happd.service 2>/dev/null || true) active=$(systemctl is-active happd.service 2>/dev/null || true)"
    info "version: $(/opt/happ/bin/happd --version 2>/dev/null | head -1 || echo unknown)"
else
    MISSING_HAPP=1
    info "Happ is NOT installed. Install it with its own installer, then run this script again."
fi

say "5. Project repo"
if [[ -d "$REPO_DIR/.git" ]]; then
    git -C "$REPO_DIR" pull --ff-only
else
    git clone "$REPO_URL" "$REPO_DIR"
fi
info "commit: $(git -C "$REPO_DIR" log --oneline -1)"

say "6. Read-only sudo rule (diagnostics without a password)"
RULE_FILE=$(mktemp)
trap 'rm -f "$RULE_FILE"' EXIT
printf '%s ALL=(root) NOPASSWD: /opt/happ/bin/happ-diag, /usr/sbin/nft list ruleset, /usr/sbin/sysctl net.ipv4.ip_forward net.ipv6.conf.all.forwarding\n' "$(id -un)" > "$RULE_FILE"
sudo visudo -cf "$RULE_FILE" >/dev/null || die "generated sudo rule failed visudo check"
sudo install -m 0440 -o root -g root "$RULE_FILE" "$SUDOERS"
info "installed $SUDOERS"

say "7. Happ GUI watcher (runs at boot, read-only)"
sudo install -d -m 0755 -o root -g root "$LIB_DIR"
for file in happ_watch.py gateway_mode.py; do
    sudo install -m 0644 -o root -g root "$REPO_DIR/gateway/$file" "$LIB_DIR/$file"
done
info "installed $LIB_DIR/happ_watch.py and gateway_mode.py"
sudo tee "/etc/systemd/system/$WATCH_UNIT" >/dev/null <<EOF
[Unit]
Description=VPN gateway: Happ GUI intent watcher (read-only, fail closed)
After=happd.service
Wants=happd.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 $LIB_DIR/happ_watch.py
Restart=always
RestartSec=5
RuntimeDirectory=vpn-gateway
RuntimeDirectoryMode=0755

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now "$WATCH_UNIT"
sleep 3
info "enabled $WATCH_UNIT: active=$(systemctl is-active "$WATCH_UNIT")"
info "state: $(cat /run/vpn-gateway/state.json 2>/dev/null || echo 'not published yet')"

say "8. Boot-time read-only baseline report"
sudo install -d -m 0755 "$LOG_DIR"
sudo tee "/etc/systemd/system/$BASELINE_UNIT" >/dev/null <<EOF
[Unit]
Description=VPN gateway read-only baseline report (changes nothing)
After=network-online.target happd.service
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/bin/bash $REPO_DIR/scripts/baseline-readonly.sh
StandardOutput=append:$LOG_DIR/boot-baseline.log
StandardError=append:$LOG_DIR/boot-baseline.log

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now "$BASELINE_UNIT"
info "enabled $BASELINE_UNIT (runs now and at every boot)"
info "result: $(systemctl show -p Result --value "$BASELINE_UNIT")"
info "report: $LOG_DIR/boot-baseline.log"

say "Done"
if [[ $MISSING_HAPP -eq 1 ]]; then
    info "NEXT: install Happ, then run this script again. Until then the watcher reports UNKNOWN and clients stay blocked."
fi
info "The gateway controller is NOT applying any firewall or routing rules yet. Its decision can be checked with: python3 $LIB_DIR/gateway_mode.py"
