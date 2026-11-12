# Raspberry Pi 5 shared Happ VPN gateway — LLM handover

**Status:** design and diagnostics phase; alpha 0.1 is read-only.  
**Repository:** https://github.com/bayunderground/setup-vpn-gateway  
**Last updated:** 2026-11-13

## 1. Goal

Turn the Raspberry Pi 5 into a shared IPv4 VPN gateway for:
- Android: `192.168.0.185`
- Ubuntu laptop/desktop `dell`: `192.168.0.105` (observed in the latest Dell diagnostic; verify before configuration)

Both clients should use the Pi's Happ VPN only while Happ is **enabled** on the Pi.

Required behavior:

| Happ state on Pi | Dell/Android Internet behavior |
|---|---|
| Disabled | Clients do not use the Pi VPN gateway; Dell retains its normal router path |
| Enabled and connected | Client Internet traffic is routed through Pi's Happ TUN |
| Enabled but disconnected, broken, or transitioning | Fail closed: no direct-router fallback through the Pi |

Keep LAN access available where possible. IPv4 only: user explicitly requested no IPv6 gateway support. The Pi's own networking and Happ operation must not be broken.

## 2. Critical state-detection requirement

Do NOT equate the Happ daemon with the VPN enabled state.

Observed on 2026-11-12:

### Happ OFF
- `happd.service`: running
- `happ-xray` interface: absent
- `xray` process: absent
- Main default route: via router `192.168.0.1 dev wlan0`
- Active NM connections: Wi-Fi and loopback only

### Happ ON
- `happd.service`: running
- `happ-xray` interface: present, `172.19.0.1/30`
- `xray` process: present
- Main default route: `default dev happ-xray metric 1`
- Active NM connections include `happ-xray` (tun)

This makes the TUN interface/process/route a useful signal for **tunnel active**, but not sufficient to distinguish:
1. Happ disabled by the user, from
2. Happ enabled but tunnel disconnected or failed.

The required client behavior differs between those states. Before implementing automatic client switching, investigate a reliable Happ enabled/disabled signal (Happ daemon IPC/API, local control socket, config/state file, D-Bus, logs, or another supported mechanism). Do not guess undocumented internals or parse volatile log text as the only safety control.

A sensible state machine is:
- DISABLED: positively confirmed by Happ control state → remove client gateway routing; Dell uses its ordinary router.
- ENABLED_UP: enabled confirmed AND TUN/routing ready → enable forwarding through Happ only.
- ENABLED_DOWN / TRANSITION / UNKNOWN: enabled but not ready, or state uncertain → block client Internet through Pi; never fall back to `wlan0`.

Unknown must fail closed, not be treated as disabled.

## 3. Current Pi facts (observed)

- Device: Raspberry Pi 5, hostname previously reported as `pi5os`; shell prompt currently showed `raspberrypi` (verify actual hostname)
- OS: Raspberry Pi OS / Debian Bookworm, aarch64
- LAN interface: `wlan0`
- Pi LAN address: `192.168.0.118/24`
- Router: `192.168.0.1`
- Wi-Fi NetworkManager profile: `TP-Link_42SN_5G`
- Happ TUN interface: `happ-xray`
- Happ TUN address when active: `172.19.0.1/30`
- Happ daemon: `happd.service`, executable `/opt/happ/bin/happd`
- Happ xray executable observed: `/opt/happ/bin/core/xray`
- NM profile `happ-xray`: type `tun`, autoconnect=no
- Pi nftables ruleset was empty at time of inspection.
- Pi main route with Happ OFF: `default via 192.168.0.1 dev wlan0`
- Pi main route with Happ ON: `default dev happ-xray metric 1`

The `happd.service` daemon stays running in both OFF and ON states. Do not stop/restart it to toggle gateway mode.

## 4. Current Dell facts (observed)

- Hostname: `dell`
- Wi-Fi interface: `wlp8s0`
- Wi-Fi address: `192.168.0.105/24`
- Router: `192.168.0.1`
- Old VPN tunnel: `tun0`, address `172.18.0.1/30`
- Old policy routing table 2022: `default via 172.18.0.2 dev tun0`
- Old custom rules include priorities 8000, 9000, 9001, 9002, 9003, 9010.
- User confirmed Dell's `tun0` and associated rules are leftovers from the earlier Android gateway experiment, not an intentional Dell VPN.

The old Dell setup was the previous Ubuntu-as-gateway design. Its old files in this repository (`setup-android-vpn-gateway.sh`, `setup-android-vpn-gateway.md`, and `setup-android-vpn-gateway_session_debug-state.md`) are historical reference only. Do not execute or blindly reuse them on the Pi. Do not flush all Dell routing rules: identify and remove only the stale rules/configuration after reviewing their source and confirming ownership.

## 5. Android facts

- Address: `192.168.0.185/24`
- MAC: `f0:35:75:23:34:62`
- Earlier intended gateway was Dell `192.168.0.105`; when migrated, it will need the Pi gateway `192.168.0.118` only in the active gateway mode.
- Confirm current Android IP/gateway configuration before cutover.
- Ensure the address is reserved or outside the DHCP pool.

## 6. Earlier routing experiment on Pi

A temporary, automatically cleaned-up test validated source-policy routing for Android when Happ was ON:

```bash
OLD_FORWARD=$(sysctl -n net.ipv4.ip_forward)
cleanup() {
  sudo ip rule del priority 8000 from 192.168.0.185/32 table 2022 2>/dev/null || true
  sudo ip rule del priority 7990 to 192.168.0.0/24 lookup main 2>/dev/null || true
  sudo ip route flush table 2022 2>/dev/null || true
  sudo sysctl -w net.ipv4.ip_forward="$OLD_FORWARD" >/dev/null
}
trap cleanup EXIT
sudo sysctl -w net.ipv4.ip_forward=1
sudo ip route add 192.168.0.0/24 dev wlan0 scope link table 2022
sudo ip route add default dev happ-xray table 2022
sudo ip rule add priority 7990 to 192.168.0.0/24 lookup main
sudo ip rule add priority 8000 from 192.168.0.185/32 table 2022
ip -4 route get 1.1.1.1 from 192.168.0.185 iif wlan0
ip -4 route get 192.168.0.1 from 192.168.0.185 iif wlan0
```

Expected results from the experiment:
- Internet destination `1.1.1.1` from Android source → `happ-xray`, table 2022.
- LAN destination `192.168.0.1` → `wlan0`, main table.
- Cleanup restored prior `net.ipv4.ip_forward` and removed temporary rules/routes.

This validates a routing concept only. It does NOT validate NAT, nftables, return traffic, DNS, multiple clients, reconnection, or the required enabled-but-disconnected state machine.

## 7. Alpha script

File: `setup-vpn-gateway-alpha.sh`

Alpha 0.1 is intentionally a **read-only diagnostic**, not an installer. Run on the Pi:

```bash
chmod +x setup-vpn-gateway-alpha.sh
./setup-vpn-gateway-alpha.sh status
```

It reports:
- happd service state
- whether `happ-xray` exists
- whether an `xray` process exists
- whether the main default route points to `happ-xray`
- current IPv4 addresses, default route, and active NetworkManager connections

It makes no changes to networking, firewall, routes, sysctls, or services. It deliberately reports tunnel-absent rather than claiming VPN-disabled.

## 8. Planned implementation architecture (not yet installed)

Target design after state detection is solved:

1. **Pi state monitor:** a systemd-managed helper subscribes to reliable Happ state changes or polls a stable local state interface. Debounce transitions.
2. **nftables:** native nftables rules, separate chain/table owned by this project; do not flush global ruleset. Forward client IPv4 only from `wlan0` to `happ-xray`; drop client forwarding to `wlan0` and all other non-VPN egress. Permit established return traffic. Add masquerade on `happ-xray`.
3. **Policy routing:** route each registered client source address through a dedicated routing table whose default is `happ-xray`, with explicit LAN subnet bypass. Preserve Happ's own rules/routes. Avoid reusing table 2022 until its ownership/conflicts are reviewed; earlier temporary test used it, but no persistent Pi gateway configuration has been installed.
4. **Clients:** configuration supports multiple clients (Android and Dell), not a hardcoded single Android. Client entries should include stable IP and optional MAC.
5. **Dell control:** Dell must use Pi as gateway only while Happ is positively confirmed enabled. When Happ is disabled, Dell uses normal router gateway. If enabled but down/unknown, Dell must fail closed. This may require a small Dell-side NetworkManager/systemd agent or another reliable mechanism; do not assume Pi can transparently change Dell's default gateway without client-side cooperation.
6. **IPv6:** no IPv6 forwarding or NAT. Drop forwarded IPv6 from clients. Important: same-LAN clients may receive IPv6 Router Advertisements directly from the Wi-Fi router and bypass the Pi. For strict no-IPv6 behavior, disable IPv6 on router Wi-Fi or client devices as appropriate. Do not globally disable IPv6 on the Pi unless explicitly agreed.
7. **Lifecycle:** start after network/Happ components; react to Wi-Fi and Happ up/down; systemd restart/reconciliation; race-safe locking; idempotent apply; clear uninstall that removes only project-owned files/rules.
8. **Diagnostics:** status, check, logs, route tests, nft counters, packet capture guidance, public IPv4 verification, and kill-switch tests.

## 9. Safety / implementation rules for the next LLM

- Work step-by-step; ask for command output before making assumptions.
- Do not run destructive commands or change live networking until the user explicitly approves the implementation stage.
- Do not install the alpha script as a service; it is read-only.
- Never flush nftables globally, flush all routing tables, reset NetworkManager, or rewrite Happ config.
- Preserve the Pi's own routing and Happ control daemon.
- Never let client traffic fall back to the Pi's ordinary Wi-Fi WAN while Happ is enabled.
- When state is UNKNOWN, fail closed for clients.
- Distinguish user intent (Happ enabled/disabled) from tunnel readiness (interface/process/route).
- Keep client addresses configurable and validate duplicate/out-of-subnet addresses.
- Use native nftables on Pi OS; do not copy Ubuntu iptables setup.
- Use explicit backup/rollback and uninstall plans before applying persistent changes.
- Verify all routes and firewall counters before asking the user to change Android or Dell gateway settings.
- Do not claim IPv6 is blocked end-to-end just because the Pi drops forwarded IPv6; same-LAN router advertisements can bypass the Pi.

## 10. Next concrete task

Investigate how Happ 4.7.2 on this Pi exposes the **user-selected enabled/disabled state separately from tunnel readiness**. Start with read-only inspection and documentation/help for `/opt/happ/bin/happd`, local sockets, D-Bus, files under Happ's own application data/config directories, and logs. Avoid dumping secrets or credentials. If no reliable signal is exposed, discuss an alternative explicit toggle/marker controlled by the user rather than guessing from interface presence.

Only after that signal is established should the next LLM design and implement the real Pi gateway installer and Dell-side state-following behavior.
