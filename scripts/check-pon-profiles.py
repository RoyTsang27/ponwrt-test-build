#!/usr/bin/env python3
"""Check Airoha board package defaults, resolved configurations and rootfs files."""
import argparse
from collections import Counter
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FRONTENDS = {
    'airoha,en7572': 'kmod-airoha-en7572',
    'airoha,paged-bosa': 'kmod-airoha-paged-bosa',
}
FIRMWARE = ('A60993.elf.pm', 'A60993.elf.dm')
ZN515_PROFILE = 'znxt_zn515xg-d'
ZN515_WIFI_PACKAGES = (
    'kmod-mt7915e', 'kmod-mt7916-firmware', 'znxt-zn515-mt7916-eeprom', 'wpad-openssl',
)
ZN515_WIFI_MODULES = ('cfg80211', 'mac80211', 'mt76', 'mt76-connac-lib', 'mt7915e')
ZN515_EEPROM = 'lib/firmware/mediatek/znxt-zn515-mt7916-eeprom.bin'
ZN515_WIFI_FILES = (
    'lib/firmware/mediatek/mt7916_rom_patch.bin',
    'lib/firmware/mediatek/mt7916_wa.bin',
    'lib/firmware/mediatek/mt7916_wm.bin',
    ZN515_EEPROM,
    'sbin/wifi',
    'usr/sbin/wpad',
)


def without_comments(source):
    # Preserve quoted strings, including // in a property value.
    return re.sub(r'"(?:\\.|[^"\\])*"|/\*.*?\*/|//[^\n]*',
                  lambda m: m[0] if m[0].startswith('"') else ' ', source, flags=re.S)


def expand_dts(path, stack=()):
    if path in stack:
        raise ValueError('Recursive device tree include: ' + str(path))
    source = without_comments(path.read_text())
    return re.sub(r'^\s*#include\s+"([^"\n]+)"',
                  lambda m: expand_dts(path.parent / m[1], (*stack, path)),
                  source, flags=re.M)


def node_bodies(source, selector):
    """Read balanced node bodies, ignoring braces in string properties."""
    for match in re.finditer('(?:' + selector + r')\s*\{', source):
        start = match.end()
        depth = 1
        for token in re.finditer(r'"(?:\\.|[^"\\])*"|[{}]', source[start:]):
            if token[0] == '{':
                depth += 1
            elif token[0] == '}':
                depth -= 1
            if depth == 0:
                yield source[start:start + token.start()]
                break
        else:
            raise ValueError('Unbalanced device tree node')


def property_value(body, name):
    # Current xPON/provider nodes have no child nodes containing these properties.
    matches = re.findall(r'(?:^|;)\s*' + re.escape(name) + r'\s*=\s*([^;]+);', body)
    return matches[-1].strip() if matches else None


def required_frontend(source):
    status, provider = None, None
    for body in node_bodies(source, r'\bxpon_mac\s*:\s*[\w@,-]+|&xpon_mac'):
        status = property_value(body, 'status') or status
        provider = property_value(body, 'optical-front-end') or provider
    if status not in ('"okay"', '"ok"'):
        return None
    match = re.fullmatch(r'<\s*&([\w]+)\s*>', provider or '')
    if not match:
        raise ValueError('Enabled xPON has no optical frontend phandle')
    bodies = list(node_bodies(source, r'\b' + re.escape(match[1]) + r'\s*:\s*[\w@,-]+'))
    bodies += list(node_bodies(source, r'&' + re.escape(match[1]) + r'\b'))
    compatible, status = None, '"okay"'
    for body in bodies:
        compatible = property_value(body, 'compatible') or compatible
        status = property_value(body, 'status') or status
    if status not in ('"okay"', '"ok"'):
        raise ValueError('Enabled xPON references a disabled frontend')
    packages = {package for name, package in FRONTENDS.items()
                if '"' + name + '"' in (compatible or '')}
    if len(packages) != 1:
        raise ValueError('Unknown or ambiguous optical frontend: ' + str(compatible))
    return packages.pop()


def required_packages(profile, frontend):
    packages = (frontend,) if frontend else ()
    if profile == ZN515_PROFILE:
        packages += ZN515_WIFI_PACKAGES
    return packages


def profiles(root=ROOT):
    """Use Make to resolve inherited DEVICE_PACKAGES, instead of grepping definitions."""
    source = '\n'.join('include ' + str(root / 'target/linux/airoha/image' / (soc + '.mk'))
                       for soc in ('an7581', 'an7583')) + '''
define dump
$(eval DEVICE_PACKAGES:=)
$(eval DEVICE_DTS:=)
$(eval $(call Device/$(1)))
$(info $(1)|$(DEVICE_DTS)|$(DEVICE_PACKAGES))
endef
$(strip $(foreach d,$(TARGET_DEVICES),$(call dump,$(d))))
all:
\t@:
'''
    with tempfile.TemporaryDirectory(prefix='pon-profiles-') as directory:
        makefile = Path(directory) / 'Makefile'
        makefile.write_text(source)
        output = subprocess.run(['make', '--no-print-directory', '-s', '-f', str(makefile)],
                                cwd=root, text=True, capture_output=True, check=True).stdout
    result = {}
    for line in output.splitlines():
        name, dts, packages = line.split('|')
        package_set = set()
        for package in packages.split():
            if package.startswith('-'):
                package_set.discard(package[1:])
            else:
                package_set.add(package)
        frontend = required_frontend(expand_dts(root / 'target/linux/airoha/dts' / (dts + '.dts')))
        for package in required_packages(name, frontend):
            if package not in package_set:
                raise ValueError(name + ': DEVICE_PACKAGES is missing ' + package)
        result[name] = (dts[:6], frontend)
    if not result:
        raise ValueError('No Airoha profiles found')
    return result


def check_config(path, boards):
    settings = dict(line.split('=', 1) for line in Path(path).read_text().splitlines()
                    if line.startswith('CONFIG_') and '=' in line)
    per_device = settings.get('CONFIG_TARGET_PER_DEVICE_ROOTFS') == 'y'
    for name, (soc, frontend) in boards.items():
        suffix = 'airoha_' + soc + '_DEVICE_' + name
        selected = any(settings.get('CONFIG_TARGET_' + prefix + suffix) == 'y'
                       for prefix in ('', 'DEVICE_'))
        if not selected:
            continue
        override = settings.get('CONFIG_TARGET_DEVICE_PACKAGES_' + suffix, '').strip('"').split()
        for package in required_packages(name, frontend):
            if '-' + package in override:
                raise ValueError(name + ': device override removes required ' + package)
            selection = settings.get('CONFIG_PACKAGE_' + package)
            if selection != 'y' and not (per_device and selection == 'm'):
                raise ValueError(name + ': select CONFIG_PACKAGE_' + package +
                                 '=y (or =m with per-device root filesystems)')


def check_rootfs(profile, directory, boards):
    if profile not in boards:
        raise ValueError('Unknown profile: ' + profile)
    frontend = boards[profile][1]
    if not frontend:
        return
    root = Path(directory)
    modules = ('airoha-xpon', 'airoha-pon-frontend-core', frontend.removeprefix('kmod-'))
    if profile == ZN515_PROFILE:
        modules += ZN515_WIFI_MODULES
    for module in modules:
        if not any(p.is_file() and p.stat().st_size for p in root.glob('lib/modules/*/' + module + '.ko*')):
            raise ValueError(profile + ': rootfs is missing module ' + module)
    if frontend == 'kmod-airoha-en7572':
        for name in FIRMWARE:
            path = root / 'lib/firmware/airoha/en7572' / name
            if not path.is_file() or not path.stat().st_size:
                raise ValueError(profile + ': rootfs is missing firmware ' + name)
    if profile == ZN515_PROFILE:
        for name in ZN515_WIFI_FILES:
            path = root / name
            if not path.is_file() or not path.stat().st_size:
                raise ValueError(profile + ': rootfs is missing ' + name)
        template = ROOT / 'package/firmware/znxt-zn515-mt7916-eeprom/files/mt7916_eeprom.bin'
        if (root / ZN515_EEPROM).read_bytes() != template.read_bytes():
            raise ValueError(profile + ': rootfs has the wrong MT7916D EEPROM template')


def check_zn515_image(image, boards):
    # mkimage -E -p stores this board's SquashFS at an absolute FIT offset.
    offset = subprocess.check_output(
        ['fdtget', '-t', 'u', image, '/images/rootfs-1', 'data-position'], text=True).strip()
    with tempfile.TemporaryDirectory(prefix='zn515-rootfs-') as directory:
        rootfs = Path(directory) / 'rootfs'
        subprocess.run(
            [str(ROOT / 'staging_dir/host/bin/unsquashfs4'), '-no-progress', '-offset', offset,
             '-d', str(rootfs), image, 'lib/modules', 'lib/firmware/airoha/en7572',
             'lib/firmware/mediatek', 'sbin/wifi', 'usr/sbin/wpad'], check=True)
        check_rootfs(ZN515_PROFILE, rootfs, boards)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', action='append', default=[], help='Check a resolved .config')
    parser.add_argument('--rootfs', action='append', nargs=2, default=[], metavar=('PROFILE', 'DIRECTORY'),
                        help='Check the actual rootfs used by a device image, not the shared manifest')
    parser.add_argument('--zn515-image', help='Check the rootfs embedded in a ZN515XG-D sysupgrade FIT')
    args = parser.parse_args()
    try:
        boards = profiles()
        for path in args.config:
            check_config(path, boards)
        for profile, directory in args.rootfs:
            check_rootfs(profile, directory, boards)
        if args.zn515_image:
            check_zn515_image(args.zn515_image, boards)
        for name, (_, frontend) in boards.items():
            print(name + ': ' + (frontend or 'integrated PON disabled'))
        print('Checked ' + str(len(boards)) + ' profiles: ' + str(dict(Counter(
            frontend or 'PON disabled' for _, frontend in boards.values()))))
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
