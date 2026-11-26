#!/usr/bin/env python3
"""Check the actual tcboot factory image's FIT and reserved UBI volumes."""
import argparse
from pathlib import Path
import struct
import subprocess
import tempfile
import zlib

KERNEL_SLOT = 8 * 1024 * 1024
ERASEBLOCK = 128 * 1024
MD_PROFILE = 'nokia_xg-040g-md-tcboot'
UBI_DATA_OFFSET = 4096
LOAD_ADDRESSES = {
    MD_PROFILE: 0x80200000,
    'nokia_xg-140g-tf-tcboot': 0x80200000,
}


def check_fit(kernel_image, fdtget, profile):
    magic, size = struct.unpack_from('>II', kernel_image)
    if magic != 0xd00dfeed or not 40 <= size <= KERNEL_SLOT:
        raise ValueError('Kernel volume does not begin with a bounded FIT')
    if size > len(kernel_image):
        raise ValueError('Truncated kernel FIT')

    with tempfile.TemporaryDirectory() as directory:
        fit = Path(directory) / 'kernel.itb'
        dtb = Path(directory) / 'board.dtb'
        fit.write_bytes(kernel_image[:size])

        def get(file, node, prop, kind='s'):
            return subprocess.check_output([fdtget, '-t', kind, str(file), node, prop],
                                           text=True).strip()

        if get(fit, '/configurations', 'default') != 'config-1':
            raise ValueError('FIT default configuration is not config-1')
        config = '/configurations/config-1'
        kernel = '/images/' + get(fit, config, 'kernel')
        if get(fit, kernel, 'compression') != 'lzma' or get(fit, kernel, 'arch') != 'arm64':
            raise ValueError('FIT kernel is not LZMA-compressed arm64')
        for prop in ('load', 'entry'):
            cells = [int(cell, 16) for cell in get(fit, kernel, prop, 'x').split()]
            if cells not in ([LOAD_ADDRESSES[profile]], [0, LOAD_ADDRESSES[profile]]):
                raise ValueError(f'FIT kernel has the wrong tcboot {prop} address')
        fdt = '/images/' + get(fit, config, 'fdt')
        dtb.write_bytes(bytes(int(byte, 16) for byte in get(fit, fdt, 'data', 'bx').split()))
        if get(dtb, '/', 'compatible').split()[0] != profile.replace('_', ','):
            raise ValueError('FIT contains a different board device tree')
        if profile == MD_PROFILE:
            bootargs = set(get(dtb, '/chosen', 'bootargs').split())
            required = {'ubi.mtd=ubi,2048', 'ubi.block=0,rootfs',
                        'root=/dev/ubiblock0_3', 'rootfstype=squashfs'}
            if not required <= bootargs:
                raise ValueError('Device tree does not boot from tcboot rootfs volume 3')
    return size


def check_ubi(image, profile):
    tables = {}
    kernel_blocks = {}
    kernel_id = 2 if profile == MD_PROFILE else 0
    for offset in range(0, len(image), ERASEBLOCK):
        block = image[offset:offset + ERASEBLOCK]
        if block[:4] != b'UBI#' or len(block) != ERASEBLOCK:
            raise ValueError('Invalid UBI eraseblock')
        if (zlib.crc32(block[:60]) ^ 0xffffffff) != struct.unpack_from('>I', block, 60)[0]:
            raise ValueError('UBI erase-counter header CRC failed')
        vid, data = struct.unpack_from('>II', block, 16)
        if (vid, data) != (2048, UBI_DATA_OFFSET):
            raise ValueError('Invalid UBI volume header offsets')
        header = block[vid:vid + 64]
        if header == b'\xff' * 64:
            continue  # ubinize can append free eraseblocks with only an EC header.
        if header[:4] != b'UBI!':
            raise ValueError('Invalid UBI volume header')
        if (zlib.crc32(header[:60]) ^ 0xffffffff) != struct.unpack_from('>I', header, 60)[0]:
            raise ValueError('UBI volume header CRC failed')
        volume, logical_block = struct.unpack_from('>II', block, vid + 8)
        if volume == 0x7fffefff:
            if logical_block not in (0, 1) or logical_block in tables:
                raise ValueError('Invalid UBI volume table layout')
            tables[logical_block] = block[data:data + 128 * 172]
        if volume == kernel_id:
            if logical_block in kernel_blocks:
                raise ValueError('Duplicate kernel logical eraseblock')
            kernel_blocks[logical_block] = block[data:]
    if set(tables) != {0, 1} or tables[0] != tables[1]:
        raise ValueError('UBI volume table copies are missing or disagree')

    volumes = {}
    for index in range(128):
        record = tables[0][index * 172:(index + 1) * 172]
        if len(record) != 172:
            raise ValueError('Truncated UBI volume table')
        if (zlib.crc32(record[:168]) ^ 0xffffffff) != struct.unpack_from('>I', record, 168)[0]:
            raise ValueError('UBI volume table CRC failed')
        reserved = struct.unpack_from('>I', record)[0]
        if not reserved:
            continue
        length = struct.unpack_from('>H', record, 14)[0]
        if not 0 < length <= 127:
            raise ValueError('Invalid UBI volume name')
        name = bytes(record[16:16 + length]).decode('ascii')
        if name in volumes:
            raise ValueError('Duplicate UBI volume name')
        volumes[name] = (index, record[12], reserved, record[144])
    if profile == MD_PROFILE:
        names = ('bosa', 'ri', 'kernel', 'rootfs', 'rootfs_data')
        if set(volumes) != set(names):
            raise ValueError('Missing or unexpected tcboot UBI volumes')
        for index, name in enumerate(names):
            vol_id, kind, reserved, flags = volumes[name]
            if (vol_id, kind, flags) != (index, 1, int(name == 'rootfs_data')):
                raise ValueError('Wrong tcboot volume ID, type or autoresize flag: ' + name)
            if index < 2 and reserved * (ERASEBLOCK - UBI_DATA_OFFSET) < 1024 * 1024:
                raise ValueError('Missing 1 MiB PON volume reservation: ' + name)
    else:
        if volumes.get('kernel', (None,))[0] != 0 or volumes.get('rootfs', (None,))[0] != 1:
            raise ValueError('tcboot kernel/rootfs volume IDs changed')
        for name in ('bosa', 'ri'):
            if name not in volumes or volumes[name][1] != 2 or volumes[name][2] < 3:
                raise ValueError('Missing reserved static PON volume: ' + name)
    if not kernel_blocks or sorted(kernel_blocks) != list(range(len(kernel_blocks))):
        raise ValueError('Incomplete UBI kernel volume')
    return b''.join(kernel_blocks[index] for index in range(len(kernel_blocks)))


def check(path, fdtget, profile, raw_ubi):
    raw_ubi = raw_ubi or profile == MD_PROFILE
    prefix = 0 if raw_ubi else KERNEL_SLOT
    max_image = (252 if raw_ubi else 255) * 1024 * 1024
    image_size = path.stat().st_size
    if not prefix < image_size <= max_image:
        raise ValueError('Factory image size exceeds the tcboot layout')
    if (image_size - prefix) % ERASEBLOCK:
        raise ValueError('Factory UBI payload is not eraseblock aligned')
    image = path.read_bytes()
    kernel = check_ubi(memoryview(image)[prefix:], profile)
    size = check_fit(kernel, fdtget, profile)
    if prefix and image[:size] != kernel[:size]:
        raise ValueError('Factory FIT prefix differs from the UBI kernel volume')
    print(f'{path.name}: tcboot FIT, board identity and reserved PON volumes verified')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('factory', type=Path)
    parser.add_argument('--fdtget', default='fdtget')
    parser.add_argument('--profile', choices=LOAD_ADDRESSES, default=MD_PROFILE)
    parser.add_argument('--raw-ubi', action='store_true', help='Check the TF raw UBI image')
    args = parser.parse_args()
    try:
        check(args.factory, args.fdtget, args.profile, args.raw_ubi)
    except (OSError, ValueError, struct.error, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
