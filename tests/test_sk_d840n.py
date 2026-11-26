"""Verify Skyworth build metadata and native241 image components."""
import gzip
import importlib.util
import io
import json
from pathlib import Path
import struct
import subprocess
import tarfile
import tempfile
import unittest
import zlib


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('device_build', ROOT / 'scripts/device-build.py')
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)
ENTRY = json.loads((ROOT / 'config/device-build.json').read_text())['devices']['sk-d840n']


class SkyworthBuildTests(unittest.TestCase):
    def test_profile_defaults_and_source_pins(self):
        BUILD.check_source(ENTRY)
        with tempfile.TemporaryDirectory() as temporary:
            metadata = subprocess.check_output(
                ['make', '-r', '-s', '-C', 'target/linux/zte', f'TOPDIR={ROOT}',
                 f'INCLUDE_DIR={ROOT}/include', f'TMP_DIR={temporary}', 'SUBMAKE=make',
                 'DUMP=1', 'TARGET_BUILD=1', 'SUBTARGET=zx279133'], cwd=ROOT, text=True,
            )
        self.assertIn('Linux-Version: ' + ENTRY['kernel'], metadata)
        self.assertIn('Target-Profile: DEVICE_' + ENTRY['profile'], metadata)
        defaults = next(line.split(': ', 1)[1].split() for line in metadata.splitlines()
                        if line.startswith('Target-Profile-Packages:'))
        self.assertTrue(set(BUILD.PACKAGE_DEFAULTS) <= set(defaults))

    def test_native241_archive_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            image, rootfs = output / 'sysupgrade.bin', output / 'rootfs.jffs2'
            root = b'\x85\x19fixture'
            payload = gzip.compress(b'Linux version 6.18.60 test')
            header = bytearray(struct.pack(
                '>7I4B32s', 0x27051956, 0, 0, len(payload), 0x80200000, 0x80200000,
                zlib.crc32(payload), 5, 22, 2, 1, b'Skyworth test',
            ))
            struct.pack_into('>I', header, 4, zlib.crc32(header))
            parts = {'CONTROL': b'BOARD=skyworth_sk-d840n\n', 'kernel': header + payload,
                     'dtb': b'\xd0\x0d\xfe\xed' + bytes(40) + b'skyworth,sk-d840n\0',
                     'root': root}
            with tarfile.open(image, 'w') as archive:
                for name, content in parts.items():
                    member = tarfile.TarInfo('sysupgrade-skyworth_sk-d840n/' + name)
                    member.size = len(content)
                    archive.addfile(member, io.BytesIO(content))
            rootfs.write_bytes(root)
            BUILD.check_upgrade(image, rootfs, ENTRY)
            rootfs.write_bytes(root + b'changed')
            with self.assertRaisesRegex(ValueError, 'differs from the standalone'):
                BUILD.check_upgrade(image, rootfs, ENTRY)


if __name__ == '__main__':
    unittest.main()
