import gl  # type: ignore
import os

# -------------------- PLACEHOLDERS (replaced by pipeline) --------------------
IMAGELIST = __IMAGELIST__  # type: ignore
OUTPUT_DIR = r"__OUTPUT_DIR__"
WINDOW = __WINDOW__  # type: ignore
CAMERA_DISTANCE = __CAMERA_DISTANCE__  # type: ignore
OVERLAYS = __OVERLAYS__  # type: ignore
MAIN_ERODE_PREFIX = "__MAIN_ERODE_PREFIX__"
SLICE_Z_START = __SLICE_Z_START__  # type: ignore
SLICE_Z_END = __SLICE_Z_END__  # type: ignore
SLICE_H_DIVISOR = __SLICE_H_DIVISOR__  # type: ignore
SAGITTAL_SLICE_END_FRACTION = __SAGITTAL_SLICE_END_FRACTION__  # type: ignore
SLICE_ALL_DEPTHS = __SLICE_ALL_DEPTHS__  # type: ignore
SAVE_STRUCTURAL_OUTPUTS = __SAVE_STRUCTURAL_OUTPUTS__  # type: ignore
SAVE_OVERLAY_OUTPUTS = __SAVE_OVERLAY_OUTPUTS__  # type: ignore

# [label, brain_az, brain_el, clip_az, clip_el]
ANGLES = __SLICE_ANGLES__  # type: ignore
# -----------------------------------------------------------------------------

if not os.path.isdir(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def _save_erosion_snapshot_for_all_angles(tag, base):
    for label, brain_az, brain_el, _clip_az, _clip_el in ANGLES:
        gl.azimuthelevation(int(brain_az), int(brain_el))
        gl.wait(120)
        outdir = os.path.join(OUTPUT_DIR, f"{label}_erosion_{tag}")
        if not os.path.isdir(outdir):
            os.makedirs(outdir, exist_ok=True)
        outname = os.path.join(outdir, f"{label}_erosion_{tag}_{base}.png")
        gl.savebmp(outname)


def _save_slice_sweep_for_all_angles(tag, base):
    # Define a helper that saves one clipped slice sweep; tag is set by this template
    # ('main' or 'full'), and base comes from the temporary NIfTI filename created in
    # render_quant_map_mm_panel_slices_mricrogl() in volume_rendering.py.
    for label, brain_az, brain_el, clip_az, clip_el in ANGLES:
        # Loop through ANGLES, which is injected into __SLICE_ANGLES__ by
        # render_quant_map_mm_panel_slices_mricrogl(); t2_vessel_view_main.py chooses
        # whether this quant_map_mm_panel workflow is run, while volume_rendering.py
        # supplies each [label, brain_az, brain_el, clip_az, clip_el] row.
        gl.azimuthelevation(int(brain_az), int(brain_el))
        # Set the MRIcroGL viewing angle using brain_az and brain_el from ANGLES; these
        # values come from the slice_angles list inside volume_rendering.py.
        outdir = os.path.join(OUTPUT_DIR, f"{label}_slices_{tag}")
        # Build the output folder path; OUTPUT_DIR is injected from the output_dir
        # argument passed into render_quant_map_mm_panel_slices_mricrogl(), and label/tag
        # create folders such as left_slices_main or posterior_slices_full.
        if not os.path.isdir(outdir):
            # Check whether that angle/tag folder already exists before saving screenshots.
            os.makedirs(outdir, exist_ok=True)
            # Create the output folder if needed; exist_ok=True keeps reruns from failing
            # if a previous render already made the directory.
        slice_z_end_for_angle = int(SLICE_Z_END)
        # Start from the default full sweep end; SLICE_Z_END is injected from
        # volume_rendering.py and remains in use for non-sagittal panel views.
        if str(label).lower() in (
            "left",
            "right",
            "surg_left_lat",
            "surg_right_lat",
            "surg_left_ato",
            "surg_right_ato",
        ):
            # Left/right are sagittal views, so stop just past midline. The 0.52
            # fraction is injected from volume_rendering.py and multiplied by
            # SLICE_H_DIVISOR so this adapts if the divisor changes from 100.
            slice_z_end_for_angle = int(round(float(SAGITTAL_SLICE_END_FRACTION) * float(SLICE_H_DIVISOR)))
        for z in range(int(SLICE_Z_START), int(slice_z_end_for_angle) + 1):
            # Sweep from SLICE_Z_START to SLICE_Z_END inclusive; both placeholders are
            # injected from volume_rendering.py; sagittal left/right use the adjusted
            # slice_z_end_for_angle value above so they only cross slightly past midline.
            h = float(z) / float(SLICE_H_DIVISOR)
            # Convert the integer sweep position into MRIcroGL's normalized clip height;
            # SLICE_H_DIVISOR is injected from the slice_h_divisor argument in volume_rendering.py.
            gl.clipazimuthelevation(h, int(clip_az), int(clip_el))
            # Apply the clipping plane; h comes from the line above, while clip_az and
            # clip_el come from the ANGLES/__SLICE_ANGLES__ rows generated in volume_rendering.py.
            sliceno = f"{int(z):03d}"
            # Format z as a three-digit number so filenames sort in slice-sweep order.
            outname = os.path.join(outdir, f"{label}_slices_{tag}-{sliceno}-{base}.png")
            # Build the screenshot filename from label and clip position plus tag/base;
            # label comes from ANGLES, tag is assigned in this template, and base comes
            # from the current temporary image filename generated in volume_rendering.py.
            gl.savebmp(outname)
            # Save the current MRIcroGL viewport to that PNG path.


def _get_overlay_fallback_max(overlay_path):
    """Return image max for overlay fallback when explicit max is not provided."""
    try:
        import nibabel as nib
        import numpy as np

        img = nib.load(str(overlay_path))
        data = img.get_fdata(dtype=np.float32)
        finite = data[np.isfinite(data)]
        if finite.size == 0:
            return 1000.0
        return float(np.max(finite))
    except Exception:
        return 1000.0


for i in IMAGELIST:
    gl.resetdefaults()
    gl.backcolor(0, 0, 0)
    gl.colorbarposition(0)
    gl.overlaymaskwithbackground(0)

    gl.shadername('OverlaySurface')
    gl.shaderadjust('diffuse', 0)
    gl.shaderadjust('shininess', 0)
    gl.shaderadjust('specular', 0)
    gl.shaderadjust('ambient', 1)
    gl.shaderadjust('overlayClip', 1)
    gl.shaderadjust('overlayFuzzy', 1)
    gl.shaderadjust('overlayDepth', 0)

    # Optional camera distance
    try:
        if isinstance(CAMERA_DISTANCE, (int, float)) and CAMERA_DISTANCE > 0:
            gl.cameradistance(float(CAMERA_DISTANCE))
    except Exception:
        pass

    layer_number = 0
    gl.loadimage(i)
    try:
        if isinstance(WINDOW, (list, tuple)) and len(WINDOW) == 2:
            gl.minmax(layer_number, int(WINDOW[0]), int(WINDOW[1]))
    except Exception:
        pass
    gl.hiddenbycutout(layer_number, 1)
    gl.opacity(layer_number, 100)

    base = os.path.splitext(os.path.basename(i))[0]

    # Structural erosion snapshots
    if bool(SAVE_STRUCTURAL_OUTPUTS):
        _save_erosion_snapshot_for_all_angles('structural', base)

    # Overlay layers (stacked over base)
    overlay_layer_numbers = []
    if isinstance(OVERLAYS, list):
        for ov in OVERLAYS:
            try:
                ov_path = ov.get('path', '')
                if not ov_path:
                    continue
                layer_number = layer_number + 1
                overlay_layer_numbers.append(layer_number)
                gl.overlayload(str(ov_path))
                gl.hiddenbycutout(layer_number, 1)
                gl.opacity(layer_number, int(ov.get('opacity', 35)))
                gl.colorname(layer_number, str(ov.get('color', 'jet')))
                ov_max = ov.get('max')
                if ov_max is None:
                    ov_max = _get_overlay_fallback_max(ov_path)
                gl.minmax(layer_number, float(ov.get('min', 0.0)), float(ov_max))
            except Exception:
                pass

    # Overlay erosion snapshots
    if bool(SAVE_OVERLAY_OUTPUTS):
        _save_erosion_snapshot_for_all_angles('overlay', base)

    # QMM sweeps only its selected depth; custom panels can sweep all depths.
    if bool(SLICE_ALL_DEPTHS) or (
        MAIN_ERODE_PREFIX and (str(MAIN_ERODE_PREFIX) + "_eroded") in base
    ):
        if bool(SAVE_OVERLAY_OUTPUTS):
            _save_slice_sweep_for_all_angles('overlay', base)
        if bool(SAVE_STRUCTURAL_OUTPUTS):
            for ln in overlay_layer_numbers:
                try:
                    gl.opacity(int(ln), 0)
                except Exception:
                    pass
            _save_slice_sweep_for_all_angles('structural', base)

gl.wait(1200)
gl.quit()
