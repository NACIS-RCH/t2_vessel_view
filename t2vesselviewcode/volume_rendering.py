import pyvista as pv
import nibabel as nib
import numpy as np
import os

def render_volume_and_save_pngs(
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
        data = img.get_fdata()
        # Window/level
        vmin, vmax = window
        data = np.clip(data, vmin, vmax)
        data = (data - vmin) / (vmax - vmin)  # normalize to 0-1

        # Create PyVista UniformGrid
        grid = pv.UniformGrid()
        grid.dimensions = data.shape
        grid.spacing = img.header.get_zooms()  # voxel size
        grid.origin = (0, 0, 0)
        grid.point_arrays['values'] = data.flatten(order='F')

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