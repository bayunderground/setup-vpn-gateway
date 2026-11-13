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

## Happ ON — pending

Next: set Happ to ON, tell me, and rerun the same script. Compare:
- Whether `happ-xray` returns and the main default route switches to it.
- Whether xray appears as a managed process again.
- Whether the daemon IPC status changes in any way.

Raw OFF output was saved on the Pi at `/tmp/opencode/pi-happ-off.txt` (not in the repo).
