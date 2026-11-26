# Skyworth SK-D840N

The ZTE ZX279133 profile targets SK-D840N devices with the native241 NAND layout
and a compatible U-Boot that loads a legacy uImage and a separate DTB. The
profile builds in the ZTE Ethernet, switch, SerDes, SPI NAND, USB controller,
and JFFS2 drivers. It installs Ethernet bonding, USB storage with UAS, and
ext4, FAT and exFAT support by default.

## Build

Use a supported Linux OpenWrt build host and a case-sensitive filesystem.
Install `zopfli` alongside the normal build prerequisites, then run these commands.

```sh
cp feeds.conf.release feeds.conf
./scripts/feeds update -a
./scripts/feeds install -a
python3 scripts/device-build.py configure sk-d840n
make defconfig
python3 scripts/device-build.py check-config sk-d840n
make -j"$(nproc)"
python3 scripts/device-build.py check-images sk-d840n bin/targets/zte/zx279133
bash scripts/verify-release.sh bin/targets/zte/zx279133
```

The configure command prepares the pinned Linux 6.18.60 source and saves any
existing `.config` as `.config.device-build.backup`. In menuconfig the profile
appears at **ZTE SoCs → ZX279133 → Skyworth SK-D840N**.

## Images

The profile produces a standalone `rootfs.jffs2` and a signed `sysupgrade.bin`
containing the JFFS2 root filesystem, DTB, and kernel. Use the sysupgrade image
on an existing compatible SK-D840N installation. The upgrade verifies the
running NAND layout before writing the three image partitions. The bootloader
and the device-specific parameter tags are outside those partitions.
