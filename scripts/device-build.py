#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Configure the Skyworth build and validate its native241 images."""

import argparse
import gzip
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import tarfile
import tempfile
import zlib


ROOT = Path(__file__).resolve().parents[1]
DEVICE = 'sk-d840n'
PACKAGE_DEFAULTS = (
    'sk-layout-check', 'kmod-bonding', 'block-mount', 'kmod-usb-storage',
    'kmod-usb-storage-uas', 'kmod-fs-ext4', 'kmod-fs-vfat', 'kmod-fs-exfat',
)
KERNEL_DRIVERS = (
    'ZTE_ZX279133_ETH', 'ZTE_ZX279133_LAN_CONDUIT', 'ZTE_ZX279133_SWITCH',
    'MDIO_ZX279133', 'PCS_XPCS', 'PHY_ZX279133_PON_SERDES', 'PHY_ZX279133_UNI_SERDES',
    'COMMON_CLK_ZX279133', 'GPIO_ZX279133', 'PINCTRL_ZX279133',
    'SPI_ZX279133_SFC', 'MTD_SPI_NAND', 'JFFS2_FS', 'LEDS_GPIO',
    'USB_XHCI_HCD', 'USB_XHCI_PLATFORM', 'USB_STORAGE',
)


def position(entry):
    return entry['target'] + '/' + entry['subtarget']


def preset():
    return ROOT / 'configs/devices' / (DEVICE + '.config')


def check_source(entry):
    target = ROOT / 'target/linux' / entry['target']
    sublevel = entry['kernel'].rsplit('.', 1)[1]
    if f'override LINUX_VERSION-6.18 := .{sublevel}' not in (target / 'Makefile').read_text():
        raise ValueError('Target kernel version differs from the external kernel pin')
    for key in ('board_source', 'kernel_source'):
        if not re.fullmatch(r'[0-9a-f]{40}', entry[key]['commit']):
            raise ValueError('External source must pin a full commit: ' + key)
    dts = (target / 'dts' / (entry['dts'] + '.dts')).read_text()
    if f'compatible = "{entry["compatible"]}"' not in dts:
        raise ValueError('The target DTS has the wrong board identity')
    drivers = set((target / entry['subtarget'] / 'config-6.18').read_text().splitlines())
    missing = [driver for driver in KERNEL_DRIVERS if f'CONFIG_{driver}=y' not in drivers]
    if missing:
        raise ValueError('Missing built-in drivers: ' + ', '.join(missing))
    if profile_setting(entry) not in preset().read_text().splitlines():
        raise ValueError('The preset selects the wrong device profile')


def profile_setting(entry):
    return f'CONFIG_TARGET_{entry["target"]}_{entry["subtarget"]}_DEVICE_{entry["profile"]}=y'


def configure(entry):
    check_source(entry)
    kernel = subprocess.check_output(
        [sys.executable, str(ROOT / 'scripts/prepare-sk-d840n-kernel.py')], text=True
    ).strip()
    if not Path(kernel).is_dir():
        raise ValueError('The prepared kernel directory is missing')
    settings = subprocess.check_output(
        ['perl', str(ROOT / 'scripts/kconfig.pl'), '+', str(preset()),
         str(ROOT / 'configs/release.config')], text=True
    )
    settings += f'CONFIG_EXTERNAL_KERNEL_TREE="{kernel}"\n'
    config = ROOT / '.config'
    if config.exists():
        (ROOT / '.config.device-build.backup').write_bytes(config.read_bytes())
    with tempfile.NamedTemporaryFile(mode='w', dir=ROOT, delete=False) as temporary:
        temporary.write(settings)
    Path(temporary.name).replace(config)


def check_config(entry, path):
    settings = set(path.read_text().splitlines())
    profiles = {line for line in settings if re.fullmatch(r'CONFIG_TARGET_\S+_DEVICE_\S+=y', line)}
    if profiles != {profile_setting(entry)}:
        raise ValueError('The resolved config must select only the Skyworth profile')
    required = {'CONFIG_TARGET_ROOTFS_JFFS2=y', 'CONFIG_KERNEL_CC_OPTIMIZE_FOR_SIZE=y',
                'CONFIG_REQUIRE_IMAGE_SIGNATURE=y', 'CONFIG_SIGN_FIRMWARE=y',
                'CONFIG_USE_APK=y', 'CONFIG_JSON_OVERVIEW_IMAGE_INFO=y'}
    required.update(f'CONFIG_PACKAGE_{package}=y' for package in PACKAGE_DEFAULTS)
    if required - settings:
        raise ValueError('Missing config settings: ' + ', '.join(sorted(required - settings)))
    if {'CONFIG_TARGET_ROOTFS_SQUASHFS=y', 'CONFIG_TARGET_ROOTFS_INITRAMFS=y',
        'CONFIG_TARGET_ROOTFS_TARGZ=y', 'CONFIG_TARGET_ROOTFS_JFFS2_NAND=y'} & settings:
        raise ValueError('SK-D840N requires the native241 JFFS2 image')
    if not any(re.fullmatch(r'CONFIG_EXTERNAL_KERNEL_TREE="[^"]+"', line) for line in settings):
        raise ValueError('The resolved config must use the prepared ZX279133 kernel')


def sha256(stream):
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1 << 20), b''):
        digest.update(chunk)
    return digest.hexdigest()


def check_upgrade(image, rootfs, entry):
    prefix = 'sysupgrade-' + entry['profile']
    limits = {'CONTROL': 64, 'kernel': 8 << 20, 'dtb': 1 << 20, 'root': 241 << 20}
    with tarfile.open(image, 'r:') as archive:
        members = archive.getmembers()
        files = [member.name for member in members if member.isreg()]
        if (sorted(files) != sorted(prefix + '/' + name for name in limits)
                or any(not member.isreg() and
                       (not member.isdir() or member.name != prefix) for member in members)):
            raise ValueError('Sysupgrade archive has invalid members')
        for name, limit in limits.items():
            if not 0 < archive.getmember(prefix + '/' + name).size <= limit:
                raise ValueError('Sysupgrade member is empty or oversized: ' + name)
        if archive.extractfile(prefix + '/CONTROL').read() != f'BOARD={entry["profile"]}\n'.encode():
            raise ValueError('Sysupgrade archive has the wrong CONTROL board')
        with archive.extractfile(prefix + '/kernel') as stream:
            header, payload = stream.read(64), stream.read()
        if len(header) != 64:
            raise ValueError('Kernel is missing its uImage header')
        magic, header_crc, _, size, load, start, data_crc, os_id, arch, kind, codec = (
            struct.unpack_from('>7I4B', header))
        if (magic != 0x27051956 or (os_id, arch, kind, codec) != (5, 22, 2, 1)
                or load != 0x80200000 or start != load or size != len(payload)
                or header_crc != zlib.crc32(header[:4] + bytes(4) + header[8:])
                or data_crc != zlib.crc32(payload)):
            raise ValueError('Kernel is not a valid ARM64 gzip uImage')
        with gzip.GzipFile(fileobj=BytesIO(payload)) as kernel:
            raw = kernel.read(64 << 20)
            version = re.escape(entry['kernel'].encode())
            if kernel.read(1) or not re.search(rb'Linux version ' + version + rb'(?:[ +\-])', raw):
                raise ValueError('Kernel version differs from the target pin')
        with archive.extractfile(prefix + '/dtb') as stream:
            dtb = stream.read()
            if (len(dtb) < 40 or dtb[:4] != b'\xd0\x0d\xfe\xed'
                    or entry['compatible'].encode() + b'\0' not in dtb):
                raise ValueError('Sysupgrade is missing its board DTB')
        with archive.extractfile(prefix + '/root') as stream, rootfs.open('rb') as standalone:
            if stream.read(2) != b'\x85\x19':
                raise ValueError('Sysupgrade root is not little-endian JFFS2')
            stream.seek(0)
            if sha256(stream) != sha256(standalone):
                raise ValueError('Sysupgrade root differs from the standalone JFFS2 image')


def check_images(entry, directory):
    info = json.loads((directory / 'profiles.json').read_text())
    if info.get('target') != position(entry) or info.get('linux_kernel', {}).get('version') != entry['kernel']:
        raise ValueError('Image target or kernel version differs from the Skyworth profile')
    profiles = info['profiles']
    if set(profiles) != {entry['profile']}:
        raise ValueError('Image directory must contain only the Skyworth profile')
    images = profiles[entry['profile']]['images']
    if sorted(image['type'] for image in images) != ['rootfs', 'sysupgrade']:
        raise ValueError('Expected one standalone rootfs and one sysupgrade image')
    paths = {}
    for image in images:
        name = image['name']
        if Path(name).name != name:
            raise ValueError('Invalid firmware filename: ' + name)
        path = directory / name
        with path.open('rb') as stream:
            if sha256(stream) != image['sha256']:
                raise ValueError('Firmware checksum mismatch: ' + name)
        paths[image['type']] = path
    check_upgrade(paths['sysupgrade'], paths['rootfs'], entry)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    commands.add_parser('check-source')
    for action in ('configure', 'check-config', 'check-images'):
        command = commands.add_parser(action)
        command.add_argument('device', choices=(DEVICE,))
        if action == 'check-config':
            command.add_argument('path', type=Path, nargs='?', default=ROOT / '.config')
        if action == 'check-images':
            command.add_argument('path', type=Path)
    args = parser.parse_args()
    try:
        entry = json.loads((ROOT / 'config/device-build.json').read_text())['devices'][DEVICE]
        if args.action == 'configure':
            configure(entry)
        elif args.action == 'check-source':
            check_source(entry)
        elif args.action == 'check-config':
            check_config(entry, args.path)
        else:
            check_images(entry, args.path)
    except (OSError, ValueError, KeyError, EOFError, struct.error, tarfile.TarError,
            subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + '\n')
    print(f'{args.action} passed for {DEVICE}')


if __name__ == '__main__':
    main()
