import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('pon_vendor', ROOT / 'scripts/pon-cargo-vendor.py')
vendor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vendor)


class CargoVendorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.downloads = self.root / 'dl'
        self.downloads.mkdir()
        self.build = self.root / 'build'
        self.lock = self.root / 'Cargo.lock'

    def archive(self, entries):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w:gz') as archive:
            for name, kind, payload in entries:
                member = tarfile.TarInfo(name)
                member.type = kind
                member.mode = 0o644
                member.size = len(payload) if kind == tarfile.REGTYPE else 0
                member.linkname = '../../outside' if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE) else ''
                archive.addfile(member, io.BytesIO(payload))
        data = stream.getvalue()
        checksum = hashlib.sha256(data).hexdigest()
        (self.downloads / 'demo-1.0.0.crate').write_bytes(data)
        self.lock.write_text('version = 3\n\n[[package]]\nname = "demo"\nversion = "1.0.0"\n'
                             'source = "' + vendor.REGISTRY + '"\nchecksum = "' + checksum + '"\n')
        return checksum

    def prepare(self):
        vendor.prepare(self.lock, self.downloads, self.build)

    def test_checksums_and_local_source_configuration(self):
        checksum = self.archive([('demo-1.0.0/Cargo.toml', tarfile.REGTYPE, b'[package]\n')])
        self.prepare()
        crate = self.build / 'vendor/demo-1.0.0'
        metadata = json.loads((crate / '.cargo-checksum.json').read_text())
        self.assertEqual(metadata['package'], checksum)
        self.assertEqual(metadata['files']['Cargo.toml'], hashlib.sha256(b'[package]\n').hexdigest())
        config = (self.build / '.cargo/config.toml').read_text()
        self.assertIn('replace-with = "pon-vendored"', config)
        self.assertIn('offline = true', config)
        # Regenerating the build sources must be repeatable.
        self.prepare()
        self.assertEqual(json.loads((crate / '.cargo-checksum.json').read_text()), metadata)

    def test_missing_or_corrupt_cache_fails_before_installing_sources(self):
        self.archive([('demo-1.0.0/Cargo.toml', tarfile.REGTYPE, b'test')])
        path = self.downloads / 'demo-1.0.0.crate'
        path.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.prepare()
        path.unlink()
        with self.assertRaises(FileNotFoundError):
            self.prepare()
        self.assertFalse((self.build / 'vendor').exists())
        self.assertFalse((self.build / '.cargo/config.toml').exists())

    def test_archive_traversal_and_links_are_rejected(self):
        for name, kind in [('demo-1.0.0/../../outside', tarfile.REGTYPE),
                           ('/outside', tarfile.REGTYPE), ('other/Cargo.toml', tarfile.REGTYPE),
                           ('demo-1.0.0/link', tarfile.SYMTYPE),
                           ('demo-1.0.0/link', tarfile.LNKTYPE)]:
            with self.subTest(name=name, kind=kind):
                self.archive([(name, kind, b'data')])
                with self.assertRaisesRegex(ValueError, 'Unsafe'):
                    self.prepare()
                self.assertFalse((self.root / 'outside').exists())

    def test_symlink_cache_and_build_paths_are_rejected(self):
        self.archive([('demo-1.0.0/Cargo.toml', tarfile.REGTYPE, b'test')])
        path = self.downloads / 'demo-1.0.0.crate'
        path.rename(self.root / 'original')
        path.symlink_to(self.root / 'original')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.prepare()
        (self.build / 'vendor').symlink_to(self.root / 'outside')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.prepare()

    def test_dependency_free_package_gets_offline_configuration(self):
        self.lock.write_text('version = 3\n[[package]]\nname = "ponctl"\nversion = "0.2.0"\n')
        self.prepare()
        self.assertEqual(list((self.build / 'vendor').iterdir()), [])
        self.assertTrue((self.build / '.cargo/config.toml').is_file())

    def test_unsupported_sources_and_malformed_metadata_fail_closed(self):
        self.archive([('demo-1.0.0/Cargo.toml', tarfile.REGTYPE, b'test')])
        valid = self.lock.read_text()
        for invalid in ('not a lockfile', valid.replace(vendor.REGISTRY, 'git+https://example.com/repo'),
                        valid.replace('name = "demo"', 'name = "../demo"'),
                        valid + 'checksum = "' + '0' * 64 + '"\n'):
            with self.subTest(lock=invalid):
                self.lock.write_text(invalid)
                with self.assertRaises(ValueError):
                    self.prepare()


if __name__ == '__main__':
    unittest.main()
