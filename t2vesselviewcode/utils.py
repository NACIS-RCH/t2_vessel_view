import os
import glob
import shutil
import SimpleITK as sitk
import ants
from . import commandline
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import patheffects as pe
from . import dir_structure

# Flag to control whether debug images are saved.
# Default False; set True when --keep-debug-images is passed on the CLI.
save_debug_images = False

# Final cleaned brain mask kept under Processing/Masks/ after default cleanup.
PREPROCESSED_MASK_FILENAME = "Preprocessed_mask.nii.gz"


# Helper function to get output directory
def get_output_dir():
    return commandline.args.output_dir or commandline.args.mri_dir


def write_debug_image(image_object, output_file, output_directory):
    """
    Write a debug image to the specified output directory.
    Only writes if save_debug_images is True.
    
    Parameters
    ----------
    image_object : SimpleITK image
        The image to write
    output_file : str
        Name of the output file
    output_directory : str
        Directory to write the file to
    """
    if save_debug_images:
        path = os.path.join(output_directory, output_file) 
        sitk.WriteImage(image_object, path)


# ------------------------ Intermediate cleanup helpers ------------------------

def keep_debug_images():
    """Return True when the user asked to retain intermediate/debug NIfTIs."""
    return bool(getattr(commandline.args, "keep_debug_images", False)) or bool(save_debug_images)


def is_under_directory(path, directory):
    """Return True if path is under directory (never delete outside Processing)."""
    if not path or not directory:
        return False
    abs_path = os.path.abspath(path)
    abs_dir = os.path.abspath(directory)
    return abs_path == abs_dir or abs_path.startswith(abs_dir + os.sep)


def remove_paths(paths, allowed_directory=None):
    """Delete existing files from a list of paths; ignore missing entries.

    When allowed_directory is set, only delete files under that directory so
    user-supplied originals outside Processing/ are never removed.
    """
    removed = []
    for path in paths:
        if not path:
            continue
        if allowed_directory is not None:
            if not is_under_directory(path, allowed_directory):
                continue
            if not os.path.isfile(path):
                continue
        if os.path.isfile(path):
            try:
                os.remove(path)
                removed.append(path)
            except OSError as e:
                print(f"[WARNING] Could not remove intermediate file {path}: {e}")
    return removed


def remove_glob(directory, pattern):
    """Delete files matching a glob pattern under directory."""
    if not directory or not os.path.isdir(directory):
        return []
    return remove_paths(
        sorted(glob.glob(os.path.join(directory, pattern))),
        allowed_directory=directory,
    )


def remove_tree(path, allowed_directory=None):
    """Delete a directory tree if it exists and is under allowed_directory."""
    if not path or not os.path.isdir(path):
        return False
    if allowed_directory is not None and not is_under_directory(path, allowed_directory):
        return False
    # Refuse to delete the allowed directory root itself.
    if allowed_directory is not None and os.path.abspath(path) == os.path.abspath(allowed_directory):
        return False
    try:
        shutil.rmtree(path)
        return True
    except OSError as e:
        print(f"[WARNING] Could not remove intermediate directory {path}: {e}")
        return False

# Robust ANTsPy image read function for all versions
def read_ants_image(path):
    if hasattr(ants, "image_read"):
        return ants.image_read(path)
    elif hasattr(ants, "read_image"):
        return ants.read_image(path)
    else:
        raise AttributeError("ANTsPy does not have image_read or read_image")

def save_qa_mask_overlay(
    main_image,
    mask_image,
    filename,
    output_dir=None,
    alpha=0.4,
    cmap_main="gray",
    cmap_mask="autumn_r",
    show_colorbar=False
):
    """
    Save a QA PNG of a mask overlaid on a main image (2D slices) using matplotlib.
    The output figure shows:
    1) top row with three orthogonal overlays (axial, coronal, sagittal)
    2) bottom axial lightbox (6 columns x 5 rows) to better reveal local mask details
    Assumes volumes have been standardised to RAS (Right–Anterior–Superior) orientation.
    Displays in radiological convention for axial and coronal (patient's Right on image Left).

    Parameters
    ----------
    main_image : SimpleITK.Image
        The main anatomical image (e.g., T1, FLAIR, T2) as a SimpleITK image.
    mask_image : SimpleITK.Image
        The binary mask image as a SimpleITK image (same shape as main_image).
    filename : str
        Output PNG filename (should end with .png).
    output_dir : str, optional
        Directory to save the PNG (defaults to Figures_for_QA dir).
    alpha : float, optional
        Transparency for mask overlay (default 0.4).
    cmap_main : str, optional
        Colormap for main image (default 'gray').
    cmap_mask : str, optional
        Colormap for mask overlay (default 'autumn_r').
    show_colorbar : bool, optional
        Whether to show colorbar (default False).
    """
    # Convert images to numpy arrays (shape: [z, y, x])
    main_np = sitk.GetArrayFromImage(main_image)
    mask_np = sitk.GetArrayFromImage(mask_image)

    # Prepare output dir
    if output_dir is None:
        output_dir = dir_structure.processing_figures_dir
    os.makedirs(output_dir, exist_ok=True)  # Safe: does not overwrite contents

    # Get middle slice indices for each axis
    mid_axial = main_np.shape[0] // 2      # z axis (axial)
    mid_coronal = main_np.shape[1] // 2    # y axis (coronal)
    mid_sagittal = main_np.shape[2] // 2   # x axis (sagittal)

    # Create a two-row figure:
    # - top: 3 orthogonal panels
    # - bottom: 6x5 axial lightbox
    fig = plt.figure(figsize=(18, 16))
    gs = fig.add_gridspec(2, 1, height_ratios=[1, 2.2], hspace=0.12)
    top_gs = gs[0].subgridspec(1, 3, wspace=0.06)
    axes = [fig.add_subplot(top_gs[0, i]) for i in range(3)]

    # Common text style with outline for readability
    text_style = dict(color='w', fontsize=12, weight='bold', ha='center', va='center',
                      path_effects=[pe.withStroke(linewidth=2, foreground='black')])

    # --- Axial (z) ---
    axes[0].imshow(main_np[mid_axial, :, :], cmap=cmap_main, interpolation="none", origin='lower')
    axes[0].imshow(np.ma.masked_where(mask_np[mid_axial, :, :] == 0, mask_np[mid_axial, :, :]),
                   cmap=cmap_mask, alpha=alpha, interpolation="none", origin='lower')
    # Radiological display: invert x-axis so patient's Right appears on image Left
    axes[0].invert_xaxis()
    axes[0].set_title("Axial")
    # Labels for radiological axial: left=R, right=L; top=A, bottom=P
    axes[0].text(0.5, 0.02, 'P', transform=axes[0].transAxes, **text_style)
    axes[0].text(0.5, 0.98, 'A', transform=axes[0].transAxes, **text_style)
    axes[0].text(0.02, 0.5, 'R', transform=axes[0].transAxes, **text_style)
    axes[0].text(0.98, 0.5, 'L', transform=axes[0].transAxes, **text_style)
    axes[0].axis("off")
    if show_colorbar:
        plt.colorbar(axes[0].images[0], ax=axes[0], fraction=0.046, pad=0.04)

    # --- Coronal (y) ---
    axes[1].imshow(main_np[:, mid_coronal, :], cmap=cmap_main, interpolation="none", origin='lower')
    axes[1].imshow(np.ma.masked_where(mask_np[:, mid_coronal, :] == 0, mask_np[:, mid_coronal, :]),
                   cmap=cmap_mask, alpha=alpha, interpolation="none", origin='lower')
    # Radiological display: invert x-axis so patient's Right appears on image Left
    axes[1].invert_xaxis()
    axes[1].set_title("Coronal")
    # Labels for radiological coronal: left=R, right=L; top=S, bottom=I
    axes[1].text(0.5, 0.02, 'I', transform=axes[1].transAxes, **text_style)
    axes[1].text(0.5, 0.98, 'S', transform=axes[1].transAxes, **text_style)
    axes[1].text(0.02, 0.5, 'R', transform=axes[1].transAxes, **text_style)
    axes[1].text(0.98, 0.5, 'L', transform=axes[1].transAxes, **text_style)
    axes[1].axis("off")
    if show_colorbar:
        plt.colorbar(axes[1].images[0], ax=axes[1], fraction=0.046, pad=0.04)

    # --- Sagittal (x) ---
    axes[2].imshow(main_np[:, :, mid_sagittal], cmap=cmap_main, interpolation="none", origin='lower')
    axes[2].imshow(np.ma.masked_where(mask_np[:, :, mid_sagittal] == 0, mask_np[:, :, mid_sagittal]),
                   cmap=cmap_mask, alpha=alpha, interpolation="none", origin='lower')
    axes[2].set_title("Sagittal")
    # Sagittal unchanged: left=P, right=A; top=S, bottom=I
    axes[2].text(0.5, 0.02, 'I', transform=axes[2].transAxes, **text_style)
    axes[2].text(0.5, 0.98, 'S', transform=axes[2].transAxes, **text_style)
    axes[2].text(0.02, 0.5, 'P', transform=axes[2].transAxes, **text_style)
    axes[2].text(0.98, 0.5, 'A', transform=axes[2].transAxes, **text_style)
    axes[2].axis("off")
    if show_colorbar:
        plt.colorbar(axes[2].images[0], ax=axes[2], fraction=0.046, pad=0.04)

    # --- Axial lightbox (6 cols x 5 rows) ---
    n_cols = 6
    n_rows = 5
    n_tiles = n_cols * n_rows
    lightbox_gs = gs[1].subgridspec(n_rows, n_cols, wspace=0.01, hspace=0.01)

    # Evenly sample slices across the superior-inferior range with a small margin.
    z_size = main_np.shape[0]
    z_start = max(0, int(round(0.05 * (z_size - 1))))
    z_end = max(z_start, int(round(0.95 * (z_size - 1))))
    if z_end == z_start:
        z_indices = np.full(n_tiles, z_start, dtype=int)
    else:
        z_indices = np.linspace(z_start, z_end, n_tiles).astype(int)

    for idx in range(n_tiles):
        r = idx // n_cols
        c = idx % n_cols
        ax = fig.add_subplot(lightbox_gs[r, c])
        z = int(z_indices[idx])
        ax.imshow(main_np[z, :, :], cmap=cmap_main, interpolation="none", origin='lower')
        ax.imshow(
            np.ma.masked_where(mask_np[z, :, :] == 0, mask_np[z, :, :]),
            cmap=cmap_mask,
            alpha=alpha,
            interpolation="none",
            origin='lower',
        )
        # Radiological axial convention
        ax.invert_xaxis()
        ax.axis("off")

        # Orientation labels only on top-left tile (requested)
        if idx == 0:
            ax.text(0.5, 0.02, 'P', transform=ax.transAxes, **text_style)
            ax.text(0.5, 0.98, 'A', transform=ax.transAxes, **text_style)
            ax.text(0.02, 0.5, 'R', transform=ax.transAxes, **text_style)
            ax.text(0.98, 0.5, 'L', transform=ax.transAxes, **text_style)
            ax.set_title("Axial Lightbox (sampled slices)", fontsize=10)

    # Set the main title and save the figure
    fig.suptitle("Mask overlay QA (Radiological display)", fontsize=16)
    plt.tight_layout(rect=[0, 0.02, 1, 0.96])
    outpath = os.path.join(output_dir, filename)
    plt.savefig(outpath, bbox_inches="tight", dpi=150)
    plt.close(fig)
    print(f"[INFO] Saved QA mask overlay (all axes): {outpath}")

