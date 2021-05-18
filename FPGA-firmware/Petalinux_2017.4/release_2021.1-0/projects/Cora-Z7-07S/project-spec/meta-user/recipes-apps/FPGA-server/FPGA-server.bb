#
# This file is the FPGA-server recipe.
#

SUMMARY = "Simple FPGA-server application"
SECTION = "PETALINUX/apps"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://FPGA-server.cpp \
           file://simple-server.cpp \
           file://FPGA-server.h \
           file://simple-server.h \
           file://dio24_server.h \
           file://list.h \
           file://common.h \
           file://Makefile \
          "

#Andi: use <dio24/driver.h> and <dio24/dio24_driver.h> from dio24 module
#      headers found in build/tmp/sysroot/plnx_arm/usr/include/dio24
DEPENDS = "dio24"

S = "${WORKDIR}"

do_compile() {
	     oe_runmake
}

do_install() {
	     install -d ${D}${bindir}
	     install -m 0755 FPGA-server ${D}${bindir}
}

#Andi: share all header files for building apps and dio24 module
#      creates & copies header to build/tmp/sysroot/plnx_arm/usr/include/dio24
#add following line to create dio24-share folder (not needed since dio24 folder already existing for module)
do_install_append() {
    install -d -m 0655 ${D}${includedir}/dio24-share/
	install -d ${D}${includedir}
	install -m 0644 ${S}/*.h ${D}${includedir}/dio24-share
}

#Andi: use <dio24/dio24_driver.h> and <dio24/dio24_server.h> from dio24 module
#      headers found in build/tmp/sysroot/plnx_arm/usr/include/dio24
#DEPENDS = "FPGA-server"

