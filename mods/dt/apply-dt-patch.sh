#!/bin/bash
# Build a patched DTB from the msm8916-mainline kernel source, with an
# extra .dtsi injected into the lxf-p5000 tree. Used by the GitHub workflow.
set -euo pipefail

KERNEL_SRC="${KERNEL_SRC:-/tmp/kernel}"
PATCH_DTSI="$1"       # e.g. mods/dt/yt3-gpu.dtsi
OUT_DTB="$2"          # output DTB file
KERNEL_TAG="${KERNEL_TAG:-v6.12.1-msm8916}"

if [ ! -d "$KERNEL_SRC/.git" ]; then
    git clone -q --depth 1 --filter=blob:none --sparse \
        --branch "$KERNEL_TAG" \
        https://github.com/msm8916-mainline/linux.git "$KERNEL_SRC"
    git -C "$KERNEL_SRC" sparse-checkout set \
        arch/arm/boot/dts/qcom include/dt-bindings scripts/dtc/include-prefixes
fi

# Make sure the p5000 DTS exists (the 6.12 branch only has p5100).
D=arch/arm/boot/dts/qcom
if [ ! -f "$KERNEL_SRC/$D/qcom-msm8909-lenovo-lxf-p5000.dts" ]; then
    sed -e 's/model = "Lenovo Yoga Tab 3 10 LTE";/model = "Lenovo Yoga Tab 3 8";/' \
        -e 's/lenovo,lxf-p5100/lenovo,lxf-p5000/' \
        "$KERNEL_SRC/$D/qcom-msm8909-lenovo-lxf-p5100.dts" \
        > "$KERNEL_SRC/$D/qcom-msm8909-lenovo-lxf-p5000.dts"
fi

# Inject the patch by appending the .dtsi include at the end of the
# shared dtsi. Works because our patch uses &soc { ... } overrides.
SHARED="$KERNEL_SRC/$D/qcom-msm8909-lenovo-lxf-p5x00.dtsi"
MARK="/* yt3-patch */"
if ! grep -q "$MARK" "$SHARED"; then
    PATCH_ABS="$(realpath "$PATCH_DTSI")"
    printf '\n%s\n#include "%s"\n' "$MARK" "$PATCH_ABS" >> "$SHARED"
fi

# Preprocess and compile.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cpp -nostdinc -undef -D__DTS__ -x assembler-with-cpp \
    -I "$KERNEL_SRC/include" \
    -I "$KERNEL_SRC/scripts/dtc/include-prefixes" \
    -I "$KERNEL_SRC/$D" \
    "$KERNEL_SRC/$D/qcom-msm8909-lenovo-lxf-p5000.dts" \
    > "$TMP/preprocessed.dts"

dtc -I dts -O dtb \
    -i "$KERNEL_SRC/$D" \
    -i "$KERNEL_SRC/scripts/dtc/include-prefixes" \
    -o "$OUT_DTB" "$TMP/preprocessed.dts"

ls -la "$OUT_DTB"
echo "patched DTB built OK"
