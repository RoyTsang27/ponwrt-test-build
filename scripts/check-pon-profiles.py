#!/usr/bin/env python3
"""Check Airoha board frontend defaults, resolved configurations and staged rootfs files."""
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
        if frontend and frontend not in package_set:
            raise ValueError(name + ': DEVICE_PACKAGES is missing ' + frontend)
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
        if not selected or not frontend:
            continue
        override = settings.get('CONFIG_TARGET_DEVICE_PACKAGES_' + suffix, '').strip('"').split()
        if '-' + frontend in override:
            raise ValueError(name + ': device override removes required ' + frontend)
        selection = settings.get('CONFIG_PACKAGE_' + frontend)
        if selection != 'y' and not (per_device and selection == 'm'):
            raise ValueError(name + ': select CONFIG_PACKAGE_' + frontend +
                             '=y (or =m with per-device root filesystems)')


def check_rootfs(profile, directory, boards):
    if profile not in boards:
        raise ValueError('Unknown profile: ' + profile)
    frontend = boards[profile][1]
    if not frontend:
        return
    root = Path(directory)
    for module in ('airoha-xpon', 'airoha-pon-frontend-core', frontend.removeprefix('kmod-')):
        if not any(p.is_file() and p.stat().st_size for p in root.glob('lib/modules/*/' + module + '.ko*')):
            raise ValueError(profile + ': rootfs is missing module ' + module)
    if frontend == 'kmod-airoha-en7572':
        for name in FIRMWARE:
            path = root / 'lib/firmware/airoha/en7572' / name
            if not path.is_file() or not path.stat().st_size:
                raise ValueError(profile + ': rootfs is missing firmware ' + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', action='append', default=[], help='Check a resolved .config')
    parser.add_argument('--rootfs', action='append', nargs=2, default=[], metavar=('PROFILE', 'DIRECTORY'),
                        help='Check the actual rootfs used by a device image, not the shared manifest')
    args = parser.parse_args()
    try:
        boards = profiles()
        for path in args.config:
            check_config(path, boards)
        for profile, directory in args.rootfs:
            check_rootfs(profile, directory, boards)
        for name, (_, frontend) in boards.items():
            print(name + ': ' + (frontend or 'integrated PON disabled'))
        print('Checked ' + str(len(boards)) + ' profiles: ' + str(dict(Counter(
            frontend or 'PON disabled' for _, frontend in boards.values()))))
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
