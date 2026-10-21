# Linux 6.18.58 update

The fork now selects Linux **6.18.58**. Its source SHA256 is
`069b19f9032c4dac8149ae4b6520c35debca0f42a9f6d52ee55ba6ca9b818013`,
verified against kernel.org's
[checksum list](https://cdn.kernel.org/pub/linux/kernel/v6.x/sha256sums.asc).

The [official changelog](https://cdn.kernel.org/pub/linux/kernel/v6.x/ChangeLog-6.18.58)
contains 49 commits including the version bump. Compared with 6.18.57, notable
fixes include a KSMBD Kerberos heap out-of-bounds write, an IMA stack out-of-bounds
access, USB iowarrior disconnect races, DAMON exit races, mremap locked-memory
accounting leaks, and dm-integrity resume validation. Networking changes include
an IPv6 GRE/ERSPAN PMTU correction and an mt76 inactive-BSS deactivation fix.
Their effect depends on enabled features. The changelog contains no direct
Airoha or BBR changes; no PON throughput improvement is claimed.

Thirteen downstream patches were refreshed for the new source tree:

- Keep the bridge neighbour-address snapshot when applying the proxy-ARP guard.
- Preserve upstream phylink, SFP, fq_codel and SPI-NAND changes while retaining
  the fork's release, module-quirk, memory-default and compatible-override logic.
- Retain the upstream PCS index bounds check once, plus the AN7583 port counts.
- Rebase Airoha Ethernet/PON changes around open-failure cleanup. Guard phylink
  teardown for PON devices, which can have no phylink instance, and route a failed
  PON start through the common cleanup path.

All 609 active generic/Airoha patches apply with zero fuzz. Prepared-source
checks cover the known networking/UART invariants, PCS bounds validation and
the PON-safe error cleanup. The mac80211 compatibility check includes 6.18.58's
native `sockaddr_unsized` type and its existing `kernel_connect` prototype.
All five socket-wrapper cases pass locally. The Python regression suite passes
(69 tests discovered, 11 requiring Linux or separately built signing tools
skipped); the two PON Rust package recipes also build with an empty Cargo cache
using verified local crate sources.

The audited PON packages remain selected by default. Upstream BBR, the inactive
experimental BBRv3 patch, signed-image enforcement and the XG-040G-MD tcboot
profile are retained. Full AN7581/AN7583 kernel, mac80211 and PON cross-builds,
plus tcboot image/signature checks, run in CI after publication. Local source
checks do not establish hardware boot, PON registration or physical upgrade
compatibility.
