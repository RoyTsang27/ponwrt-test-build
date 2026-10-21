#!/usr/bin/env python3
"""Compile the mac80211 socket wrappers across the 6.18.57 stable API change."""
import argparse
import hashlib
import os
from pathlib import Path
import re
import shlex
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'package/kernel/mac80211'


def prepare(work):
    makefile = (PACKAGE / 'Makefile').read_text()
    version = re.search(r'^PKG_SOURCE_VERSION:=(\d+(?:\.\d+)+)$', makefile, re.M).group(1)
    checksum = re.search(r'^PKG_HASH:=([0-9a-f]{64})$', makefile, re.M).group(1)
    filename = 'backports-' + version + '.tar.zst'
    url = 'https://github.com/openwrt/backports/releases/download/backports-v' + version + '/' + filename
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read(64 * 1024 * 1024 + 1)
    if len(data) > 64 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != checksum:
        raise ValueError('Backports source checksum failed')
    archive = work / filename
    archive.write_bytes(data)
    source = work / 'source'
    source.mkdir()
    # Extract only after checking the repository's pinned release checksum.
    subprocess.run(['tar', '-xf', str(archive), '-C', str(source),
                    '--strip-components=1', '--no-same-owner'], check=True)
    for patch in sorted((PACKAGE / 'patches/build').glob('*.patch')):
        with patch.open('rb') as stream:
            subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-d', str(source)],
                           stdin=stream, check=True, stdout=subprocess.DEVNULL)
    return source


def check(source, work):
    compiler = shlex.split(os.environ.get('CC', 'cc'))
    # Model only the native socket types/prototype used by these wrappers.
    # Verified against official v6.12.108, v6.18.56, v6.18.57, v6.18.58 and v6.19
    # headers. In particular, 6.18.57 adds the type but retains old connect().
    versions = [((6, 12, 108), False, False), ((6, 18, 56), False, False),
                ((6, 18, 57), True, False), ((6, 18, 58), True, False),
                ((6, 19, 0), True, True)]
    for version, native_unsized, new_connect in versions:
        label = '.'.join(map(str, version))
        case = work / label
        linux = case / 'linux'
        linux.mkdir(parents=True)
        (linux / 'version.h').write_text(
            '#define KERNEL_VERSION(a,b,c) (((a) << 16) + ((b) << 8) + (c))\n'
            '#define LINUX_VERSION_CODE KERNEL_VERSION(%s,%s,%s)\n' % version)
        (linux / 'static_key.h').touch()
        unsized = ('struct sockaddr_unsized { __kernel_sa_family_t sa_family; char sa_data[]; };\n'
                   if native_unsized else '')
        (linux / 'socket.h').write_text(
            '#ifndef NATIVE_SOCKET_H\n#define NATIVE_SOCKET_H\n'
            'typedef unsigned short __kernel_sa_family_t;\n'
            'struct sockaddr { __kernel_sa_family_t sa_family; char sa_data[14]; };\n'
            + unsized + '#endif\n')
        address_type = 'sockaddr_unsized' if new_connect else 'sockaddr'
        (linux / 'net.h').write_text(
            '#include <linux/socket.h>\nstruct socket;\n'
            'int kernel_connect(struct socket *, struct ' + address_type + ' *, int, int);\n')
        unit = case / 'check.c'
        unit.write_text(
            '#include <linux/socket.h>\n#include <linux/net.h>\n'
            '_Static_assert(__builtin_offsetof(struct sockaddr_unsized, sa_data) == 2, "address layout");\n'
            'int check(struct socket *sock, struct sockaddr_unsized *addr) {\n'
            '  int (*connect_fn)(struct socket *, struct sockaddr_unsized *, int, int) = kernel_connect;\n'
            '  return connect_fn(sock, addr, sizeof(*addr), 0);\n}\n')
        subprocess.run(compiler + ['-std=gnu11', '-Wall', '-Wextra', '-Werror', '-fsyntax-only',
                                   '-I', str(source / 'backport-include'), '-I', str(case), str(unit)],
                       check=True)
        print('mac80211 socket/connect compatibility: Linux ' + label + ' passed', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('work', type=Path, help='New temporary check directory')
    parser.add_argument('--source', type=Path, help='Use an already prepared backports source tree')
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    source = args.source.resolve() if args.source else prepare(work)
    check(source, work)


if __name__ == '__main__':
    main()
