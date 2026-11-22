> Русская версия: [README_RU.md](README_RU.md)

# Shared VPN for the home network (Raspberry Pi)

Default device: the Raspberry Pi (`pi5home`). Commands on this page run on the Pi unless they say otherwise.

## What this project is

This project lets several devices in your home (an Android phone and a Linux computer called `dell`) use the Happ VPN through a single device, a Raspberry Pi 5 called `pi5home`. Traffic from those devices leaves the house through the VPN, without each device needing its own setup.

**Current state (2026-11-15):** the Pi shares its Happ VPN with `dell` and the phone. Both are set to use the Pi (`192.168.0.118`) as their gateway. When Happ is ON, their internet exits through the Pi's VPN; when Happ is OFF, it goes through the router. This is confirmed working: the phone has no VPN app of its own, and its public address is a VPN address (`152.233.43.93`), not the home connection's own address (`46.8.62.23`).

## Devices and addresses

| Device | Name | IP address | Note |
|---|---|---|---|
| Raspberry Pi 5 (**default device**) | `pi5home` | `192.168.0.118` | Shared VPN gateway, wired LAN (`eth0`); `wlan0` is down |
| Computer | `dell` | `192.168.0.105` | Gateway is the Pi. Older docs say `.103`; the live address is `.105` |
| Phone | Android | `192.168.0.185` | Client, static IP. Gateway is the Pi; no VPN app on the phone |
| Router | — | `192.168.0.1` | Default gateway for the whole network |

Open the Pi from another computer: `ssh bliss@192.168.0.118`

## Status

| Part | Status |
|---|---|
| Pi can be checked safely (read-only) | Done |
| See whether Happ is switched ON or OFF (from the Happ GUI) | Done. The watcher runs at every boot and follows your ON/OFF choice |
| Share the Pi's VPN with `dell` | Done (2026-11-14). `dell` exits through the Pi's Happ |
| Share the Pi's VPN with the phone | Done (2026-11-15). The phone's gateway is the Pi; its public address is a VPN address |
| Blocking clients when the VPN drops or the state is unclear | Done. Unknown or stale state means blocked |
| Fail closed if a traffic rule cannot be applied | Done. The controller falls back to blocked, not to the normal path |

## How the ON/OFF choice is followed

The Pi can see the VPN process, but not whether **you** want it on. The watcher reads the ON/OFF control messages from the Happ GUI and publishes that intent to `/run/vpn-gateway/state.json`. The controller follows it:

- Happ ON and the tunnel is up: client traffic goes through the VPN.
- Happ OFF (positively observed): client traffic goes through the router.
- Missing, stale, unknown, or contradictory: clients are blocked.

If a new ruleset cannot be applied, the controller falls back to **blocked** rather than leaving the normal path open. It never flushes the global nftables ruleset and never enables `nftables.service`.

## What you need to do

1. **Android gateway — done (2026-11-15).** The phone's gateway is `192.168.0.118` and it has no VPN app, so its traffic goes through the Pi. Confirmed: the phone's public address is a VPN address (`152.233.43.93`), while the home connection's own address is `46.8.62.23`.
2. **The computer's VPN (Happ on `dell`).** Do you still use Happ on that computer? If not, should it be removed or left as it is? Nothing will be changed on it until you answer.
3. **Happ OFF test — done (2026-11-15).** With Happ OFF the controller reports `ORDINARY` and `dell` still has internet through the router, at the home address `46.8.62.23`.

4. **After a Pi reboot with Happ OFF, clients lose internet until Happ is toggled ON and OFF once.** The Pi cannot see your OFF choice after a restart, so it blocks rather than guessing. This is a real gap when you keep Happ OFF; it can be fixed by remembering your last choice across reboots.

## How to tell whether a device uses the VPN

Do not compare devices by public address alone: the VPN provider hands out different exit addresses (`152.233.71.89`, `152.233.108.41`, `152.233.43.93`), so they rotate. Compare against the home connection instead:

- `curl -s --interface eth0 https://api.ipify.org` on the Pi gives the home connection's own address (`46.8.62.23` when checked).
- With the VPN on, any client's public address starts with `152.233.`.
- If a client shows the home address instead, it is bypassing the Pi's VPN.

## Setting up a new device (Raspberry Pi)

One command. It asks for your sudo password once:

```bash
git clone https://github.com/bayunderground/setup-vpn-gateway.git ~/setup-vpn-gateway && bash ~/setup-vpn-gateway/scripts/new-host-setup.sh
```

The script installs packages (including `strace`), keeps nftables off, checks Happ, updates the project, installs a sudo rule for checks without a password, starts the Happ watcher at every boot, installs the forwarding controller at every boot (project table `ip vpn_gateway` only), and enables IPv4 forwarding with `/etc/sysctl.d/90-vpn-gateway.conf`. The controller follows the Happ GUI: ON -> VPN_EXIT, OFF -> ORDINARY, unknown -> BLOCK. The read-only report goes to `/var/log/vpn-gateway/boot-baseline.log`. To remove everything it added: `bash ~/setup-vpn-gateway/scripts/new-host-setup.sh --uninstall` (it removes the units, the project table, and the sysctl file; IPv4 forwarding stays on until the next boot).

Happ is installed separately, with its own installer. The script tells you if Happ is missing.

## Safety rules

- Do not run `happ-diag --repair`. It restarts Happ.
- Do not turn on `nftables.service` on the Pi. Its default settings erase all firewall rules.
- Do not remove network routing rules unless the change has been reviewed and approved.
- If the VPN state is unclear, treat it as **off and blocked**, not as "off and fine".

## Where to find more

| Need | File |
|---|---|
| Full record of everything found so far | `docs/PROJECT-DOCUMENTARY-2026-11-14.md` |
| How the ON/OFF choice is followed | `docs/LLM-HANDOVER.md` (section 5.2) |
| Earlier marker design (fallback) | `docs/happ-intent-marker-design-2026-11-14.md` |
| Step-by-step commands for a new Pi | `docs/pi-reinstall.md` and `docs/new-host-commands.md` |
| Commands for you to run | `docs/user-commands-2026-11-14.md` |
| Project rules for developers and AI helpers | `CLAUDE.md` |
| Detailed log of past sessions | `docs/RUNNING-LOG.md` |

## Key words

- **Happ**: the VPN app. Its background part is called `happd`.
- **VPN tunnel**: the encrypted connection to the VPN server. On the Pi it appears as `happ-xray`.
- **Gateway**: the device that other devices send their internet traffic to.
- **Fail closed**: if something is unclear, block the internet connection instead of falling back to the normal one.
