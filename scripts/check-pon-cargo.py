#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Exercise the PON package recipes with a populated DL_DIR and empty Cargo cache."""
import argparse
import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RUST_URL = ('https://raw.githubusercontent.com/immortalwrt/packages/'
            'e731ba76764082d9db71de60f1ddac43f4114101/lang/rust/rust-package.mk')
RUST_HASH = '102f1dcf6a1042be48cf20d0bc67de43c91019b99519857120864da0873761be'


def fetch(url, checksum, destination):
    if not destination.exists():
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read(16 * 1024 * 1024 + 1)
        if len(data) > 16 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != checksum:
            raise ValueError('Download checksum failed: ' + destination.name)
        destination.write_bytes(data)
    if hashlib.sha256(destination.read_bytes()).hexdigest() != checksum:
        raise ValueError('Cached checksum failed: ' + destination.name)


def check(work, downloads, rust_package):
    spec = importlib.util.spec_from_file_location('pon_vendor', ROOT / 'scripts/pon-cargo-vendor.py')
    vendor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vendor)
    downloads.mkdir(parents=True, exist_ok=True)
    rust = work / 'feeds/packages/lang/rust'
    rust.mkdir(parents=True)
    if rust_package:
        shutil.copyfile(rust_package, rust / 'rust-package.mk')
        if hashlib.sha256((rust / 'rust-package.mk').read_bytes()).hexdigest() != RUST_HASH:
            raise ValueError('Unexpected Rust feed helper')
    else:
        fetch(RUST_URL, RUST_HASH, rust / 'rust-package.mk')
    # Use the pinned feed's actual compile macro and the repository's actual
    # Download macro. Stub only the surrounding OpenWrt cross-toolchain setup.
    (rust / 'rust-values.mk').write_text('CARGO_PKG_PROFILE:=release\n')
    (work / 'include').mkdir()
    (work / 'include/package.mk').write_text('include ' + str(ROOT / 'include/download.mk') + '\n')
    shared = work / 'package/pon/userspace'
    shared.mkdir(parents=True)
    (shared / 'rust-vendor.mk').symlink_to(ROOT / 'package/pon/userspace/rust-vendor.mk')
    (work / 'rules.mk').write_text(
        'INCLUDE_DIR:=$(TOPDIR)/include\nSCRIPT_DIR:=' + str(ROOT / 'scripts') + '\n'
        'PYTHON:=python3\nCP:=cp -fpR\nHOSTCC_NOCACHE:=cc\n'
        'PKG_BUILD_DIR:=$(TOPDIR)/build/$(CHECK_PACKAGE)\n'
        'PKG_INSTALL_DIR:=$(PKG_BUILD_DIR)/install\n'
        'STAMP_PREPARED:=$(PKG_BUILD_DIR)/.prepared\n')
    harness = work / 'check.mk'
    harness.write_text(
        'include $(CHECK_MAKEFILE)\n.PHONY: prepare compile show-compile\n'
        'prepare: $(STAMP_PREPARED)\n$(STAMP_PREPARED):\n'
        '\t$(Build/Prepare)\n\ttouch "$@"\n'
        'compile:\n\t$(Build/Compile)\n'
        'show-compile:\n\t$(info $(Build/Compile))\n\t@:\n')
    env = dict(os.environ, CARGO_HOME=str(work / 'empty-cargo-home'),
               CARGO_TARGET_DIR=str(work / 'target'), CARGO_NET_OFFLINE='true')
    for package, binary in (('airoha-pon-daemons', 'airoha-pond'), ('airoha-ponctl', 'ponctl')):
        source = ROOT / 'package/pon/userspace' / package
        lock = source / 'src/Cargo.lock'
        original = lock.read_bytes()
        for name, version, checksum in vendor.crates(lock):
            filename = name + '-' + version + '.crate'
            fetch('https://static.crates.io/crates/' + name + '/' + filename,
                  checksum, downloads / filename)
        command = ['make', '--no-print-directory', '-f', str(harness), 'TOPDIR=' + str(work),
                   'DL_DIR=' + str(downloads), 'CHECK_PACKAGE=' + package,
                   'CHECK_MAKEFILE=' + str(source / 'Makefile')]
        # Preparation depends on every registered OpenWrt Download entry.
        subprocess.run(command + ['prepare'], cwd=source, env=env, check=True)
        dry = subprocess.check_output(command + ['show-compile'], cwd=source, env=env, text=True)
        if '--frozen' not in dry or '--config' not in dry:
            raise ValueError('Package compilation must use the frozen vendor config')
        # Run outside PKG_BUILD_DIR, exactly as OpenWrt does. No registry cache
        # or registry configuration is supplied to Cargo.
        subprocess.run(command + ['compile'], cwd=source, env=env, check=True)
        build = work / 'build' / package
        if not (build / 'install/bin' / binary).is_file():
            raise ValueError('Missing installed binary: ' + binary)
        if lock.read_bytes() != original or (build / 'Cargo.lock').read_bytes() != original:
            raise ValueError('Compilation changed the locked dependencies')
        print('Offline package recipe passed: ' + package, flush=True)
    if any((work / 'empty-cargo-home/registry' / part).exists() for part in ('index', 'cache', 'src')):
        raise ValueError('Offline compilation unexpectedly populated a registry cache')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('work', type=Path, help='New temporary check directory')
    parser.add_argument('--downloads', type=Path, help='Existing verified crate download cache')
    parser.add_argument('--rust-package', type=Path, help='Previously downloaded pinned Rust helper')
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    check(work, args.downloads.resolve() if args.downloads else work / 'dl', args.rust_package)


if __name__ == '__main__':
    main()
