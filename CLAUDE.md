# CLAUDE.md

## Project purpose

Build a safe, persistent, IPv4-only shared Happ VPN gateway on a Raspberry Pi 5 running Raspberry Pi OS / Debian Bookworm (aarch64).

The gateway is intended to serve multiple LAN clients:
- Android: `192.168.0.185` (historically observed MAC `f0:35:75:23:34:62`)
- Ubuntu computer `dell`: `192.168.0.105` (verify before changing client configuration)

Observed Pi network details (verify at runtime; do not assume they remain unchanged):
- LAN interface: `wlan0`
- Pi LAN address: `192.168.0.118/24`
- Router: `192.168.0.1`
- NetworkManager Wi-Fi profile: `TP-Link_42SN_5G`
- Happ TUN interface: `happ-xray`
- Happ TUN address when active: `172.19.0.1/30`
- Happ daemon: `happd.service`, executable observed at `/opt/happ/bin/happd`
- Happ xray executable observed at `/opt/happ/bin/core/xray`

The project is in the design and diagnostics phase. The existing `setup-vpn-gateway-alpha.sh` is a read-only diagnostic, not an installer.

## Mandatory network state model

Never infer the user's Happ enabled/disabled intent from `happd.service` being active. The daemon was observed running both when Happ was OFF and ON.

The required gateway behavior is:

| Happ control state | Tunnel readiness | Client behavior |
|---|---|---|
| Positively confirmed DISABLED | Any | Do not route clients through the Pi VPN gateway; Dell should retain its ordinary router path |
| Positively confirmed ENABLED | TUN and route ready | Route registered clients through Happ only |
| ENABLED | TUN absent, broken, or transitioning | Fail closed; no direct-Wi-Fi fallback |
| UNKNOWN / inconsistent | Any | Fail closed; never interpret UNKNOWN as DISABLED |

The TUN interface, xray process, and main default route can indicate that the tunnel is active. They do not, by themselves, distinguish a user-disabled VPN from an enabled-but-disconnected VPN.

Before implementing client gateway switching, investigate a reliable, stable Happ 4.7.2 control-state signal. Candidate sources include documented daemon IPC/API, a local control socket, D-Bus, stable application state/configuration, or another supported interface. Do not invent undocumented interfaces, expose credentials, or make volatile log parsing the sole safety control. If no reliable signal exists, propose an explicit user-controlled state marker/toggle and document its failure semantics before implementation.

## Non-negotiable safety rules

1. **Do not break the Pi's own networking or Happ.** Preserve the Pi's own default routing, Happ control daemon, and Happ-managed routes/rules.
2. **No direct-WAN leakage for clients.** While Happ is enabled, client Internet traffic must never fall back to `wlan0` or another non-VPN egress. A missing tunnel must result in a drop.
3. **Unknown means fail closed.** Do not treat missing evidence as VPN disabled.
4. **IPv4 gateway only.** The user explicitly requested no IPv6 gateway support. Do not add IPv6 forwarding or NAT. Drop client IPv6 forwarded through the Pi. Explain that same-LAN router advertisements can give clients a direct IPv6 path around the Pi; Pi-side filtering alone cannot guarantee end-to-end IPv6 blocking.
5. **Use native nftables on Pi OS.** Do not port the old Ubuntu iptables implementation to the Pi. Own a dedicated nftables table/chain and never flush the global ruleset.
6. **Protect unrelated routing.** Do not flush all routing tables, reset NetworkManager, or overwrite Happ routing. Inspect rule priorities and table ownership before choosing a project table. The earlier temporary test used table 2022; this does not establish that table 2022 is free for persistent use.
7. **No blind cleanup on Dell.** Dell's `tun0` and policy rules at priorities 8000 and 9000–9010 were identified as leftovers from an earlier experiment. Do not remove them until their live source/ownership is inspected and the user approves the cleanup.
8. **No premature client cutover.** Do not change Android or Dell gateway settings until routing, NAT, return traffic, DNS, and kill-switch behavior have been tested.
9. **Safe changes only.** Before any persistent or potentially disruptive change, explain impact, take a backup where applicable, provide rollback, and obtain explicit user approval.
10. **Uninstall only project-owned resources.** Remove only files, nftables objects, sysctl settings, and service units created by this project.

## Architecture expectations

- Support a configurable list of clients, not a single hardcoded Android address.
- Validate client addresses, subnet membership, duplicate IPs, and optional MAC identities.
- Keep LAN access available where possible, including access to the local router/subnet while the VPN is unavailable. Define and test LAN exceptions explicitly.
- Use per-client IPv4 policy routing or an equally robust design that preserves Happ's policy-routing behavior.
- Use nftables to allow client forwarding only from LAN to the Happ TUN, allow established return traffic, masquerade out the TUN, and drop every other client Internet egress.
- Handle Wi-Fi and Happ transitions, boot ordering, restarts, and races with idempotent reconciliation and locking.
- Provide clear commands for status, diagnostics, logs, checks, and safe uninstall.
- Dell must use the Pi as gateway only in the intended active mode. When Happ is positively disabled, Dell should use its normal router. When Happ is enabled but unavailable or state is unknown, Dell must fail closed. This likely requires a Dell-side agent or another explicit client-side mechanism; do not assume the Pi can transparently change a remote host's default gateway.

## Development workflow

- Read the current repository files and inspect the live device state before making assumptions.
- Work in small, reviewable stages. Do not build the installer before the Happ intent signal and state machine are understood.
- Prefer Python for substantial application logic; shell is acceptable for small, auditable Linux integration scripts. Keep dependencies minimal.
- Keep scripts idempotent, strict about errors, and safe to run repeatedly.
- Separate read-only diagnostics from commands that mutate the system.
- Add tests for state parsing, state transitions, configuration validation, nftables generation, and failure/rollback paths. Unit tests must not require root or alter the host network.
- Test routing and firewall behavior in a controlled way before production activation.
- Document every assumption as VERIFIED, OBSERVED, INFERRED, or UNKNOWN. Include the date and command/source for device-specific observations.
- Never claim the gateway is secure or working based only on a successful service exit. Verify actual routes, nftables counters, packet flow, return traffic, DNS, and public IPv4 from each client.

## Existing repository files

- `setup-vpn-gateway-alpha.sh`: read-only Pi diagnostic. It intentionally reports `TUNNEL_ABSENT`, not “Happ disabled”.
- `RASPBERRY_PI_GATEWAY_LLM_HANDOVER.md`: current design/handover reference; read it before implementation.
- `setup-android-vpn-gateway.sh` and `setup-android-vpn-gateway.md`: historical Ubuntu-as-gateway implementation/reference only. Do not run on the Pi or copy its iptables logic.
- `setup-android-vpn-gateway_session_debug-state.md`: historical Ubuntu troubleshooting context only.

## Definition of done

The gateway is not complete until all of the following are demonstrated:
- Happ DISABLED, ENABLED_UP, ENABLED_DOWN, TRANSITION, and UNKNOWN are distinguished safely.
- Multiple registered clients behave as specified in every state.
- Client Internet traffic exits only via Happ when enabled.
- No client traffic leaks to the ordinary Wi-Fi WAN if Happ is down or state is unknown.
- LAN access works as documented.
- IPv6 is not forwarded by the gateway and the direct-router IPv6 limitation is explicitly addressed.
- Pi-originated traffic and Happ behavior remain unaffected.
- Reboot, Wi-Fi reconnect, Happ reconnect, and tunnel loss/recovery are tested.
- Dell's state-following behavior is tested separately from Android.
- Diagnostics, logs, backup/rollback, and uninstall are documented and verified.
