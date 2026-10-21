# Integrated PON packages

These are maintained copies of the two pbs05 PON repositories, at the commits
recorded in `upstream.json`, with the local changes described in
[the PON audit](../../docs/PON-SECURITY-AUDIT.md). Original licenses, source
headers, firmware, documentation and Cargo lockfiles are retained.

The package sources live here, rather than in external feeds. Feed updates
cannot replace the audited copies. AN7581 and AN7583 select the frontend core,
xPON driver, control utility, protocol daemon, diagnostic tools and both LuCI
apps by default. Optical frontend modules are still selected by each device.
Packet capture and IPTV configuration remain disabled until the administrator
enables them. EN7523 does not support these drivers.

When updating, compare both upstream trees against `upstream.json`, preserve
local security changes, update the recorded commits and package releases, and
run the security checks and both Airoha kernel/PON package builds. Never add
these repositories back as feeds alongside these built-in packages.

Existing PON feed symlinks are ignored by the package scanner, so an older
checkout cannot override these copies. For housekeeping, run `./scripts/feeds
uninstall -a` followed by the normal feed update/install steps after switching
to this branch. Use the new `feeds.conf.release` or `feeds.conf.default`; a
previously copied `feeds.conf` may still list the removed external PON feeds.

The Rust packages register every external crate from `Cargo.lock` as an OpenWrt
download, with its locked SHA256. Preparation creates a local Cargo directory
source from those verified archives. Compilation uses `--frozen` and an explicit
offline configuration, including when Cargo runs outside the build directory.
No crates.io index or Cargo registry cache is needed during compilation.

Prefetch with `make download -j4`, or download just the daemon dependencies with
`make package/pon/userspace/airoha-pon-daemons/download V=s`. This stage still
needs access to `static.crates.io` or a populated OpenWrt `dl/` cache. For an
offline build, transfer the verified `.crate` files into `dl/` first. A missing
or corrupted archive stops preparation; TLS and checksum checks stay enabled.

After updating an existing checkout, rebuild the two Rust packages:

```sh
make package/pon/userspace/airoha-pon-daemons/clean
make package/pon/userspace/airoha-ponctl/clean
make download -j4
make package/pon/userspace/airoha-pon-daemons/compile -j1 V=s
make package/pon/userspace/airoha-ponctl/compile -j1 V=s
```

Keep `Cargo.lock` committed when changing dependencies; download metadata is
derived from that lockfile. `scripts/check-pon-cargo.py` checks the package
prepare/compile recipes with the pinned Rust feed helper, local crate archives,
and an empty Cargo cache. CI also tests source behavior and dependency advisories.
