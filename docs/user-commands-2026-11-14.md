# Commands to run — 2026-11-14

Read-only unless marked otherwise. Run the commands on the machine named in each heading.

## On the Pi (`pi5home`, 192.168.0.118)

Update the repo and run the read-only baseline (safe to repeat):

```bash
cd ~/setup-vpn-gateway && git pull --ff-only
bash ~/setup-vpn-gateway/scripts/baseline-readonly.sh
```

Check the Happ daemon and TUN directly:

```bash
systemctl is-active happd.service
ip -br link show happ-xray 2>&1
ip route show default
```

Do NOT run:

```bash
/opt/happ/bin/happ-diag --repair     # restarts happd
sudo systemctl enable nftables       # stock config runs "flush ruleset"
```

## On Dell (`dell`, 192.168.0.105)

Read-only checks (safe):

```bash
ip rule show
ip route show table 2022
ip -br addr show tun0
ip route show default
cat /proc/sys/net/ipv4/ip_forward
systemctl is-active happd.service
/opt/happ/bin/happd --version 2>/dev/null || echo "no happd --version"
```

Check whether Android is currently using Dell's forwarded path (read-only):

```bash
grep "192.168.0.185" /proc/net/nf_conntrack | head
ip neigh show 192.168.0.185
ping -c3 -W2 192.168.0.185
```

HOLD — do not run until Android's gateway is confirmed AND you approve:

```bash
sudo ip rule del priority 8000
```

Verify afterwards (read-only):

```bash
ip rule show | grep -E "^8000:" || echo "rule 8000 removed"
```

## On Android (optional, requires USB debugging and `adb` on Dell)

Read-only (replace nothing; run from Dell):

```bash
adb devices
adb shell ip -4 addr show wlan0
adb shell ip -4 route show
adb shell dumpsys connectivity | grep -iE "gateway|dnses|mWifi" | head -20
```

If you don't use `adb`, read the same values from Android's Wi-Fi settings (IP, gateway, prefix, DNS, static/DHCP).

## Not available yet

- Happ intent marker file: not implemented, no command yet.
- Dell Happ uninstall: wait for your decision; no command provided.
