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
