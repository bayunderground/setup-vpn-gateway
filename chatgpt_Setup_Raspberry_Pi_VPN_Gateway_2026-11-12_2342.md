---
url: "https://chatgpt.com/g/g-p-69db4952deec8191bbcce6f3c3cff6c4-pi-wifi/c/6af61f15-c754-83eb-9862-db600c65de14"
exported_date: "2026-11-12T20:42:57.508Z"
---

# Setup Raspberry Pi VPN Gateway

**User**

bliss@raspberrypi:/tmp $ #!/usr/bin/env bash
set -e

OLD_FORWARD=$(sysctl -n net.ipv4.ip_forward)

cleanup() {
    sudo ip rule del priority 8000 from 192.168.0.185/32 table 2022 2>/dev/null || true
    sudo ip rule del priority 7990 to 192.168.0.0/24 lookup main 2>/dev/null || true
    sudo ip route flush table 2022 2>/dev/null || true
    sudo sysctl -w net.ipv4.ip_forward="$OLD_FORWARD" >/dev/null
}
trap cleanup EXIT

echo "===== ENABLE TEMPORARY FORWARDING ====="
sudo sysctl -w net.ipv4.ip_forward=1

echo "===== TEMPORARY ROUTING RULES ====="
sudo ip route add 192.168.0.0/24 dev wlan0 scope link table 2022
sudo ip route add default dev happ-xray table 2022
sudo ip rule add priority 7990 to 192.168.0.0/24 lookup main
sudo ip rule add priority 8000 from 192.168.0.185/32 table 2022

echo "===== INTERNET ROUTE ====="
ip -4 route get 1.1.1.1 from 192.168.0.185 iif wlan0

echo "===== LAN ROUTE ====="
ip -4 route get 192.168.0.1 from 192.168.0.185 iif wlan0

echo "===== RULES ====="
ip -4 rule show

echo "===== CLEANUP (AUTOMATIC) ====="
===== ENABLE TEMPORARY FORWARDING =====
net.ipv4.ip_forward = 1
===== TEMPORARY ROUTING RULES =====
===== INTERNET ROUTE =====
1.1.1.1 from 192.168.0.185 dev happ-xray table 2022 
    cache iif wlan0 
===== LAN ROUTE =====
192.168.0.1 from 192.168.0.185 dev wlan0 
    cache <redirect> iif wlan0 
===== RULES =====
0:	from all lookup local
7990:	from all to 192.168.0.0/24 lookup main
8000:	from 192.168.0.185 lookup 2022
32766:	from all lookup main
32767:	from all lookup default
===== CLEANUP (AUTOMATIC) =====

---

**Assistant**

Excellent. This is exactly the result we wanted.

| Test | Result |
| --- | --- |
| Android → Internet (`1.1.1.1`) | `happ-xray`, table`2022` |
| Android → LAN (`192.168.0.1`) | `wlan0`, main table |
| Forwarding | Enabled temporarily |
| Cleanup | Successful; forwarding restored |

The routing design is now validated.


## Final configuration design

I'll use these settings for the Raspberry Pi gateway:

| Setting | Value |
| --- | --- |
| LAN interface | `wlan0` |
| Pi address | `192.168.0.118` |
| Android address | `192.168.0.185` |
| Android MAC | `f0:35:75:23:34:62` |
| VPN interface | `happ-xray` |
| Routing table | `2022` |
| LAN bypass rule | Priority`7990` |
| Android VPN rule | Priority`8000` |

The firewall will have three important behaviors:


1. **LAN bypass:**Android can access`192.168.0.0/24`, even when Happ is disconnected.
2. **VPN-only Internet:**Android's external traffic can leave only through`happ-xray`.
3. **Kill switch:**If Happ disconnects, Android cannot fall back to the router's ordinary Internet connection.

I'll implement this with native`nftables`, a systemd service, and automatic recovery after Wi-Fi or Happ reconnections. The Pi's own Internet traffic and Happ configuration will remain untouched.


## One final preference

Should the gateway also support**IPv6 LAN access**, while blocking IPv6 Internet traffic from Android to prevent VPN bypass?

My recommendation is**yes**: preserve local IPv6 connectivity, but don't allow Android to reach the public IPv6 Internet outside Happ.

---

**User**

no IPv6 at all

---

**Assistant**

Understood. We'll make the Android gateway **IPv4-only**.


- No IPv6 routing through `happ-xray`.
- No IPv6 forwarding through the Pi.
- No IPv6 NAT.
- Drop all IPv6 packets forwarded from Android through the Pi.
- Keep the Pi's own IPv6 configuration unchanged, to avoid interfering with Debian, NetworkManager or Happ.

**One important limitation:** Android and the Pi are on the same Wi-Fi network. Your router could advertise an IPv6 route directly to Android, bypassing the Pi entirely. To guarantee that Android has no IPv6 connectivity, IPv6 must also be disabled for that Wi-Fi network on the router or Android itself.

The IPv4 gateway design is fully validated. Next I'll prepare the Pi-specific installer, recovery service, diagnostics and uninstall procedure, preserving the existing Happ configuration.

---

**User**

one more thing. I want to use same gateway from my Ubuntu dell

---

**Assistant**

Yes. We can make the Raspberry Pi a **shared VPN gateway for both Android and your Ubuntu Dell**.

The Pi will route traffic from both devices through its Happ tunnel (`happ-xray`), independently of the Pi's own traffic.


### Updated design

**Raspberry Pi 5 — 192.168.0.118**

Happ VPN · happ-xray

Shared VPN gateway

**Android**

192.168.0.185

**Ubuntu Dell**

192.168.0.105*

*Previous Dell address; we'll verify its current address before configuring it.

Both devices will have:


- Internet traffic routed through Happ.
- LAN access preserved, even if Happ disconnects.
- An independent kill switch.
- IPv4 only; no IPv6 forwarding.
- No fallback to the router's direct Internet connection.


### One question

Do you want **all Internet traffic from the Dell** to go through the Pi's Happ VPN, just like Android?

My recommendation is yes. I'll then design the installer to support multiple clients rather than hardcode only the Android device.