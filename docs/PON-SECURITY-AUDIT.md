# PON userspace and driver security audit

## Scope and integration

Reviewed `pbs05/openwrt-pon-userspace` at
`cce9d756742487b378749c606b30e13ee9b0f093` and
`pbs05/openwrt-pon-drivers` at
`e5194d2dfd169eef8f4a944fdc3f929e0287b680`. The reviewed copies and local fixes
are part of `package/pon`, with original licenses and provenance retained.
The external PON feed entries were removed to avoid duplicate package names
and prevent feed updates from discarding the fixes.

Both supported Airoha subtargets select the core stack, diagnostics and LuCI
PON/IPTV apps by default. Optical modules and calibration remain board-specific.
Packet capture and IPTV remain disabled in their shipped runtime configuration.
Release validation also requires the resolved core package selections.

The review covered OMCI/OAM framing, authentication, kernel control attributes,
netlink authorization, firmware loading, frontend lifetimes, Rust parsing and
configuration/control handlers, LuCI access rules and root-run shell helpers.
It does not prove the absence of all defects, and does not reverse-engineer
the EN7572 firmware blobs or test live optical hardware.

## Findings and changes

| Finding | Effect and correction |
| --- | --- |
| OMCI extended TX length narrows a 16-bit length plus a 10-byte header back to `u16`. | Values near 65535 wrap and can accept inconsistent frames, including trimming a ten-byte packet to six bytes. Use an unsigned integer wide enough for the addition, retaining the existing size limit. This is a local raw-socket TX path requiring `CAP_NET_RAW`; remote code execution was not demonstrated. |
| Board-image upload and recovery backups use predictable paths in shared `/tmp`. | Pre-created symlinks can redirect privileged file access; backup copies can be readable to other users. Put uploads, locks, work files and backups in checked root-owned 0700 directories; use umask 077 and exclusive temporary names. Give each upload its own token, reject symlinks, hardlinks, non-root owners and invalid lengths before flash access, and retain verified private backups for recovery. |
| Diagnostic state and archive paths are predictable in shared `/tmp`, and archive permissions are tightened only after creation. | Pre-created directories/symlinks can redirect root writes and expose configuration or captured credentials. Check ownership and permissions before using runtime directories, create archives with private permissions from the beginning, use unique staging directories and atomic publication, and serialize collection. |
| A read-only LuCI PON role can read the diagnostic archive. | Archives may contain registration credentials, raw packets and configuration. Restrict the archive path to the write role while retaining ordinary status access. |
| Enhanced-security authentication compares tags with ordinary slice equality. | Replace the potentially early-exiting comparison with `subtle::ConstantTimeEq`. This reduces timing leakage; an exploitable timing attack was not demonstrated. |
| Control sockets read unlimited request lines and serve clients serially without a timeout. | A local client can consume memory or stall status handling. Limit requests to 128 bytes with a two-second whole-request deadline and bounded response writes; reject incomplete/invalid input. Refuse to delete regular files or symlinks at the configured socket path. Control socket permissions remain 0600. |
| Raw packet descriptors lack close-on-exec. | Set `SOCK_CLOEXEC` when opening the daemon packet socket to avoid accidental inheritance by future child processes. |

The fixed authentication PSK in upstream class 332 is preserved for protocol
compatibility. This review does not establish that it provides an operator-specific
trust boundary. Debug archives still contain sensitive data for administrator
troubleshooting, and RAM backups do not survive reboot. Save needed backups
securely before rebooting. Root privileges remain necessary for the current
netlink, sysfs and network configuration backend.

## Advisories and validation

Checked the locked Rust dependency names against the official RustSec advisory
database snapshot `550efd3d587a29b2e2c2b21b17a440da4fede999`.
The one matching package advisory, `RUSTSEC-2020-0146` / `CVE-2020-36465`, affects
older generic-array releases; the locked 0.14.7 version is in its patched range
(`>= 0.13.3`). No applicable assigned CVE was confirmed by that check. The new
code findings above have no assigned CVE IDs. CI runs cargo-audit 0.22.2 against
the current advisory database for both Cargo lockfiles; there is no blanket
claim that the firmware or kernel is free of CVEs.

Regression coverage exercises all 65536 declared OMCI content lengths against
the actual C normalizer, valid baseline/extended frames, symlink and ownership
attacks, unique uploads, private backups, flash readback using a fake storage
file, constant-time tag matching and bounded Unix-socket requests. Linux CI runs
ownership tests as root; no test writes router flash. It also runs the existing
Rust suites and cross-compiles integrated packages with Linux 6.18.55 on AN7581
and AN7583. Build and test results will be recorded after CI completes.
