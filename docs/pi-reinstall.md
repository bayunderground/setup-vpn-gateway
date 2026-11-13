# Raspberry Pi reinstall checklist (pi5home)

Target: Raspberry Pi 5, Raspberry Pi OS (Debian 13 trixie, aarch64), hostname `pi5home`.
Run commands as user `bliss` unless marked otherwise. Commands prefixed with `sudo` will prompt for the password.

Status of each step is noted so you know what the project expects. Nothing here enables the gateway or firewall.

## 1. Base system and packages

```bash
sudo apt-get update
sudo apt-get full-upgrade -y
sudo apt-get install -y git nftables iproute2 python3 network-manager openssh-server curl
```

- `nftables` is installed but must stay **disabled** (see step 5).

## 2. Hostname

```bash
sudo hostnamectl set-hostname pi5home
sudo sed -i 's/^127\.0\.1\.1.*/127.0.1.1\tpi5home/' /etc/hosts
hostnamectl --static
```

Expected output: `pi5home`.

## 3. SSH access from Dell

The public key used from Dell is `bliss@localhost.localdomain` (RSA, SHA256:GGx4GRx/e2zBDgbxxPB2x97cR+VrTUkMAER9rt4fy6Y).

From **Dell**, copy it to the Pi once (asks for the password):

```bash
ssh-copy-id -i ~/.ssh/id_rsa.pub bliss@<PI_IP>
```

Then verify on Dell without a password:

```bash
ssh bliss@<PI_IP> 'hostname; whoami'
```

Keep `sshd` enabled:

```bash
sudo systemctl enable --now ssh
```

Note: the current Pi `authorized_keys` contains this key twice. Harmless; remove the duplicate only if you want tidiness.

## 4. NetworkManager and Wi-Fi

```bash
sudo systemctl enable --now NetworkManager
nmcli -t -f NAME,TYPE,DEVICE connection show
```

Expected Wi-Fi profile: `TP-Link_42SN_5G` on `wlan0`. Confirm the Pi gets `192.168.0.118/24` (or record the new address and update the docs).

## 5. nftables: keep disabled

Do **not** run `systemctl enable nftables`. The stock `/etc/nftables.conf` begins with `flush ruleset`, which would wipe every firewall rule on the Pi. The project will own its own table later.

Verify:

```bash
systemctl is-enabled nftables.service    # expected: disabled
systemctl is-active nftables.service     # expected: inactive
```

## 6. Clone the project

```bash
git clone https://github.com/bayunderground/setup-vpn-gateway.git ~/setup-vpn-gateway
cd ~/setup-vpn-gateway
git log --oneline -1
```

Then run the read-only diagnostic:

```bash
bash ~/setup-vpn-gateway/setup-vpn-gateway-alpha.sh
```

## 7. Happ 4.7.2 (manual)

Reinstall Happ using its own installer. It installs:
- `/opt/happ/bin/happd`
- `happd.service` (enabled, root, `Restart=always`)
- `/tmp/happd.sock` and `/var/log/happd.log`

Verify afterward:

```bash
systemctl is-enabled happd.service
systemctl is-active happd.service
/opt/happ/bin/happd --version   # expected: 4.7.2 (if the binary supports it)
```

Do not run `/opt/happ/bin/happ-diag --repair`. It restarts `happd`.

## 8. sudo for read-only diagnostics (optional)

Lets the diagnostics read nftables, sysctls, and happ-diag without typing a password each time. Only run this if you want that convenience.

```bash
sudo tee /etc/sudoers.d/vpn-gateway-readonly >/dev/null <<'EOF'
bliss ALL=(root) NOPASSWD: /opt/happ/bin/happ-diag, /usr/sbin/nft list ruleset, /usr/sbin/sysctl net.ipv4.ip_forward net.ipv6.conf.all.forwarding
EOF
sudo chmod 0440 /etc/sudoers.d/vpn-gateway-readonly
sudo visudo -c
```

Remove it later with `sudo rm /etc/sudoers.d/vpn-gateway-readonly`.

## 9. Verification after reinstall

```bash
hostnamectl --static
ip -br addr
ip rule show
ip route show
systemctl is-active ssh NetworkManager happd.service
systemctl is-enabled nftables.service
```

Expected:
- hostname `pi5home`
- Wi-Fi on `wlan0`
- default route via `192.168.0.1` (or via the Happ TUN if Happ is ON)
- `nftables.service` disabled

## Rollback

- Hostname: `sudo hostnamectl set-hostname raspberrypi` and restore `/etc/hosts`.
- Packages: `sudo apt-get remove --purge nftables` (only if you do not want it).
- sudoers: `sudo rm /etc/sudoers.d/vpn-gateway-readonly`.
