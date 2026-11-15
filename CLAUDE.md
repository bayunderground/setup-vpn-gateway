# CLAUDE.md

Instructions for AI assistants working in this repository. Read this first, then `docs/LLM-HANDOVER.md`, which has the full brief, the evidence, and the decision log.

## What this project is

**Default host: `pi`** (`pi5home`, `192.168.0.118` on `eth0`, user `bliss`). Any command, script, or check that does not name a host runs on the Pi. Commands for Dell (`dell`) or Android (`192.168.0.185`) must say so explicitly.

Access: `ssh bliss@192.168.0.118` (from Dell). The Pi's `sudo` and Dell's `sudo` need a password. Never store it in the repo, logs, or shell history.

A one-click install for a Raspberry Pi 5 (`pi5home`, `192.168.0.118`) that shares its Happ VPN with the home network. Clients are an Android phone (`192.168.0.185`) and the Ubuntu computer `dell` (currently `192.168.0.103`; older docs say `.105`). Clients are pointed at the Pi once, in their Wi-Fi settings. The user turns Happ ON and OFF in the Happ GUI, and the gateway follows that choice.

Client routing, decided by the user (2026-11-14):
- Happ ON on the Pi: Dell and Android go through Happ (`happ-xray`).
- Happ OFF on the Pi: Dell and Android go without VPN, through the router path.
- Unknown or stale state: blocked (rule 1).

## Current state (2026-11-14)

- `scripts/new-host-setup.sh` is installed on the Pi. It installed the watcher, the read-only sudo rule, and the boot baseline.
- `gateway/happ_watch.py` (`vpn-gateway-watch.service`, read-only): reads the Happ GUI's control messages and publishes the user's intent to `/run/vpn-gateway/state.json`.
- `gateway/gateway_mode.py`: decides the client mode (ORDINARY, VPN_EXIT, or BLOCK). It only reads and prints.
- `gateway/forward_policy.py`: builds the nftables ruleset for the project-owned table `ip vpn_gateway`. Pure, no host changes.
- `gateway/forward_apply.py` (`vpn-gateway-forward.service`, root, Pi): re-reads the mode and reapplies the ruleset only when it changes. Each ruleset is checked with `nft -c` before it is applied.
- **Pi:** table `ip vpn_gateway` applied and the service running (VPN_EXIT, 2026-11-14 19:48). `ip_forward=1` was already set.
- **Dell:** NetworkManager `TP-Link_42SN` gateway is `192.168.0.118` (applied 2026-11-14 ~21:00). Dell's exit IP matches the Pi's Happ exit. Dell's rule 8000, table 2022, `tun0`, and its own Happ 2.17.1 are untouched.
- **Not done or not tested:** Android's gateway on the phone (user step); the Happ OFF path for Dell (direct through the router); IPv6 handling (see rule 4).
- **Out of scope, not touched:** `postgresql@16-main` fails on Dell because another postgres holds port 5432.

## Rules

1. **Fail closed.** If the state is missing, stale, unknown, or contradictory, client internet is blocked. It never falls back to the normal Wi-Fi connection.
2. **Only a positively observed user OFF** sends clients through the normal path.
3. **Do not break the Pi.** Keep its own routing, `happd`, and Happ's routes and rules intact. Never cut the Pi's own internet or SSH: rules touch only forwarded traffic from client addresses.
4. **IPv4 only.** Do not forward or NAT IPv6. IPv6 is a known limitation: clients may still reach the internet directly over IPv6 through router advertisements. State this rather than hiding it.
5. **Never flush the global nftables ruleset.** Never enable `nftables.service`. Use a project-owned table (`ip vpn_gateway`).
6. **No blind cleanup.** Do not remove Dell's rule 8000, rules 9000 to 9010, table 2022, or `tun0` without the user's approval.
7. **Approval before host changes.** Explain the change, back it up, give the rollback, and wait for the user's explicit approval.
8. **Never run** `happ-diag --repair` (it restarts Happ) or `systemctl enable nftables` (its config flushes all rules).
9. **Do not send undocumented socket commands** to `happd`, especially `start` or `stop`, unless the user asks.
10. **Never commit or log secrets.** This includes `Happ.conf`, `subs.db`, `state.db`, `start` payloads (they carry the xray config), sudo passwords, GitHub tokens, and anything under `/tmp/opencode`. Never write raw strace lines to disk.
11. **Label every finding** VERIFIED, OBSERVED, USER, INFERRED, or UNKNOWN, with its date and source.
12. **Tests first.** Every parser, state rule, and decision change needs a test. Run `python3 -m unittest discover -s tests` before committing.

## Known facts that matter

- The daemon does not reliably send a `finished` event after a user stop. A stop request followed by `Process not found` is the dependable user-stop signature.
- After a crash, the GUI sends its own stop request about 0.3 s later. The watcher ignores a stop request when the process is already down.
- Observer sockets get no lifecycle events. Only the controlling GUI connection does.
- `Happ.conf` `mode` is the UI theme, not VPN state.
- The Pi's default routes: `happ-xray` at metric 1 when Happ is up, and `eth0` via `192.168.0.1` at metric 100.
- Dell's Wi-Fi profile is `TP-Link_42SN` (manual IPv4). Its DNS points at public resolvers, which reach the Internet through the Pi.

## Working style

- Keep changes small and reviewable. Commit only what the user asked for.
- Push only when the user asks.
- The user works in English and Russian. Documentation is in English, with a Russian README.
- Before editing a file, read it. Do not overwrite the user's own changes.
- Record every host change, approval, and rollback in `docs/RUNNING-LOG.md`.

## Where things are

| Path | Purpose |
|---|---|
| `docs/LLM-HANDOVER.md` | Full brief for assistants: evidence, design, decisions, commands |
| `docs/RUNNING-LOG.md` | Dated log of every session, host change, and rollback step |
| `docs/PROJECT-DOCUMENTARY-2026-11-14.md` | Narrative and timeline of the 2026-11-14 investigation |
| `docs/happ-intent-marker-design-2026-11-14.md` | Earlier marker design, kept as a fallback |
| `scripts/new-host-setup.sh` | One-click install and `--uninstall` |
| `gateway/happ_watch.py` | Happ GUI watcher (service) |
| `gateway/gateway_mode.py` | Client-mode decision (read-only) |
| `gateway/forward_policy.py` | Builds the project nftables ruleset for a mode (pure) |
| `gateway/forward_apply.py` | Root controller that applies the ruleset on mode change (service) |
| `scripts/baseline-readonly.sh` | Read-only baseline report |
| `scripts/happd-observe.py` | Passive socket observer (proved observers get no lifecycle events) |
| `tests/` | Unit tests for the watcher, the mode decision, the ruleset, and the controller |
| `README.md`, `README_RU.md` | User-facing overview and install instructions |
| `setup-android-vpn-gateway*` | Historical Ubuntu iptables gateway. **Do not run or copy its logic** |
