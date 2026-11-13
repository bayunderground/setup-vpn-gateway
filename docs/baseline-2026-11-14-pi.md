# Pi baseline — 2026-11-14 (Phase 0, partial)

Status: read-only observations. No configuration was changed on the Pi.
Session host: Dell (`dell`, Ubuntu 24.04). Pi accessed over SSH as `bliss@192.168.0.118`.
Repo cloned on the Pi to `/home/bliss/setup-vpn-gateway` (HEAD `d0f4f19`).

## Observation legend
VERIFIED = directly observed this session. INFERRED = reasoned from observations. UNKNOWN = not yet checked.

## Host
- VERIFIED `hostname`: `raspberrypi` (docs say `pi5os` or `raspberrypi`; current is `raspberrypi`).
- VERIFIED OS: Debian GNU/Linux 13 (trixie), aarch64. Docs say Bookworm. **Discrepancy.**
- VERIFIED login: `bliss` has passwordless SSH key access. `pi` user is rejected.
- VERIFIED sudo: **requires a password** (`sudo -n` fails). Root-only checks are blocked until a password or NOPASSWD rule is provided.
- UNKNOWN kernel version (only `uname -m` checked).

## Network (alpha probe run 2026-11-14 00:40 +03:00)
- VERIFIED `wlan0` `192.168.0.118/24`; `happ-xray` `172.19.0.1/30`.
- VERIFIED main default routes: `default dev happ-xray metric 1` and `default via 192.168.0.1 dev wlan0 metric 600`.
- VERIFIED alpha state: `TUNNEL_ACTIVE`. The user's Happ intent is NOT confirmed, so the control state is UNKNOWN.
- VERIFIED `ip rule`: only `0 local`, `32766 main`, `32767 default`. No Happ policy rules present.
- VERIFIED tables in use: `local`, `main`. `default` table listed but not populated.
- UNKNOWN `/etc/iproute2/rt_tables` absent — no custom table names defined.
- UNKNOWN nftables ruleset and sysctl values: `nft` and `sysctl` not on PATH for non-root user.
- UNKNOWN IPv6 forwarding and address state on `wlan0` (no global IPv6 address reported by `ip -6 addr show wlan0 scope global`).

## Happ
- VERIFIED `happd` version `4.7.2`.
- VERIFIED `happd.service`: enabled, active, `Restart=always`, runs as root, `ExecStart=/opt/happ/bin/happd`.
- VERIFIED process tree: `happd` (pid 990) -> `/opt/happ/bin/core/xray`.
- VERIFIED local control socket: `/tmp/happd.sock` (root-owned, mode `srw-rw-rw-`), "Local socket server started".
- VERIFIED root-only state store: `/var/lib/happd/state.db` ("[state] opened" in log). Not readable without root.
- VERIFIED log: `/var/log/happd.log` (world-readable). Events observed: client connections, `Started process "xray-core"`, MCS push reconnects. **No explicit "enabled"/"disabled" event observed in the readable portion.**
- VERIFIED user state: `~/.config/Happ.conf` (contains a `mode` key and last-server fields; values not recorded here) and `~/.config/Happ/subs.db`.
- INFERRED: `~/.config/Happ.conf` values may hold UI state, but whether `mode` reflects VPN enabled/disabled is UNKNOWN.
- UNKNOWN: documented protocol for `/tmp/happd.sock`. Not probed; no commands were sent.

## Not yet verified
- Happ OFF state (not yet tested — user to confirm or allow toggling).
- Android and Dell gateway/address/reservation checks (Dell checked only locally).
- Dell `tun0` (`172.18.0.1/30`, Dell local) ownership and priority 8000/9000–9010 rules — not inspected yet.

## Notes
- `happ-diag` (no args) is read-only health checks; `--repair` restarts `happd` and must NOT be run.
- Repo on Dell has pre-existing staged files `chatgpt_Continue_VPN_Gateway_Setup_2026-11-14_0017.md` and `..._0021.md`. Not touched.
