# Happ OFF / ON test — Pi (pi5home) — 2026-11-14

Method: user set Happ to OFF / ON in the GUI. Read-only snapshot taken with
`scripts/baseline-readonly.sh` (run as `bliss`, root checks via `sudo -n`).

## Happ OFF — 2026-11-14 01:06 +03:00 (VERIFIED)

| Item | Result |
|---|---|
| `happd.service` | enabled, active (running), pid 990 |
| `happd` IPC `/tmp/happd.sock` | connected; `happ-diag` reports `IPC response: status success` |
| Managed processes (happ-diag) | `0` — xray-core not running |
| `happ-xray` TUN | absent (`No Happ TUN adapter currently present`) |
| Main default route | `default via 192.168.0.1 dev wlan0 metric 600` only |
| Policy rules | `0 local`, `32766 main`, `32767 default` (unchanged) |
| nftables ruleset | empty |
| `ip_forward` / IPv6 forwarding | 0 / 0 |
| Pi LAN address | `192.168.0.118/24` on `wlan0` |

Interpretation:
- `happd` running does **not** mean Happ is ON. With Happ OFF the daemon is still active.
- Happ OFF removes the TUN and xray, and restores `wlan0` as the default route.
- The daemon reports no managed process and no TUN; this is the first positive OFF evidence collected from the Pi.

## Happ ON — 2026-11-14 01:07 +03:00 (VERIFIED)

| Item | OFF | ON |
|---|---|---|
| `happd.service` | active, pid 990 | active, pid 990 (unchanged) |
| Managed processes | 0 | 1: `xray-core` (xray, pid changes per run) |
| `happ-xray` TUN | absent | UP, `172.19.0.1/30` |
| Main default route | `wlan0` only | `default dev happ-xray metric 1` **plus** `default via 192.168.0.1 dev wlan0 metric 600` |
| Main route `172.19.0.0/30` | absent | `dev happ-xray` |
| Policy rules | unchanged | unchanged |
| nftables / forwarding | empty / 0 | empty / 0 |

Interpretation:
- Happ ON adds the TUN, the xray process, and a higher-priority default route through `happ-xray` (metric 1). The `wlan0` default (metric 600) remains as a fallback.
- That fallback is exactly what the design must prevent for clients. For the Pi itself it is normal behavior. For forwarded client traffic, the gateway must drop anything not leaving via `happ-xray`.
- `happd` stays running in both states, so the daemon's active state does not distinguish OFF from ON.
- The daemon IPC answered `success` in both states. The response does not include an enabled/disabled field, so it is not a usable intent signal yet.

Raw outputs are on the Pi at `/tmp/opencode/pi-happ-off.txt` and `/tmp/opencode/pi-happ-on.txt` (not in the repo).

## Summary

- OFF and ON differ in the TUN, xray process, and default route (metric 1 via `happ-xray`).
- The daemon's active state and IPC status are identical in both states, so neither proves intent.
- The existing signals (TUN, xray, route) reflect readiness, not the user's intent. This matches the CLAUDE.md warning.
- Still needed: a reliable Happ enabled/disabled signal, or a user-controlled marker.
