# Nokia XG-040G-MD and XG-140G-TF with tcboot U-Boot

Both AN7581 profiles are selected in `configs/an7581.config` and in the smaller
`configs/an7581-tcboot.config`, which builds just these two devices with separate
root filesystems.

In `make menuconfig`, select **Target System → Airoha ARM**, then
**Subtarget → AN7581 / AN7566 / AN7551** and one of these **Target Profile** entries:

- **Nokia XG-040G-MD (tcboot)** (`nokia_xg-040g-md-tcboot`)
- **Nokia XG-140G-TF (tcboot)** (`nokia_xg-140g-tf-tcboot`)

To build both, select **Multiple devices** and enable both entries under
**Target Devices**, with **Use a per-device root filesystem that adds profile packages**.
The existing XG-040G-MD UBI and UBI-USB-SFP entries remain available with their
original names and profile IDs. Select a tcboot profile only for the flash layout
below.

## Boot and UBI layout

The XG-040G-MD uses tcboot layout 2.0, with the FIT in UBI volume 2.
Both models load an LZMA arm64 FIT at `0x80200000`, expose `lan1` through
`lan4`, and use `pon0` as WAN. The MD image includes its EN8811H PHY,
EN7572 optical frontend, NPU firmware, and USB host and storage support.
The XG-140G-TF image uses its separate tcboot layout and hardware configuration.

| Partition | Offset | Size |
| --- | --- | --- |
| bootloader, read-only in Linux | 0 | 512 KiB |
| env | 512 KiB | 512 KiB |
| ubi | 1 MiB | 255 MiB |

Factory images use 128 KiB eraseblocks, 2 KiB pages, and a 4 KiB UBI data offset.

| UBI volume | XG-040G-MD layout 2.0 | XG-140G-TF |
| --- | --- | --- |
| `bosa` | 0, 1 MiB reserved | 3, static |
| `ri` | 1, 1 MiB reserved | 4, static |
| `kernel` | 2 | 0 |
| `rootfs` | 3 | 1 |
| `rootfs_data` | 4, autoresize | 2, autoresize |

## Build

On a supported Linux OpenWrt build host, run the following commands.

```sh
cp feeds.conf.release feeds.conf
./scripts/feeds update -a
./scripts/feeds install -a
./scripts/kconfig.pl + configs/an7581-tcboot.config configs/release.config > .config
make defconfig
python3 scripts/check-release.py --config .config
python3 scripts/check-pon-profiles.py --config .config
make -j12
```

## Choose the image

Build outputs are under `bin/targets/airoha/an7581/`. Match the filename to the
device profile and installed recovery format.

| Device | Profile | Recovery that writes directly to the `ubi` partition | PonWrt sysupgrade |
| --- | --- | --- | --- |
| XG-040G-MD | `nokia_xg-040g-md-tcboot` | `*-squashfs-factory.bin` | `*-squashfs-sysupgrade.bin` |
| XG-140G-TF | `nokia_xg-140g-tf-tcboot` | `*-squashfs-factory-ubi.bin` | `*-squashfs-sysupgrade.bin` |

The MD factory image starts with raw UBI. The XG-140G-TF also builds
`*-squashfs-factory.bin` for recovery variants that expect an 8 MiB FIT prefix.

These images require an already-installed, compatible tcboot U-Boot. The Nokia
UBI/FIP profiles use a separate bootloader and flash layout.

Factory recovery replaces the contents of `ubi`, including any existing `bosa`
and `ri`. Back up both volumes before recovery, restore the device's own backups
in LuCI under **Network → PON → Configuration → PON board data**, then reboot.
To migrate an MD installation from the earlier tcboot layout, use tcboot
recovery with the layout 2.0 factory image and restore the original `bosa`
and `ri` backups. Use the signed sysupgrade tar for later updates from the
matching layout. The MD upgrade checks the expected UBI volume IDs before
writing the kernel and root filesystem.

Use the same firmware signing key trusted by the installed PonWrt firmware.
CI checks the factory image structure and verifies the sysupgrade signatures.
Booting both models and recovering through Web U-Boot still require hardware
validation.
