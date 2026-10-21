# Master integration review — 2026-10-21

Selective imports are worthwhile. A full merge needs a separate integration and
build pass because master also contains kernel, bootloader and subsystem changes.

Compared `origin/master` at `d01485cc90` with `codex/security-audit` at
`508bc11959`, including the mac80211 compatibility fix. Git reports
861 commits reachable only from master and 19 only from security-audit. These
are ancestry counts, including merges, rather than counts of independent fixes.
The review examined the graph, affected paths and the candidate diffs below; it
does not classify every master commit as a security fix. No master commits have
been imported as part of this comparison.

## Best candidates for Airoha robustness

| Priority | Master commit | Reason and conditions |
| --- | --- | --- |
| High for routed IPTV | [`8fb27e6f5c`](https://github.com/RoyTsang27/ponwrt-test-build/commit/8fb27e6f5c) | Keep fraglist GRO opt-in on Airoha. The branch currently enables it by default; large GRO batches can be dropped by IPv4 multicast forwarding before segmentation. Verify IPTV forwarding and unicast throughput after import. The same patch path appears in `7ed681ac1c`; take the final change once. |
| High for VLAN/bridge use | [`3a985c7398`](https://github.com/RoyTsang27/ponwrt-test-build/commit/3a985c7398) | MT7530 VLAN fixes restore VLAN-unaware operation after a VLAN-aware bridge is removed and correct PVID untag handling. Check the two patches against the existing Airoha switch backports and Linux 6.18.57 before import. |
| High before adding AN7583 zones | [`53e165762c`](https://github.com/RoyTsang27/ponwrt-test-build/commit/53e165762c) | Serialize the shared thermal ADC, check mux selection and reject a zero gain. This prevents incorrect readings during concurrent sampling. The optional three-sensor change, `0a7d2ceb9b`, depends on this fix and also changes the device-tree binding. |
| Model-specific | [`829275e7ab`](https://github.com/RoyTsang27/ponwrt-test-build/commit/829275e7ab) | Pin the HG5585F-CT GPY211C PHY ID so reset GPIO registration precedes probing. Useful for that model's warm-boot reliability; it is not a Nokia tcboot fix. |
| Lower priority | [`e2cf59b780`](https://github.com/RoyTsang27/ponwrt-test-build/commit/e2cf59b780) | Correct UNG00A panel LED/PHY mapping. Worth taking for UNG00A support, with physical port checks. |

`41f0eb4a79` fixes MT7530 statistics reads sleeping in atomic context, but its
own implementation explicitly leaves MMIO-connected EN7581/AN7583 switches on
the direct-read path. It is useful for MDIO-connected switches elsewhere in the
tree, with less immediate benefit for these Airoha targets.

## Security and shared userspace candidates

| Master commits | Assessment |
| --- | --- |
| [`83c18c360e`](https://github.com/RoyTsang27/ponwrt-test-build/commit/83c18c360e), then [`e056c32ed0`](https://github.com/RoyTsang27/ponwrt-test-build/commit/e056c32ed0) | Take together when updating the MTD utility: close/unmap the TRX error path and validate image-provided lengths before calculating the CRC. `mtd` is selected in both saved Airoha configurations, although the TRX path is for other image formats. |
| [`d09134f6ed`](https://github.com/RoyTsang27/ponwrt-test-build/commit/d09134f6ed) | Bound NVRAM parsing and mapping to the actual partition/file. A useful malformed-input fix when this optional utility is shipped. |
| [`b2cca02d47`](https://github.com/RoyTsang27/ponwrt-test-build/commit/b2cca02d47) | Validate EAD client packet lengths, salt and parameter indices before writes/copies. Useful if EAD is shipped; importing a fix does not require enabling the service. |
| [`64901feeea`](https://github.com/RoyTsang27/ponwrt-test-build/commit/64901feeea) plus [`e95288dcd5`](https://github.com/RoyTsang27/ponwrt-test-build/commit/e95288dcd5) | Treat the json-c 0.19 upgrade and its release-build memory-leak fix as a bundle. The branch uses 0.18. Its signing-test helper also hardcodes the old json-c download location, so that helper must be updated and real signing tests repeated with an upgrade. |
| [`5edcc1c43c`](https://github.com/RoyTsang27/ponwrt-test-build/commit/5edcc1c43c), [`26410f4160`](https://github.com/RoyTsang27/ponwrt-test-build/commit/26410f4160) | OpenSSL 3.5.9 and the uhttpd source update deserve a dependency-update review. Check upstream release notes, the associated compiler/VRF changes, LuCI HTTPS and signatures; a version increase alone is not evidence of a particular CVE fix. |

These are source-level bug findings or maintenance candidates. No unverified
CVE identifiers or exploitability claims are assigned to them here.

## Build, upgrade and wireless changes to stage separately

- `195c2ce324` and `de24245e08` fix firmware-header generation with uutils/pipe
  reads. Keep the accompanying host GNU `dd` change, and preserve this branch's
  signing-error handling in `include/image-commands.mk`.
- `3f26ab3d4d` reserves the last UBI volume ID for provisioning. Test it against
  the tcboot kernel/rootfs IDs and reserved PON identity/calibration volumes
  before changing the upgrade path.
- `18d0619283` corrects the band used for mac80211 Ethernet-encapsulation
  offload. It is a focused wireless candidate. Master's wider MLO/hostapd/mt76
  series needs coordinated wireless testing and does not fix the
  `sockaddr_unsized` duplicate definition reported on Linux 6.18.57.

## Changes that need deliberate conflict resolution

Master's kernel file selects **6.18.55**, while this branch selects **6.18.57**.
Retain 6.18.57 and validate any imported kernel patches against it. Master also
carries active `951-net-tcp-bbr3-support.patch`; keep BBRv3 inactive as previously
chosen for this branch. Bootloader/ATF updates and other targets' large hardware
series need their own device and recovery validation.

A `git merge-tree` analysis, without changing the checkout/index, reports five
content conflicts: `package/base-files/Makefile`,
`package/kernel/mac80211/Makefile`, `target/linux/generic/kernel-6.18`, and the
generic `700-netfilter-nft_flow_offload-*` and `737-10-net-ethernet-mtk_eth_soc-*`
pending patches. Resolve the mac80211 package release while retaining the new
socket guard, and preserve the 6.18.57 patch refreshes and signing policy.

Recommended order: finish the mac80211 build fix; import focused Airoha
networking fixes with kernel/packet tests; handle parser/dependency fixes in
small bundles; review flash-layout, bootloader and larger wireless changes
separately. Preserve the audited default PON packages, required signatures and
tcboot calibration-volume guards throughout.
