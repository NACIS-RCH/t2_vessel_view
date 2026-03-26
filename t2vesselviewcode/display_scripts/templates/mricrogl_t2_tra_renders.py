#### MRIcroGL template script for T2 transverse vessels (executed by MRIcroGL)
# Usage (pipeline): MRIcroGL -s /abs/path/to/generated_temp_script.py
# Notes:
# - TEMPLATE: the pipeline generates a temporary script by replacing placeholders below.
# - MRIcroGL interprets 'gl' internally; see: https://github.com/rordenlab/MRIcroGL12/blob/master/PYTHON.md

import gl # type: ignore
import os

# -------------------- PLACEHOLDERS (to be replaced by pipeline) --------------------
# Absolute paths to T2 transverse vessel NIfTI files to render (use temp .nii if needed)
IMAGELIST = __IMAGELIST__ # type: ignore

# Absolute output directory for PNGs
OUTPUT_DIR = r"__OUTPUT_DIR__"

# Angles: [azimuth, elevation, label]
ANGLES = __ANGLES__  # type: ignore # e.g., [[90,0,'left'],[270,0,'right'],[0,0,'posterior'],[180,0,'anterior'],[0,90,'superior'],[180,-90,'inferior']]

# Intensity window [min, max]
WINDOW = __WINDOW__  # type: ignore # e.g., [0, 1000]

# PNG size [width, height]
VIEW_SIZE = __VIEW_SIZE__  # type: ignore # e.g., [1200, 1200]

# Optional camera distance (float). Smaller=closer. Set to -1 to skip.
CAMERA_DISTANCE = __CAMERA_DISTANCE__  # type: ignore # e.g., 0.6
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

    # View size
    try:
        if isinstance(VIEW_SIZE, (list, tuple)) and len(VIEW_SIZE) == 2:
            gl.viewsize(int(VIEW_SIZE[0]), int(VIEW_SIZE[1]))
    except Exception:
        pass

    # Shader for vessels
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

    # Optional camera distance
    try:
        if isinstance(CAMERA_DISTANCE, (int, float)) and CAMERA_DISTANCE > 0:
            gl.cameradistance(float(CAMERA_DISTANCE))
    except Exception:
        pass

    gl.hiddenbycutout(layer_number, 1)
    gl.opacity(layer_number, 100)

    # Screenshots for specified angles
    base = os.path.splitext(os.path.basename(i))[0]
    for az, el, label in ANGLES:
        gl.azimuthelevation(int(az), int(el))
        gl.wait(200)
        outdir = os.path.join(by_angle_dir, str(label))
        if not os.path.isdir(outdir):
            os.makedirs(outdir, exist_ok=True)
        outfile = os.path.join(outdir, f"T2_tra_vessels-{label}-{az}-{el}-{base}.png")
        gl.savebmp(outfile)

# Final pause before exit
gl.wait(1200)
# Exit MRIcroGL when done
gl.quit() 