#!/usr/bin/env python3
"""Passive probe on the Pi (default host): what the Android phone asks its gateway and DHCP server.

Listens on wlan0 for 120 seconds and prints only ARP and DHCP messages that involve the
phone (192.168.0.185, MAC f0:35:75:23:34:62). Read-only. Needs root for raw packets:
  sudo python3 scripts/probe-android-gateway.py

Result on 2026-11-14: no phone ARP or DHCP seen in 120 s (the phone's ARP cache was still valid).
"""
import socket, struct, time
ANDROID_MAC = bytes.fromhex("f0357523" + "3462")
ANDROID_IP = socket.inet_aton("192.168.0.185")
s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0003))
s.bind(("wlan0", 0)); s.settimeout(1)
def mac(b): return ":".join(f"{x:02x}" for x in b)
def ip(b): return socket.inet_ntoa(b)
seen = set()
end = time.time() + 120
while time.time() < end:
    try:
        pkt, _ = s.recvfrom(65535)
    except socket.timeout:
        continue
    eth = pkt[12:14]
    if eth == b"\x08\x06" and len(pkt) >= 42:
        op = struct.unpack(">H", pkt[20:22])[0]
        smac, sip, tip = pkt[22:28], pkt[28:32], pkt[38:42]
        if smac == ANDROID_MAC or sip == ANDROID_IP:
            key = ("arp", op, mac(smac), ip(sip), ip(tip))
            if key not in seen:
                seen.add(key)
                print(f"ARP {'request' if op == 1 else 'reply'}: {mac(smac)} {ip(sip)} asks/answers for {ip(tip)}", flush=True)
    elif eth == b"\x08\x00" and len(pkt) > 42 and pkt[23] == 17:
        ihl = (pkt[14] & 0x0F) * 4
        u = 14 + ihl
        sport, dport = struct.unpack(">HH", pkt[u:u+4])
        if {sport, dport} & {67, 68}:
            b = u + 8
            chaddr = pkt[b+28:b+34]
            if chaddr != ANDROID_MAC and pkt[b+16:b+20] != ANDROID_IP and pkt[b+12:b+16] != ANDROID_IP:
                continue
            opts = {}
            i = b + 240
            while i < len(pkt):
                code = pkt[i]
                if code == 255: break
                if code == 0: i += 1; continue
                ln = pkt[i+1]; opts[code] = pkt[i+2:i+2+ln]; i += 2 + ln
            key = ("dhcp", tuple(sorted((k, bytes(v)) for k, v in opts.items() if k in (1,3,6,50,53,54))))
            if key in seen: continue
            seen.add(key)
            names = {1: "subnet", 3: "router", 6: "dns", 50: "requested-ip", 53: "msg-type", 54: "server-id"}
            parts = []
            for k, v in sorted(opts.items()):
                if k not in names: continue
                if k == 6: val = ", ".join(ip(v[j:j+4]) for j in range(0, len(v), 4))
                elif k == 3 or k in (50, 54): val = ip(v[:4])
                elif k == 1: val = ip(v[:4]) + " (mask " + str(bin(int.from_bytes(v[:4],"big")).count("1")) + " bits)"
                elif k == 53: val = {1:"DISCOVER",2:"OFFER",3:"REQUEST",5:"ACK",6:"NAK",8:"INFORM"}.get(v[0], str(v[0]))
                parts.append(f"{names[k]}={val}")
            print(f"DHCP from {'client' if sport == 68 else 'server'} chaddr={mac(chaddr)}: " + "; ".join(parts), flush=True)
print("probe finished", flush=True)
