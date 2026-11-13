# User actions — 2026-11-14

Read-only baseline and hostname checks were done. Commands below are the ones you run. Nothing here changes routing or firewall rules.

## A. Android: confirm its gateway (blocks Dell cleanup)

Dell has `ip rule 8000: from 192.168.0.185 lookup 2022` and forwarding enabled (`ip_forward=1`). This may still route Android through Dell's `tun0`.

On Android, open Wi-Fi settings for the current network and note:
- IP address
- Gateway
- Prefix length / netmask
- DNS

Reply with those values. Do not change Android yet.

## B. Happ OFF / ON test (needed for Phase 1)

I cannot toggle the Happ GUI or verify its enabled state from the command line yet. The daemon's socket answers `get-privilege` but I have not found a documented enabled/disabled field.

1. Set Happ to **OFF** on the Pi.
2. Tell me. I will run:
   ```bash
   bash ~/setup-vpn-gateway/scripts/baseline-readonly.sh
   ```
   on the Pi.
3. Set Happ to **ON** and tell me. I will run the same command.

Record whether `happd` / `happ-xray` change between the two states.

## C. Dell Happ version

Dell's `happd` reports version **2.17.1**. The Pi reports **4.7.2**.

- Confirm whether Dell's Happ is intended to be part of this setup.
- If it is not, say so before any Dell cleanup.

## D. Dell cleanup (approval required, not yet done)

Do not run these until Android's gateway is confirmed (step A) and you approve:

```bash
sudo ip rule del priority 8000
```

Dell's `tun0` and the other priority 9000–9010 rules remain untouched until their owner is confirmed.

## E. Pi: already done

- Hostname set to `pi5home` (`/etc/hosts` updated).
- `sudo -n` works for `bliss`. The read-only NOPASSWD rule is already present.
- `nftables.service` stays disabled. Do not enable it.

## F. Commands for reinstall

See `docs/pi-reinstall.md` for the full checklist.
