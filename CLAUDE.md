# CLAUDE.md

Instructions for AI assistants working in this repository. Read this first, then `docs/LLM-HANDOVER.md`, which has the full brief, the evidence, and the decision log.

## What this project is

**Default host: `pi`** (`pi5home`, `192.168.0.118`, user `bliss`). Any command, script, or check that does not name a host runs on the Pi. Commands for Dell (`dell`, `192.168.0.105`) or Android must say so explicitly.

A one-click install for a Raspberry Pi 5 (`pi5home`, `192.168.0.118`) that shares its Happ VPN with the home network. Clients are an Android phone (`192.168.0.185`) and the Ubuntu computer `dell` (`192.168.0.105`). The user turns Happ ON and OFF in the Happ GUI as usual, and the gateway follows that choice. Clients are pointed at the Pi once, in their Wi-Fi settings. Nothing else is manual.

## Current state

- `scripts/new-host-setup.sh` installs everything the Pi needs. It has not yet been re-run successfully on the Pi, because it needs the user's sudo password.
- `gateway/happ_watch.py`: a read-only watcher that runs as a systemd service at boot. It reads the Happ GUI's control messages and publishes the user's intent to `/run/vpn-gateway/state.json`.
- `gateway/gateway_mode.py`: decides the client mode (ORDINARY, VPN_EXIT, or BLOCK). It only reads and prints. It applies nothing.
- The firewall and routing controller is **not built**. No nftables, routing, or sysctl change is approved or made.

## Rules

1. **Fail closed.** If the state is missing, stale, unknown, or contradictory, client internet is blocked. It never falls back to the normal Wi-Fi connection.
2. **Only a positively observed user OFF** sends clients through the normal path.
3. **Do not break the Pi.** Keep its own routing, `happd`, and Happ's routes and rules intact.
4. **IPv4 only.** Do not forward or NAT IPv6. State the router-advertisement limitation rather than hiding it.
5. **Never flush the global nftables ruleset.** Never enable `nftables.service`. Use a project-owned table.
6. **No blind cleanup.** Do not remove Dell's rule 8000, rules 9000 to 9010, table 2022, or `tun0` without the user's approval.
7. **Approval before host changes.** Explain the change, back it up, give the rollback, and wait for the user's explicit approval.
8. **Never run** `happ-diag --repair` (it restarts Happ) or `systemctl enable nftables` (its config flushes all rules).
9. **Do not send undocumented socket commands** to `happd`, especially `start` or `stop`, unless the user asks.
10. **Never commit or log secrets.** This includes `Happ.conf`, `subs.db`, `state.db`, `start` payloads (they carry the xray config), and anything under `/tmp/opencode`. Never write raw strace lines to disk.
11. **Label every finding** VERIFIED, OBSERVED, USER, INFERRED, or UNKNOWN, with its date and source.
12. **Tests first.** Every parser, state rule, and decision change needs a test. Run `python3 -m unittest discover -s tests` before committing.

## Known facts that matter

- The daemon does not reliably send a `finished` event after a user stop. A stop request followed by `Process not found` is the dependable user-stop signature.
- After a crash, the GUI sends its own stop request about 0.3 s later. The watcher ignores a stop request when the process is already down.
- Observer sockets get no lifecycle events. Only the controlling GUI connection does.
- `Happ.conf` `mode` is the UI theme, not VPN state.

## Working style

- Keep changes small and reviewable. Commit only what the user asked for.
- Ask before any push to GitHub. Push only when the user asks.
- The user works in English and Russian. Documentation is in English, with a Russian README.
- Before editing a file, read it. Do not overwrite the user's own changes.

## Where things are

| Path | Purpose |
|---|---|
| `docs/LLM-HANDOVER.md` | Full brief for assistants: evidence, design, decisions, commands |
| `docs/PROJECT-DOCUMENTARY-2026-11-14.md` | Narrative and timeline of the 2026-11-14 investigation |
| `docs/happ-intent-marker-design-2026-11-14.md` | Earlier marker design, kept as a fallback |
| `scripts/new-host-setup.sh` | One-click install and `--uninstall` |
| `gateway/happ_watch.py` | Happ GUI watcher (service) |
| `gateway/gateway_mode.py` | Client-mode decision (read-only) |
| `scripts/baseline-readonly.sh` | Read-only baseline report |
| `scripts/happd-observe.py` | Passive socket observer (proved observers get no lifecycle events) |
| `tests/` | Unit tests for the watcher and the mode decision |
| `README.md`, `README_RU.md` | User-facing overview and install instructions |
| `setup-android-vpn-gateway*` | Historical Ubuntu iptables gateway. **Do not run or copy its logic** |
