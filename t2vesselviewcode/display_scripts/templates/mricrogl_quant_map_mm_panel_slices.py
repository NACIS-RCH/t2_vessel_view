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
    for label, brain_az, brain_el, clip_az, clip_el in ANGLES:
        gl.azimuthelevation(int(brain_az), int(brain_el))
        outdir = os.path.join(OUTPUT_DIR, f"{label}_slices_{tag}")
        if not os.path.isdir(outdir):
            os.makedirs(outdir, exist_ok=True)
        for z in range(int(SLICE_Z_START), int(SLICE_Z_END) + 1):
            h = float(z) / float(SLICE_H_DIVISOR)
            gl.clipazimuthelevation(h, int(clip_az), int(clip_el))
            sliceno = f"{int(z):03d}"
            outname = os.path.join(outdir, f"{label}_slices_{tag}-{sliceno}-{base}.png")
            gl.savebmp(outname)


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
    _save_erosion_snapshot_for_all_angles('overlay', base)

    # Full slice sweeps only for the selected main erosion depth
    if MAIN_ERODE_PREFIX and (str(MAIN_ERODE_PREFIX) + "_eroded") in base:
        _save_slice_sweep_for_all_angles('overlay', base)
        for ln in overlay_layer_numbers:
            try:
                gl.opacity(int(ln), 0)
            except Exception:
                pass
        _save_slice_sweep_for_all_angles('structural', base)

gl.wait(1200)
gl.quit()
