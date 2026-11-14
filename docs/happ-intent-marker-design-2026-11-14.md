> **Superseded as the primary design (2026-11-14).** The user chose the trace-based GUI watcher, which needs no second click. This marker design is kept as a fallback. See `docs/LLM-HANDOVER.md` section 5.2.

# Happ intent marker: design (2026-11-14)

Status: DESIGN ONLY. Not implemented. Needs user approval before any code or host change.
Evidence labels: VERIFIED = observed. INFERRED = reasoned. UNKNOWN = not checked.

## 1. Why a marker

- VERIFIED: `happd.service` is active in both Happ OFF and ON states (`happ-off-on-test-2026-11-14.md`).
- VERIFIED: the daemon socket answers `success` in both states and exposes no enabled/disabled field.
- VERIFIED: the state DB `/var/lib/happd/state.db` has only `pending_push`. No intent flag.
- VERIFIED: `happd.log` records xray starts but not stops or crashes.
- VERIFIED: socket observers receive no lifecycle events (start, stop, crash). Only the controlling client does.
- VERIFIED: `status` on `xray-core` gives running or `Process not found`. Readiness only.
- VERIFIED: restart after a crash is inconsistent (one restart seen, others not). Owner unknown.

Conclusion: no supported, passive signal reports user intent. A user-set marker is the only source of intent.

## 2. States (from `DEVELOMPENT_PLAN.md` Phase 1)

| State | Marker | Readiness (TUN, xray, route) | Client behaviour |
|---|---|---|---|
| DISABLED | `disabled`, valid | any | Clients use ordinary router path |
| ENABLED_UP | `enabled`, valid | TUN up, xray running, route present | Forward through `happ-xray` only |
| ENABLED_DOWN | `enabled`, valid | not ready | Fail closed (drop client WAN) |
| TRANSITION | `enabled` or `disabled` | marker and readiness disagree, or change in progress | Fail closed |
| UNKNOWN | missing, unreadable, malformed, or unparseable | any | Fail closed |

Only DISABLED permits the ordinary path. Everything else fails closed.

## 3. Marker file

- Path: `/var/lib/vpn-gateway/happ.intent` (directory `0755 root:root`).
- Ownership: `root:root`, mode `0644`. Readable by the reconciler and diagnostics. Writable only by root.
- Format: exactly two lines, key=value, UTF-8, LF line endings:
  ```
  intent=enabled
  set_at=2026-11-14T02:30:00+03:00
  ```
- `intent` must be `enabled` or `disabled`. Any other value, extra keys, or missing `set_at` is UNKNOWN.
- Writes are atomic: write to a temp file in the same directory, `fsync`, then `rename`. Never truncate in place.
- No secrets. The file holds only the intent and a timestamp.

## 4. Setting and clearing

- Set via one project command (for example `happ-intent enabled|disabled|status`), run as root through a `sudo` rule. It only writes the marker. It never starts or stops Happ.
- Clearing is not a state. To return to UNKNOWN, delete the file (`happ-intent clear`). That fails closed.
- The GUI does not update the marker. The user sets it alongside the GUI toggle. This is the main usability cost.
- Each change prints the new state and the readiness evidence, so the user sees a mismatch at once.

## 5. Authentication and trust

- Trust comes from file ownership and mode, not from content.
- The reconciler refuses a marker that is not owned by root, is group- or world-writable, or is a symlink. Any of these is UNKNOWN.
- The `sudo` rule permits only the exact command path, no arguments wildcard. It is granted only after approval (same pattern as the read-only rule).

## 6. Readiness checks (read-only)

- TUN: `ip -br link show happ-xray` exists and is UP.
- Process: `status` on `xray-core` over `/tmp/happd.sock` returns `running:true`. Repeat across two polls to avoid a race.
- Route: main table has `default dev happ-xray` at metric lower than the `wlan0` default.
- Daemon: `happd.service` active (necessary, never sufficient).
- Readiness is a snapshot. The reconciler debounces: a state must hold for N consecutive polls (default 3, interval 2 s) before it changes firewall or routing.

## 7. Transitions

- DISABLED to ENABLED_UP: apply the client forwarding plan only after the marker is `enabled` and readiness holds for N polls.
- ENABLED_UP to ENABLED_DOWN or TRANSITION: immediately apply the drop rules for client WAN egress. Drop first, then investigate.
- Any to DISABLED: restore the ordinary path only after the marker is `disabled`. Do not remove the drop rules while readiness is unknown.
- The reconciler takes a lock (`flock /run/vpn-gateway.lock`). Overlapping runs exit without changes.

## 8. Reboot and recovery

- After reboot the marker is read as it was written. The gateway starts in fail-closed mode until the marker and readiness both agree.
- If Happ starts after the Pi (common), the state is ENABLED_DOWN until the TUN appears. Client WAN stays dropped in that window. This is intended.
- A missing marker after reboot is UNKNOWN and fails closed. The user must set `enabled` or `disabled` explicitly.
- Crash of the reconciler: the systemd unit restarts it. Its firewall and routing state persists, so a restart cannot widen access.

## 9. Failure matrix

| Case | Result |
|---|---|
| Marker missing | UNKNOWN, fail closed |
| Marker malformed or unknown value | UNKNOWN, fail closed |
| Marker not root-owned, or symlink | UNKNOWN, fail closed |
| `enabled`, TUN absent | ENABLED_DOWN, drop client WAN |
| `enabled`, xray not running | ENABLED_DOWN, drop client WAN |
| `enabled`, readiness flapping | TRANSITION, drop client WAN until stable |
| `disabled`, xray running (GUI on, marker off) | TRANSITION, drop client WAN until marker and readiness agree |
| `disabled`, TUN absent | DISABLED, ordinary path |
| `happd` down | readiness fails, treated as ENABLED_DOWN if enabled, UNKNOWN if not |
| Reconciler crash mid-apply | rules remain as last applied (no widening); restart re-evaluates |

## 10. Tests before activation

Unit tests (no root, no live network):
- parse valid and invalid markers
- ownership and symlink checks (using temp dirs)
- state evaluation table above
- debounce behaviour

Controlled host tests (after approval):
1. Marker `disabled`, Happ OFF: ordinary path; no drop rules.
2. Marker `enabled`, Happ ON: ENABLED_UP; route and counters show `happ-xray`.
3. Marker `enabled`, Happ OFF: ENABLED_DOWN; drop rules active; client WAN blocked.
4. Marker `disabled`, Happ ON: TRANSITION; drop rules active.
5. Marker removed: UNKNOWN; drop rules active.
6. Kill xray with marker `enabled`: drop within N polls; no WAN fallback.
7. Reboot with marker `enabled`: fail closed until TUN appears.

## 11. Decisions (user, 2026-11-14)

1. The user sets the marker with `happ-intent`, alongside the GUI toggle. **Accepted.**
2. No expiry. A valid marker stays valid until changed. **Accepted.**
3. Path `/var/lib/vpn-gateway/happ.intent` (root-owned). **Accepted.**
4. Next step: unit tests and parser first, with no host changes. Firewall and routing code only after review. **Pending implementation approval.**
