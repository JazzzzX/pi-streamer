include $(sort $(wildcard $(BR2_EXTERNAL_STREAMER_PATH)/package/*/*.mk))

# LDAC for Buildroot's bluez-alsa package, which has no option for it. Its dependency
# list is already fixed by the time this file is read, so the build order is given
# with a rule of its own: libldac must be installed before bluez-alsa is configured.
ifeq ($(BR2_PACKAGE_BLUEZ_ALSA)$(BR2_PACKAGE_LIBLDAC),yy)
BLUEZ_ALSA_CONF_OPTS += --enable-ldac
$(BLUEZ_ALSA_TARGET_CONFIGURE): | libldac
endif
