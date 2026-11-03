# Linux 6.18.60 update

The Airoha kernel now selects **6.18.60**, released October 30, 2026. The downloaded
kernel.org archive matches the published SHA256:
`3c2f44ef6acc021a7ad444d9a2e6ec1ef488ff09368793d0004a6080f69d621e`.
Sources: [official checksum list](https://cdn.kernel.org/pub/linux/kernel/v6.x/sha256sums.asc)
and [stable changelog](https://cdn.kernel.org/pub/linux/kernel/v6.x/ChangeLog-6.18.60).

Compared with 6.18.59, the changelog contains 113 commits including the version
bump. Relevant changes include keyring lifetime and authorization checks,
io_uring cancellation and buffer accounting, bounded recursive IP-in-IP
segmentation, fq_codel empty-flow state, and AX.25/NET/ROM packet bounds. Several
changes affect optional features; applicability depends on the image's kernel
configuration. The stable changelog lists no direct Airoha driver change.

The previous 609 generic/Airoha patches apply to the verified archive with zero
fuzz. The selected upstream integration adds four patches: the Airoha thermal
ADC fix, two MT7530 VLAN fixes and the Airoha fraglist-GRO default change. All
**613 active kernel patches** apply with zero fuzz, following OpenWrt's order
and copying both common and versioned kernel files before patching.

Prepared-source checks preserve the earlier TCP RCU, bridge IPv6, PON cleanup,
PCS bounds and serial invariants. New checks cover ADC locking and zero gain,
VLAN0 restoration/PVID untagging, and opt-in fraglist GRO. Negative mutations
confirm that removing these new protections is rejected.
The prepared tree also retains 6.18.60's IPv4/IPv6 GSO recursion guards and
CoDel empty-flow timer reset.

The mac80211 socket-wrapper matrix now includes the actual 6.18.60 header ABI:
native `sockaddr_unsized`, with the older `kernel_connect` prototype. All seven
compatibility cases compile. The complete wireless patch stack and all 62
hostapd patches also apply with zero fuzz to their checksum-verified sources.

The [upstream integration audit](UPSTREAM-AUDIT-2026-11-03.md) records the 23
selected commits, follow-up parser fixes and deferred work. Upstream BBR,
inactive experimental BBRv3, default PON frontends, tcboot identity-volume
guards and mandatory image signatures are retained.

CI cross-builds both Airoha targets, GLib core, wireless backports, OpenSSL and
mbedTLS wpad variants, PON packages, and signed MD tcboot/MF UBI images. Local
source preparation and host tests do not establish router boot, PON registration,
physical VLAN/IPTV behavior or upgrade success. Check the exact commit's CI
result before treating the firmware build as validated.
