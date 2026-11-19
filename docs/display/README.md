# Display panel (found via lk2nd getvar)

- `lk2nd:panel:qcom,mdss_dsi_boent35523_800p_video`: BOE panel, Novatek NT35523 controller, 800x1280, DSI video mode, 4 lanes, 24 bpp, burst mode, 60 Hz.
- `lk2nd:model: Lenovo Yoga Tab 3 8 WIFI`, `lk2nd:compatible: lenovo,lxf-p5000` (mainline has qcom-msm8909-lenovo-lxf-p5000.dts; images currently use the p5100 DTB).
- Downstream panel description (init sequence, timings, reset sequence) from Lenovo kernel ARTEM-x92/android_kernel_lenovo_lxf_p5x00: dsi-panel-boent35523_800p_video.dtsi in this folder.
