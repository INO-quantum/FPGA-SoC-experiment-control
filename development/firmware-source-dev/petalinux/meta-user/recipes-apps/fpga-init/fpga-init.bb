#
# This file is the fpga-init recipe.
#

SUMMARY = "Simple fpga-init application"
SECTION = "PETALINUX/apps"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://fpga-init \
	"

S = "${WORKDIR}"

FILESEXTRAPATHS_prepend := "${THISDIR}/files:"

inherit update-rc.d

INITSCRIPT_NAME = "fpga-init"
INITSCRIPT_PARAMS = "start 99 S ."

do_install() {
    #install -d ${D}${bindir}
    #install -m 0755 fpga-init ${D}${bindir}
    install -d ${D}${sysconfdir}/init.d
    install -m 0755 ${S}/fpga-init ${D}${sysconfdir}/init.d/fpga-init
}

FILES_${PN} += "${sysconfdir}/*"
