# LLM handover: VPN gateway project

Read this file first. It is the complete, self-contained brief for any future AI assistant or developer working on this repository. It replaces `CLAUDE.md`, which was removed on 2026-11-14 at the user's request. The rules in section 4 are the project's requirements. Do not drop them without the user's explicit instruction.

Evidence labels:
- **VERIFIED**: observed directly on a host, with date and method.
- **OBSERVED**: seen in a captured trace or log, with timestamp.
- **USER**: stated by the user. Not independently checked.
- **INFERRED**: reasoned from evidence.
- **UNKNOWN**: not checked.

Dates are 2026-11-14 unless stated. Times are +03:00.

---

## 1. What the user wants

- A **one-click install** on a Raspberry Pi 5, which shares its Happ VPN with other devices on the home network.
- **Day-to-day use:** the user turns Happ ON or OFF in the Happ GUI, as usual. The gateway follows that choice automatically. There is no second step.
- The only manual steps on client devices are a **one-time Wi-Fi setting**: set the Pi as the default gateway.
- Clients in scope: Android (`192.168.0.185`) and the Ubuntu computer `dell` (`192.168.0.105`).
- **IPv4 only.** IPv6 is not forwarded and not NAT'd.

Behaviour the user expects:

| Happ state (set in GUI) | Client internet behaviour |
|---|---|
| ON, tunnel up | Exits through Happ's VPN |
| OFF (user stopped Happ) | Exits through the normal router, with no VPN and no block |
| ON but tunnel down or crashed | **Blocked.** Never falls back to the normal connection |
| Unknown or unreadable state | **Blocked** (fail closed) |

The user accepted this design on 2026-11-14 with the trace-based approach described in section 6.

---

## 2. Environment

### 2.1 Hosts (VERIFIED unless noted)

| Host | Address | Role | Notes |
|---|---|---|---|
| Pi `pi5home` | `192.168.0.118` on `wlan0` | Future gateway | Raspberry Pi 5, Debian 13 (trixie), aarch64, kernel 6.18.29+rpt-rpi-2712. User `bliss`, SSH key login. Passwordless `sudo` only for read-only commands |
| Dell `dell` | `192.168.0.105` on `wlp8s0` | Client, and today also a VPN exit for Android | Ubuntu 24.04, kernel 6.17, x86_64. Runs its own Happ 2.17.1 |
| Android | `192.168.0.185` (static, USER) | Client | MAC `f0:35:75:23:34:62`. Gateway, prefix and DNS not confirmed |
| Router | `192.168.0.1` | LAN default gateway | |

Hostname on the Pi: `pi5home` (static). Some prompts show `raspberrypi`, which is a transient name.

### 2.2 Happ

| Item | Pi | Dell |
|---|---|---|
| Daemon | `happd` 4.7.2, `/opt/happ/bin/happd`, PID 990 | `happd` 2.17.1, PID 1978 |
| Service | `happd.service`, enabled, active, `Restart=always`, runs as root | active |
| Control socket | `/tmp/happd.sock` (root-owned, mode `srw-rw-rw-`) | not probed |
| State DB | `/var/lib/happd/state.db` (root only). Only table `pending_push`. **No intent flag** | not checked |
| Log | `/var/log/happd.log` (world-readable). Records xray starts only | not checked |
| Tunnel interface | `happ-xray`, `172.19.0.1/30`, present only when ON | `tun0`, `172.18.0.1/30` |
| Tunnel process | `/opt/happ/bin/core/xray` (xray-core 26.10.29) | not checked |
| User config | `~/.config/Happ.conf`. `mode=Dark` is the UI theme, **not** VPN state | not checked |

Do not read, print, or commit `Happ.conf` values beyond key names. It can contain server data.

### 2.3 Pi network state (VERIFIED, 02:20 check, Happ OFF)

- `ip_forward=0`. IPv6 forwarding off.
- Default route only via `wlan0`: `default via 192.168.0.1 dev wlan0 metric 600`.
- No `happ-xray` device.
- `ip rule`: `0 local`, `32766 main`, `32767 default`. No Happ policy rules.
- `nft list ruleset`: empty.
- `nftables.service`: disabled. **Never enable it.** Its stock config starts with `flush ruleset`.

### 2.4 Dell network state (VERIFIED earlier in session)

- `ip_forward=1`.
- Android traffic is currently routed through Dell's Happ: rule `8000: from 192.168.0.185 lookup 2022`, table 2022 `default via 172.18.0.2 dev tun0`.
- Other rules (`9000` to `9010`, `9003` for `lo`) are part of the same old experiment. Owner: the old Ubuntu gateway design, not yet proven.
- Dell's conntrack is not loaded (`/proc/net/nf_conntrack` absent).
- Do not remove any of these rules without the user's approval.

### 2.5 Android

- USER: static IP `192.168.0.185`. Gateway reported once as `192.168.0.185` (probably a misread) and once as "DHCP, as on Dell". **Not confirmed.**
- UNKNOWN: DNS 1 and 2, prefix (expected `/24`), exit IP from a browser.

---

## 3. Happ intent: what has been established

### 3.1 Signals tested

| Candidate | Result | Use |
|---|---|---|
| `happd.service` active | Active in both OFF and ON | Not intent |
| `get-privilege`, `daemon-version` on socket | Returns version and privilege level. No enabled field | Not intent |
| `status` for `xray-core` on socket | Running with pid and start time, or `Process not found` | Readiness only |
| TUN `happ-xray` present | Present ON, absent OFF | Readiness only |
| Default route via `happ-xray` | Present ON, absent OFF | Readiness only |
| `happd.log` | Records `Started process "xray-core"`. No stop, crash, or restart lines | Not sufficient |
| `Happ.conf` `mode` | `Dark`, the UI theme | Not intent |
| `state.db` | One table `pending_push`, no intent | Not intent |
| Passive socket observer | Receives only the connection event, a push token, and its own replies | Not usable for lifecycle |
| Restart after crash | Inconsistent: restart within 1 s once, none for 54 s once, none for 11 s once | Owner unknown, possibly the GUI |

### 3.2 Socket protocol (OBSERVED via `strace` on `happd`, 2026-11-14)

Framing: each message is a 4-byte big-endian length, then UTF-8 JSON. No trailing NUL.

Requests the GUI sends:

| Action | Fields | Reply |
|---|---|---|
| `heartbeat` | `request-id` | `{"request-id":...,"status":"success"}`, about every 2 s |
| `get-privilege` | `request-id` | `privilege-level` 2, `status` success |
| `status` | `process-id:"xray-core"`, `request-id` | `running:true`, `pid`, `start-time`, `state:2`. Or error `Process not found: xray-core` |
| `start` | `process-id`, `executable`, `environment`, `arguments`, `stdin-data` (**contains the xray config, never log or commit**) | event `started`, then `Process started successfully` |
| `stop` | `process-id:"xray-core"`, `request-id` | `Process stop requested` (`status:stopping`) |

Events, sent **only to the controlling client (the GUI)**:

| Event | Payload | Meaning |
|---|---|---|
| `started` | `process-id` | xray started |
| `finished` | `data`: exit code as a string | `"0"` after a user stop. `"9"` after SIGKILL (crash) |
| `error` | `data:"Process crashed"` | Emitted before `finished` on a crash |
| `stdout` | `data`: xray log line | Includes requests to `happ-watchdog` about every 15 s. This is probably a GUI health check |

Other command names exist in the `happd` binary but are **not probed**: `auto-restart`, `max-restart-attempts`, `restart-delay-ms`, `start-wg`, `stop-wg`, `privilege-level`, `happ-tun`, `happ-xray`, `happ-wg`, `happ-default-tun`, `reclaim-session-processes`, `push-message`. Do not send them: they may change the live tunnel.

### 3.3 Lifecycle sequences (OBSERVED)

- **User stop (OFF):** `stop` request, then `stopping`. xray runs about 30 ms more, then exits. `finished` with `"0"`. No `error` event. Status then returns `Process not found`. No restart seen within 9 to 12 s, in two cycles.
- **User start (ON):** `get-privilege`, then `start`. `started` event. Status returns running, with a new pid.
- **Crash (SIGKILL):** kernel reports `SIGCHLD`, `CLD_KILLED`, `SIGKILL`. Then `error` `Process crashed`, then `finished` with `"9"`. No automatic restart within 54 s in one test. Restart owner unknown.

### 3.4 Observer clients (OBSERVED, important)

A socket client that is not the GUI receives **no** `started`, `finished`, or `error` events during a 5-minute window that included a kill. Lifecycle events go only to the controlling connection.

Consequence: the gateway cannot learn intent from the socket by being a passive client. It has to observe the GUI's own traffic.

---

## 4. Project requirements (replace CLAUDE.md)

These come from the user's own specification and the earlier plan. Keep them unless the user changes them.

1. **Do not break the Pi.** Keep the Pi's own default routing, `happd`, and Happ's routes and rules intact. The Pi itself is not routed through the gateway logic.
2. **No WAN leak.** When Happ is ON, client internet traffic must never fall back to `wlan0`. If the tunnel is missing, drop it.
3. **Unknown means blocked.** Missing, unreadable, or contradictory state is never treated as OFF.
4. **IPv4 only.** Do not add IPv6 forwarding or NAT. Drop forwarded client IPv6. Same-LAN router advertisements can give clients a direct IPv6 path. This must be stated, not hidden.
5. **Native nftables only, owned table.** Create a project-owned table. **Never flush the global ruleset. Never enable `nftables.service`.**
6. **Protect unrelated routing.** Do not flush tables. Do not reset NetworkManager. Inspect rule priorities and table ownership before choosing a table. Table 2022 is used by the old experiment and is not free by default.
7. **No blind cleanup on Dell.** Rules 8000 and 9000 to 9010, `tun0`, and table 2022 are removed only after their ownership is proven and the user approves.
8. **No client cutover before tests.** Routing, NAT, return traffic, DNS, and the kill switch must be tested first.
9. **Safe changes.** Before any persistent or disruptive change: explain it, back it up, give a rollback command, and get explicit user approval.
10. **Uninstall only project-owned things.** Remove only the files, nftables table, sysctls, and units this project created.
11. **Do not run `happ-diag --repair`.** It restarts `happd`.
12. **Do not commit secrets.** Never commit `Happ.conf`, `subs.db`, `state.db`, `start` payloads, or anything from `/tmp/opencode`. `.gitignore` covers the common cases.
13. **Document every assumption** with a VERIFIED, OBSERVED, INFERRED, or UNKNOWN label and its date and source.
14. **Verify, don't assume.** A successful service start proves nothing. Check routes, nftables counters, packet flow, return traffic, DNS, and the public IPv4 from each client.

---

## 5. Approved design (from 2026-11-14)

### 5.1 Components

1. **One-click installer** (`scripts/new-host-setup.sh`): packages, nftables kept off, Happ check, repo update, read-only sudo rule, boot-time read-only report. Status: **written and pushed. Partly run on the Pi.** The first run failed at the apt step because of unrelated third-party repos. That is now tolerated (commit `63d06ee`). The user must run it again.
2. **Happ GUI watcher** (root service, to be built): observes the GUI's control messages on the `happd` socket in real time and derives the intent. Design in section 5.2.
3. **Gateway controller** (to be built): applies the owned nftables table and project routing rules according to the intent state. It must be idempotent, use a lock, and fail closed.
4. **Client setup**: manual, once, on Android and Dell (Pi `192.168.0.118` as the Wi-Fi gateway).

### 5.2 Happ GUI watcher (approved approach)

- Attach to `happd` (PID from `systemctl show -p MainPID --value happd.service`) with `strace -f`, filtering `read`, `write`, `sendmsg`, `recvmsg`, and parse the messages in memory.
- **Never write the raw trace to disk.** Start payloads contain the xray configuration. The parser keeps only: action, process-id, request-id, event, and exit code.
- Derive state:

| Observed | Intent state |
|---|---|
| `started` event, or a `status` reply with `running:true` | ENABLED |
| `stop` request followed by `finished` with `"0"` | DISABLED |
| `error` `Process crashed`, or `finished` with a non-zero code | ENABLED_DOWN (fail closed) |
| Watcher not running, or attach failed, or parse error | UNKNOWN (fail closed) |
| Happ restarted, `happd` PID changed | re-attach, UNKNOWN until the next event or a status poll |

- On startup, poll `status xray-core` (read-only) to set the initial state. Do not infer DISABLED from absence at startup. Start in UNKNOWN until a stop is actually observed. This matters after reboot.
- Debounce: a state changes only after it holds for N polls or events. Default N = 3.
- The watcher writes only its own state file (for example `/run/vpn-gateway/state`) and logs state changes. It never logs payloads.

**Known risks, stated to the user:**
- Depends on Happ's undocumented protocol. A Happ update can break it. Re-check the protocol after every Happ update.
- ptrace on `happd` adds overhead. It has not been measured under continuous client traffic. Measure before enabling for clients.
- Runs as root. It reads control messages and never sends any.
- If it is not running, all client traffic is blocked. This is the fail-closed choice.

### 5.3 Gateway controller (to be designed, not built)

- Owned nftables table, for example `inet vpn_gateway`. Forward chain: LAN to `happ-xray` allowed. Established return allowed. Masquerade on `happ-xray`. Drop all other client WAN egress. Drop forwarded IPv6.
- In DISABLED: allow client WAN via `wlan0` with masquerade on `wlan0`. This is the only ordinary path, and it applies only when DISABLED is positively observed.
- Policy routing per client IPv4 address, using a free table chosen after inspection. Not table 2022.
- Forwarding via a project sysctl file, only after approval.
- Transitions: drop rules first, then change the path. Never open a gap where clients use the normal path while the state is unknown.
- Lock with `flock`. Idempotent.
- Rollback: a `--rollback` command that removes only the owned table and the owned sysctl file, and restores the previous forwarding value.

### 5.4 Build order (user-approved)

1. One-click install and remove script on the Pi (exists, needs re-run).
2. Happ GUI watcher, read-only first: it logs the states it derives, changes nothing else, and is tested while the user toggles Happ.
3. Gateway controller, in dry-run mode first: prints the nftables and routing plan without applying.
4. Controlled application on the Pi, with a backup, a rollback, and a test window. Tests: Happ ON, OFF, crash, reboot, Wi-Fi drop.
5. Android, with the user doing the Wi-Fi setting and testing. Then Dell, after its own Happ and rule decision.

Each step needs the user's approval before the next one starts.

---

## 6. What is built, and what is not

| Item | Status |
|---|---|
| `setup-vpn-gateway-alpha.sh` (read-only probe) | Exists. Read-only. Reports `TUNNEL_ABSENT`, not "disabled" |
| `scripts/baseline-readonly.sh` (read-only report) | Exists. Used by the boot service |
| `scripts/happd-observe.py` (passive observer) | Exists. Shows that observers get no lifecycle events. Not a watcher |
| `scripts/new-host-setup.sh` (one-click install) | Exists. Partly run on the Pi |
| Boot service `vpn-gateway-boot-baseline.service` | Defined by the installer. Not yet verified on the Pi |
| Read-only sudo rule | Active on the Pi. The file name in the docs was not found in `/etc/sudoers.d`. Source not traced |
| Happ GUI watcher | **Not built** |
| Gateway controller (nftables, routing, sysctl) | **Not built** |
| Marker file design | Superseded by the trace-based approach (section 5.2). Kept as fallback in `docs/happ-intent-marker-design-2026-11-14.md` |
| Unit tests | **None yet** |
| Android gateway setup | **Not done.** Values not confirmed |
| Dell Happ and rules | **Not changed.** Decision pending |

---

## 7. Repository

- Remote: `https://github.com/bayunderground/setup-vpn-gateway.git`, branch `main`.
- Latest pushed commit at the time of writing: `63d06ee` (new-host script tolerance fix). Earlier: `ca66186` (README install section), `fafaafa` (new-host script), `2fe6f03`, `0f69013`, `37e4ee8`, `aad6f62`.
- Pi clone: `~/setup-vpn-gateway`, updated to `63d06ee`.
- `CLAUDE.md`: deleted at the user's request. The deletion is committed in `5b611e5`.
- Untracked before this document: `.gitignore` and `scripts/happd-observe.py` (both pushed in `aad6f62`).

### 7.1 Files

| Path | Purpose |
|---|---|
| `README.md`, `README_RU.md` | Plain-language overview for new users (English and Russian). Install command, IP table, user questions, safety rules |
| `DEVELOMPENT_PLAN.md` | Original phased development plan (filename typo kept) |
| `RASPBERRY_PI_GATEWAY_LLM_HANDOVER.md` | Older design handover. Not reviewed against the current findings in this session. This document supersedes it |
| `setup-vpn-gateway-alpha.sh` | Read-only Happ probe |
| `scripts/new-host-setup.sh` | One-click install (`--uninstall` removes what it added) |
| `scripts/baseline-readonly.sh` | Read-only baseline report |
| `scripts/happd-observe.py` | Passive socket observer. Redacts push tokens |
| `docs/LLM-HANDOVER.md` | This document |
| `docs/PROJECT-DOCUMENTARY-2026-11-14.md` | Full narrative and timeline of 2026-11-14 |
| `docs/happ-intent-marker-design-2026-11-14.md` | Marker design (fallback) |
| `docs/handoff-2026-11-14.md` | Earlier handoff |
| `docs/baseline-2026-11-14-pi.md` | Earlier Pi baseline (partly superseded) |
| `docs/happ-off-on-test-2026-11-14.md` | OFF and ON snapshots |
| `docs/user-actions-2026-11-14.md`, `docs/user-commands-2026-11-14.md` | Steps for the user |
| `docs/new-host-commands.md`, `docs/pi-reinstall.md` | Older command lists. Overlap with `new-host-setup.sh` |
| `docs/RUNNING-LOG.md` | Older detailed log (formerly the root README) |
| `setup-android-vpn-gateway.sh`, `.md`, `_session_debug-state.md` | Historical Ubuntu iptables gateway. **Do not run on the Pi. Do not copy its iptables logic** |
| `chatgpt_Continue_*.md` | Chat transcripts. Checked: no keys |

---

## 8. Commands

Run on the Pi as `bliss` unless noted.

### 8.1 Safe, read-only

```bash
ip -br link show happ-xray 2>&1                 # tunnel present?
ip route show default                           # default route
pgrep -af "/opt/happ/bin/core/xray" | grep -v pgrep   # xray running?
cat /proc/sys/net/ipv4/ip_forward
sudo -n nft list ruleset                        # only if sudo rule is active
bash ~/setup-vpn-gateway/scripts/baseline-readonly.sh
python3 ~/setup-vpn-gateway/scripts/happd-observe.py 60 /tmp/opencode/observer.log
systemctl is-enabled nftables.service           # expect: disabled
```

### 8.2 Install and remove (one click)

```bash
bash ~/setup-vpn-gateway/scripts/new-host-setup.sh                  # install
PI_HOSTNAME=pi5home bash ~/setup-vpn-gateway/scripts/new-host-setup.sh   # also set hostname
bash ~/setup-vpn-gateway/scripts/new-host-setup.sh --uninstall      # remove what it added
```

Happ must be installed separately, with its own installer. The script reports if it is missing.

### 8.3 Forbidden

- `/opt/happ/bin/happ-diag --repair`: restarts `happd`.
- `sudo systemctl enable nftables`: stock config flushes all firewall rules.
- `nft flush ruleset`, or any command that flushes the global ruleset.
- Sending undocumented socket commands (section 3.2). Especially `start` or `stop` without the user asking.
- `strace` writing raw output to disk on the Pi (start payloads contain config). Parse in memory only.
- Deleting or editing `/tmp/opencode/*` without telling the user. They are evidence.

### 8.4 Repository commands

```bash
cd ~/setup-vpn-gateway && git pull --ff-only
git log --oneline -5
```

---

## 9. Known issues

1. **Docs contradict the host.** `DEVELOMPENT_PLAN.md` and older docs say Bookworm and `pi5os`. The host is trixie and `pi5home`.
2. **Android record conflict.** `user-commands-2026-11-14.md` records Android offline (ARP FAILED). Later records say online and routed through Dell. The later record is more likely right.
3. **Duplicate command docs.** `docs/pi-reinstall.md` and `docs/new-host-commands.md` overlap with `scripts/new-host-setup.sh`.
4. **Restart owner unknown.** After a crash, a restart was seen once but not twice. Test with the GUI idle before relying on it.
5. **OFF monitor at 02:01:49.** Xray pid changed from 54915 to 54954 with no capture. Cause not determined.
6. **Brave apt repository** returns 403 and its signature changed. It is not part of this project. The user may remove it: `/etc/apt/sources.list.d/brave-browser-release.sources`.
7. **Boot baseline log grows.** `/var/log/vpn-gateway/boot-baseline.log` is appended at every boot and never rotated.
8. **Plan conflict.** `DEVELOMPENT_PLAN.md` Phase 8 says not to install the alpha probe as a service. The boot service runs `baseline-readonly.sh`, not the alpha probe. The user asked for it. Keep the distinction clear.
9. **Old trace files on the Pi** contain xray configuration: `/tmp/opencode/happd-toggle.strace`, `happd-off2.strace`, `happd-crash2.strace`. Not in git. The user said they do not need them deleted. Mention again before any backup.
10. **Read-only sudo rule file.** The documented file `/etc/sudoers.d/vpn-gateway-readonly` was not in the directory listing, yet `sudo -l` shows the rule. The source is not traced.
11. **`openvpn.service` is enabled** on the Pi but runs `/bin/true`. Not part of this project. Harmless.
12. **Dell has its own Happ 2.17.1** and carries Android's traffic today. Its rules must not be touched without a decision.

---

## 10. Decisions log

| Date | Decision | By |
|---|---|---|
| 2026-11-14 | Dell Happ stays independent for now | USER |
| 2026-11-14 | Trace-based observer to read the GUI's own control messages (option 1) | USER |
| 2026-11-14 | Approved removing Dell's tcpdump sudoers rule (done) | USER |
| 2026-11-14 | Approved crash test (done) | USER |
| 2026-11-14 | Marker file design: user sets it. No expiry. Path `/var/lib/vpn-gateway/happ.intent` | USER (superseded by trace-based approach) |
| 2026-11-14 | Commit chatgpt transcripts (done) | USER |
| 2026-11-14 | Commit and push all, with secrets excluded (done) | USER |
| 2026-11-14 | Plain-language README, Russian README, IP table (done) | USER |
| 2026-11-14 | Remove `CLAUDE.md`, do not follow it. This document replaces it | USER |
| 2026-11-14 | "One click" means install and setup. Happ is still toggled in its GUI | USER |
| 2026-11-14 | Approved the trace-based watcher design, with the build order in section 5.4 | USER (interpreted from the request for documentation) |
| Pending | Re-run `new-host-setup.sh` on the Pi | USER |
| Pending | Build the GUI watcher (read-only first) | — |
| Pending | Build the gateway controller, dry-run first | — |
| Pending | Any firewall, routing, or sysctl change on the Pi | — (needs approval per step) |
| Pending | Android gateway, DNS, prefix, exit IP | USER |
| Pending | Dell Happ: keep, move to Pi, or replace | USER |
| Pending | Dell rules 8000 and 9000 to 9010, table 2022, `tun0` | USER (after Android is settled) |
| 2026-11-14 | Commit the `CLAUDE.md` deletion (done in `5b611e5`, together with this document) | USER |

---

## 11. How to continue (for an assistant starting a new session)

1. Read sections 1, 4, 5 and 10. Then check the Pi's current state with the read-only commands in section 8.1. Do not assume the state in this document is still current.
2. Ask the user what they want to do next, and check whether the decisions in section 10 changed.
3. Before any change to the Pi or Dell: explain it, back it up, give the rollback, and wait for approval.
4. Keep labels (VERIFIED, OBSERVED, INFERRED, UNKNOWN) on every new finding, with its date and source.
5. Keep the user's language. The user works in English and Russian. Documentation is in English, with a Russian README.
6. Commit and push only what the user asked for. Never commit secrets (section 4, rule 12).

---

## 12. Glossary

- **Happ**: the VPN client. `happd` is its daemon. Its GUI sends control messages over the socket.
- **xray-core**: the tunnel process that `happd` starts.
- **`happ-xray`**: the tunnel interface on the Pi, present only while Happ is ON.
- **Intent**: whether the user wants Happ ON or OFF. Not the same as readiness.
- **Readiness**: the tunnel is up, the process runs, the route exists.
- **Fail closed**: block client internet rather than fall back to the normal connection.
- **Gateway**: the device other devices send traffic to. Here, the Pi.
- **nftables**: the Linux firewall. The project owns one table and never flushes the whole ruleset.
- **TUN**: a virtual network interface that carries the VPN tunnel.
