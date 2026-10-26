import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('pon_profiles', ROOT / 'scripts/check-pon-profiles.py')
profiles = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profiles)


class PonProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.boards = profiles.profiles()

    def test_inherited_defaults_match_all_board_device_trees(self):
        self.assertEqual(self.boards['nokia_xg-040g-mf-ubi'][1], 'kmod-airoha-en7572')
        self.assertEqual(self.boards['nokia_xg-040g-md-tcboot'][1], 'kmod-airoha-en7572')
        self.assertEqual(self.boards['fiberhome_hg5585f-cu-usb-sfp'][1], 'kmod-airoha-paged-bosa')
        self.assertIsNone(self.boards['nokia_valyrian'][1])

    def test_missing_inherited_frontend_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / 'target/linux/airoha/image'
            image.mkdir(parents=True)
            (image.parent / 'dts').symlink_to(ROOT / 'target/linux/airoha/dts', target_is_directory=True)
            for soc in ('an7581', 'an7583'):
                source = (ROOT / 'target/linux/airoha/image' / (soc + '.mk')).read_text()
                (image / (soc + '.mk')).write_text(source.replace('kmod-airoha-en7572', ''))
            with self.assertRaisesRegex(ValueError, 'DEVICE_PACKAGES is missing kmod-airoha-en7572'):
                profiles.profiles(root)

    def test_shared_and_per_device_package_selections(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / '.config'
            selected = 'CONFIG_TARGET_airoha_an7583_DEVICE_nokia_xg-040g-mf-ubi=y\n'
            for selection, per_device, valid in (
                    ('y', False, True), ('m', False, False), ('n', False, False),
                    ('m', True, True), ('n', True, False)):
                with self.subTest(selection=selection, per_device=per_device):
                    config.write_text(selected + 'CONFIG_PACKAGE_kmod-airoha-en7572=' + selection + '\n' +
                                      ('CONFIG_TARGET_PER_DEVICE_ROOTFS=y\n' if per_device else ''))
                    if valid:
                        profiles.check_config(config, self.boards)
                    else:
                        with self.assertRaisesRegex(ValueError, 'CONFIG_PACKAGE_kmod-airoha-en7572'):
                            profiles.check_config(config, self.boards)

    def test_per_device_override_cannot_remove_frontend(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / '.config'
            config.write_text('CONFIG_TARGET_DEVICE_airoha_an7583_DEVICE_nokia_xg-040g-mf-ubi=y\n'
                              'CONFIG_PACKAGE_kmod-airoha-en7572=y\n'
                              'CONFIG_TARGET_PER_DEVICE_ROOTFS=y\n'
                              'CONFIG_TARGET_DEVICE_PACKAGES_airoha_an7583_DEVICE_nokia_xg-040g-mf-ubi=' +
                              '"-kmod-airoha-en7572"\n')
            with self.assertRaisesRegex(ValueError, 'override removes required'):
                profiles.check_config(config, self.boards)

    def test_provider_phandle_not_unrelated_i2c_node_determines_frontend(self):
        source = '''
        xpon_mac: xpon-mac@1 { status = "disabled"; };
        unrelated: optical-front-end@50 { compatible = "airoha,en7572"; };
        bosa: optical-front-end@51 { compatible = "fiberhome,hg5x-bosa", "airoha,paged-bosa"; };
        &xpon_mac { optical-front-end = <&bosa>; status = "okay"; };
        '''
        self.assertEqual(profiles.required_frontend(source), 'kmod-airoha-paged-bosa')
        with self.assertRaisesRegex(ValueError, 'Unknown or ambiguous'):
            profiles.required_frontend(source.replace('airoha,paged-bosa', 'other,frontend'))
        with self.assertRaisesRegex(ValueError, 'disabled frontend'):
            profiles.required_frontend(source + '&bosa { status = "disabled"; };')

    def test_rootfs_requires_module_and_both_firmware_blobs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            modules = root / 'lib/modules/6.18.58'
            modules.mkdir(parents=True)
            for name in ('airoha-xpon', 'airoha-pon-frontend-core', 'airoha-en7572'):
                (modules / (name + '.ko')).write_bytes(b'module fixture')
            firmware = root / 'lib/firmware/airoha/en7572'
            firmware.mkdir(parents=True)
            for name in profiles.FIRMWARE:
                (firmware / name).write_bytes(b'firmware fixture')
            profiles.check_rootfs('nokia_xg-040g-mf-ubi', root, self.boards)
            (modules / 'airoha-en7572.ko').unlink()
            with self.assertRaisesRegex(ValueError, 'missing module airoha-en7572'):
                profiles.check_rootfs('nokia_xg-040g-mf-ubi', root, self.boards)
            (modules / 'airoha-en7572.ko.zst').write_bytes(b'compressed module fixture')
            profiles.check_rootfs('nokia_xg-040g-mf-ubi', root, self.boards)
            for name in profiles.FIRMWARE:
                path = firmware / name
                path.write_bytes(b'')
                with self.assertRaisesRegex(ValueError, 'missing firmware ' + name):
                    profiles.check_rootfs('nokia_xg-040g-mf-ubi', root, self.boards)
                path.write_bytes(b'firmware fixture')


if __name__ == '__main__':
    unittest.main()
