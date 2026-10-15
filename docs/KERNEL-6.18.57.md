# Linux 6.18.57 compared with 6.18.56

The [official changelog](https://cdn.kernel.org/pub/linux/kernel/v6.x/ChangeLog-6.18.57)
contains 622 commits including the version bump. The upstream incremental patch
changes 864 files. The most relevant changes for PonWrt are:

| Area | Changes in 6.18.57 |
| --- | --- |
| Firewall and flow offload | Prevent bridge-VLAN encapsulation underflow and the resulting out-of-bounds read; fix nftables forwarding recursion, packet headroom and hook lifecycle handling. |
| IP and TCP | Validate IPv4 checksum metadata before completing checksums; fix IPv4 nexthop/route-dump races, IPv6 UDP/RAW redirect handling, and a TCP zero-copy NULL dereference involving device-memory fragments. |
| Other memory-safety fixes | Bound KSMBD authentication-response hash lengths; fix MediaTek GPIO and MMC teardown use-after-free errors. Benefits depend on enabled drivers and features. |

The upstream delta does not directly change Airoha drivers, BBR, or MTD/UBI.
For this fork, the main expected benefit is more robust networking and firewall
handling. Existing PON fixes, upstream BBR selection and the tcboot target remain
in place; no PON throughput improvement is claimed.

The kernel source SHA256 is
`5bd9acdc82ec5efc3790ae840e5aaa40dfde7efff261cf6dde902dc570acf98c`,
verified against the [official checksum list](https://cdn.kernel.org/pub/linux/kernel/v6.x/sha256sums.asc).
All 609 downstream generic/Airoha patches apply unchanged to a fresh source tree,
and the prepared-source networking/UART invariant checks pass.

This update also fixes the release verifier's host-tool search path. The previous
[6.18.56 run](https://github.com/RoyTsang27/ponwrt-test-build/actions/runs/38182790322)
built both kernels/PON stacks and the complete tcboot images, and passed the
FIT/UBI layout check. Signature verification then failed because `ucert` could
not find `usign`. The verifier now exports the host-tool directory; regression
tests run it with a clean system PATH and still reject tampered images.

Local regression tests pass (63 discovered, 11 requiring Linux or separately
built signing tools skipped). Full 6.18.57 cross-compilation and image-signature
verification run in CI. Hardware boot, PON registration and physical upgrade
testing remain unverified.
