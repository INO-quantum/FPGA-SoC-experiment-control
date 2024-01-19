#
# This file is the fpga-test recipe.
#

SUMMARY = "Simple fpga-test application"
SECTION = "PETALINUX/apps"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://fpga-test.cpp \
           file://USB.c \
           file://data_xy.c \
           file://data_xy.h \
           file://Makefile \
	  "

# to inlcude libusb see:
# https://forums.xilinx.com/t5/Embedded-Linux/PetaLinux-2019-need-to-support-on-adding-libusb/td-p/1010540
inherit pkgconfig
TARGET_CC_ARCH += "${LDFLAGS}"

#Andi: use <dio24/driver.h> and <dio24/dio24_driver.h> from dio24 module
#      headers found in build/tmp/sysroot/plnx_arm/usr/include/dio24
DEPENDS = "dio24"
DEPENDS += "fpga-server"
DEPENDS += "glib-2.0"
DEPENDS += "libusb"
RDEPENDS_${PN} += "libstdc++"

S = "${WORKDIR}"

do_compile() {
	     oe_runmake
}

do_install() {
	     install -d ${D}${bindir}
	     install -m 0755 fpga-test ${D}${bindir}
}

