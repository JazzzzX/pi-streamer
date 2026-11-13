################################################################################
#
# librespot
#
################################################################################

LIBRESPOT_VERSION = 0.8.0
LIBRESPOT_SITE = $(call github,librespot-org,librespot,v$(LIBRESPOT_VERSION))
LIBRESPOT_LICENSE = MIT
LIBRESPOT_LICENSE_FILES = LICENSE
LIBRESPOT_DEPENDENCIES = host-pkgconf alsa-lib openssl
# Zeroconf through the system's Avahi daemon: a second mDNS responder (libmdns) on the
# same host collides with Avahi over the name streamer.local.
LIBRESPOT_CARGO_BUILD_OPTS = \
	--no-default-features \
	--features alsa-backend,with-avahi,native-tls

LIBRESPOT_CARGO_INSTALL_OPTS = $(LIBRESPOT_CARGO_BUILD_OPTS)

$(eval $(cargo-package))
