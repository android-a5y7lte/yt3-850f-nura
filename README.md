# Nura edge (postmarketOS) for Lenovo Yoga Tab 3 8 (YT3-850F)

Automated build of postmarketOS edge with Phosh for the Lenovo Yoga Tab 3 8
(codename `lenovo-lxf-p5000`, APQ8009/MSM8909), using the generic
`qcom-msm8909` port and the lk2nd bootloader.

**Status: builds, not yet tested on the tablet.**

## What the build does

1. Runs `pmbootstrap install` for `qcom-msm8909` (armv7, kernel
   `linux-postmarketos-qcom-msm8916` 6.12) with the Phosh interface.
2. Adds a device tree for the 8-inch tablet. The packaged kernel only ships
   the 10-inch one (`lxf-p5100`); in the msm8916-mainline kernel both tablets
   share one hardware description, so the `lxf-p5000` tree is derived from the
   packaged `lxf-p5100` tree with only model/compatible changed.
3. Downloads the latest lk2nd release for MSM8909 (it already knows this
   tablet as "Lenovo Yoga Tab 3 8 WIFI").

## Files in a release

| File | What it is |
|---|---|
| `lk2nd-msm8909.img` | Secondary bootloader, goes in the `boot` partition |
| `qcom-msm8909.img.xz` | The OS image (about 2.4 GiB unpacked), goes in `userdata` |
| `qcom-msm8909-lenovo-lxf-p5000.dtb` | The tablet's device tree (already inside the image) |
| `SHA256SUMS.txt` | Checksums of the unpacked image and device tree |

## Flashing (needs a computer with fastboot once)

**Back up first.** In TWRP, back up `boot`, `modem`, `persist` and anything
else it offers except data, to the SD card. Wi-Fi/Bluetooth firmware is read
from the tablet's own partitions, so never wipe those. This install erases
`userdata` (all Android apps and files).

```
unxz qcom-msm8909.img.xz
adb reboot bootloader
fastboot flash boot lk2nd-msm8909.img
fastboot reboot
```

Hold **Volume Down** while it restarts to stay in the lk2nd menu. The screen
should show lk2nd and name the device as a Lenovo Yoga Tab 3 8. Then:

```
fastboot flash userdata qcom-msm8909.img
fastboot reboot
```

Login: user `user`, password/PIN `147147` (change it with `passwd`).

## Going back to Android

Restore the `boot` backup in TWRP (TWRP itself is not touched by this
install), then format data.

## Rebuilding

Actions → "Build Nura edge (postmarketOS) for YT3-850F" → Run workflow.
Choose the interface (`phosh`, `sxmo-de-sway`, `xfce4`) and tick "Publish a
GitHub release" to get downloadable files.
