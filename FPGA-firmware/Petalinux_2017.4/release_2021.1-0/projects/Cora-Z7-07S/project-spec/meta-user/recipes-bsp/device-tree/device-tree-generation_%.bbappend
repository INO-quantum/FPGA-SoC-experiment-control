SRC_URI_append ="\
    file://system-user.dtsi \
    file://0001-Update-the-logic-to-check-if-cpu-is-present-in-the-d.patch \
"
FILESEXTRAPATHS_prepend := "${THISDIR}/files:"
