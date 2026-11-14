> **Superseded (2026-11-14).** Use `scripts/new-host-setup.sh` for install and `--uninstall` for removal. See `docs/LLM-HANDOVER.md`.

# Commands for a new host (after reinstall)

Consolidated command list for rebuilding the Pi (`pi5home`), checking Dell, and checking Android. Run each block on the machine named in its heading. Commands marked **root** prompt for the sudo password.

Prerequisite: the repo commits must be pushed to GitHub, or the scripts copied to the host by hand. Until then, `git pull` will not bring `scripts/` to a host.

## 1. Pi (`pi5home`): base system (root)

```bash
sudo apt-get update
sudo apt-get full-upgrade -y
sudo apt-get install -y git nftables iproute2 python3 network-manager openssh-server curl
sudo systemctl enable --now ssh NetworkManager
```

## 2. Pi: hostname (root)

```bash
sudo hostnamectl set-hostname pi5home
sudo sed -i 's/^127\.0\.1\.1.*/127.0.1.1\tpi5home/' /etc/hosts
hostnamectl --static
getent hosts pi5home
```

## 3. Pi: keep nftables disabled

Do NOT enable it. The stock `/etc/nftables.conf` starts with `flush ruleset`.

```bash
systemctl is-enabled nftables.service    # expected: disabled
systemctl is-active nftables.service     # expected: inactive
```

## 4. Pi: SSH key from Dell (run on Dell)

```bash
ssh-copy-id -i ~/.ssh/id_rsa.pub bliss@<PI_IP>
ssh bliss@<PI_IP> 'hostname; whoami'
```

Dell's key fingerprint at time of writing: `SHA256:GGx4GRx/e2zBDgbxxPB2x97cR+VrTUkMAER9rt4fy6Y`.

## 5. Pi: NetworkManager Wi-Fi

```bash
nmcli -t -f NAME,TYPE,DEVICE connection show
ip -br addr show wlan0
```

Expected: profile `TP-Link_42SN_5G` on `wlan0`, address `192.168.0.118/24`.

## 6. Pi: sudo for read-only diagnostics (root, optional)

```bash
sudo tee /etc/sudoers.d/vpn-gateway-readonly >/dev/null <<'EOF'
bliss ALL=(root) NOPASSWD: /opt/happ/bin/happ-diag, /usr/sbin/nft list ruleset, /usr/sbin/sysctl net.ipv4.ip_forward net.ipv6.conf.all.forwarding
EOF
sudo chmod 0440 /etc/sudoers.d/vpn-gateway-readonly
sudo visudo -c
```

Remove later with `sudo rm /etc/sudoers.d/vpn-gateway-readonly`.

## 7. Pi: Happ 4.7.2 (manual install, then verify)

Install Happ with its own installer. Then verify:

```bash
systemctl is-enabled happd.service
systemctl is-active happd.service
/opt/happ/bin/happd --version
```

Never run `/opt/happ/bin/happ-diag --repair`; it restarts `happd`.

## 8. Pi: clone the project and run the read-only baseline

```bash
git clone https://github.com/bayunderground/setup-vpn-gateway.git ~/setup-vpn-gateway
cd ~/setup-vpn-gateway && git pull --ff-only
bash ~/setup-vpn-gateway/setup-vpn-gateway-alpha.sh
bash ~/setup-vpn-gateway/scripts/baseline-readonly.sh
```

If `scripts/baseline-readonly.sh` is missing, the GitHub copy is behind the local commits. Push first, or copy the file from Dell:

```bash
scp ~/setup-vpn-gateway/scripts/baseline-readonly.sh bliss@<PI_IP>:~/setup-vpn-gateway/scripts/
```

## 9. Pi: Happ OFF / ON test

1. Set Happ OFF in the GUI.
2. Run `bash ~/setup-vpn-gateway/scripts/baseline-readonly.sh`.
3. Set Happ ON and wait for "connected".
4. Run the same script again.

Expected OFF: no `happ-xray`, no managed xray process, default only via `wlan0`.
Expected ON: `happ-xray` UP, one managed `xray-core`, `default dev happ-xray metric 1`.

## 10. Dell (`dell`): read-only checks

```bash
ip rule show
ip route show table 2022
ip -br addr show tun0
ip route show default
cat /proc/sys/net/ipv4/ip_forward
systemctl is-active happd.service
/opt/happ/bin/happd --version
```

Dell-specific facts at time of writing: stale rule `8000: from 192.168.0.185 lookup 2022`; Happ `2.17.1`.

## 11. Dell: is Android still routed through Dell? (root for tcpdump)

```bash
ip neigh show 192.168.0.185
ping -c3 -W2 192.168.0.185
sudo timeout 30 tcpdump -ni wlp8s0 host 192.168.0.185 -c 20
```

Do not use `/proc/net/nf_conntrack`; it is not loaded on Dell.

## 12. Dell: cleanup (HOLD, root)

Only after Android's gateway is confirmed and the user approves:

```bash
sudo ip rule del priority 8000
ip rule show | grep -E "^8000:" || echo "rule 8000 removed"
```

## 13. Android: gateway check (optional, requires USB debugging on Dell)

```bash
adb devices
adb shell ip -4 addr show wlan0
adb shell ip -4 route show
adb shell dumpsys connectivity | grep -iE "gateway|dnses|mWifi" | head -20
```

Without `adb`, read IP, gateway, prefix, DNS, and static/DHCP from Android's Wi-Fi settings.

## Rollback

- Hostname (original name before this project was `raspberrypi`): `sudo hostnamectl set-hostname raspberrypi`, then restore `/etc/hosts`.
- Sudoers: `sudo rm /etc/sudoers.d/vpn-gateway-readonly`.
- Dell rule 8000 (if removed by mistake): `sudo ip rule add priority 8000 from 192.168.0.185 lookup 2022`.

## Dell: allow the Android capture without a password (root, optional)

Gives `bliss` NOPASSWD for exactly one tcpdump command (fixed interface, host, and count). Nothing else is granted.

```bash
sudo tee /etc/sudoers.d/vpn-gateway-tcpdump >/dev/null <<'SUDOERS'
bliss ALL=(root) NOPASSWD: /usr/bin/tcpdump -ni wlp8s0 host 192.168.0.185 -c 20
SUDOERS
sudo chmod 0440 /etc/sudoers.d/vpn-gateway-tcpdump
sudo visudo -c
```

Then the capture can run without a password:

```bash
timeout 30 sudo -n /usr/bin/tcpdump -ni wlp8s0 host 192.168.0.185 -c 20
```

Remove after testing:

```bash
sudo rm /etc/sudoers.d/vpn-gateway-tcpdump
```
