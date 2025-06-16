import os
import SimpleITK as sitk
import ants
from . import commandline
import numpy as np
import matplotlib.pyplot as plt
from . import dir_structure

# Flag to control whether debug images are saved
save_debug_images = True

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

# Robust ANTsPy image read function for all versions
def read_ants_image(path):
    if hasattr(ants, "image_read"):
        return ants.image_read(path)
    elif hasattr(ants, "read_image"):
        return ants.read_image(path)
    else:
        raise AttributeError("ANTsPy does not have image_read or read_image")

## 
test_data_dir = '/Users/bonniealexander/Code/NACIS-RCH/testing_t2vv/test_dataset'
test_output_dir = '/Users/bonniealexander/Code/NACIS-RCH/testing_t2vv/test_outputs'
#rxs_mask_path = os.path.join(test_data_dir, "rxs_mask.nii.gz")

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
    The output figure will show overlays for all three anatomical axes (axial, coronal, sagittal).

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

    # Create a figure with 3 subplots (one for each anatomical axis)
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))

    # --- Axial (z) ---
    # Show the middle axial slice (z = mid_axial)
    axes[0].imshow(main_np[mid_axial, :, :], cmap=cmap_main, interpolation="none")
    axes[0].imshow(np.ma.masked_where(mask_np[mid_axial, :, :] == 0, mask_np[mid_axial, :, :]),
                   cmap=cmap_mask, alpha=alpha, interpolation="none")
    axes[0].set_title(f"Axial (z={mid_axial})")
    axes[0].axis("off")
    if show_colorbar:
        plt.colorbar(axes[0].images[0], ax=axes[0], fraction=0.046, pad=0.04)

    # --- Coronal (y) ---
    # Show the middle coronal slice (y = mid_coronal)
    axes[1].imshow(main_np[:, mid_coronal, :], cmap=cmap_main, interpolation="none")
    axes[1].imshow(np.ma.masked_where(mask_np[:, mid_coronal, :] == 0, mask_np[:, mid_coronal, :]),
                   cmap=cmap_mask, alpha=alpha, interpolation="none")
    axes[1].set_title(f"Coronal (y={mid_coronal})")
    axes[1].axis("off")
    if show_colorbar:
        plt.colorbar(axes[1].images[0], ax=axes[1], fraction=0.046, pad=0.04)

    # --- Sagittal (x) ---
    # Show the middle sagittal slice (x = mid_sagittal)
    axes[2].imshow(main_np[:, :, mid_sagittal], cmap=cmap_main, interpolation="none")
    axes[2].imshow(np.ma.masked_where(mask_np[:, :, mid_sagittal] == 0, mask_np[:, :, mid_sagittal]),
                   cmap=cmap_mask, alpha=alpha, interpolation="none")
    axes[2].set_title(f"Sagittal (x={mid_sagittal})")
    axes[2].axis("off")
    if show_colorbar:
        plt.colorbar(axes[2].images[0], ax=axes[2], fraction=0.046, pad=0.04)

    # Set the main title and save the figure
    fig.suptitle("Mask overlay QA: Axial / Coronal / Sagittal", fontsize=16)
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    outpath = os.path.join(output_dir, filename)
    plt.savefig(outpath, bbox_inches="tight", dpi=150)
    plt.close(fig)
    print(f"[INFO] Saved QA mask overlay (all axes): {outpath}")

