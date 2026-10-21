#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Prepare locked PON Rust dependencies from OpenWrt's verified download cache."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile
import tempfile

REGISTRY = 'registry+https://github.com/rust-lang/crates.io-index'


def crates(lock):
    """Read the registry fields of Cargo.lock's generated package records."""
    result = []
    seen = set()
    blocks = re.split(r'^\[\[package\]\][ \t]*$', lock.read_text(), flags=re.M)[1:]
    if not blocks:
        raise ValueError('Cargo.lock has no package records')
    for block in blocks:
        fields = {}
        for key in ('name', 'version', 'source', 'checksum'):
            match = re.search(r'^' + key + r' = "([^"\\]+)"$', block, re.M)
            if len(re.findall(r'^' + key + r'\s*=', block, re.M)) > 1:
                raise ValueError('Duplicate Cargo.lock field: ' + key)
            if re.search(r'^' + key + r'\s*=', block, re.M) and not match:
                raise ValueError('Unsupported Cargo.lock field: ' + key)
            fields[key] = match.group(1) if match else None
        if not fields['name'] or not fields['version']:
            raise ValueError('Missing Cargo.lock package name/version')
        if fields['source'] is None:
            continue
        if fields['source'] != REGISTRY:
            raise ValueError('Unsupported Cargo source: ' + fields['source'])
        name, version, checksum = (fields[k] for k in ('name', 'version', 'checksum'))
        if (not re.fullmatch(r'[A-Za-z0-9_-]+', name) or
                not re.fullmatch(r'[0-9][A-Za-z0-9.+-]*', version) or
                not checksum or not re.fullmatch(r'[0-9a-f]{64}', checksum)):
            raise ValueError('Invalid locked crate metadata')
        if (name, version) in seen:
            raise ValueError('Duplicate locked crate')
        seen.add((name, version))
        result.append((name, version, checksum))
    return sorted(result)


def unpack(data, crate, checksum, vendor):
    destination = vendor / crate
    destination.mkdir()
    files, seen, total = {}, set(), 0
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        for member in archive:
            parts = PurePosixPath(member.name).parts
            if (not parts or parts[0] != crate or '..' in parts or
                    '\\' in member.name or parts in seen or
                    not (member.isfile() or member.isdir())):
                raise ValueError('Unsafe crate archive member: ' + member.name)
            seen.add(parts)
            total += member.size
            if len(seen) > 10000 or total > 128 * 1024 * 1024:
                raise ValueError('Crate archive is too large')
            relative = Path(*parts[1:])
            target = destination / relative
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if len(parts) == 1 or relative.as_posix() == '.cargo-checksum.json':
                raise ValueError('Invalid crate file')
            target.parent.mkdir(parents=True, exist_ok=True)
            payload = archive.extractfile(member).read()
            target.write_bytes(payload)
            target.chmod(member.mode & 0o755)
            files[relative.as_posix()] = hashlib.sha256(payload).hexdigest()
    (destination / '.cargo-checksum.json').write_text(
        json.dumps({'package': checksum, 'files': files}, sort_keys=True) + '\n')


def prepare(lock, downloads, build):
    build.mkdir(parents=True, exist_ok=True)
    vendor, config = build / 'vendor', build / '.cargo'
    if vendor.is_symlink() or config.is_symlink():
        raise ValueError('Generated Cargo paths must not be symlinks')
    with tempfile.TemporaryDirectory(prefix='.pon-cargo-', dir=build) as temporary:
        staged = Path(temporary) / 'vendor'
        staged.mkdir()
        for name, version, checksum in crates(lock):
            crate = name + '-' + version
            archive = downloads / (crate + '.crate')
            if archive.is_symlink():
                raise ValueError('Crate cache entry must not be a symlink')
            with archive.open('rb') as stream:
                data = stream.read(16 * 1024 * 1024 + 1)
            if len(data) > 16 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != checksum:
                raise ValueError('Crate checksum failed: ' + crate)
            unpack(data, crate, checksum, staged)
        if vendor.exists():
            shutil.rmtree(vendor)
        staged.rename(vendor)
    config.mkdir(exist_ok=True)
    text = ('[source.crates-io]\nreplace-with = "pon-vendored"\n'
            '[source.pon-vendored]\ndirectory = "vendor"\n'
            '[net]\noffline = true\n')
    with tempfile.NamedTemporaryFile(mode='w', dir=config, delete=False) as stream:
        stream.write(text)
        temporary = Path(stream.name)
    temporary.replace(config / 'config.toml')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['list', 'prepare'])
    parser.add_argument('lock', type=Path)
    parser.add_argument('--downloads', type=Path)
    parser.add_argument('--build', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'list':
            for crate in crates(args.lock):
                print('/'.join(crate))
        else:
            if args.downloads is None or args.build is None:
                parser.error('prepare requires --downloads and --build')
            prepare(args.lock, args.downloads, args.build)
    except (OSError, ValueError, tarfile.TarError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
