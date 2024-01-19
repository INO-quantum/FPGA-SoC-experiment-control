SUMMARY = "Recipe for  build an external dio24 Linux kernel module"
SECTION = "PETALINUX/modules"
LICENSE = "GPLv2"
LIC_FILES_CHKSUM = "file://COPYING;md5=12f884d2ae1ff87c09e5b7ccc2c4ca7e"

inherit module

INHIBIT_PACKAGE_STRIP = "1"

SRC_URI = "file://Makefile \
           file://driver.c \
           file://dma.c \
           file://dma.h \
           file://dio24_driver.h \
           file://driver.h \
	       file://COPYING \
          "

S = "${WORKDIR}"

# The inherit of module.bbclass will automatically name module packages with
# "kernel-module-" prefix as required by the oe-core build environment.

#Andi: share all header files for building apps and dio24 module
#      creates & copies header to build/tmp/sysroot/plnx_arm/usr/include/dio24
#add following line to create dio24-share folder (not needed since dio24 folder already existing for module)
#      install -d -m 0655 ${D}${includedir}/dio24-share/
do_install_append() {
	install -d ${D}${includedir}
	install -m 0644 ${S}/*.h ${D}${includedir}/dio24
}

#Andi: use <dio24/dio24_driver.h> and <dio24/dio24_server.h> from dio24 module
#      headers found in build/tmp/sysroot/plnx_arm/usr/include/dio24
#DEPENDS = "dio24"

