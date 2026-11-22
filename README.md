> Русская версия: [README_RU.md](README_RU.md)

# Shared VPN for the home network (Raspberry Pi)

Default device: the Raspberry Pi (`pi5home`). Commands on this page run on the Pi unless they say otherwise.

## What this project is

This project lets several devices in your home (an Android phone and a Linux computer called `dell`) use the Happ VPN through a single device, a Raspberry Pi 5 called `pi5home`. Traffic from those devices leaves the house through the VPN, without each device needing its own setup.

**Current state (2026-11-22):** the Pi shares its Happ VPN with `dell` and the phone. Both are set to use the Pi (`192.168.0.118`) as their gateway. When Happ is ON, their internet exits through the Pi's VPN; when Happ is OFF, it goes through the router. The phone's DNS is answered by a small encrypted DNS forwarder on the Pi (`192.168.0.118`, see "Phone DNS" below). This is confirmed working: the phone's public address is a VPN address (for example `152.233.43.93`), not the home connection's own address (`46.8.62.23`).

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
| Phone DNS through the Pi | Done (2026-11-22). Encrypted DNS forwarder on the Pi; the phone must use `192.168.0.118` as DNS (see below) |
| Happ OFF survives a Pi reboot | Done in code (2026-11-22), deployed. Not yet tested with a real reboot |

## How the ON/OFF choice is followed

The Pi can see the VPN process, but not whether **you** want it on. The watcher reads the ON/OFF control messages from the Happ GUI and publishes that intent to `/run/vpn-gateway/state.json`. The controller follows it:

- Happ ON and the tunnel is up: client traffic goes through the VPN.
- Happ OFF (positively observed): client traffic goes through the router.
- Missing, stale, unknown, or contradictory: clients are blocked.

If a new ruleset cannot be applied, the controller falls back to **blocked** rather than leaving the normal path open. It never flushes the global nftables ruleset and never enables `nftables.service`.

**After a reboot.** The state file lives in `/run`, which is cleared at boot. So the watcher also saves your last explicit ON or OFF to `/var/lib/vpn-gateway/last_choice.json`. After a reboot, a saved OFF is used only while the tunnel is down. A live tunnel, a saved ON, or no saved choice still blocks clients.

## What you need to do

1. **Android gateway — done (2026-11-15).** The phone's gateway is `192.168.0.118` and it has no VPN app, so its traffic goes through the Pi. Confirmed: the phone's public address is a VPN address (`152.233.43.93`), while the home connection's own address is `46.8.62.23`.
2. **The computer's VPN (Happ on `dell`).** Do you still use Happ on that computer? If not, should it be removed or left as it is? Nothing will be changed on it until you answer.
3. **Happ OFF test — done (2026-11-15).** With Happ OFF the controller reports `ORDINARY` and `dell` still has internet through the router, at the home address `46.8.62.23`.

4. **After a Pi reboot with Happ OFF — fixed in code (2026-11-22), not yet tested with a real reboot.** The Pi remembers your last explicit OFF and uses it while the tunnel is down. Before this fix, clients stayed blocked until Happ was toggled. A reboot test (with Happ OFF) still needs your approval.
5. **Phone DNS — set once on the phone.** In the phone's Wi-Fi settings for this network, set DNS to `192.168.0.118`. Also set Settings → Network → **Private DNS** to **Off**: Android's Private DNS overrides the Wi-Fi DNS, so the phone would skip the Pi's forwarder.

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

**Phone DNS forwarder (not in the installer yet).** On 2026-11-22 the Pi got a DNS forwarder by hand: the Debian package `unbound`, with the config saved in this repo as `dns/unbound-vpn-gateway.conf` (it is installed on the Pi as `/etc/unbound/unbound.conf.d/vpn-gateway-dns.conf`). It listens on `192.168.0.118:53` for the home network and sends queries to Google's DNS over TLS (port 853), because plain UDP DNS gets no reply through the Happ tunnel. Note: installing `unbound` also points the Pi's own `/etc/resolv.conf` at this forwarder.

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
