# Upstream integration audit — November 3, 2026

## Compared snapshots and scope

- Source: `pbs05/ponwrt:master` at
  [`03c134544714617e196dd399c85ebb90fb6eefa1`](https://github.com/pbs05/ponwrt/commit/03c134544714617e196dd399c85ebb90fb6eefa1).
- Starting destination: `RoyTsang27/ponwrt-test-build:codex/security-audit` at
  `185da37faf5d2a722c89c88d39d1340657262cc9`.
- Common ancestor: `04986da1e63cf2c52521c1aa737ee5d59e05986d`.
- Upstream-only ancestry: 1,044 commits, comprising 1,026 non-merge commits and
  18 merge commits. The destination initially had 25 exclusive commits.

The [complete inventory](UPSTREAM-REVIEW-2026-11-03.csv) records a disposition for
every incoming commit: 23 imported, two earlier kernel bumps superseded by
6.18.60, 18 merge umbrellas not imported, and 1,001 deferred. All incoming paths
and subjects were triaged; the selected bundle received source-diff review and
the checks below. Deferred changes are **not cleared as secure** by this audit.

Imports use `git cherry-pick -x` to retain authorship and exact upstream source
references without admitting unrelated merge ancestry. Original upstream SHAs
therefore remain outside the destination's ancestry even when their patches
have been integrated. This supersedes the earlier recommendation-only review.

## Imported changes

Each commit below links to the reviewed upstream diff. The destination commit
messages contain its full original SHA.

| Upstream commit | Reason for import and applicability |
| --- | --- |
| [83c18c360e](https://github.com/pbs05/ponwrt/commit/83c18c360eaf0ba35c267536d4294195a13598ba) | Release the TRX mapping and descriptor on bad magic. |
| [e056c32ed0](https://github.com/pbs05/ponwrt/commit/e056c32ed0042b54d567059420454a4864b2222e) | Check the flash-supplied TRX length before calculating its CRC. This protects a root-run utility against corrupted input, rather than establishing a new privilege boundary. |
| [d09134f6ed](https://github.com/pbs05/ponwrt/commit/d09134f6edeff8d445cb96ed3689f4d072a9666f) | Bound NVRAM variable scans, CRC reads and file mappings; retain optional-platform support without enabling NVRAM on Airoha. |
| [b2cca02d47](https://github.com/pbs05/ponwrt/commit/b2cca02d47072c0abe6bec095a306e0646247592) | Reject overflowing salt/number lengths, invalid SRP parameter indices and overflowing receive lengths in the EAD client. The package installs the daemon, not this manually built client; EAD is not enabled in the supplied profiles. |
| [5edcc1c43c](https://github.com/pbs05/ponwrt/commit/5edcc1c43cb97048b506168fbbe00538956796d6) | Update OpenSSL 3.5.8 to the 3.5.9 security release. |
| [b71d03a79c](https://github.com/pbs05/ponwrt/commit/b71d03a79cabe2d9d627e365046d99858287b21c) | Make OpenSSL probe its intended cross compiler when the host compiler differs. |
| [64901feeea](https://github.com/pbs05/ponwrt/commit/64901feeea93b317428b786a4949c00527602437) | Update json-c to 0.19, including deep-nesting and large array-index robustness changes. Keep its unused CLI out of firmware. |
| [e95288dcd5](https://github.com/pbs05/ponwrt/commit/e95288dcd5fa61004c08a07f5d051a3af2192872) | Required companion to json-c 0.19: move object freeing outside `assert()` so release builds do not leak nested objects. |
| [9b835ec626](https://github.com/pbs05/ponwrt/commit/9b835ec6264f3364a22a9c67909f16bf5e5328d1) | Supply libffi in the core tree so development-feed migration cannot remove its only provider. |
| [32bec3df41](https://github.com/pbs05/ponwrt/commit/32bec3df4163228f00dd1cd054a28e7053f4d2ac) | Stage `fficonfig.h` for libffi consumers such as node.js. |
| [53e165762c](https://github.com/pbs05/ponwrt/commit/53e165762c16ad6891efe20f36ba3a3e7f2e0fef) | Lock the shared Airoha ADC, verify mux selection and reject zero gain instead of returning a false critical temperature or dividing by zero. |
| [3a985c7398](https://github.com/pbs05/ponwrt/commit/3a985c739820c0acb37f94bcfd90ce61d7b46930) | Restore MT7530 VLAN0 after bridge teardown and untag bridge PVID traffic correctly. |
| [8fb27e6f5c](https://github.com/pbs05/ponwrt/commit/8fb27e6f5c6a679ad2569fc2a443c6d12bd177d0) | Keep fraglist GRO opt-in on Airoha, avoiding oversized GRO batches being dropped during routed IPv4 multicast/IPTV forwarding. |
| [829275e7ab](https://github.com/pbs05/ponwrt/commit/829275e7ab0a355b35768bf455046882081642a1) | Register the HG5585F-CT PHY reset GPIO before its first probe by specifying the PHY ID. |
| [e2cf59b780](https://github.com/pbs05/ponwrt/commit/e2cf59b7801d20a4bc33e270fcd3145069c23f39) | Align UNG00A panel LED configuration with its PHY/port wiring. |
| [be388d995d](https://github.com/pbs05/ponwrt/commit/be388d995dfe38138bd29ae324664d72ae99fd86) | Regenerate mac80211 metadata after a driver makefile changes. |
| [18d0619283](https://github.com/pbs05/ponwrt/commit/18d0619283a4de1dc5091a7c10596d6746edb403) | Use the channel's band for Ethernet-encapsulation offload and drop frames without channel context. |
| [c6c02f7e79](https://github.com/pbs05/ponwrt/commit/c6c02f7e799e5aea6d2945261ff07cd993ac4ac1) | Preserve repeated random bytes when generating the uhttpd certificate ID. |
| [274c8a3d7c](https://github.com/pbs05/ponwrt/commit/274c8a3d7cf14a354c796b10e94d8d343b261406) | Reload odhcpd when DHCP service data changes; the required procd helper already exists in this branch. |
| [0dfc92701b](https://github.com/pbs05/ponwrt/commit/0dfc92701ba0eb7c5438c728a8be11420c152a90) | Import both dnsmasq name-block fixes together to avoid quadratic large-host-file reloads without wasting all remaining block space. |
| [d6c5598e2f](https://github.com/pbs05/ponwrt/commit/d6c5598e2ff78e2ae18656ace00a7c84f6ee74f6) | Check APuP station allocation before dereferencing the result. |
| [218dae245a](https://github.com/pbs05/ponwrt/commit/218dae245aad74bab478896c2f9df3dc3e2b7c4f) | Initialize the mbedTLS certificate subject-match prefix. |
| [9e21f779cb](https://github.com/pbs05/ponwrt/commit/9e21f779cb72fb9e0628ac12e13ff119585874de) | Correct the mbedTLS cipher-name suffix comparison. |

OpenSSL's [official 3.5 release notes](https://openssl-library.org/news/openssl-3.5-notes/index.html)
confirm that 3.5.9 is a security release, including DTLS, resource-exhaustion and
SM2 timing fixes. The affected functionality varies with configuration; this
audit does not claim every listed OpenSSL CVE is reachable in these images.
Other findings above are described as verified code defects or robustness
improvements, without assigning unverified CVE identifiers.

## Follow-up fixes and integration

- Reject an MTD partition smaller than a TRX header before opening/mapping and
  reading that header. The imported length checks alone did not cover this case.
- Use `uintptr_t` for NVRAM commit padding, avoiding pointer truncation and signed
  remainder calculations on a 64-bit host.
- Update the real signing-tool test builder to use json-c's declared release URL
  and disable its unused applications, matching the updated package recipe.
- Keep Linux 6.18.60, PON frontend defaults, disabled experimental BBRv3, firmware
  signature enforcement and tcboot identity-volume protections.
- Resolve only the dnsmasq release-number conflict. Its separate VRF feature
  change is not required by the imported cache fixes and was not included.
- Bump the hostapd, mac80211 and odhcpd package releases so these backports are
  visible as package upgrades; bump MTD/NVRAM for the additional bounds fixes.
- Update the [GLib recovery guide](GLIB2-BUILD.md) for the core libffi package and
  removal of a stale feed symlink. Release feed pins are retained.

## Deliberately deferred

The full list is in the inventory. Significant excluded groups include:

- Bootloader/ATF updates, DT overlays, UBI volume provisioning and image-header
  changes, including the non-Airoha development-key series. These need their own
  recovery, layout and trust-policy validation.
- HM2004-DU FTTR USB-PCS routing/MAC changes, LRO/QoS/offload expansions, and the
  AN7583 three-zone thermal binding. These require the affected hardware.
- The wider hostapd/mac80211 MLO series and its dependent ubus/WNM changes. Three
  isolated hostapd fixes were selected; this is not a wholesale wireless update.
- Unrelated Qualcomm, Realtek, Rockchip and other platform expansions; removal
  of old kernel modules/6.12 support across the tree.
- Additional ucode/procd/uhttpd Git upgrades, VRF support, cipher preference and
  optional certificate-tool changes outside the reviewed bundle.

Deferral is not a finding that these commits are malicious or unnecessary. It
means their dependencies, security behavior or hardware effects have not been
validated sufficiently to integrate them into this audit branch.

## Validation and limits

- Python regression: 80 tests discovered, 68 passed and 12 platform/tool-dependent
  tests skipped locally. The new json-c release test also passed separately with
  its real library build. All six JavaScript PON status tests and all 24 device
  frontend checks passed.
- Verify the Linux 6.18.60 archive against kernel.org's SHA256 and apply all 613
  active patches with zero fuzz. Check the prepared-source invariants, including
  negative mutations of the thermal, multicast and VLAN protections.
- Verify package-source hashes. Apply all hostapd, mac80211, OpenSSL, json-c and
  dnsmasq patches with zero fuzz. Compile seven mac80211 socket-wrapper ABI cases.
- Compile/run the actual TRX and EAD parser functions and full NVRAM parser/CLI
  CRC code with AddressSanitizer and UndefinedBehaviorSanitizer. Use mocked TRX
  I/O and temporary NVRAM files; tests never write router flash.
- Build json-c in release mode. Pass 27 upstream library tests and its CLI
  regression under Bash (macOS `/bin/sh` has incompatible `echo -n` behavior).
  Independently confirm all 66 nested JSON objects are freed with `NDEBUG`.
- CI builds both Airoha kernels and signed images, plus GLib core, mac80211 and
  both OpenSSL/mbedTLS wpad variants. The real signing-tool integration suite
  runs on Linux against the updated json-c package.

Local source/host checks do not replace the exact commit's Linux CI result or
device testing. Boot, physical upgrade, PON/OMCI registration, thermal readings,
VLAN isolation and IPTV behavior must still be checked on the affected devices.
