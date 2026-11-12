# Android VPN Gateway via Ubuntu + Happ

## Goal

Share the Ubuntu PC's Happ VLESS/REALITY VPN connection with one Android device on the same Wi-Fi. Ubuntu acts as the Android device's IPv4 gateway. The setup is intended to persist across reboots, Wi-Fi reconnects, and Happ/TUN restarts.

## Network topology

```text
Internet
   |
Wi-Fi router: 192.168.0.1
   |
   +--- Ubuntu PC (`dell`)
   |      Wi-Fi: wlp8s0
   |      LAN:   192.168.0.105/24
   |      Happ TUN: tun0 (172.18.0.1/30, peer 172.18.0.2)
   |      Happ routing table: 2022
   |
   +--- Android
          IP:      192.168.0.185/24
          Gateway: 192.168.0.105
          MAC:     f0:35:75:23:34:62
```

## Known device/network details

| Item | Value |
|---|---|
| Ubuntu hostname | `dell` |
| Wi-Fi NetworkManager connection | `TP-Link_42SN_5G` |
| Ubuntu Wi-Fi interface | `wlp8s0` |
| Ubuntu Wi-Fi MAC | `a4:34:d9:24:57:2f` |
| Ubuntu static LAN IP | `192.168.0.105/24` |
| Router/gateway | `192.168.0.1` |
| Android static IP | `192.168.0.185/24` |
| Android MAC | `f0:35:75:23:34:62` |
| Happ TUN interface | `tun0` |
| TUN address / peer | `172.18.0.1/30` / `172.18.0.2` |
| Happ routing table | `2022` |
| Android policy-routing rule | `priority 8000 from 192.168.0.185/32 lookup 2022` |

When sharing was confirmed working, both Ubuntu and Android showed public IPv4 `152.233.108.41`.

## Android Wi-Fi configuration

Set the Android Wi-Fi network's IP settings to **Static**:

- IP address: `192.168.0.185`
- Gateway: `192.168.0.105`
- Network prefix length: `24` (or subnet mask `255.255.255.0`)
- DNS 1: `1.1.1.1`
- DNS 2: `8.8.8.8`
- Proxy: None

The gateway must be Ubuntu's current address, `192.168.0.105`, not the former `.103`.

## Ubuntu installer and persistent components

The installer used was `setup-android-vpn-gateway.sh`, run with:

```bash
sudo ./setup-android-vpn-gateway.sh
```

It completed successfully and configured:

- NetworkManager connection `TP-Link_42SN_5G` with static address `192.168.0.105/24`, router `192.168.0.1`, and DNS `192.168.0.1 1.1.1.1`.
- IPv4 forwarding via `/etc/sysctl.d/90-android-vpn-share.conf`.
- Helper script: `/usr/local/sbin/android-vpn-share`.
- NetworkManager dispatcher: `/etc/NetworkManager/dispatcher.d/90-android-vpn-share`.
- systemd oneshot service: `/etc/systemd/system/android-vpn-share.service`.
- systemd timer: `/etc/systemd/system/android-vpn-share.timer`, enabled and scheduled every 30 seconds.
- Policy-routing rule for Android: `ip rule` priority `8000`, source `192.168.0.185/32`, table `2022`.
- iptables forwarding/NAT rules intended to route Android IPv4 through `tun0` and drop forwarded Android traffic when the VPN interface is unavailable.
- IPv6 forwarding drop rule associated with the Android Wi-Fi MAC to reduce IPv6 bypass risk.

The installer output confirmed:
- `wlp8s0` was up with `192.168.0.105/24`.
- The priority-8000 policy rule was present.
- The timer was enabled and waiting.

## Important routing detail

Happ uses policy routing, not just the main routing table. Its relevant rules observed during setup included:

```text
9000: from all to 172.18.0.0/30 lookup 2022
9001: from all lookup 2022 suppress_prefixlength 0
9002: not from all dport 53 lookup main suppress_prefixlength 0
9002: from all iif tun0 goto 9010
9003: not from all iif lo lookup 2022
9003: from 0.0.0.0 iif lo lookup 2022
9003: from 172.18.0.0/30 iif lo lookup 2022
9010: from all nop
```

The additional rule for Android is essential:

```bash
sudo ip rule add priority 8000 from 192.168.0.185/32 lookup 2022
```

Do not replace Happ's routing setup with a generic default-route/NAT recipe without checking its policy-routing behavior.

## Verification and troubleshooting

Run on Ubuntu:

```bash
ip -4 addr show dev wlp8s0
ip rule show
ip route show table 2022
ip link show tun0
sysctl net.ipv4.ip_forward
sudo systemctl status android-vpn-share.timer
sudo systemctl status android-vpn-share.service
curl -4 https://api.ipify.org
```

Expected key values:
- `wlp8s0`: `192.168.0.105/24`
- Android rule: `8000: from 192.168.0.185 lookup 2022`
- IPv4 forwarding: `1`
- Happ TUN: `tun0`
- With Happ connected, Ubuntu and Android should use the same VPN public IPv4.

From Android, open an IP-checking website or query a public IPv4 endpoint. Its public IPv4 should match Ubuntu's `curl -4 https://api.ipify.org` result while Happ is connected.

If Android loses connectivity:
1. Confirm Android's gateway is exactly `192.168.0.105`.
2. Confirm Ubuntu and Android are on the same LAN/subnet.
3. Confirm Happ is connected and `tun0` exists.
4. Check the Android policy rule and table `2022`.
5. Check timer/service status and inspect logs:

```bash
sudo journalctl -u android-vpn-share.service -n 100 --no-pager
sudo journalctl -u android-vpn-share.timer -n 50 --no-pager
```

## Kill-switch test

With Android configured to use Ubuntu as its gateway:

1. Connect Happ on Ubuntu. Confirm Android has internet and its public IPv4 matches Ubuntu's VPN public IPv4.
2. Disconnect Happ. Android should lose internet rather than fall back to the router's ordinary internet connection.
3. Reconnect Happ. Android should regain internet through the VPN.

If Android still has internet with Happ disconnected, stop using the setup until the forwarding/firewall rules are inspected.

## Router DHCP reservation

Create a DHCP reservation in the router for Ubuntu:

- MAC: `a4:34:d9:24:57:2f`
- Reserved IP: `192.168.0.105`

This helps prevent an address conflict or accidental change. Android is configured with a static IP; ensure `192.168.0.185` is outside the router's DHCP pool or reserved for Android as well.

## IPv6 limitation

The configured gateway and policy-routing setup shares **IPv4** through Happ. The installer added an IPv6 forwarding drop rule for the Android device's MAC, but this alone does not guarantee that Android cannot obtain IPv6 connectivity directly from the router or another network path.

For a strict no-leak setup, verify Android has no usable IPv6 route while using this gateway. Depending on the router and Android version, disable IPv6 on the router/Wi-Fi network or disable IPv6 for that Android connection if possible. Do not assume an IPv4 public-IP check proves IPv6 is protected.

## Maintenance notes / caveats for a future LLM

- Ubuntu is the gateway; Android's gateway must remain `192.168.0.105`.
- Android MAC is `f0:35:75:23:34:62`; Android IPv4 is `192.168.0.185`.
- Ubuntu Wi-Fi interface is `wlp8s0`; connection profile is `TP-Link_42SN_5G`.
- Happ uses `tun0` and routing table `2022`. Preserve Happ's policy routing.
- The installed helper/timer periodically reapplies firewall and routing rules.
- The helper no longer flushes its `ANDROID_VPN_OUT` chain. Each run adds only missing rules (`add_once`), so the kill-switch is never emptied between timer runs. The ACCEPT rule for `tun0` exists only while `tun0` is up; DROP stays last.
- Wi-Fi power saving is disabled on the `TP-Link_42SN_5G` connection (`802-11-wireless.powersave 2`). Power saving was enabled and could cause stalls for the forwarded Android traffic.
- The helper also runs on NetworkManager `vpn-up`/`vpn-down` events and on `wlp8s0`/`tun0` `up`/`down`/`dhcp4-change`, and the 30-second timer remains as a backstop.
- `happd.service` starts about 20 seconds after boot, after the first helper run, so `tun0` may not exist at boot. The DROP rule still protects Android in that window, and the timer adds the rest once `tun0` appears.
- The installer does not configure the router's DHCP reservation; do that manually.
- Before changing or replacing the script, inspect the live files and current rules rather than assuming they exactly match this note.
