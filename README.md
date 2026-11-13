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
