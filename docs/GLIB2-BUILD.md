# GLib cannot find target libffi

The reported GLib 2.88.1 failure occurs during target package configuration:

```text
pkg-config --modversion libffi -> 1
Package libffi was not found in the pkg-config search path.
Run-time dependency libffi found: NO
ERROR: Subproject exists but has no meson.build file.
```

The final message is a secondary error: Meson tries GLib's libffi fallback after
the cross-target dependency lookup fails. The log uses the target staging
directory for both `PKG_CONFIG_PATH` and `PKG_CONFIG_LIBDIR`. Installing Ubuntu's
`libffi-dev` does not supply an AArch64 library in that directory.

The reviewed packages feed at
[`e731ba76764082d9db71de60f1ddac43f4114101`](https://github.com/immortalwrt/packages/blob/e731ba76764082d9db71de60f1ddac43f4114101/libs/glib2/Makefile)
declares `+libffi` on `glib2-gobject` and `glib2-gio`, and `+zlib` on `glib2-gio`.
Although these are split output packages, `scripts/package-metadata.pl` collects
their dependencies for the whole GLib source package. Evaluating the actual
recipe and metadata generator confirms that its build graph orders target
libffi and zlib before GLib even with only `glib2-core` selected. Adding a duplicate build
dependency or changing kernel sources would not repair missing staging files.

The supplied logs do not establish why libffi was absent. Check for stale package
metadata, an incomplete libffi staging installation, a local recipe override,
or use of `NO_DEPS=1`. The earlier failed Meson feature probes are expected
configure checks, not separate compilation defects.

In the failing Linux checkout, retain `.config` and the toolchain, then regenerate
metadata and rebuild only the affected packages:

```sh
./scripts/feeds update -i packages
./scripts/feeds install libffi glib2
rm -rf tmp
make defconfig
make package/feeds/packages/glib2/clean -j1 V=s
make package/feeds/packages/libffi/clean -j1 V=s
make package/feeds/packages/libffi/compile -j1 V=s
ls -l staging_dir/target-*/usr/lib/pkgconfig/libffi.pc
make package/feeds/packages/glib2/compile -j1 V=s
make -j2 V=s
```

Stop at the first failing command and retain its complete log. These commands
assume the normal `packages` feed layout and no intentional local recipe
override. Do not use `NO_DEPS=1` when rebuilding. A full `make clean` is
unnecessary. If `libffi.pc` is still absent after libffi compiles, inspect its
`Build/InstallDev` output and the target staging stamp rather than modifying
GLib's bundled subproject.

CI now builds `glib2-core=m` for both Airoha targets with GObject, GIO and libffi
unselected. It relies on the generated dependency graph to stage target libffi
and checks for `libffi.pc` after the cross-build. GLib core remains outside the
firmware images used by these checks.
