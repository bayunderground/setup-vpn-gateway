# Development Plan — Raspberry Pi Shared Happ VPN Gateway

**Status:** Planning / discovery. No persistent gateway implementation is installed.  
**Current diagnostic:** `setup-vpn-gateway-alpha.sh` v0.1.0-alpha (read-only).  
**Primary design reference:** `RASPBERRY_PI_GATEWAY_LLM_HANDOVER.md`

## 1. Objective

Make the Raspberry Pi 5 a shared IPv4-only gateway for Android and the Ubuntu machine `dell`, using the Pi's existing Happ VPN tunnel. Preserve the Pi's own networking and Happ operation.

The system must follow the user's Happ enable/disable intent, not merely the presence of the Happ daemon or TUN interface.

## 2. Required behavior

| State | Pi gateway behavior for registered clients |
|---|---|
| Happ positively confirmed DISABLED | Do not force clients through the Pi VPN gateway; Dell returns to its ordinary router path |
| Happ positively confirmed ENABLED and tunnel ready | Forward client IPv4 Internet traffic through `happ-xray` only |
| Happ ENABLED but tunnel missing, broken, or transitioning | Fail closed; block client Internet rather than fall back to Wi-Fi WAN |
| Happ state UNKNOWN, inconsistent, or stale | Fail closed |

LAN access should remain available where technically possible. IPv6 forwarding/NAT is out of scope and must be blocked through the Pi. Same-LAN router advertisements can bypass the Pi, so end-to-end IPv6 blocking requires action on the router or clients.

## 3. Known environment (verify before implementation)

### Raspberry Pi

| Item | Observed value |
|---|---|
| Device | Raspberry Pi 5 |
| OS | Raspberry Pi OS / Debian 13 (trixie), aarch64 (verified 2026-11-14) |
| Hostname | `pi5home` (verified 2026-11-14) |
| LAN interface | `wlan0` |
| LAN address | `192.168.0.118/24` |
| Router | `192.168.0.1` |
| NetworkManager profile | `TP-Link_42SN_5G` |
| Happ daemon | `happd.service` |
| TUN interface | `happ-xray` |
| TUN address when active | `172.19.0.1/30` |
| xray executable | `/opt/happ/bin/core/xray` |

### Clients

| Client | Observed IPv4 | Notes |
|---|---|---|
| Android | `192.168.0.185/24` | MAC previously observed as `f0:35:75:23:34:62`; verify current gateway and reservation |
| Ubuntu `dell` | `192.168.0.105/24` | Verify current IP; old local tunnel/rules are stale remnants of the previous Ubuntu gateway experiment |

All values above are observations from prior diagnostics, not immutable configuration. Discover current interface names, addresses, routes, and client settings before changing anything.

## 4. Current repository state

- `setup-vpn-gateway-alpha.sh` is a read-only probe of the Happ service, TUN interface, xray process, main default route, IPv4 addresses, and active NetworkManager connections.
- The probe correctly warns that tunnel absence does not prove Happ is disabled.
- `RASPBERRY_PI_GATEWAY_LLM_HANDOVER.md` records the design, network facts, temporary routing experiment, and safety constraints.
- `setup-android-vpn-gateway.sh` and its companion documentation are an older Ubuntu-as-gateway implementation. They are historical reference only; their iptables setup is not the Pi implementation.
- A temporary Pi source-policy-routing experiment successfully sent Android-sourced traffic to `happ-xray` while preserving LAN routing, and automatically restored the prior forwarding setting and removed temporary rules. This validated only the route decision, not NAT, firewall, return traffic, DNS, multiple clients, or reconnection behavior.
- No persistent Pi gateway forwarding, NAT, nftables, or client-routing configuration is documented as installed.

## 5. Phased implementation

### Phase 0 — Repository and device baseline

**Goal:** establish an accurate, non-destructive baseline.

Tasks:
- Review all current repository files and preserve the historical Ubuntu implementation as reference.
- Run the alpha diagnostic on the Pi in Happ OFF and ON states.
- Record current hostname, OS/kernel, LAN interface/address, router, active NetworkManager profiles, Happ service, TUN, xray process, main and policy routes, nftables ruleset, forwarding sysctls, and IPv6 status.
- Verify current Android and Dell addresses, gateways, subnet masks, and DHCP reservations.
- Inspect Dell's old `tun0` and policy-routing rules; identify their source/owner without deleting them.
- Save a dated, sanitized baseline report. Never include VPN credentials, private keys, tokens, or full secret-bearing Happ configuration.

**Exit criteria:** current topology and ownership of existing routes/rules are documented; no live configuration was changed.

### Phase 1 — Reliable Happ intent-state detection

**Highest priority / blocking dependency.**

**Goal:** distinguish user intent from tunnel readiness.

Tasks:
- Investigate Happ 4.7.2's documented control interface and read-only local interfaces: daemon IPC/API, sockets, D-Bus, stable state files, process arguments, and relevant logs.
- Avoid dumping secrets or credentials. Do not modify Happ configuration or restart its daemon.
- Correlate observations across deliberate OFF, ON, disconnect, reconnect, and transition tests.
- Assess signal stability, permissions, latency, and behavior after reboot.
- If no supported signal exists, design an explicit user-controlled marker/toggle. Define how it is set, cleared, authenticated, and recovered after crashes/reboots.

Proposed logical states:
- `DISABLED`: explicit positive evidence of user-disabled state.
- `ENABLED_UP`: explicit enabled intent plus verified TUN/process/route readiness.
- `ENABLED_DOWN`: enabled intent but tunnel not ready.
- `TRANSITION`: state change in progress or signals disagree.
- `UNKNOWN`: unavailable, stale, or untrusted state signal.

Safety rule: only `DISABLED` permits the disabled-mode behavior. `ENABLED_DOWN`, `TRANSITION`, and `UNKNOWN` fail closed.

**Exit criteria:** a repeatable, documented state signal and state-transition test matrix. Do not proceed to automatic client gateway switching without this.

### Phase 2 — Gateway architecture and threat/failure analysis

**Goal:** design the data plane without touching live networking.

Tasks:
- Choose a project-owned policy-routing table and priorities only after inspecting Happ's active rules and all existing table use. Do not assume table 2022 is available merely because the temporary experiment used it.
- Define LAN subnet bypass and client-source routing for multiple clients.
- Design an owned nftables table with explicit forward, return, NAT, and fail-closed rules.
- Ensure client packets can leave only via `happ-xray` while enabled; all other non-LAN egress must drop.
- Define connection tracking, DNS behavior, MTU considerations, rp_filter requirements, and handling when the TUN disappears.
- Decide how Dell follows Pi state: likely a small Dell-side NetworkManager/systemd agent or a deliberately configured client-side mechanism. Pi-side changes alone cannot reliably change a remote host's default route.
- Define IPv6 behavior and document direct-router RA bypass.
- Specify systemd units, ordering, reconciliation interval/events, locking, idempotence, logs, health checks, and rollback.

**Exit criteria:** reviewed architecture, rule/route diagrams, explicit failure matrix, and user approval before implementation.

### Phase 3 — Configuration model and testable core

**Goal:** implement logic without applying host networking changes.

Tasks:
- Create a validated client configuration format supporting multiple clients with IPv4 address and optional MAC.
- Reject duplicate IPs, invalid addresses, out-of-subnet entries, invalid interface names, and unsafe configuration.
- Implement state evaluation and transition/debounce logic.
- Generate nftables and policy-routing plans from configuration and state.
- Separate plan/dry-run output from apply operations.
- Add unit tests for parsing, validation, state transitions, stale signals, and rule generation.
- Keep core logic testable without root or access to the live network.

**Exit criteria:** deterministic tests pass; dry-run output is reviewable and makes no system changes.

### Phase 4 — Pi data-plane implementation

**Goal:** implement controlled forwarding on the Pi.

Tasks:
- Add project-owned nftables objects only; never flush the global ruleset.
- Enable IPv4 forwarding through a project-owned sysctl configuration only after explicit approval.
- Apply source-policy routing for registered clients while preserving Happ rules.
- Permit client-to-LAN traffic as designed.
- Permit client Internet egress only through `happ-xray`.
- Add established/related return handling and masquerade on the TUN.
- Drop client IPv4 Internet egress when tunnel/state is not safe.
- Drop forwarded client IPv6.
- Ensure no changes redirect Pi-originated traffic or interfere with Happ's own routes.
- Provide backup and rollback before activation.

**Exit criteria:** route lookups, nftables inspection/counters, and controlled packet tests prove correct egress and return behavior; fail-closed tests pass.

### Phase 5 — Lifecycle, recovery, and observability

**Goal:** make the Pi gateway reliable across normal lifecycle events.

Tasks:
- Add systemd-managed state monitor/reconciler with correct ordering after networking and Happ components.
- React to Happ state changes, TUN appearance/disappearance, Wi-Fi up/down, and reboot.
- Use locking and idempotent reconciliation to prevent overlapping updates.
- Ensure rule transitions are atomic or fail closed throughout; never create a gap where client traffic can use ordinary Wi-Fi WAN.
- Provide `status`, `check`, `logs`, and safe diagnostic commands.
- Report observed intent state separately from tunnel readiness and effective gateway state.

**Exit criteria:** reboot, Wi-Fi reconnect, Happ OFF/ON, tunnel loss, and tunnel recovery tests pass without manual repair or leakage.

### Phase 6 — Android client integration

**Goal:** migrate Android from the old Dell gateway to the Pi only after Pi-side verification.

Tasks:
- Verify Android's current static/DHCP configuration and address reservation.
- Confirm subnet/prefix and gateway values.
- Switch gateway to Pi `192.168.0.118` only during an approved test window.
- Test LAN access, DNS, IPv4 public address, tunnel loss, Happ OFF, and reconnect.
- Verify IPv6 is not silently bypassing the Pi; configure router/client IPv6 as needed.

**Exit criteria:** Android behavior matches the state matrix and shows no direct-WAN fallback when Happ is enabled but unavailable.

### Phase 7 — Dell client integration

**Goal:** make Dell follow the same state machine safely.

Tasks:
- Verify Dell's current Wi-Fi IP, interface, gateway, NetworkManager profile, and active routes.
- Identify and document stale rules and configuration from the previous Dell-as-gateway experiment.
- Design and test a Dell-side state-following mechanism.
- In confirmed Happ-disabled mode, restore/retain the ordinary router gateway.
- In enabled-and-ready mode, route through Pi.
- In enabled-down, transitioning, or unknown mode, fail closed.
- Remove old Dell leftovers only after source ownership is proven and the user approves.

**Exit criteria:** Dell's public IPv4 matches the Pi Happ exit while enabled and connected; no direct-WAN fallback occurs during failure; normal routing returns only when Happ is positively disabled.

### Phase 8 — Packaging, documentation, and release

**Goal:** provide maintainable installation and recovery.

Tasks:
- Build a Pi-specific installer with dependency checks and preflight validation.
- Do not install the read-only alpha diagnostic as a service.
- Provide update/repair, status, check, logs, backup, rollback, and uninstall commands.
- Ensure uninstall removes only project-owned files, nftables objects, sysctl settings, and units.
- Document client onboarding, router reservations, IPv6 caveat, supported OS/Happ versions, and troubleshooting.
- Add a test checklist and known limitations.

**Exit criteria:** clean install, upgrade/repair, reboot, recovery, and uninstall have been tested and documented.

## 6. Validation matrix

| Test | Expected result |
|---|---|
| Happ explicitly OFF | Clients are not forced through Pi VPN; Dell uses ordinary router |
| Happ ON and connected | Registered clients use Happ public IPv4 |
| Happ ON, then TUN disappears | Client Internet is blocked; no Wi-Fi WAN fallback |
| Happ state signal unavailable | Fail closed |
| Conflicting or stale state indicators | Fail closed |
| Happ reconnects | Gateway restores only after intent and tunnel readiness are verified |
| Pi Wi-Fi drops/reconnects | No client WAN leak; gateway recovers automatically |
| Pi reboot | Safe default until state and tunnel are verified |
| LAN/router access | Works according to documented LAN exception policy |
| IPv6 client traffic through Pi | Dropped; no IPv6 NAT/forwarding |
| Router advertises IPv6 directly | Documented and handled on router/client; not misrepresented as Pi-protected |
| Pi-originated traffic | Existing Happ and normal Pi networking remain unaffected |
| Android | Verified independently |
| Dell | Verified independently, including its own state-following agent |

## 7. Out of scope

- Replacing, reconfiguring, or reverse-engineering Happ's VPN protocol.
- Changing the Pi's own default route or making the Pi itself depend on the gateway data plane.
- IPv6 gateway support.
- Reusing the old Ubuntu iptables installer on Raspberry Pi OS.
- Automatically deleting unrelated routing rules or firewall configuration.
- Client cutover before state detection and fail-closed behavior are proven.

## 8. Immediate next action

Continue with **Phase 0 and Phase 1 only**:

1. Run and compare the read-only diagnostic in Happ OFF and ON states.
2. Investigate a reliable Happ 4.7.2 enabled/disabled intent signal using read-only inspection.
3. Record the evidence and propose the state machine/signal to the user.
4. Do not install services, change routes, enable forwarding, or modify nftables yet.
