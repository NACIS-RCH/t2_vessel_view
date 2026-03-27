

#### MRIcroGL template script (executed by MRIcroGL, not standard Python)
# Usage (from pipeline): MRIcroGL -s /abs/path/to/generated_temp_script.py
# Notes:
# - This file is a TEMPLATE. The pipeline will generate a temporary copy,
#   replacing the placeholder tokens below with absolute values.
# - Do NOT attempt to run this template directly.
# - MRIcroGL interprets 'gl' commands internally; see docs: https://github.com/rordenlab/MRIcroGL12/blob/master/PYTHON.md

import gl # type: ignore
import os

# -------------------- PLACEHOLDERS (to be replaced by pipeline) --------------------
# List of absolute NIfTI paths to render (use temporary .nii copies if needed)
IMAGELIST = __IMAGELIST__  # type: ignore # e.g., [' /abs/path/Preprocessed_main_image.nii']

# Absolute output directory where PNGs will be saved
OUTPUT_DIR = r"__OUTPUT_DIR__"  # e.g., '/abs/base/T2VesselView/3D_renders_png/T1_3D_renders'

# List of camera angles: [azimuth, elevation, label]
ANGLES = __ANGLES__  # type: ignore # e.g., [[90,0,'left'], [270,0,'right'], [0,90,'superior']]

# Intensity window [min, max]
WINDOW = __WINDOW__  # type: ignore # e.g., [0, 1000]

# PNG size [width, height]; if not supported on your build, this is ignored
VIEW_SIZE = __VIEW_SIZE__  # type: ignore # e.g., [1200, 1200]

# Optional camera distance (float). Smaller = closer. If not desired, set to -1.
CAMERA_DISTANCE = __CAMERA_DISTANCE__  # type: ignore # e.g., 0.6

# Optional overlays loaded directly by MRIcroGL.
# Format:
# OVERLAYS = [
#   {'path': '/abs/PET_to_T1.nii.gz', 'color': 'jet', 'min': 2000, 'max': 23000, 'opacity': 35},
#   {'path': '/abs/other_overlay.nii.gz', 'color': 'red', 'min': 10, 'max': 120, 'opacity': 40},
# ]
OVERLAYS = __OVERLAYS__  # type: ignore
# -----------------------------------------------------------------------------------

# Ensure base output and per-angle subfolders exist
if not os.path.isdir(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
by_angle_dir = os.path.join(OUTPUT_DIR, 'by_angle')
if not os.path.isdir(by_angle_dir):
    os.makedirs(by_angle_dir, exist_ok=True)

# Render each image with the specified settings
for i in IMAGELIST:
    gl.resetdefaults()
    # Background and basic look
    gl.backcolor(0,0,0)
    gl.colorbarposition(0)
    gl.overlaymaskwithbackground(0)
    # Hide orientation cube if supported
    try:
        gl.orientcube(0)
    except Exception:
        try:
            gl.orientcubevisible(0)
        except Exception:
            pass

    # Optional view size
    try:
        if isinstance(VIEW_SIZE, (list, tuple)) and len(VIEW_SIZE) == 2:
            gl.viewsize(int(VIEW_SIZE[0]), int(VIEW_SIZE[1]))
    except Exception:
        pass

    # Lighting/shader tuned for surface-like overlay
    gl.shadername('OverlaySurface')
    gl.shaderadjust('diffuse', 0)
    gl.shaderadjust('shininess', 0)
    gl.shaderadjust('specular', 0)
    gl.shaderadjust('ambient', 1)
    gl.shaderadjust('overlayClip', 1)
    gl.shaderadjust('overlayFuzzy', 1)
    gl.shaderadjust('overlayDepth', 0)

    # Load image as base layer
    layer_number = 0
    gl.loadimage(i)
    try:
        if isinstance(WINDOW, (list, tuple)) and len(WINDOW) == 2:
            gl.minmax(layer_number, int(WINDOW[0]), int(WINDOW[1]))
    except Exception:
        pass
    # Optional camera distance (float acceptable here)
    try:
        if isinstance(CAMERA_DISTANCE, (int, float)) and CAMERA_DISTANCE > 0:
            gl.cameradistance(float(CAMERA_DISTANCE))
    except Exception:
        pass

    gl.hiddenbycutout(layer_number, 1)
    gl.opacity(layer_number, 100)

    # Optional overlays: stack each overlay as a new layer over the base T1.
    if isinstance(OVERLAYS, list):
        for ov in OVERLAYS:
            try:
                ov_path = ov.get('path', '')
                if not ov_path:
                    continue
                layer_number = layer_number + 1
                gl.overlayload(str(ov_path))
                gl.hiddenbycutout(layer_number, 1)
                gl.opacity(layer_number, int(ov.get('opacity', 35)))
                gl.colorname(layer_number, str(ov.get('color', 'jet')))
                gl.minmax(layer_number, int(ov.get('min', 0)), int(ov.get('max', 1000)))
            except Exception:
                # Keep rendering even if one overlay entry fails.
                pass

    # Save screenshots at specified angles
    base = os.path.splitext(os.path.basename(i))[0]
    for az, el, label in ANGLES:
        gl.azimuthelevation(int(az), int(el))
        gl.wait(200)
        outdir = os.path.join(by_angle_dir, str(label))
        if not os.path.isdir(outdir):
            os.makedirs(outdir, exist_ok=True)
        outfile = os.path.join(outdir, f"{label}-{az}-{el}-{base}.png")
        gl.savebmp(outfile)

# Brief pause before quit to reduce exit glitches
gl.wait(1200)
# Exit MRIcroGL when done
gl.quit()


