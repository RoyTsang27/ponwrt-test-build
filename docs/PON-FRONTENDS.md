# PON frontend defaults and missing status

The XG-040G-MF UBI firmware manifest supplied for commit `9ea2348870` contains
`kmod-airoha-xpon` and `kmod-airoha-pon-frontend`, but no `kmod-airoha-en7572`.
Both MF device trees reference an EN7572 optical frontend. The core frontend
package provides the shared API; the EN7572 package provides its driver and
both `A60993.elf.pm` and `A60993.elf.dm` firmware files.

If this driver is missing on the router, xPON waits for its frontend provider
with `-EPROBE_DEFER`. The `pon0` xPON binding and OMCI interface cannot finish
initializing, and the userspace status commands fail. This explains the observed
symptoms, but runtime driver presence has not been confirmed over SSH.
Calibration or probe failures can also prevent startup.

There is an important manifest limitation: `Image/Manifest` in `include/image.mk`
lists the shared `TARGET_DIR_ORIG`, whereas per-device image assembly can add
packages to a separate root filesystem. A module selected as `m` is valid with
`CONFIG_TARGET_PER_DEVICE_ROOTFS=y` when the device's `DEVICE_PACKAGES` includes
it. The supplied manifest alone therefore cannot prove that the flashed image
lacks the module, or establish a Linux 6.18.58 regression.

The supplied configurations now explicitly select the required frontends as
`y`, including the single-device tcboot and MF UBI configurations. This installs
them in the shared rootfs as well as the device images, and avoids depending on
per-device additions for the optical frontend. The AN7581 multi-device config
includes both frontend packages because it selects both board families; each
driver binds to its matching device-tree hardware. Existing board-specific
`DEVICE_PACKAGES` defaults are retained. Individual custom profiles can still
use `m` with per-device root filesystems.

LuCI now checks command exit status and displays stderr from `ponctl`/`pondctl`.
A missing device binding or daemon socket no longer becomes an empty stdout
parse error. JSON objects and the versioned line schema are validated before
rendering. Backend messages are rendered as text. Read-only users gain the ubus
`file.exec` method needed for these existing, explicitly allowlisted status
commands; board writes and diagnostic bundles still require write permission.

All 24 AN7581/AN7583 profiles were checked by resolving Make inheritance and
following local device-tree includes and the `optical-front-end` phandle:

| Required frontend | Device profiles |
| --- | --- |
| EN7572 (11) | `gemtek_xg2010g`, `znxt_zn515xg-d`, `znxt_zn504xg-d`, `unionman_ung00a`, `h3c_hm2004-du`, `nokia_xg-040g-md-ubi`, `nokia_xg-040g-md-ubi-usb-sfp`, `nokia_xg-040g-md-tcboot`, `nokia_xg-040g-tf-ubi`, `nokia_xg-040g-mf`, `nokia_xg-040g-mf-ubi` |
| Paged-BOSA / GN28L95 / UX3363 (5) | `fiberhome_hg5382a`, `fiberhome_hg5585f-ct`, `fiberhome_hg5585f-cu`, `fiberhome_hg5585f-ct-usb-sfp`, `fiberhome_hg5585f-cu-usb-sfp` |
| Integrated PON disabled (8) | `airoha_an7581-evb`, `airoha_an7581-evb-emmc-eagle`, `airoha_an7581-evb-emmc-kite`, `gemtek_w1700k-ubi`, `nokia_valyrian`, `quantum_q1000k-ubi`, `airoha_an7583-evb`, `airoha_an7583-evb-emmc` |

Every enabled PON profile already had the matching frontend in `DEVICE_PACKAGES`.
CI now rejects a missing profile default, an unresolved package selection, or a
per-device override removing the required frontend. Its single-device MD tcboot
and MF UBI builds additionally check the actual staged rootfs for xPON, frontend
core, frontend module, and EN7572 firmware, then verify image signatures.

For the existing MF UBI checkout, set `CONFIG_PACKAGE_kmod-airoha-en7572=y` in
`.config`, preserving other configuration choices, then run:

```sh
make defconfig
python3 scripts/check-pon-profiles.py --config .config
make -j"$(nproc)"
```

Alternatively, start with `configs/an7583.config` for the supplied multi-device
build, or merge `configs/an7583-mf-ubi.config` with `configs/release.config` for
the minimal signed MF UBI build. Use the rebuilt image or packages from that same
build; kernel modules must match the running kernel's ABI, not just its version.
The driver still requires the board's correct calibration data.

To check an assembled single-device rootfs directly:

```sh
python3 scripts/check-pon-profiles.py --rootfs nokia_xg-040g-mf-ubi \
  build_dir/target-aarch64_cortex-a53_musl/root-airoha
```

With per-device root filesystems, pass that image's `target-dir-<hash>` directory
instead of the shared rootfs. On the router, the decisive checks are the module
under `/lib/modules/$(uname -r)/`, `/sys/class/net/pon0/xpon`, and
`ponctl --device pon0 status --json`. Image assembly checks cannot establish
physical PON registration or hardware boot success.
