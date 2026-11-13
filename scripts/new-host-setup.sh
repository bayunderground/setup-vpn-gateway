#!/usr/bin/env bash
# new-host-setup.sh: prepare a Raspberry Pi (Raspberry Pi OS / Debian) for this project.
#
# Run as your normal user (not root). It asks for your sudo password once:
#   bash scripts/new-host-setup.sh
#   PI_HOSTNAME=pi5home bash scripts/new-host-setup.sh     # also set the hostname
#   bash scripts/new-host-setup.sh --uninstall              # remove what this script added
#
# It DOES:
#   - install packages
#   - keep nftables disabled (its stock config erases all firewall rules)
#   - check that Happ is installed (Happ is installed separately, not by this script)
#   - clone or update the project repo
#   - install a read-only sudo rule for diagnostics
#   - install a boot-time service that writes a read-only baseline report
#
# It does NOT: change routing, firewall rules, IP forwarding, Happ, or start any gateway.
set -Eeuo pipefail

REPO_URL="https://github.com/bayunderground/setup-vpn-gateway.git"
REPO_DIR="${REPO_DIR:-$HOME/setup-vpn-gateway}"
LOG_DIR=/var/log/vpn-gateway
UNIT=vpn-gateway-boot-baseline.service
UNIT_PATH="/etc/systemd/system/$UNIT"
SUDOERS=/etc/sudoers.d/vpn-gateway-readonly
PACKAGES=(git nftables iproute2 python3 network-manager openssh-server curl)

say()  { printf '\n== %s\n' "$*"; }
info() { printf '   %s\n' "$*"; }
die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

uninstall() {
    say "Uninstall (only files this script created)"
    sudo systemctl disable --now "$UNIT" 2>/dev/null || true
    sudo rm -f "$UNIT_PATH"
    sudo systemctl daemon-reload
    sudo rm -f "$SUDOERS"
    info "removed $UNIT_PATH and $SUDOERS"
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

say "7. Boot-time read-only baseline report"
sudo install -d -m 0755 "$LOG_DIR"
sudo tee "$UNIT_PATH" >/dev/null <<EOF
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
sudo systemctl enable --now "$UNIT"
info "enabled $UNIT (runs now and at every boot)"
info "result: $(systemctl show -p Result --value "$UNIT")"
info "report: $LOG_DIR/boot-baseline.log"

say "Done"
if [[ $MISSING_HAPP -eq 1 ]]; then
    info "NEXT: install Happ, then run this script again."
fi
info "The gateway itself is NOT installed or running. It needs approval (see docs/PROJECT-DOCUMENTARY-2026-11-14.md)."
