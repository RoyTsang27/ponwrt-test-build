"""Resolve real image recipes and feed their metadata to the menuconfig generator."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROFILES = ('nokia_xg-040g-md-tcboot', 'nokia_xg-140g-tf-tcboot')


def definition(source, name):
    return re.search(r'^define ' + re.escape(name) + r'\n.*?^endef$',
                     source, re.M | re.S)[0]


class TcbootProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        image = (ROOT / 'include/image.mk').read_text()
        airoha = (ROOT / 'target/linux/airoha/image/Makefile').read_text()
        variables = ('DEVICE_TITLE', 'DEVICE_DTS', 'KERNEL_LOADADDR', 'KERNEL',
                     'KERNEL_SIZE', 'IMAGE_SIZE', 'BLOCKSIZE', 'PAGESIZE',
                     'UBINIZE_OPTS', 'KERNEL_IN_UBI', 'UBOOTENV_IN_UBI',
                     'DEVICE_COMPAT_VERSION', 'UBINIZE_PARTS',
                     'IMAGES', 'IMAGE/factory.bin', 'IMAGE/factory-ubi.bin',
                     'IMAGE/sysupgrade.bin', 'UBINIZE_PARTS_AFTER', 'DEVICE_PACKAGES')
        makefile = '\n'.join(definition(image, name) for name in
                             ('Device/InitProfile', 'Device/Init', 'Device/DumpInfo'))
        makefile += '\n' + definition(airoha, 'Device/Default')
        makefile += '\n' + re.search(r'^AIROHA_USB_STORAGE_PACKAGES := .*?\n\n',
                                     airoha, re.M | re.S)[0]
        makefile += '''
comma := ,
loadaddr-y := 0x80200000
KDIR := /image-build
TARGET_FILESYSTEMS := squashfs
include target/linux/airoha/image/an7581.mk
define dump
$(eval $(call Device/InitProfile,$(1)))
$(eval $(call Device/Init,$(1)))
$(eval $(call Device/Default,$(1)))
$(eval $(call Device/$(1),$(1)))
$(eval DEVICE_DISPLAY := $(DEVICE_TITLE))
'''
        makefile += '\n'.join('$(info FIELD|$(1)|' + name + '|$(' + name + '))'
                              for name in variables)
        makefile += '''
$(info $(call Device/DumpInfo,$(1)))
endef
$(strip $(foreach device,$(TARGET_DEVICES),$(call dump,$(device))))
all:
\t@:
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'Makefile').write_text(makefile)
            result = subprocess.run(['make', '-s', '--no-print-directory', '-f',
                                     str(path / 'Makefile')], cwd=ROOT, text=True,
                                    capture_output=True)
            if result.returncode:
                raise RuntimeError(result.stderr)
            cls.profiles = {}
            metadata = []
            for line in result.stdout.splitlines():
                if line.startswith('FIELD|'):
                    _, profile, name, value = line.split('|', 3)
                    cls.profiles.setdefault(profile, {})[name] = value
                else:
                    metadata.append(line)
            header = '''Target: airoha
Target-Name: Airoha ARM
Target-Arch: arm
Linux-Version: 6.18.64
Default-Packages: base-files
Target: airoha/an7581
Target-Name: AN7581 / AN7566 / AN7551
Target-Arch: aarch64
Linux-Version: 6.18.64
Default-Packages: base-files
'''
            (path / 'targetinfo').write_text(header + '\n'.join(metadata))
            cls.menuconfig = subprocess.run(
                ['perl', str(ROOT / 'scripts/target-metadata.pl'), 'config',
                 str(path / 'targetinfo')], text=True, capture_output=True, check=True).stdout

    def test_tcboot_profiles_are_selectable_with_bootloader_help(self):
        for profile in PROFILES:
            with self.subTest(profile=profile):
                symbol = 'airoha_an7581_DEVICE_' + profile
                entry = self.menuconfig.split('config TARGET_' + symbol + '\n', 1)[1]
                entry = entry.split('\nconfig ', 1)[0]
                self.assertIn('bool "' + self.profiles[profile]['DEVICE_TITLE'] + '"', entry)
                self.assertIn('depends on TARGET_airoha_an7581', entry)
                self.assertIn('existing TCBOOT U-Boot', entry)
                self.assertIn('menuconfig TARGET_DEVICE_' + symbol, self.menuconfig)

    def test_original_md_ubi_profiles_remain_separate(self):
        for profile, variant in (('nokia_xg-040g-md-ubi', 'UBI'),
                                 ('nokia_xg-040g-md-ubi-usb-sfp', 'UBI-USB-SFP')):
            with self.subTest(profile=profile):
                device = self.profiles[profile]
                self.assertEqual(device['DEVICE_TITLE'], 'Nokia XG-040G-MD (' + variant + ')')
                self.assertEqual(device['UBOOTENV_IN_UBI'], '1')
                self.assertEqual(device['IMAGES'], 'sysupgrade.itb')
                self.assertEqual(device['UBINIZE_PARTS_AFTER'], '')
                self.assertIn('config TARGET_airoha_an7581_DEVICE_' + profile, self.menuconfig)

    def test_tcboot_profiles_use_their_own_layouts(self):
        for profile in PROFILES:
            with self.subTest(profile=profile):
                device = self.profiles[profile]
                self.assertEqual(device['KERNEL_LOADADDR'], '0x80200000')
                self.assertIn('kernel-bin | lzma | fit lzma ', device['KERNEL'])
                self.assertEqual(device['BLOCKSIZE'], '128k')
                self.assertEqual(device['PAGESIZE'], '2048')
                self.assertIn('-s 2048', device['UBINIZE_OPTS'])
                self.assertEqual(device['KERNEL_IN_UBI'], '1')
                self.assertEqual(device['UBOOTENV_IN_UBI'], '')
                self.assertIn('sysupgrade-tar | append-metadata', device['IMAGE/sysupgrade.bin'])
                if profile == PROFILES[0]:
                    self.assertEqual(device['DEVICE_COMPAT_VERSION'], '2.0')
                    self.assertEqual(device['IMAGE_SIZE'], '258048k')
                    self.assertEqual(device['UBINIZE_PARTS'], 'bosa ri')
                    self.assertEqual(device['UBINIZE_PARTS_AFTER'], '')
                    self.assertEqual(device['IMAGES'].split(), ['factory.bin', 'sysupgrade.bin'])
                    self.assertEqual(device['IMAGE/factory.bin'], 'append-ubi | check-size')
                    continue
                self.assertEqual(device['KERNEL_SIZE'], '8192k')
                self.assertEqual(device['IMAGE_SIZE'], '261120k')
                self.assertEqual(device['IMAGES'].split(),
                                 ['factory.bin', 'factory-ubi.bin', 'sysupgrade.bin'])
                self.assertRegex(device['IMAGE/factory.bin'],
                                 r'append-kernel \| pad-to .*KERNEL_SIZE.* \| ')
                self.assertIn('nokia-tcboot-pon-placeholders | append-ubi',
                              device['IMAGE/factory.bin'])
                self.assertNotIn('append-kernel', device['IMAGE/factory-ubi.bin'])
                self.assertIn('check-size 258048k', device['IMAGE/factory-ubi.bin'])
                for volume in ('bosa', 'ri'):
                    self.assertIn(volume + '=:/image-build/nokia-tcboot-empty-pon-data.bin',
                                  device['UBINIZE_PARTS_AFTER'])

    def test_tf_keeps_its_usb_package_exclusions_and_pon_frontend(self):
        for profile in PROFILES:
            packages = set()
            for package in self.profiles[profile]['DEVICE_PACKAGES'].split():
                if package.startswith('-'):
                    packages.discard(package[1:])
                else:
                    packages.add(package)
            self.assertTrue({'kmod-airoha-en7572', 'kmod-airoha-xpon',
                             'airoha-ponctl', 'airoha-pond', 'nand-utils', 'ubi-utils'} <= packages)
            self.assertEqual('kmod-usb3' in packages, profile == PROFILES[0])
            self.assertEqual('kmod-usb-storage' in packages, profile == PROFILES[0])


if __name__ == '__main__':
    unittest.main()
