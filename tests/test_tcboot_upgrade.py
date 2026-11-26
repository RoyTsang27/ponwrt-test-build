"""Exercise tcboot image dispatch without accessing router flash."""
import io
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / 'target/linux/airoha/an7581/base-files/lib/upgrade/platform.sh'
BOARDS = ('nokia,xg-040g-md-tcboot', 'nokia,xg-140g-tf-tcboot')


class TcbootUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.image = self.directory / 'sysupgrade.bin'

    def tar_image(self, path, profile):
        with tarfile.open(path, 'w') as archive:
            for name in ('CONTROL', 'kernel', 'root'):
                entry = tarfile.TarInfo('sysupgrade-' + profile + '/' + name)
                entry.size = 4
                archive.addfile(entry, io.BytesIO(b'test'))

    def run_platform(self, command, missing='', platform=PLATFORM, board=BOARDS[0], legacy=False):
        mocks = r'''
board_name() { echo "$BOARD"; }
nand_do_platform_check() { echo "checked:$1"; }
# Match the OpenWrt helpers: an unsuccessful search may return status 0
# while producing no output. Callers must check the returned device name.
nand_find_ubi() { [ "$MISSING" = ubi ] && return 0; echo ubi0; }
nand_find_volume() {
    [ "$MISSING" = "$2" ] && return 0
    case "$2" in
        bosa) [ "$LEGACY" = 1 ] && echo ubi0_3 || echo ubi0_0 ;;
        ri) [ "$LEGACY" = 1 ] && echo ubi0_4 || echo ubi0_1 ;;
        kernel) echo ubi0_2 ;;
        rootfs) echo ubi0_3 ;;
        *) echo ubi0_5 ;;
    esac
}
nand_do_upgrade() { echo "upgraded:$CI_UBIPART:$CI_KERNPART:$CI_SKIP_KERNEL_MTD"; }
fit_do_upgrade() { echo 'unexpected FIT upgrade'; return 1; }
fw_setenv() { echo 'unexpected environment write'; return 1; }
'''
        return subprocess.run(['sh', '-c', platform.read_text() + '\n' + mocks + '\n'
                               'MISSING="$2"\nBOARD="$3"\nLEGACY="$4"\n' + command,
                               'test', str(self.image), missing, board, str(int(legacy))],
                              text=True, capture_output=True)

    def test_accepts_own_sysupgrade_tar(self):
        for board in BOARDS:
            with self.subTest(board=board):
                self.tar_image(self.image, board.replace(',', '_'))
                result = self.run_platform('platform_check_image "$1"', board=board)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), 'checked:' + board)

    def test_rejects_factory_images_and_other_profiles(self):
        for board, other in zip(BOARDS, reversed(BOARDS)):
            for image in (b'\xd0\x0d\xfe\xed', b'UBI#', other, 'nokia,xg-040g-md-ubi'):
                with self.subTest(board=board, image=image):
                    if isinstance(image, bytes):
                        self.image.write_bytes(image + b'\0' * 1024)
                    else:
                        self.tar_image(self.image, image.replace(',', '_'))
                    result = self.run_platform('platform_check_image "$1"', board=board)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn('checked:', result.stdout)

    def test_upgrade_uses_ubi_kernel_volume(self):
        for board in BOARDS:
            with self.subTest(board=board):
                result = self.run_platform('platform_do_upgrade "$1"', board=board)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), 'upgraded:ubi:kernel:1')

    def test_missing_ubi_or_personal_data_blocks_flash(self):
        for board in BOARDS:
            for missing in ('ubi', 'bosa', 'ri'):
                with self.subTest(board=board, missing=missing):
                    result = self.run_platform('platform_do_upgrade "$1"', missing, board=board)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn('upgraded:', result.stdout)
                    self.assertNotIn('environment write', result.stdout)

    def test_md_rejects_pre_layout_2_ubi_before_any_write(self):
        self.tar_image(self.image, BOARDS[0].replace(',', '_'))
        for step in ('platform_check_image', 'platform_do_upgrade'):
            with self.subTest(step=step):
                result = self.run_platform(step + ' "$1"', legacy=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('bosa must use ID 0', result.stdout)
                self.assertNotIn('upgraded:', result.stdout)

    def test_missing_existing_ubi_base_volume_is_detected(self):
        for target in ('an7581', 'an7583'):
            platform = ROOT / 'target/linux/airoha' / target / 'base-files/lib/upgrade/platform.sh'
            for missing in ('fip', 'ubootenv', 'ubootenv2', 'factory', 'bosa', 'ri'):
                with self.subTest(target=target, missing=missing):
                    result = self.run_platform('airoha_require_ubi_layout factory bosa ri',
                                               missing, platform)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('UBI base volume ' + missing + ' is missing', result.stdout)
                    self.assertEqual(result.stderr, '')


class TcbootBoardDataTests(unittest.TestCase):
    def test_both_models_expose_restorable_calibration_and_identity(self):
        script = ROOT / 'target/linux/airoha/base-files/etc/board.d/03_pon_data'
        source = re.sub(r'^\. /[^\n]+\n', '', script.read_text(), flags=re.M)
        mocks = r'''
board_name() { echo "$1"; }
board_config_update() { :; }
board_config_flush() { :; }
json_add_object() { echo "object:$1"; }
json_close_object() { :; }
json_add_string() { echo "string:$1:$2"; }
json_add_int() { echo "int:$1:$2"; }
touch() { echo "identity-available:$identity_available"; }
'''
        for board in BOARDS:
            with self.subTest(board=board):
                # board_name has no parameters in the installed script.
                result = subprocess.run(['sh', '-c', mocks +
                    '\nboard_name() { echo "' + board + '"; }\n' + source],
                    text=True, capture_output=True, check=True)
                for expected in ('object:bosa', 'object:ri', 'string:type:ubi',
                                 'int:size:262144', 'string:parent:ubi',
                                 'string:codec:nokia-ri-v1', 'object:pon_sn',
                                 'object:board_mac', 'identity-available:1'):
                    self.assertIn(expected, result.stdout)
                self.assertEqual(result.stdout.count('string:type:ubi'), 2)


if __name__ == '__main__':
    unittest.main()
