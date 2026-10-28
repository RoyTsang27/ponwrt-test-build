# Linux 6.18.59 update

PonWrt now selects Linux **6.18.59**, released on October 26, 2026. The downloaded
kernel.org archive matches the official SHA256:
`53a55ac9863a5547e292b8e381d4e4c2240dd1127d5428a7c44dbc550be23963`.
Sources: [checksum list](https://cdn.kernel.org/pub/linux/kernel/v6.x/sha256sums.asc)
and [official changelog](https://cdn.kernel.org/pub/linux/kernel/v6.x/ChangeLog-6.18.59).

The changelog contains 189 commits, including the version bump. Compared with
6.18.58, fixes include TCP congestion-control query use-after-free races,
netfilter byte-order bounds handling, a CIFS ACL heap overflow, concurrent SMB
truncate/write corruption, bridge multicast teardown, and connected-vsock packet
source validation. The update also introduces IPv6 payload-length helpers for
BIG TCP. Applicability depends on the features enabled in the image. The
changelog lists no direct Airoha driver change; no hardware PON improvement is
claimed.

One downstream bridge conntrack patch was rebased around
`skb_ipv6_payload_len()`, preserving the upstream helper while retaining the
fork's double-VLAN/PPPoE tracking and fragmentation changes. All 609 active
generic/Airoha patches apply with zero fuzz. Prepared-source checks also verify
the bridge helper and the RCU protection around both TCP congestion-control
queries, alongside the existing PCS, UART and PON-safe cleanup invariants.
The complete stack was checked against two fresh extractions of the verified
archive. Local regression results: 65 Python tests passed, 11 Linux/tool-specific
tests skipped, six JavaScript status tests passed, and all 24 frontend profiles
passed. Negative checks confirm that either missing TCP RCU lock is rejected.

The mac80211 socket-wrapper matrix includes 6.18.59. Its native
`sockaddr_unsized` definition still uses the older `kernel_connect` prototype,
so both parts of the existing compatibility fix remain necessary.
All six modeled socket-wrapper ABI cases compile successfully.

The preceding AN7583 CI failure occurred before kernel preparation: the minimal
MF UBI profile inherited an incomplete shared release policy. That policy now
explicitly selects HTTPS LuCI, strong userspace/kernel stack protection,
fortification, full RELRO, seccomp and APK. A regression check validates the
merged release policy for both minimal device profiles.

Upstream BBR, inactive experimental BBRv3, optical frontend defaults and signed
image enforcement are retained. CI cross-builds both Airoha targets, mac80211,
PON packages, and signed MD tcboot/MF UBI images, checking the installed frontend
modules and firmware. Local preparation and regression checks do not establish
hardware boot, PON registration or physical upgrade success.
