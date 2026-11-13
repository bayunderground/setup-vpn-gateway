# VPN Gateway Project: Documentary (2026-11-14)

This document records everything established on 2026-11-14: the hosts, the Happ investigation, every test and its timing, the decisions made, the repository state, and what remains. It is the single entry point for anyone picking the project up later. Detailed topic notes are linked in section 13.

Evidence labels used throughout:
- **VERIFIED**: directly observed on a host during this session.
- **OBSERVED**: seen in a captured trace or log, with timestamp.
- **USER**: reported by the user, not independently checked.
- **INFERRED**: reasoned from observations.
- **UNKNOWN**: not yet checked.

Times are local (+03:00) unless stated. Hosts: Dell is `dell` (192.168.0.105, Ubuntu 24.04). Pi is `pi5home` (192.168.0.118, Raspberry Pi OS, Debian 13 trixie). Android is 192.168.0.185.

---

## 1. Summary

- Goal: a shared, IPv4-only Happ VPN gateway on the Raspberry Pi 5 for Android and Dell, with no client WAN leak and with Happ's own operation preserved.
- **No gateway is installed or active.** The Pi has no forwarding, no nftables rules, and no client routing. Dell still routes Android through its own Happ TUN (old experiment, rule 8000 live).
- The central blocker was the **Happ intent signal**: whether the user wants Happ enabled or disabled. This session showed that no passive, supported signal reports intent. The decision is a **user-set marker file** (design approved, section 9).
- Local commits were held until the final push of this session: sixteen earlier commits plus the session commits.
- Security posture: secret-bearing files are excluded by `.gitignore`. No API keys or VPN credentials appear in the repository. Two captured traces on the Pi contain the xray configuration; see section 12.

---

## 2. Hosts (current state)

### 2.1 Raspberry Pi (`pi5home`)
- VERIFIED: Raspberry Pi 5, Debian 13 (trixie), aarch64, kernel 6.18.29+rpt-rpi-2712. Earlier docs said Bookworm; they are wrong.
- VERIFIED: hostname `pi5home` (`hostnamectl --static`). Some prompts show `raspberrypi` (transient hostname). Check with `hostnamectl`.
- VERIFIED: `wlan0` 192.168.0.118/24, router 192.168.0.1, NetworkManager profile `TP-Link_42SN_5G`.
- VERIFIED: user `bliss` via SSH key. `sudo` needs a password, except the read-only sudoers rule.
- VERIFIED: `/etc/sudoers.d/vpn-gateway-readonly` allows `happ-diag`, `nft list ruleset`, and `sysctl` forwarding reads (NOPASSWD). Read-only.
- VERIFIED: `nftables.service` disabled and inactive. `nft list ruleset` empty.
- VERIFIED: `net.ipv4.ip_forward=0`, IPv6 forwarding 0.
- VERIFIED (2026-11-14 02:20 check): Happ OFF. No `happ-xray` device. Default route only via `wlan0`.
- VERIFIED: `happd` 4.7.2, PID 990, `happd.service` enabled, active, root, `Restart=always`.

### 2.2 Dell (`dell`)
- VERIFIED: Ubuntu 24.04.4 LTS, kernel 6.17, x86_64. Wi-Fi `wlp8s0` 192.168.0.105/24, gateway 192.168.0.1.
- VERIFIED: `ip_forward=1`.
- VERIFIED: `happd` 2.17.1 (different from the Pi's 4.7.2), `happd.service` active, PID 1978.
- VERIFIED: TUN `tun0` 172.18.0.1/30 owned by NetworkManager connection `tun0`. Table 2022 has `default via 172.18.0.2 dev tun0`.
- VERIFIED: policy rules (live): `8000: from 192.168.0.185 lookup 2022`, `9000` to `172.18.0.0/30`, `9001` suppress_prefixlength, `9002` (dport 53 and `iif tun0` goto 9010), `9003` (lo), `9010 nop`.
- VERIFIED: no `/proc/net/nf_conntrack` (conntrack not loaded). Do not use it.
- VERIFIED: no `adb` installed.
- VERIFIED: sudoers rule `/etc/sudoers.d/vpn-gateway-tcpdump` was **removed** by the user (2026-11-14). Confirmed: `sudo -n` now requires a password (the earlier pass was a cached credential, cleared with `sudo -k`).

### 2.3 Android (`192.168.0.185`)
- VERIFIED (earlier): online, reachable from Dell and Pi. MAC `f0:35:75:23:34:62`.
- VERIFIED (earlier): `ip route get` from Dell sends Android traffic through Dell's `tun0` (table 2022). Android is currently using Dell's Happ as its exit.
- USER: Wi-Fi IP is static `192.168.0.185`. Gateway reported as `192.168.0.185` once and as "DHCP as on Dell" later. **Not confirmed.**
- UNKNOWN: DNS 1/2, prefix, exit IP from a browser. Still outstanding.

---

## 3. Timeline (2026-11-14)

| Time | Event | Evidence |
|---|---|---|
| 00:40 | Alpha probe on Pi: TUNNEL_ACTIVE, Happ intent unknown | VERIFIED |
| 01:06 | Pi Happ OFF snapshot (`baseline-readonly.sh`): no `happ-xray`, 0 xray processes, default via `wlan0` only | VERIFIED |
| 01:07 | Pi Happ ON snapshot: `happ-xray` UP 172.19.0.1/30, one xray-core, `default dev happ-xray metric 1` | VERIFIED |
| 01:18 | Re-check: Happ ON | VERIFIED |
| 01:49:46 to 01:50:20 | Dell `happd` (PID 1978) capture, `strace`: heartbeats only, no state messages | OBSERVED |
| 01:50:14 | Pi xray-core started for client `245849144bf95a45` (the GUI). This is the xray process killed later in the crash test | OBSERVED |
| 01:52:18 to 01:52:54 | Pi `happd` (PID 990) capture #1: GUI stop at 01:52:25.14, start at 01:52:28.42, stop at 01:52:44.85 | OBSERVED |
| 01:57:58 | Crash test #1: `kill -9` xray pid 54022. New xray pid 54070 seen at the first 1-second poll | OBSERVED |
| 01:58 | Python `sqlite3` read-only check of `state.db`: one table, `pending_push` | VERIFIED |
| 02:01:39 to 02:02:39 | OFF monitor (no capture): xray pid changed 54915 to 54954 at 02:01:49. Cause not determined. Happ OFF by 02:02:39 | OBSERVED |
| 02:05:39 | ON (GUI): `get-privilege`, `start xray-core`; event `started` | OBSERVED |
| 02:05:50 | OFF (GUI): `stop xray-core`; event `finished` with data `"0"` | OBSERVED |
| 02:06:02 | ON (GUI): `start xray-core` | OBSERVED |
| 02:06:33 | OFF (GUI): `stop xray-core`; `Process not found` at 02:06:33.71 | OBSERVED |
| 02:09:15.31 | Crash test #2: `kill -9` xray pid 56076 during capture. Socket: `error` "Process crashed", then `finished` with data `"9"` | OBSERVED |
| 02:10:09 | ON (GUI): new xray started (no automatic restart in the 54 s before) | OBSERVED |
| 02:10:11 | OFF (GUI): stop | OBSERVED |
| 02:13:37 | Observer script test (6 s): connect, `get-privilege`, `push-token` received (redacted in logs) | VERIFIED |
| 02:14:58 to 02:16:04 | Observer run interrupted by Ctrl-C. Crash-test kill of xray pid 56984 at 02:16:04 (not captured) | USER |
| 02:17:51 to 02:22:51 | Observer run (300 s, detached): **no lifecycle events received** | OBSERVED |
| 02:20:04 | Kill xray pid 57452 (user). No xray at 02:20:15; no TUN; no restart within 11 s | OBSERVED |
| (session) | Local commit `ebb85a0`: two `chatgpt_Continue_*` transcripts. Checked: no API keys (only chat URLs) | VERIFIED |
| (session) | Design doc written and user decisions recorded | VERIFIED |

---

## 4. Happ investigation: findings

### 4.1 Signals examined

| Candidate signal | Result | Verdict |
|---|---|---|
| `happd.service` active | Active in both OFF and ON | Not an intent signal |
| Socket `get-privilege` / `daemon-version` | Returns `privilege-level` and version. No enabled field | Not an intent signal |
| Socket `status xray-core` | Returns running with pid, start-time, `state:2`, or `Process not found` | **Readiness only** |
| TUN `happ-xray` present/UP | Present in ON, absent in OFF | Readiness only |
| Main default route | `happ-xray` metric 1 when ON, absent when OFF | Readiness only |
| `happd.log` | Records `Started process "xray-core"`. Does not record stop, crash, or restart | Not sufficient |
| `~/.config/Happ.conf` `mode` key | Value `Dark`. This is the UI theme | **Not intent** |
| `/var/lib/happd/state.db` | One table, `pending_push`, no intent flag | Not intent |
| Socket observer (passive) | Receives connection and handshake only, no start/stop/crash events | Not usable for live state |
| Restart behaviour after crash | Inconsistent: one restart within 1 s (test #1), none in 54 s (test #2), none within 11 s (test #3) | Owner unknown (possibly the GUI) |

### 4.2 Conclusion

No supported, passive signal reports the user's Happ enabled or disabled intent. Readiness (TUN, process, route) is observable. Intent is not. Per `CLAUDE.md`, intent must not be inferred from readiness or from `happd` being active. The approved path is a user-set marker (section 9).

---

## 5. Happ control socket: observed protocol

Socket: `/tmp/happd.sock` (root-owned, mode `srw-rw-rw-`). Observed on Pi 4.7.2 and Dell 2.17.1 (heartbeats only on Dell).

### 5.1 Framing (VERIFIED)
- Each frame: 4-byte big-endian length, then UTF-8 JSON, no trailing NUL.
- Requests carry `action` and `request-id`. Replies carry `request-id` and `status`.

### 5.2 Requests seen

| Action | Purpose | Notes |
|---|---|---|
| `heartbeat` | Keep-alive | Sent by the GUI about every 2 s. Reply `status:success` |
| `get-privilege` | Returns `privilege-level` 2 | Read-only |
| `status` (process-id `xray-core`) | Returns pid, running, start-time, state | Read-only. Error `Process not found: xray-core` when stopped |
| `start` (process-id `xray-core`) | Starts xray with executable, environment, and a config in `stdin-data` | **Contains the xray configuration. Never recorded here** |
| `stop` (process-id `xray-core`) | Stops xray | Reply `Process stop requested`, then events |

Other command names exist in the binary (`auto-restart`, `max-restart-attempts`, `restart-delay-ms`, `start-wg`, `stop-wg`, `privilege-level`, `happ-tun`, `happ-xray`, `happ-wg`, `happ-default-tun`, `reclaim-session-processes`, `push-message`). **Not probed.** Their behaviour is UNKNOWN, and sending them could change the live tunnel.

### 5.3 Events seen (sent to the controlling client only)
- `started`: `process-id`, timestamp. Followed by `Process started successfully` (status `started`).
- `finished`: `data` is the exit code. `"0"` after a user stop. `"9"` after a SIGKILL crash.
- `error` with data `Process crashed`: emitted before `finished` on a crash.
- `stdout`: xray log lines. Includes requests to the local `happ-watchdog` host about every 15 s, which looks like a GUI health check.

### 5.4 Observer behaviour (VERIFIED)
- An observer connection receives the `connected` event (`daemon-version`, `privilege-level`), the `push-token` event, and replies to its own requests.
- It received **no** `started`, `finished`, or `error` events during a 5-minute window that included a kill. Lifecycle events are not broadcast.

### 5.5 Heartbeat (VERIFIED)
- The GUI sends `heartbeat` every 2 s. The daemon answers each one. A client that stops sending heartbeats may be dropped (UNKNOWN; observer kept sending them).

---

## 6. Happ lifecycle: observed sequences

### 6.1 Explicit stop (OFF)
1. `stop` request, reply `Process stop requested` (`status: stopping`).
2. xray reports `running:true` for about 30 ms, then exits.
3. Event `finished` with data `"0"`. No `error` event.
4. `status` returns `Process not found: xray-core`.
5. No restart observed in the following 9 to 12 seconds (two cycles).

### 6.2 Explicit start (ON)
1. `get-privilege`, then `start` with executable and config.
2. `started` event, `Process started successfully`.
3. `status` returns running with a new pid and start-time.

### 6.3 Crash (SIGKILL)
1. Kernel reports SIGKILL to the daemon (`SIGCHLD`, `CLD_KILLED`).
2. Event `error`: `Process crashed`.
3. Event `finished` with data `"9"`.
4. Restart: **inconsistent** across three tests (section 4.1). The restart owner is UNKNOWN. Likely the GUI, which polls `happ-watchdog` through xray.

### 6.4 Consequence for design
- A stop and a crash differ on the socket, but only the controlling client sees the events. A gateway service that is not the GUI cannot rely on them.
- Polling `status` tells the gateway whether xray is running, but not why it stopped. Hence the marker design.

---

## 7. Network state (routing, NAT, firewall)

### 7.1 Pi (VERIFIED, Happ OFF at 02:20)
- `ip rule`: `0 local`, `32766 main`, `32767 default`. No Happ policy rules.
- `default via 192.168.0.1 dev wlan0 metric 600`. No `happ-xray`.
- `nft list ruleset`: empty. `nftables.service` disabled.
- `ip_forward=0`.

### 7.2 Pi with Happ ON (VERIFIED, 01:07)
- `happ-xray` UP, `172.19.0.1/30`.
- `default dev happ-xray metric 1` and `default via 192.168.0.1 dev wlan0 metric 600`.
- The `wlan0` default is a fallback. For forwarded client traffic, the gateway must drop anything not leaving via `happ-xray`. This is exactly the WAN-leak case the design must prevent.

### 7.3 Dell (VERIFIED, earlier in session)
- Android traffic (source 192.168.0.185, `iif wlp8s0`) is routed `via 172.18.0.2 dev tun0 table 2022`.
- Rule 8000 is live and must not be removed without the user's approval.
- `tun0` moved about 460 KB each way in 10 seconds while Android was online.

### 7.4 Android (USER, partial)
- Gateway, prefix, DNS, and exit IP not yet confirmed.

---

## 8. Actions taken on hosts (complete list)

| Host | Action | Who | Reverted? |
|---|---|---|---|
| Pi | Hostname set to `pi5home` (`/etc/hosts` updated) | USER (earlier) | No (intended) |
| Pi | `/etc/sudoers.d/vpn-gateway-readonly` created | USER (earlier) | Remove with `sudo rm` if not wanted |
| Pi | Happ toggled OFF/ON repeatedly via GUI | USER | Currently OFF |
| Pi | xray killed with `sudo kill -9` (3 times: 01:57:58, 02:09:15, 02:16:04 / 02:20:04) | USER, approved | Restarted by the GUI or the user |
| Pi | `strace -p 990` attached to `happd` (3 captures) | USER, approved | Detached; daemon unaffected |
| Pi | Observer script run (`/tmp/opencode/happd-observe.py`), read-only | Assistant, with user approval | Finished |
| Pi | `/tmp/opencode/*` files created (traces, logs, observer output) | Assistant and USER | **Not deleted** (see section 12) |
| Dell | `/etc/sudoers.d/vpn-gateway-tcpdump` removed | USER | Intended |
| Dell | `/tmp/opencode/happd-toggle.strace` created (root-owned, heartbeats only) | USER | Not deleted |
| Dell | Nothing else changed. Rule 8000, `tun0`, table 2022 unchanged | — | — |

Nothing changed routing, firewall, forwarding, or Happ configuration on either host.

---

## 9. Decisions

| Date | Decision | By |
|---|---|---|
| 2026-11-14 | Dell Happ 2.17.1 stays independent of the Pi project for now | USER |
| 2026-11-14 | Option 1 for intent investigation: capture socket traffic during toggles | USER |
| 2026-11-14 | Approved removal of Dell tcpdump sudoers rule | USER |
| 2026-11-14 | Approved crash test (kill xray on the Pi) | USER |
| 2026-11-14 | Marker file is the intent source. User sets it alongside the GUI toggle | USER |
| 2026-11-14 | No expiry for the marker | USER |
| 2026-11-14 | Marker path `/var/lib/vpn-gateway/happ.intent` accepted | USER |
| 2026-11-14 | Commit the two `chatgpt_Continue_*` transcripts (checked: no keys) | USER |
| 2026-11-14 | Commit and push all, with secrets excluded | USER |
| Pending | Approval to implement the parser and unit tests (no host changes) | — |
| Pending | Approval for any firewall, routing, or sysctl change | — |
| Pending | Android gateway, DNS, and exit-IP values | — |
| Pending | Dell Happ: keep, move to Pi, or replace | — |
| Pending | Dell rule 8000 removal | — (requires Android to be moved or confirmed) |

---

## 10. Repository state

### 10.1 Commits (local, now pushed)
Earlier commits (pre-session and session, from the handoff): `d0f4f19` plan, `4485afb` Pi baseline, `6c07a53` Pi reinstall checklist, `2851a26` baseline script and user actions, `0b54889` README next steps, `6965f93` Happ OFF snapshot, `cf9dc6f` Happ ON snapshot and comparison, `11393bd` explicit user commands, `a8440f7` command corrections, `2d2e24e` consolidated new-host commands, `34ce9d4` Android unreachable note, `1da582a` narrow sudoers rule doc for Dell capture, `5de5f00` Dell capture: no traffic, `b12f5df` Android online: traffic through Dell tun0, `1a71b32` unresolved Android gateway check, `59cab2c` handoff.

Session commits: `ebb85a0` two `chatgpt_Continue_*` transcripts.

Final commit of this session (documentary, marker design, observer script, `.gitignore`): listed in the git log after push.

### 10.2 Files of interest
- `DEVELOMPENT_PLAN.md`: phased plan (note filename typo, kept as-is).
- `CLAUDE.md`: project rules, state model, safety rules.
- `README.md`: plain-language overview for non-developers.
- `docs/RUNNING-LOG.md`: detailed running log (formerly the root README).
- `setup-vpn-gateway-alpha.sh`: read-only diagnostic, v0.1.0-alpha.
- `scripts/baseline-readonly.sh`: read-only baseline for Pi and Dell.
- `scripts/happd-observe.py`: passive socket observer (get-privilege and heartbeat only; redacts push token).
- `docs/`: all topic notes (section 13).
- `.gitignore`: excludes secrets, databases, captures, logs.
- `chatgpt_Continue_VPN_Gateway_Setup_2026-11-14_0017.md` and `..._0021.md`: chat transcripts.

### 10.3 Historical reference (do not run on Pi)
- `setup-android-vpn-gateway.sh`, `setup-android-vpn-gateway.md`, `setup-android-vpn-gateway_session_debug-state.md`: Ubuntu-as-gateway with iptables. Historical only.
- `RASPBERRY_PI_GATEWAY_LLM_HANDOVER.md`: referenced by the plan and handoff. Not checked in this session (see section 11).

---

## 11. Known issues and discrepancies

1. OS: `DEVELOMPENT_PLAN.md` and `CLAUDE.md` say Bookworm. The Pi is trixie. Correct the docs.
2. Hostname: docs say `pi5os` or `raspberrypi`. The verified value is `pi5home`.
3. Android: `user-commands-2026-11-14.md` records Android unreachable (ARP FAILED). The handoff records it online and routed through Dell. The later record is more likely correct, but the older text is still in the file.
4. Duplicate docs: `docs/pi-reinstall.md` and `docs/new-host-commands.md` overlap.
5. Baseline note: `baseline-2026-11-14-pi.md` said `mode` in `Happ.conf` might reflect enabled/disabled. Disproved: it is the UI theme (`Dark`).
6. Restart owner: inconsistent restart behaviour after a crash (section 6.3). Not resolved.
7. OFF monitor at 02:01:49 (xray pid changed from 54915 to 54954 without a capture): cause not determined.
8. `RASPBERRY_PI_GATEWAY_LLM_HANDOVER.md`: not verified to exist in the repository during this session.
9. Dell's happd version 2.17.1 differs from the Pi's 4.7.2. Any Dell-specific behaviour is separate.
10. Happ command names other than those in section 5.2 are unverified and not probed.
11. Observer does not receive lifecycle events (section 5.4). Any gateway design must not depend on it.

---

## 12. Security and secrets

- VERIFIED: `.gitignore` excludes `.env`, keys, certificates, databases (`*.db`, `subs.db`), captures (`*.strace`, `*.pcap`), logs (`*.log`), and `Happ.conf`.
- VERIFIED: a repository-wide scan (regex for API keys, tokens, private keys, VLESS/VMess/Trojan URIs, UUIDs) found no credentials. Matches were documentation text or chat URLs.
- VERIFIED: the push token from the daemon is redacted by `scripts/happd-observe.py`.
- **Risk, not in repository:** the Pi's `/tmp/opencode/happd-toggle.strace`, `/tmp/opencode/happd-off2.strace`, and `/tmp/opencode/happd-crash2.strace` contain the xray configuration sent in `start` requests. They are on the Pi, not in git. The user has said they do not need them deleted. If the Pi is shared or backed up, delete them: `sudo rm /tmp/opencode/happd-*.strace` on the Pi.
- **Risk, not in repository:** `/tmp/opencode/pi-happ-*.txt` and `/tmp/opencode/happd-observer*.log` may contain IPs and timestamps. The observer log has no tokens.
- Never commit: `Happ.conf`, `subs.db`, `state.db`, any `start` request payload, or any file from `/tmp/opencode`.

---

## 13. Topic documents

| File | Contents |
|---|---|
| `docs/handoff-2026-11-14.md` | Entry point for a new chat |
| `docs/baseline-2026-11-14-pi.md` | Pi baseline (partly superseded) |
| `docs/happ-off-on-test-2026-11-14.md` | OFF and ON snapshots compared |
| `docs/user-actions-2026-11-14.md` | Steps only the user can do |
| `docs/user-commands-2026-11-14.md` | Commands by host |
| `docs/new-host-commands.md` | Rebuild and check commands; sudoers rules; rollback |
| `docs/pi-reinstall.md` | Pi reinstall checklist |
| `docs/happ-intent-marker-design-2026-11-14.md` | Marker design, decisions, failure matrix, tests |
| `docs/PROJECT-DOCUMENTARY-2026-11-14.md` | This document |

---

## 14. Status against the development plan

| Phase | Status | Notes |
|---|---|---|
| 0. Baseline | Mostly done | Pi OFF and ON captured. Android gateway, DNS, exit IP not confirmed. Dell `tun0` and rule ownership partly traced |
| 1. Intent detection | Design approved (marker). Parser and tests not started | Socket investigation complete (section 4). Observer tests complete |
| 2. Architecture | Not started | Needs Phase 1 implementation and a free routing table choice |
| 3. Config and tests | Not started | Awaiting approval |
| 4. Pi data plane | Not started | Requires explicit approval |
| 5. Lifecycle | Not started | |
| 6. Android cutover | Not started | Blocked on Android values and Phases 1 to 5 |
| 7. Dell agent | Not started | Blocked; rule 8000 cleanup needs approval |
| 8. Packaging | Not started | |

---

## 15. Next steps

1. **Implement the Phase 1 parser and unit tests** (no host changes). Requires explicit approval. Scope: marker parsing, ownership and symlink checks, state table, debounce logic. Tests run without root.
2. **Android values:** gateway, prefix, DNS 1 and 2, static or DHCP, exit IP from a browser.
3. **Dell Happ decision:** keep, move to Pi, or replace.
4. **Fix the documentation discrepancies** in section 11 (OS, hostname, Android record, duplicate docs).
5. **Delete the Pi trace files** containing the xray configuration (section 12), if you want them removed.
6. **Resolve the restart owner** (section 6.3): optional test with the GUI idle and xray killed, or confirm that the GUI always restarts xray.
7. Later: design the Pi data plane (Phase 2) and get approval before any firewall, routing, or sysctl change.

---

## 16. How to repeat the key checks

Run on the Pi as `bliss` unless marked root. Read-only unless marked.

```bash
# Readiness (read-only)
ip -br link show happ-xray 2>&1
ip route show default
pgrep -af "/opt/happ/bin/core/xray" | grep -v pgrep

# Socket status (read-only): see scripts/happd-observe.py for framing
# Observer for 120 s (read-only, no start/stop)
python3 scripts/happd-observe.py 120 /tmp/opencode/happd-observer.log

# Baseline (read-only)
bash scripts/baseline-readonly.sh

# State DB schema (read-only, root)
sudo python3 -c "import sqlite3; c=sqlite3.connect('file:/var/lib/happd/state.db?mode=ro', uri=True); print([r[0] for r in c.execute(\"select sql from sqlite_master\")])"
```

Do not run `/opt/happ/bin/happ-diag --repair`, which restarts `happd`.

Do not run `sudo systemctl enable nftables`. The stock config starts with `flush ruleset`.

---

## 17. Glossary

- **Happ**: the VPN client. `happd` is its daemon. `xray-core` is the tunnel process it starts.
- **TUN `happ-xray`**: the tunnel interface, `172.19.0.1/30` on the Pi when up.
- **Intent**: the user's enabled or disabled choice for Happ. Not readiness.
- **Readiness**: TUN, xray process, and route present. Does not imply intent.
- **Fail closed**: block client Internet rather than fall back to ordinary Wi-Fi WAN.
- **Marker**: the planned root-owned file recording user intent (section 9).
- **Observer**: a socket client that only listens and sends harmless requests.
