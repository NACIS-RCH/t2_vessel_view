import pyvista as pv
import nibabel as nib
import numpy as np
import os
import tempfile
import shutil
import subprocess

from . import dir_structure


def _ensure_ras(img):
    ax = nib.aff2axcodes(img.affine)
    if ax != ('R', 'A', 'S'):
        img = nib.as_closest_canonical(img)
        ax2 = nib.aff2axcodes(img.affine)
        if ax2 != ('R', 'A', 'S'):
            raise ValueError(f"Non-RAS after canonicalization: pre={ax}, post={ax2}")
    return img

def render_volume_and_save_pngs_mricrogl(
    nifti_paths,
    output_dir,
    angles=None,
    window=(0, 1000),
    image_size=(1200, 1200),
    mricrogl_path="/Applications/MRIcroGL.app/Contents/MacOS/MRIcroGL",
    template_filename="mricrogl_T1_screenshot_test.py",
    camera_distance=0.6
):
    """
    Render volumes using MRIcroGL by generating a temporary gl script from a template.

    This does not modify stored outputs. It creates temporary uncompressed .nii copies
    for MRIcroGL to read reliably, runs MRIcroGL with the generated script, saves PNGs
    to output_dir, and cleans up temps.

    Parameters
    ----------
    nifti_paths : list[str]
        Absolute paths to input NIfTI files to render.
    output_dir : str
        Absolute output directory for PNG screenshots.
    angles : list[[azimuth, elevation, label]]
        Camera angles; defaults to six standard views if None.
    window : (float, float)
        Intensity window (min, max).
    image_size : (int, int)
        PNG size in pixels (width, height).
    mricrogl_path : str
        Path to the MRIcroGL executable.
    template_filename : str
        Template script filename located under display_scripts/templates/ within the package.
    camera_distance : float
        Camera distance to use (>0 applies; smaller is closer). Set <=0 to skip.
    """
    if angles is None:
        angles = [
            [90, 0, 'left'],
            [270, 0, 'right'],
            [180, 0, 'anterior'],
            [0, 0, 'posterior'],
            [0, 90, 'superior'],
            [180, -90, 'inferior'],
        ]

    os.makedirs(output_dir, exist_ok=True)

    # Resolve template path inside the installed package
    templates_dir = os.path.join(os.path.dirname(__file__), 'display_scripts', 'templates')
    template_path = os.path.join(templates_dir, template_filename)
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"MRIcroGL template not found: {template_path}")

    # Create a temp workspace
    tmp_root = tempfile.mkdtemp(prefix='t2vv_mricrogl_')
    tmp_imgs = []
    try:
        # Create temporary uncompressed .nii copies for MRIcroGL
        for p in nifti_paths:
            if not os.path.isabs(p):
                raise ValueError(f"Input path must be absolute for MRIcroGL: {p}")
            img = nib.load(p)
            # Keep dtype as float32 to preserve intensity scaling; MRIcroGL handles .nii float32 fine
            data = img.get_fdata(dtype=np.float32)
            tmp_p = os.path.join(tmp_root, os.path.splitext(os.path.basename(p))[0] + '.nii')
            nib.Nifti1Image(data, img.affine, header=img.header).to_filename(tmp_p)
            tmp_imgs.append(tmp_p)

        # Fill the template placeholders
        with open(template_path, 'r') as f:
            tpl = f.read()

        # Build literal strings for placeholders
        # Ensure paths are properly quoted for MRIcroGL's interpreter
        img_list_literal = '[' + ', '.join([repr(s) for s in tmp_imgs]) + ']'
        angles_literal = '[' + ', '.join([f"[{a[0]}, {a[1]}, '{a[2]}']" for a in angles]) + ']'
        window_literal = f"[{int(window[0])}, {int(window[1])}]"
        view_literal = f"[{int(image_size[0])}, {int(image_size[1])}]"
        camera_literal = f"{float(camera_distance)}" if camera_distance and camera_distance > 0 else "-1"

        script_text = tpl
        script_text = script_text.replace('__IMAGELIST__', img_list_literal)
        script_text = script_text.replace('__OUTPUT_DIR__', output_dir)
        script_text = script_text.replace('__ANGLES__', angles_literal)
        script_text = script_text.replace('__WINDOW__', window_literal)
        script_text = script_text.replace('__VIEW_SIZE__', view_literal)
        script_text = script_text.replace('__CAMERA_DISTANCE__', camera_literal)

        # Write temp script
        tmp_script = os.path.join(tmp_root, 'mricrogl_run.py')
        with open(tmp_script, 'w') as f:
            f.write(script_text)

        # Run MRIcroGL
        cmd = [mricrogl_path, '-s', tmp_script]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"MRIcroGL failed (code {proc.returncode}). stderr: {proc.stderr}\nstdout: {proc.stdout}")

        print(f"[INFO] MRIcroGL renders saved under: {output_dir}")
    finally:
        # Cleanup temp files
        try:
            shutil.rmtree(tmp_root)
        except Exception:
            pass

def render_volume_and_save_pngs_pyvista(
    nifti_paths,
    output_dir,
    angles=[('left', 90, 0), ('right', 270, 0), ('posterior', 0, 0), ('anterior', 180, 0), ('superior', 0, 90), ('inferior', 180, -90)],
    window=(0, 1000),
    image_size=(800, 800)
):
    """
    Render a list of NIfTI volumes using PyVista and save PNG screenshots from multiple angles.
    Parameters
    ----------
    nifti_paths : list of str
        List of paths to NIfTI files to render.
    output_dir : str
        Directory to save PNG screenshots (by angle subfolders will be created).
    angles : list of (str, float, float)
        List of (name, azimuth, elevation) tuples for camera angles.
    window : (float, float)
        Intensity window (min, max) for display.
    image_size : (int, int)
        Output PNG size in pixels.
    """
    for nifti_path in nifti_paths:
        # Load NIfTI
        img = nib.load(nifti_path)
        img = _ensure_ras(img)
        data = img.get_fdata()
        # Window/level
        vmin, vmax = window
        data = np.clip(data, vmin, vmax)
        data = (data - vmin) / (vmax - vmin)  # normalize to 0-1

        # Create PyVista UniformGrid
        grid = pv.ImageData()
        grid.dimensions = np.array(data.shape) + 1
        grid.origin = (0, 0, 0)
        grid.spacing = img.header.get_zooms()
        grid.cell_data["values"] = data.flatten(order="F")

        # Set up plotter (offscreen)
        plotter = pv.Plotter(off_screen=True, window_size=image_size)
        plotter.add_volume(
            grid,
            scalars='values',
            opacity='sigmoid',  # or 'linear', or a custom transfer function
            cmap='gray',
            shade=True,
            opacity_unit_distance=0.1,  # controls sharpness
            show_scalar_bar=False
        )

        # Output for each angle
        for name, azimuth, elevation in angles:
            plotter.camera_position = 'xy'  # reset to default
            plotter.camera.azimuth = azimuth
            plotter.camera.elevation = elevation
            plotter.camera.zoom(1.0)
            outdir = os.path.join(output_dir, 'by_angle', name)
            os.makedirs(outdir, exist_ok=True)
            outpath = os.path.join(outdir, f"{name}-{azimuth}-{elevation}-{os.path.basename(nifti_path).split('.')[0]}.png")
            plotter.show(screenshot=outpath, auto_close=False)
        plotter.close()

def render_volume_and_save_pngs_vedo(
    nifti_paths,
    output_dir,
    angles=[('left', 90, 0), ('right', 270, 0), ('posterior', 0, 0), ('anterior', 180, 0), ('superior', 0, 90), ('inferior', 180, -90)],
    window=(0, 1000),
    image_size=(800, 800)
):
    """
    Render a list of NIfTI volumes using vedo and save PNG screenshots from multiple angles.
    Parameters
    ----------
    nifti_paths : list of str
        List of paths to NIfTI files to render.
    output_dir : str
        Directory to save PNG screenshots (by angle subfolders will be created).
    angles : list of (str, float, float)
        List of (name, azimuth, elevation) tuples for camera angles.
    window : (float, float)
        Intensity window (min, max) for display.
    image_size : (int, int)
        Output PNG size in pixels.
    """
    from vedo import Volume, Plotter
    import nibabel as nib
    import numpy as np
    import os

    for nifti_path in nifti_paths:
        img = nib.load(nifti_path)
        img = _ensure_ras(img)
        data = img.get_fdata()
        vmin, vmax = window
        data = np.clip(data, vmin, vmax)
        data = (data - vmin) / (vmax - vmin)  # normalize to 0-1

        vol = Volume(data)
        #vol.cmap('gray')
        #vol.alpha([0, 0, 1, 1])  # No transparency on main volume

        for name, azimuth, elevation in angles:
            plt = Plotter(offscreen=True, size=image_size, bg='black')
            plt.show(vol, resetcam=True)
            plt.camera.Azimuth(azimuth)
            plt.camera.Elevation(elevation)
            plt.camera.Zoom(1.0)
            outdir = os.path.join(output_dir, 'by_angle', name)
            os.makedirs(outdir, exist_ok=True)
            outpath = os.path.join(outdir, f"{name}-{azimuth}-{elevation}-{os.path.basename(nifti_path).split('.')[0]}.png")
            plt.screenshot(outpath)
            plt.close() 