> Русская версия: [README_RU.md](README_RU.md)

# Shared VPN for the home network (Raspberry Pi)

Default device: the Raspberry Pi (`pi5home`). Commands on this page run on the Pi unless they say otherwise.

## What this project is

This project is an attempt to let several devices in your home (an Android phone and a Linux computer called `dell`) use the Happ VPN through a single device, a Raspberry Pi 5 called `pi5home`. Traffic from those devices would leave the house through the VPN, without each device needing its own setup.

**Right now, nothing new is set up.** The Pi does not share its VPN with anyone yet, and the project is still in the investigation stage. One thing is already happening: the phone's traffic goes through the VPN on `dell` (an older setup), and that is unchanged.

## Devices and addresses

| Device | Name | IP address | Note |
|---|---|---|---|
| Raspberry Pi 5 (**default device**) | `pi5home` | `192.168.0.118` | Future shared VPN gateway, Wi-Fi (`wlan0`) |
| Computer | `dell` | `192.168.0.105` | Still runs its own Happ (version 2.17.1) |
| Phone | Android | `192.168.0.185` | Client, static IP |
| Router | — | `192.168.0.1` | Default gateway for the whole network |

Open the Pi from another computer: `ssh bliss@192.168.0.118`

## Status

| Part | Status |
|---|---|
| Pi can be checked safely (read-only) | Done |
| See whether Happ is switched ON or OFF (from the Happ GUI) | Done and installed on the Pi (2026-11-14, 03:02). The watcher runs at every boot and follows your ON/OFF choice |
| Share the Pi's VPN with the phone and computer | Not started. The watcher is ready; the traffic rules are not written yet |
| Blocking clients when the VPN drops | Not started. Planned together with the traffic rules |

## The main problem being solved

The Pi can see whether the VPN is running, but it cannot see whether **you** want it on. Those can differ, for example when the VPN drops by itself. Guessing wrong could send your traffic out of your normal internet connection without the VPN.

So the plan is: you tell the Pi your choice with a simple setting (a small file that says "on" or "off"). If that setting is missing or unclear, the shared connection is blocked rather than guessed. The design is in `docs/happ-intent-marker-design-2026-11-14.md`.

## What you need to do

Please answer these when you can. None of them change anything on their own.

1. **Android network details.** On the phone, open the Wi-Fi settings for your home network and send me:
   - IP address
   - Gateway (the address the phone sends traffic to)
   - Prefix or netmask
   - DNS servers
   - Whether the address is set by hand (static) or automatic (DHCP)

2. **The computer's VPN (Happ on `dell`).** Do you still use Happ on that computer? If not, should it be removed or left as it is? Nothing will be changed on it until you answer.

3. **Your ON/OFF choice (once the design is approved).** You will set the choice with a command, alongside the Happ app toggle. The exact steps will be written here when they exist.

## Setting up a new device (Raspberry Pi)

One command. It asks for your sudo password once:

```bash
git clone https://github.com/bayunderground/setup-vpn-gateway.git ~/setup-vpn-gateway && bash ~/setup-vpn-gateway/scripts/new-host-setup.sh
```

The script installs packages (including `strace`), keeps nftables off, checks Happ, updates the project, installs a sudo rule for checks without a password, starts the Happ watcher at every boot, and sets up a read-only check that also runs at every boot. The watcher only reads Happ's messages and writes its state to `/run/vpn-gateway/state.json`. It does not change routing or the firewall. The report goes to `/var/log/vpn-gateway/boot-baseline.log`. To remove what it added: `bash ~/setup-vpn-gateway/scripts/new-host-setup.sh --uninstall`.

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
| How the ON/OFF setting will work | `docs/happ-intent-marker-design-2026-11-14.md` |
| Step-by-step commands for a new Pi | `docs/pi-reinstall.md` and `docs/new-host-commands.md` |
| Commands for you to run | `docs/user-commands-2026-11-14.md` |
| Development plan | `DEVELOMPENT_PLAN.md` |
| Project rules for developers and AI helpers | `CLAUDE.md` |
| Detailed log of past sessions | `docs/RUNNING-LOG.md` |

## Key words

- **Happ**: the VPN app. Its background part is called `happd`.
- **VPN tunnel**: the encrypted connection to the VPN server. On the Pi it appears as `happ-xray`.
- **Gateway**: the device that other devices send their internet traffic to.
- **Fail closed**: if something is unclear, block the internet connection instead of falling back to the normal one.
