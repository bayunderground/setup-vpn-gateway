# Android VPN Gateway — Debug State & Session Notes (2026-11-08 21:15 MSK)

Purpose: resume this session later without re-deriving anything.
Subject machine: Ubuntu desktop `dell` (this machine). Goal: share Happ (VLESS/REALITY)
VPN with one Android device over Wi-Fi.

---

## 1. Reference files (repo, read-only copies of what is installed)

- `bin/setup-android-vpn-gateway.sh` — installer (writes the helper, dispatcher, units)
- `bin/setup-android-vpn-gateway.md` — design doc / maintenance notes

Installed live components (all rewritten **Nov 08 19:04**, when the user re-ran the installer):

| Path | Notes |
|---|---|
| `/usr/local/sbin/android-vpn-share` | the "apply" helper, mode 0755, 2675 bytes |
| `/etc/NetworkManager/dispatcher.d/90-android-vpn-share` | runs helper on `up`/`dhcp4-change` for `wlp8s0`/`tun0` |
| `/etc/systemd/system/android-vpn-share.service` | oneshot |
| `/etc/systemd/system/android-vpn-share.timer` | enabled, `OnUnitActiveSec=30s` |
| `/etc/sysctl.d/90-android-vpn-share.conf` | `net.ipv4.ip_forward=1` |

---

## 2. Fixed parameters (must stay consistent)

```
CONNECTION   = TP-Link_42SN_5G
LAN_IF       = wlp8s0
LAN_IP       = 192.168.0.105/24      (gw 192.168.0.1, DNS 192.168.0.1,1.1.1.1)
ROUTER       = 192.168.0.1
ANDROID_IP   = 192.168.0.185/24
ANDROID_MAC  = f0:35:75:23:34:62
UBUNTU_MAC   = a4:34:d9:24:57:2f
VPN_IF       = tun0  (172.18.0.1/30, peer 172.18.0.2)
VPN_TABLE    = 2022
RULE_PRIO    = 8000   -> "from 192.168.0.185 lookup 2022"
CHAIN        = ANDROID_VPN_OUT
```

Happ processes observed: `happd` (root), `Happ` (GUI), `sing-box` (`/opt/happ/bin/tun/sing-box`,
config `/home/bliss/.config/Happ/config.json`), `xray` (SOCKS on `127.0.0.1:10808`, also `10809`).

Happ TUN inbound config: `auto_route: true`, `strict_route: true`, `stack: mixed`, address `172.18.0.1/30`.
Route rules: sniff, `hijack-dns` (protocol dns), final = `proxy` (SOCKS → xray), DNS server `8.8.8.8 detour direct`.

---

## 3. What was VERIFIED WORKING (measured 2026-11-08 ~21:00–21:12 MSK)

Boot: 17:54 MSK, uptime 3h11m at time of audit.

| Check | Command | Result |
|---|---|---|
| Happ VPN works locally | `curl -4 -m10 https://api.ipify.org` | `152.233.43.93` ✅ (doc's old value was `152.233.108.41`) |
| LAN address | `ip -br addr show wlp8s0` | `UP 192.168.0.105/24` ✅ |
| NM profile | `nmcli -f ipv4.method,ipv4.gateway,ipv4.addresses,ipv6.method con show TP-Link_42SN_5G` | `manual / 192.168.0.1 / 192.168.0.105,192.168.0.1 / disabled` ✅ (ipv6 **disabled**) |
| IP forwarding | `sysctl net.ipv4.ip_forward` | `1` ✅ |
| rp_filter | `sysctl net.ipv4.conf.{all,wlp8s0}.rp_filter` | `2` (loose) ✅ |
| Policy rule | `ip -4 rule show` | `8000: from 192.168.0.185 lookup 2022` ✅ present |
| Android route decision | `ip -4 route get 1.1.1.1 from 192.168.0.185 iif wlp8s0` | `via 172.18.0.2 dev tun0 table 2022` ✅ |
| Local route decision | `ip route get 1.1.1.1` | `via 172.18.0.2 dev tun0 table 2022 src 172.18.0.1` ✅ |
| tun0 | `ip link show tun0` | up, `172.18.0.1/30` ✅ |
| table 2022 | `ip route show table 2022` | `default via 172.18.0.2 dev tun0` ✅ |
| Timer | `systemctl status android-vpn-share.timer` | enabled, active(waiting), triggering every 30s ✅ |
| Helper exit code | `journalctl -u android-vpn-share.service` | "Deactivated successfully" every 30s → **all iptables/sysctl/ip commands inside succeed** ✅ |
| Android on LAN | `ping -c3 192.168.0.185` | 0% loss, ttl=64 (real phone) ✅ |
| Android ARP | `ip -s neigh show dev wlp8s0` | `192.168.0.185 lladdr f0:35:75:23:34:62 REACHABLE`, `used` timestamp refreshed to `0/0/0` during sampling → **this box actively transmits replies to Android** ✅ |
| Router reachable | `ping 192.168.0.1` | OK ✅ |
| Forwarding in progress | `/proc/net/snmp` `Ip: ForwDatagrams` | +65/10s, +119/30s, +209/30s → **~4–7 pkt/s are being forwarded right now** ✅ |
| No unroutable packets | `/proc/net/snmp` `Ip: OutNoRoutes` | delta 0 over 30s ✅ |
| Forwarded packets get transmitted | `OutTransmits - OutRequests` ≈ `ForwDatagrams` (294710 vs 294861) | forwarded packets are **not** being wholesale dropped ✅ |
| UFW | `systemctl is-active ufw` | **active**, `/etc/default/ufw`: `DEFAULT_FORWARD_POLICY="DROP"` ⚠️ |
| ufw logging | `/var/log/ufw.log`, `journalctl -k \| grep "UFW BLOCK"` | **absent / zero lines** → logging is off, so ufw drops are invisible ⚠️ |
| IPv6 on LAN iface | `sysctl net.ipv6.conf.wlp8s0.disable_ipv6` | `1` (because NM profile `ipv6.method: disabled`) → Ubuntu has **no IPv6 on wlp8s0** |
| Other net services | `systemctl list-units --state=running` | only `ufw`, `NetworkManager`, `happd` (no tailscale/firewalld/openvpn/wg running) |
| `wg0` NM connection | journal 19:04:53 | `Activation: failed for connection 'wg0'` then marked unmanaged (probably unrelated, but noted) |

### Neighbor-table oddity (probably a red herring)
`ip -s neigh` shows `8.8.8.8 FAILED` and `178.214.109.2 FAILED`, both last used ~7400s ago
(**≈19:04, exactly when the installer reactivated Wi-Fi**), 6 ARP probes each.
An on-link ARP for `8.8.8.8` implies that at that instant Ubuntu had a **device-only default route**
(`default dev wlp8s0`, no gateway) or an equivalent link-scope route. Currently the default route is
correctly `via 192.168.0.1`, so this was transient — but it is a clue that something (NM activation
window, or Happ reconnect) briefly had no gateway. Not confirmed as the cause.

---

## 4. What is NOT yet known (needs root — `sudo` requires a password, agent cannot run it)

1. **Live `iptables` filter/nat/mangle rules and their packet counters** — specifically:
   - is `-j ANDROID_VPN_OUT` actually at `FORWARD` position 1, *above* ufw's chains?
   - does `ANDROID_VPN_OUT` contain `-o tun0 -j ACCEPT` then `-j DROP`, and which counter is growing?
   - is `-A POSTROUTING -s 192.168.0.185/32 -o tun0 -j MASQUERADE` present?
   - is the return rule `-i tun0 -o wlp8s0 -d 192.168.0.185 -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT` present?
2. **Whether Android's traffic actually egresses `tun0` (tunnelled) or `wlp8s0` (leaked).**
   Counter arithmetic could not separate it: local streaming traffic dominates both interfaces
   (`tun0 TX 197424`, `wlp8s0 TX 49064` per 30s vs only ~120 forwarded packets).
3. **`conntrack` state for 192.168.0.185** (are connections being created and replied to?).
   Note: `/proc/net/nf_conntrack` does **not** exist on this box even though `nf_conntrack`,
   `xt_conntrack`, `nf_nat`, `xt_MASQUERADE` are loaded (checked via `lsmod`).
4. **Packet capture** — whether replies to Android come from a WAN/VPN address (good) or the
   LAN router (leak), and whether Android's packets appear on `tun0` at all.
5. **Android-side state**: gateway actually set to `192.168.0.105` (not the old `.103`),
   static IP `.185`, DNS `1.1.1.1`/`8.8.8.8`, and whether Android receives IPv6 from the router
   (would explain "Connected, no internet" or an IPv6 leak).

---

## 5. Pending diagnostic commands (run when resuming)

### 5a. Firewall / conntrack (root)

```bash
sudo bash -c '
echo "=== filter FORWARD ==="; iptables -S FORWARD
echo "=== ANDROID_VPN_OUT counters ==="; iptables -L ANDROID_VPN_OUT -v -n -x
echo "=== nat POSTROUTING ==="; iptables -t nat -S POSTROUTING
echo "=== mangle ==="; iptables -t mangle -S | head -30
echo "=== ufw chains present ==="; iptables -S ufw-before-forward 2>/dev/null | head
echo "=== nft ruleset (head) ==="; nft list ruleset 2>/dev/null | head -100
echo "=== conntrack for android ==="; conntrack -L 2>/dev/null | grep 192.168.0.185 | head -15
'
```

**How to read it:**
- If `ANDROID_VPN_OUT` counters show a large `-o tun0 ACCEPT` count → tunnel path is used.
- If the final `-j DROP` counter is the one growing → traffic is being killed (check why tun0 rule missing).
- If `ANDROID_VPN_OUT` has no `-o tun0` rule or the chain/jump is missing → the helper is failing
  to install it (but the service exits 0, so this would be surprising).
- If ufw's chains come *before* our jump in `iptables -S FORWARD` → ufw is winning; fix ordering.
- If no `MASQUERADE` rule → replies from sing-box may not un-NAT back to `.185`.

### 5b. Packet capture while testing on the phone (root)

```bash
sudo tcpdump -ni wlp8s0 host 192.168.0.185 -c 40   # replies should come from a non-LAN source IP
sudo tcpdump -ni tun0 -c 40                        # look for src 192.168.0.185 (no NAT) or 172.18.0.1 (masqueraded)
```

- Android packets appearing on `tun0` ⇒ forwarding into the tunnel works.
- Replies on `wlp8s0` sourced from a WAN/VPN IP ⇒ return path works.
- Only LAN-sourced replies (192.168.0.x) ⇒ traffic is bypassing/leaking via the router.

### 5c. No-root re-checks (fast)

```bash
ip -4 rule show; ip route show table 2022; ip route get 1.1.1.1 from 192.168.0.185 iif wlp8s0
sysctl net.ipv4.ip_forward; ip -br addr show wlp8s0
systemctl status android-vpn-share.timer --no-pager
journalctl -u android-vpn-share.service -n 50 --no-pager
awk '/^Ip: /{print "Forw="$7" OutNoRoutes="$13}' /proc/net/snmp   # sample twice, 30s apart
ip -s neigh show dev wlp8s0                                        # does .185 "used" stay 0?
curl -4 -s -m10 https://api.ipify.org
```

---

## 6. Hypotheses, ranked (state at end of session)

| # | Hypothesis | Evidence for | Evidence against | Status |
|---|---|---|---|---|
| H1 | Android's gateway is not `192.168.0.105` (e.g. still `.103`, or DHCP) | doc explicitly warns about the old `.103`; would give total "no internet" | ARP `.185` refresh shows this box transmits to Android; ~4–7 pkt/s are being forwarded | **needs Android-side check / tcpdump** |
| H2 | ufw (`FORWARD` policy DROP) is beating the helper's ACCEPT rules | ufw active; its log is disabled so drops would be silent; helper only inserts at position 1 every 30s (gap on `ufw reload`) | helper exits 0, and counter arithmetic shows forwarded packets *are* transmitted | **needs `iptables -S FORWARD` + counters** |
| H3 | Android prefers IPv6 from the router (Ubuntu's IPv6 is disabled) → broken/leaky path → "Connected, no internet" | `ipv6.method: disabled` on the Ubuntu profile; doc's IPv6 section anticipates this; classic Android symptom | not yet checked on the phone | **needs Android-side check** |
| H4 | MASQUERADE/conntrack issue: packets go in but replies don't come back to `.185` | would explain forwarding+transmission while Android has no service | `.185` neighbor `used 0/0/0` suggests replies *are* being sent to it | **needs conntrack + tcpdump** |
| H5 | DNS failure on Android (static 1.1.1.1/8.8.8.8, or Private DNS/DoT) | only-UDP-53 traffic gets `hijack-dns`; DoT/DoH would take a different path | local DNS works through the same hijack | **needs Android-side check** |
| H6 | Transient "no default route" during NM activation (see §3 neighbour oddity) | FAILED ARP for `8.8.8.8`/`178.214.109.2` at exactly 19:04 | current default route is correct | historical, likely not the live cause |
| H7 | Nothing is broken on Ubuntu; issue is Android-side or already fixed by the 19:04 reinstall | all Ubuntu checks pass; traffic flows both ways | user reports it is not working | **confirm symptom first** |

---

## 7. Design caveats already documented (do not contradict these)

- Happ uses **policy routing**; never replace it with a generic default-route/NAT recipe.
  Preserve rules 9000–9010 and table `2022`.
- The helper **flushes `ANDROID_VPN_OUT` before rebuilding it** → a brief kill-switch gap every
  30s. It is **not** a mathematically gap-free kill switch. A safer revision builds a new chain
  and switches to it only when complete.
- The setup shares **IPv4 only**; the `ip6tables` drop rule (by Android MAC) does **not** stop
  Android getting IPv6 straight from the router.
- The installer does **not** create the router DHCP reservation (Ubuntu `a4:34:d9:24:57:2f` →
  `192.168.0.105`); that must be done manually.
- Always inspect live files/rules before editing the script — never assume they match the note.

---

## 8. Resume checklist

1. Ask the user for the exact Android symptom (was asked; user deferred — ask again):
   - connects but "no internet" / works but wrong public IP / won't join Wi-Fi / only some apps fail
2. Get root output from §5a, plus §5b captures taken while the phone tries to load a page.
3. On the phone, confirm: IP `192.168.0.185`, gateway `192.168.0.105`, prefix 24,
   DNS `1.1.1.1`/`8.8.8.8`, and whether the network has an IPv6 address.
4. Compare Android's public IPv4 with `curl -4 https://api.ipify.org` on Ubuntu (currently
   `152.233.43.93`).
5. Only then change anything — and prefer atomic chain replacement over `flush`-then-rebuild.
