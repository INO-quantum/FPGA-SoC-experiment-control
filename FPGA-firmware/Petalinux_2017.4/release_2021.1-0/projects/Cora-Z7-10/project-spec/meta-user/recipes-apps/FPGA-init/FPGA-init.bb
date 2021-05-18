#
# This file is the FPGA-init recipe.
#
# edited by Andi, see UG1144 (2017.1) p.60
# to create: petalinux-create -t apps --template install -n FPGA-init
# check if enabled with: petalinux-config -c rootfs

SUMMARY = "Simple FPGA-init application"
SECTION = "PETALINUX/apps"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://FPGA-init \
	"

S = "${WORKDIR}"

FILESEXTRAPATHS_prepend := "${THISDIR}/files:"

inherit update-rc.d

INITSCRIPT_NAME = "FPGA-init"
INITSCRIPT_PARAMS = "start 99 S ."

#Andi: I install to rc5.d with high S99z-prefix to ensure networking is ready
#      init.d is too early. todo: maybe just retry after some wait time on error?
do_install() {
#	     install -d ${D}/${bindir}
#	     install -m 0755 ${S}/FPGA-init ${D}/${bindir}
	     install -d ${D}/${sysconfdir}/rc5.d
	     install -m 0755 ${S}/FPGA-init ${D}/${sysconfdir}/rc5.d/S99z-FPGA-init
}

FILES_${PN} += "${sysconfdir}/*"

