# SPDX-License-Identifier: GPL-2.0-only
# Fetch crate archives through OpenWrt, then compile without registry access.
PKG_FILE_DEPENDS += $(TOPDIR)/package/pon/userspace/rust-vendor.mk $(SCRIPT_DIR)/pon-cargo-vendor.py

PON_CARGO_CRATES := $(shell $(PYTHON) $(SCRIPT_DIR)/pon-cargo-vendor.py list "$(CURDIR)/src/Cargo.lock" || echo INVALID_CARGO_LOCK)
ifneq ($(filter INVALID_CARGO_LOCK,$(PON_CARGO_CRATES)),)
  $(error Cannot read the locked PON Rust dependencies)
endif

define PON/CargoDownload
  define Download/$(PKG_NAME)-$(1)-$(2)
    FILE:=$(1)-$(2).crate
    URL:=https://static.crates.io/crates/$(1)
    HASH:=$(3)
  endef
  $$(eval $$(call Download,$(PKG_NAME)-$(1)-$(2)))
endef

$(foreach crate,$(PON_CARGO_CRATES),$(eval $(call PON/CargoDownload,$(word 1,$(subst /, ,$(crate))),$(word 2,$(subst /, ,$(crate))),$(word 3,$(subst /, ,$(crate))))))

# Cargo install runs from the package directory, so pass the build config explicitly.
CARGO_PKG_ARGS += --frozen --config "$(PKG_BUILD_DIR)/.cargo/config.toml"

define PON/CargoPrepare
	$(PYTHON) $(SCRIPT_DIR)/pon-cargo-vendor.py prepare "$(PKG_BUILD_DIR)/Cargo.lock" \
		--downloads "$(DL_DIR)" --build "$(PKG_BUILD_DIR)"
endef
