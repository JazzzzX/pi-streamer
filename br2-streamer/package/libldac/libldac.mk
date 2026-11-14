################################################################################
#
# libldac
#
################################################################################

LIBLDAC_VERSION = 5b4bf66096ba0d69615efb2422ba3d023c34c2fd
LIBLDAC_SITE = $(call github,open-vela,external_libldac,$(LIBLDAC_VERSION))
LIBLDAC_LICENSE = Apache-2.0
LIBLDAC_LICENSE_FILES = LICENSE NOTICE
LIBLDAC_INSTALL_STAGING = YES
# LDACBT_LIB_VER_* in src/ldacBT_api.c
LIBLDAC_SO_VERSION = 2.0.72

# The source has no build system for Linux other than a set of sample makefiles.
# ldaclib.c and ldacBT.c include all the other source files. One library holds the
# encoder, the decoder and the adaptive bit rate module; the three pkg-config names
# are the ones bluez-alsa asks for.
define LIBLDAC_BUILD_CMDS
	$(TARGET_CC) $(TARGET_CFLAGS) -std=gnu11 -fPIC -shared \
		-Wl,-soname,libldacBT.so.2 \
		-I$(@D)/inc -I$(@D)/src -I$(@D)/abr/inc \
		$(@D)/src/ldaclib.c $(@D)/src/ldacBT.c $(@D)/abr/src/ldacBT_abr.c \
		$(TARGET_LDFLAGS) -lm -o $(@D)/libldacBT.so.$(LIBLDAC_SO_VERSION)
endef

define LIBLDAC_INSTALL_LIB
	$(INSTALL) -D -m 0755 $(@D)/libldacBT.so.$(LIBLDAC_SO_VERSION) \
		$(1)/usr/lib/libldacBT.so.$(LIBLDAC_SO_VERSION)
	ln -sf libldacBT.so.$(LIBLDAC_SO_VERSION) $(1)/usr/lib/libldacBT.so.2
endef

define LIBLDAC_INSTALL_STAGING_CMDS
	$(call LIBLDAC_INSTALL_LIB,$(STAGING_DIR))
	ln -sf libldacBT.so.2 $(STAGING_DIR)/usr/lib/libldacBT.so
	$(INSTALL) -D -m 0644 $(@D)/inc/ldacBT.h $(STAGING_DIR)/usr/include/ldac/ldacBT.h
	$(INSTALL) -D -m 0644 $(@D)/abr/inc/ldacBT_abr.h $(STAGING_DIR)/usr/include/ldac/ldacBT_abr.h
	mkdir -p $(STAGING_DIR)/usr/lib/pkgconfig
	$(foreach m,enc dec abr,\
		sed -e 's/@MODULE@/$(m)/' -e 's/@VERSION@/$(LIBLDAC_SO_VERSION)/' \
			$(LIBLDAC_PKGDIR)/ldacBT.pc.in \
			> $(STAGING_DIR)/usr/lib/pkgconfig/ldacBT-$(m).pc$(sep))
endef

# The Apache License asks for the license and the notice to go with the binary.
define LIBLDAC_INSTALL_TARGET_CMDS
	$(call LIBLDAC_INSTALL_LIB,$(TARGET_DIR))
	$(INSTALL) -D -m 0644 $(@D)/LICENSE $(TARGET_DIR)/usr/share/licenses/libldac/LICENSE
	$(INSTALL) -D -m 0644 $(@D)/NOTICE $(TARGET_DIR)/usr/share/licenses/libldac/NOTICE
endef

$(eval $(generic-package))
