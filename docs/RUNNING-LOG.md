# Setup VPN Gateway — Next Steps (2026-11-14)

This repo is for a shared IPv4-only Happ VPN gateway on a Raspberry Pi 5 (`pi5home`, `192.168.0.118`). The Dell machine (`dell`, `192.168.0.105`) and Android (`192.168.0.185`) are clients.

Current status: discovery and diagnostics only. No gateway forwarding, NAT, nftables rules, or client cutover is installed.

## What is done

- Pi hostname set to `pi5home`.
- Pi `sudo -n` works for read-only root commands (NOPASSWD rule present).
- Pi baseline: `ip_forward=0`, IPv6 forwarding off, `nft list ruleset` empty, `nftables.service` disabled, Happ TUN `happ-xray` UP and main default route.
- Dell baseline: stale rule `8000: from 192.168.0.185 lookup 2022` still present. Dell `ip_forward=1`. Dell `tun0` present.
- Happ socket `/tmp/happd.sock` answers the connection, but no documented enabled/disabled field has been found yet.
- Android is not reachable from Dell right now (ping gets no reply), and Dell's conntrack shows no Android flows.

## What you need to do

### 1. Android gateway settings (required before any Dell cleanup)

Open the Android Wi-Fi settings for the network and record:

- IP address (expected `192.168.0.185`)
- Gateway (`192.168.0.105` means Dell; `192.168.0.1` means the router; `192.168.0.118` means the Pi)
- Prefix length / netmask (expected `/24`)
- DNS servers
- Whether the address is static or DHCP

Send these values back. Do not change anything on Android yet.

Why it matters: Dell's rule `8000: from 192.168.0.185 lookup 2022` only matters if Android uses Dell as its gateway. If Android uses the router, the rule is stale.

### 2. Happ OFF/ON test on the Pi

The goal is to see what changes in the daemon and TUN when Happ is switched off and on.

1. Set Happ to **OFF** on the Pi and tell me.
2. I will run:
   ```bash
   bash ~/setup-vpn-gateway/scripts/baseline-readonly.sh
   ```
   on the Pi and save the output.
3. Set Happ to **ON** and tell me.
4. I will run the same command again and compare.

Things to watch for: whether `happ-xray` disappears, whether the main default route changes, and whether `happd` reports a different state through `happ-diag`.

If you prefer, you can run the script yourself and send the output.

### 3. Dell's Happ (decide)

Dell runs `happd` **2.17.1** and a `tun0` at `172.18.0.1/30`. The Pi runs `happd` **4.7.2** with `happ-xray` at `172.19.0.1/30`.

Recommendation: treat Dell's Happ as a separate install from the old Ubuntu gateway experiment, not part of this Pi design. Do not use Dell's `happd` state as the gateway signal.

Please confirm:

- Is Dell's Happ still used for anything you need?
- If not, should it be uninstalled or left running?

No Dell Happ change is made until you answer.

### 4. Dell cleanup (hold until steps 1–3 are answered)

Dell has these stale policy rules:

```
8000:  from 192.168.0.185 lookup 2022
9000:  from all to 172.18.0.0/30 lookup 2022
9001:  from all lookup 2022 suppress_prefixlength 0
9002:  not from all dport 53 lookup main suppress_prefixlength 0
9002:  from all iif tun0 goto 9010
9003:  not from all iif lo lookup 2022
9003:  from 0.0.0.0 iif lo lookup 2022
9003:  from 172.18.0.0/30 iif lo lookup 2022
9010:  from all nop
```

Table 2022 has `default via 172.18.0.2 dev tun0`.

Decision needed:

- **Approve** removing only rule 8000, after Android is confirmed not to use Dell.
- **Hold** the others until Dell's Happ is confirmed as a separate install.

The command for rule 8000 is listed in `docs/user-actions-2026-11-14.md`. Do not run it yet.

## Commands reference

- Pi baseline (read-only): `bash ~/setup-vpn-gateway/scripts/baseline-readonly.sh`
- Pi reinstall checklist: `docs/pi-reinstall.md`
- Pi baseline report: `docs/baseline-2026-11-14-pi.md`
- User actions: `docs/user-actions-2026-11-14.md`

## Safety notes

- Do not run `happ-diag --repair`; it restarts `happd`.
- Do not enable `nftables.service`; the stock `/etc/nftables.conf` starts with `flush ruleset`.
- Do not flush the global ruleset or remove routing rules without an approved plan.
- Unknown Happ state must be treated as disabled-unsafe: fail closed, never as Happ OFF.

## Observations 2026-11-14 ~01:20 (Android reachability)

- Dell: `ip neigh` shows `192.168.0.185 FAILED`; no ARP reply; `ping` 100% loss.
- Pi (`pi5home`): `ping 192.168.0.185` 100% loss; `ip neigh` `FAILED` on `wlan0`.
- Dell non-root `tcpdump` on `wlp8s0`: "You don't have permission to perform this capture". Root is required; the sudo password was not provided.
- Conclusion: Android is off, asleep, or on another address/network. Its gateway cannot be checked until it answers.

## Dell 30-second capture (2026-11-14 ~01:25)

- Command: `timeout 30 sudo -n /usr/bin/tcpdump -ni wlp8s0 host 192.168.0.185 -c 20` (narrow sudoers rule from `docs/new-host-commands.md`).
- Result: `0 packets captured`, `0 packets received by filter`.
- Interpretation: Dell saw no traffic to or from Android during the window. Dell is not currently forwarding any Android traffic, and Android is not active on the LAN.
- Still open: Android's gateway settings (needed before rule 8000 can be decided).

## Android online check (2026-11-14 ~01:32)

- Android `192.168.0.185` is ONLINE (user turned it on with the old settings).
- Dell ARP: `192.168.0.185 lladdr f0:35:75:23:34:62 REACHABLE` (matches the documented MAC).
- Pi ARP: `192.168.0.185 lladdr f0:35:75:23:34:62 REACHABLE` (earlier FAILED; now resolved).
- Dell 20-packet capture: Android TCP to `172.217.114.4:443` seen on `wlp8s0`. Frames reached Dell's Wi-Fi NIC, so Android sends through Dell as its gateway (INFERRED; the user's "old settings" are the gateway check still to be confirmed).
- `ip route get 172.217.114.4 from 192.168.0.185 iif wlp8s0` -> `via 172.18.0.2 dev tun0 table 2022`.
- Dell `tun0` traffic in 10 s: tx +460,695 B, rx +460,975 B. Android traffic is flowing through Dell's Happ TUN now.

Conclusion (VERIFIED for the route and traffic, INFERRED for the gateway):
- Dell's rule `8000: from 192.168.0.185 lookup 2022` is LIVE. Do NOT remove it: it is Android's current VPN exit path.
- Dell's Happ 2.17.1 is therefore not an unused leftover; it is the working Android exit today.
- The Pi is not in Android's path right now.

## Android gateway check (2026-11-14 ~01:35) — UNRESOLVED

- User report: Android's gateway is `192.168.0.185`, NOT the expected `192.168.0.105`. That value equals Android's own address, so it may be a misread of the IP field.
- `adb` is not installed on Dell, so Android settings cannot be read remotely.
- Neighbour table on Dell: `192.168.0.185 lladdr f0:35:75:23:34:62 REACHABLE`.
- Still needed: exact text of IP address, Gateway, Prefix length, DNS 1/2, and DHCP/static from Android's Wi-Fi details screen (or a screenshot).

## Dell has no internet (2026-11-14 ~19:40 MSK) — DIAGNOSED, NOT FIXED

Host: `dell` at `192.168.0.103` on `wlp8s0` (NOT `.105` as documented). Checked read-only over SSH. No host change made.

Findings (VERIFIED, OBSERVED):
- NetworkManager profile `TP-Link_42SN` is `ipv4.method manual`, `ipv4.addresses 192.168.0.103/24`, `ipv4.gateway 192.168.0.182`, DNS `8.8.8.8,8.8.4.4,1.1.1.1`.
- Only default route: `default via 192.168.0.182 dev wlp8s0 metric 20600`.
- `192.168.0.182` answers ping but refuses TCP 53 and 443. It does not route to the internet.
- `192.168.0.1` (router, also the Pi's and the documented gateway) answers ping.
- `1.1.1.1` and `8.8.8.8` time out. DNS queries time out.
- Happ on Dell is running (`happd` active since 19:20:14), but no `tun0`/Happ TUN exists. Dell is not routing through Happ.
- Pi (`192.168.0.118`) has internet: `default dev happ-xray metric 1` plus `default via 192.168.0.1 dev eth0 metric 100`.

Cause (INFERRED, strong): the static gateway `192.168.0.182` is wrong. The LAN gateway is `192.168.0.1`.

Side issue (OBSERVED, not fixed): `postgresql@16-main` failed at 19:20:15 because PID 2044 (`postgres -D /var/www/db_data/postgres`), which is not the systemd cluster, already holds port 5432.

User decision (2026-11-14 ~19:45 MSK): Dell's internet must run THROUGH the Pi, not the router. The earlier proposal (gateway `192.168.0.1`) is withdrawn.

What this needs (NOT built, NOT approved, no host change made):
- Pi (`pi5home`): `net.ipv4.ip_forward=1`, and a project-owned nftables table (never flush the global ruleset, never enable `nftables.service`) that MASQUERADEs `192.168.0.103` out of `happ-xray` and allows forward for it. Fail-closed when Happ state is not ENABLED (docs/LLM-HANDOVER.md).
- Dell: NetworkManager `TP-Link_42SN` gateway `192.168.0.118` (currently `192.168.0.182`), plus its own Happ 2.17.1 must not fight the default route. Its rule 8000 / table 2022 / `tun0` stay untouched without approval.
- IPv4 only. IPv6 is not forwarded (state the limitation).

Open decisions for the user:
1. When Happ is OFF, should Dell be blocked (fail closed, per CLAUDE.md rule 1) or go direct through the router?
2. Keep Dell's own Happ 2.17.1 or disable it while Dell uses the Pi?
3. Pi LAN interface: USER confirmed `eth0` (2026-11-14 ~19:50 MSK), and live `ip` shows `eth0` at 192.168.0.118. Docs saying `wlan0` are stale and need correction (see handover section 9).

## Session log summary (2026-11-14, Dell internet and Pi gateway) — before any host change

Order of events, all read-only so far:
1. SSH to 192.168.0.103 succeeded as `bliss`. Host is `dell` (Ubuntu 24.04, x86_64, Wi-Fi `wlp8s0`). VERIFIED.
2. Docs list Dell at `.105`. Live address is `.103`. Docs are stale or DHCP changed. OBSERVED.
3. Dell internet: router `192.168.0.182` answers ping but refuses TCP 53/443. Outside IPs and DNS time out. The `.1` router answers ping. VERIFIED.
4. Root cause: static gateway `192.168.0.182` in NM profile `TP-Link_42SN` (manual, metric 20600). INFERRED strong, not confirmed on the router.
5. Dell `postgresql@16-main` failed at boot: port 5432 held by non-systemd PID 2044 (`postgres -D /var/www/db_data/postgres`). Owner unknown. OBSERVED.
6. Repo search (whole directory): Pi-as-gateway for Dell is designed in `DEVELOMPENT_PLAN.md` and `RASPBERRY_PI_GATEWAY_LLM_HANDOVER.md` but not built. No routing or NAT code exists. VERIFIED.
7. Historical `setup-android-vpn-gateway.sh` set Dell's gateway to the router and used rule 8000 / table 2022 for Android. Do not copy its logic. VERIFIED.
8. User decision: Dell's internet goes through the Pi. Router-gateway fix withdrawn. USER.
9. Pi LAN interface is `eth0`. USER and live. Docs say `wlan0` and need correction. VERIFIED.

Still open before any host change (USER decision needed):
- Happ OFF on the Pi: block Dell (fail closed, CLAUDE.md rule 1) or go direct through the router?
- Dell's own Happ 2.17.1: keep or disable while Dell uses the Pi?

No host change has been made on Dell or the Pi in this session.

## Pi state check before Dell change (2026-11-14 ~19:55 MSK, read-only)

- Pi LAN: `eth0` 192.168.0.118/24 UP. `wlan0` DOWN. (VERIFIED)
- `net.ipv4.ip_forward = 1` already on the Pi. Source of this setting not yet identified. (VERIFIED, cause UNKNOWN)
- Routes: `default dev happ-xray metric 1`, `default via 192.168.0.1 dev eth0 metric 100`. (VERIFIED)
- Policy rules: only the kernel defaults (local, main, default). No custom rules. (VERIFIED)
- `happ-xray` UP, POINTOPOINT. Tunnel up. (VERIFIED)
- Watcher `/run/vpn-gateway/state.json`: intent ENABLED, process up, reason "started event", happd_pid 996, updated 19:38:19 +03:00. (VERIFIED)
- `gateway/gateway_mode.py` output: `VPN_EXIT` ("Happ enabled, process up, tunnel up"). (VERIFIED)
- `nft list ruleset` needs root and is not readable without sudo. Current nftables state UNKNOWN. (VERIFIED limitation)
- Unit tests: 38 pass (`python3 -m unittest discover -s tests`). (VERIFIED)

Plan for Dell through the Pi (NOT yet applied, needs approval):
1. Pi: new project-owned nftables table (e.g. `table ip vpngw`) with `forward` allow for `192.168.0.103` and `postrouting` masquerade out `happ-xray`. Only when watcher says VPN_EXIT. Fail closed otherwise. Never `flush ruleset`. Never `nftables.service`.
2. Pi: keep `ip_forward=1` (already set). Document the source.
3. Dell: NM `TP-Link_42SN` gateway `192.168.0.118`. Backup current profile first. Rollback: set gateway back to `192.168.0.182`.
4. Dell: Happ 2.17.1 handling pending user decision. Do not touch rule 8000, table 2022, or `tun0`.
5. Verify: from Dell, `curl https://example.com`, check the exit IP matches the Pi's Happ exit, check DNS.
6. Pending user decisions: Happ OFF behavior (block vs direct), Dell's own Happ.

## User answers (2026-11-14 ~20:00 MSK)

- USER: "If the Pi loses internet access, you can be blocked from running." So any change must never cut the Pi's own internet or its SSH access. Rules touch only forwarded traffic from `192.168.0.103`. The Pi's own `eth0`/`happ-xray` traffic stays untouched. (USER, binding constraint)
- USER: Dell's own Happ 2.17.1 is NOT used by default. It may be run manually. So Dell's Happ is not part of the default path. Do not enable it. Do not remove it. (USER)
- Happ OFF behaviour for Dell: NOT answered by the user yet. Repo rule 2 (CLAUDE.md) says only a positively observed user OFF sends clients through the normal path. Unknown state blocks. Open until the user confirms.

## Decision (USER, 2026-11-14 ~20:05 MSK): client routing follows Pi Happ

- Happ ON on the Pi: Dell (`192.168.0.103`) and Android (`192.168.0.185`) go through Happ (`happ-xray`).
- Happ OFF on the Pi: Dell and Android go without VPN (normal path via `192.168.0.1` on `eth0`).
- Unknown or stale state: NOT stated by the user. Keep CLAUDE.md rule 1 (block). Confirm later.
- Dell's own Happ 2.17.1: not used by default, may be run manually. Not part of the default path.

## Built: ruleset builder (2026-11-14 ~20:15 MSK). Repo only, no host change

- `gateway/forward_policy.py`: pure function `build_ruleset(mode, clients)`. Writes only table `ip vpn_gateway`. Modes: VPN_EXIT (clients out via `happ-xray`, NAT), ORDINARY (clients out via `eth0`, NAT), BLOCK (drop; also any unknown mode).
- Clients default: Dell `192.168.0.103`, Android `192.168.0.185`. IPv4 only, validated.
- `tests/test_forward_policy.py`: 10 tests. Full suite: 48 tests pass (`python3 -m unittest discover -s tests`).
- Not applied to any host. Applying needs approval.
- Limitation (VERIFIED by design): IPv6 is not handled. Clients with IPv6 from the router's RA may bypass the Pi. State this to the user before the change.

## Approval received, blocked on sudo (2026-11-14 ~20:25 MSK)

- USER: "approve" (steps 1 to 3 in the previous plan), and "you can run sudo at pi".
- Check: `sudo -n true` on the Pi -> "a password is required". Non-interactive sudo is not available to this session. (VERIFIED)
- No host change made. No password was requested or stored.
- Needed to continue: either the user runs the apply steps with sudo, or the user provides a sudo password for this session (not written to the repo), or the user adds a narrow NOPASSWD rule for `nft` and `sysctl` (the same pattern as `docs/new-host-commands.md`).

## Step 1 applied on Pi (2026-11-14 ~20:35 MSK), sudo password supplied by user for this session

- Validated `nft -c -f` OK for the VPN_EXIT ruleset.
- Backup of the global nftables ruleset before change: EMPTY (0 lines). Saved to /tmp/opencode/nft-before-vpn-gateway.txt. Rollback state = no rules.
- Applied: `table ip vpn_gateway` (forward accept/drop + postrouting masquerade for 192.168.0.103 and 192.168.0.185).
- Pi own connectivity after apply: 1.1.1.1 OK, LAN OK.
- `net.ipv4.ip_forward = 1` (unchanged). `iptables` not installed on Pi.
- Rollback: `sudo nft delete table ip vpn_gateway`.
- Dell gateway NOT changed yet. Step 3 waits for step 2 (controller), so OFF means direct and not block.
- Session password: not written to disk, log, or repo.

## Step 2 applied on Pi (2026-11-14 ~20:45 MSK): controller service

- Installed `/usr/local/lib/vpn-gateway/forward_policy.py` and `forward_apply.py` (no existing files overwritten).
- Installed `/etc/systemd/system/vpn-gateway-forward.service` (root, Restart=always). Enabled and started.
- Journal: `forward_apply: mode=VPN_EXIT` (VERIFIED). Table `ip vpn_gateway` live. Pi own internet OK.
- Tests: 55 pass.
- Rollback: `sudo systemctl disable --now vpn-gateway-forward.service; sudo nft delete table ip vpn_gateway; sudo rm /etc/systemd/system/vpn-gateway-forward.service /usr/local/lib/vpn-gateway/forward_policy.py /usr/local/lib/vpn-gateway/forward_apply.py; sudo systemctl daemon-reload`.

## Step 3 blocked on Dell sudo (2026-11-14 ~20:50 MSK)

- Dell NM profile backup taken (no secrets, `nmcli connection show` masks PSK): /tmp/opencode/dell-nm-TP-Link_42SN.before.txt
- Dell `sudo -n true` -> password required. Gateway change needs root on Dell. Not done.
- Planned change: `sudo nmcli connection modify TP-Link_42SN ipv4.gateway 192.168.0.118` then `sudo nmcli connection up TP-Link_42SN`.
- Rollback: same command with `ipv4.gateway 192.168.0.182`.

## Step 3 applied on Dell (2026-11-14 ~21:00 MSK): Dell gateway = Pi

- Command (sudo password supplied by user, same as Pi, passed via stdin only): `nmcli connection modify TP-Link_42SN ipv4.gateway 192.168.0.118`, then `nmcli connection up TP-Link_42SN`.
- Dell route now: `default via 192.168.0.118 dev wlp8s0 metric 600`. (VERIFIED)
- Dell -> 1.1.1.1 ping OK. DNS OK (example.com resolves). HTTPS to example.com returned 200. (VERIFIED)
- Dell exit IP `104.194.144.71` equals the Pi exit IP `104.194.144.71`, so Dell traffic exits through Happ. (VERIFIED, Happ ON)
- Dell rule 8000, table 2022, `tun0`, and Dell's Happ 2.17.1: NOT touched.
- Rollback on Dell: `sudo nmcli connection modify TP-Link_42SN ipv4.gateway 192.168.0.182 && sudo nmcli connection up TP-Link_42SN`. Backup: /tmp/opencode/dell-nm-TP-Link_42SN.before.txt (on Pi).
- NOT yet tested: Happ OFF behaviour (Dell should go direct via router). Needs the user to turn Happ OFF in the GUI, or permission to stop it.
- IPv6: not tested or handled (see limitation above).
- Android (step 4): still on the phone. Not changed.
