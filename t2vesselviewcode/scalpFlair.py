#!/usr/bin/env python

### Thanks Richard Beare for this code
### Simple watershed scalping for FLAIR 



import sys
import re
import os
import os.path
import subprocess
import SimpleITK as sitk
import ants

# template path resolution:
# 1) package assets/templates/adult
# 2) FSL standard path derived from `which fsl`
def resolve_template_paths():
    # Prefer packaged templates first
    package_adult_dir = os.path.join(
        os.path.dirname(__file__),
        "assets",
        "templates",
        "adult"
    )
    package_mni = os.path.join(package_adult_dir, "MNI152_T1_1mm.nii.gz")
    package_mask = os.path.join(package_adult_dir, "MNI152_T1_1mm_brain_mask_dil.nii.gz")
    if os.path.exists(package_mni) and os.path.exists(package_mask):
        return package_mni, package_mask

    # Fallback: derive FSL standard folder from `which fsl`
    fsl_bin = ""
    try:
        which_result = subprocess.run(
            ["which", "fsl"],
            capture_output=True,
            text=True,
            check=False
        )
        if which_result.returncode == 0:
            fsl_bin = which_result.stdout.strip()
    except Exception:
        fsl_bin = ""

    if fsl_bin:
        fsl_standard_dir = os.path.normpath(
            os.path.join(os.path.dirname(fsl_bin), "..", "data", "standard")
        )
        fsl_mni = os.path.join(fsl_standard_dir, "MNI152_T1_1mm.nii.gz")
        fsl_mask = os.path.join(fsl_standard_dir, "MNI152_T1_1mm_brain_mask_dil.nii.gz")
        if os.path.exists(fsl_mni) and os.path.exists(fsl_mask):
            return fsl_mni, fsl_mask

    raise FileNotFoundError(
        "Could not locate required MNI templates. "
        "Checked package path "
        f"'{package_adult_dir}' and FSL standard path derived from `which fsl`. "
        "This module cannot run without MNI152_T1_1mm.nii.gz and "
        "MNI152_T1_1mm_brain_mask_dil.nii.gz."
    )


# we use this mask because we want ventricles included
mni, mnibrainmask = resolve_template_paths()

# the compute functions are a mix of toolkits, so
# pass in filenames

# registration settings for debugging
TFTYPE="Affine"
METRIC="MI"
AFF_SAMPLING=0.25
# Random seed
RS = 334

VERBOSE = True

def alignmask(flair, template, template_mask):
    flairI = ants.image_read(flair)
    templateI = ants.image_read(template)
    # affine reg 
    mni2flair = ants.registration(fixed=flairI, moving=templateI,
                                 type_of_transform=TFTYPE,
                                 verbose=VERBOSE, aff_metric = METRIC,
                                 aff_random_sampling_rate = AFF_SAMPLING,
                                 random_seed = RS)
    del(templateI)
    templatemaskI = ants.image_read(template_mask, pixeltype='unsigned char')
    mask = ants.apply_transforms(fixed=flairI, moving=templatemaskI, transformlist = mni2flair['fwdtransforms'], interpolator = 'nearestNeighbor', whichtoinvert=[False])
    return mask

def Scalp(flair, template_mask, workdir):
    # assuming template mask is in flair space
    # inputs are filenames
    # These flair scans have a really bright brain compared to the
    # scalp. Means the old style T1 watershed (using an inverted
    # image as the control) isn't great. However an outer gradient
    # might be good (dilation - original)
    maskI = sitk.ReadImage(template_mask, sitk.sitkUInt8) > 0
    # create the marker image
    radius = (19,19,19)
    #brainmarker = sitk.BinaryErode(maskI, radius, sitk.sitkBox)
    brainmarker = sitk.GrayscaleErode(maskI, radius, sitk.sitkBox)
    # invert and erode to get the background (erosion doesn't need to be the same)
    radius = (5,5,5)
    #bgmarker = 2 * sitk.BinaryErode(maskI == 0, radius, sitk.sitkBox)
    bgmarker = 2 * sitk.GrayscaleErode(maskI == 0, radius, sitk.sitkBox)
    
    marker = brainmarker + bgmarker
    del(maskI)
    del(brainmarker)
    del(bgmarker)
    os.makedirs(workdir, exist_ok=True)
    sitk.WriteImage(marker, os.path.join(workdir, "marker.nii.gz"))
    # set up the flair for watershed
    flairI = sitk.ReadImage(flair)
    # Small opening to clean up noise and some of the dura
    opened = sitk.GrayscaleMorphologicalOpening(flairI, (3,3,3), sitk.sitkBox)
    # make the gradient
    control = sitk.GrayscaleDilate(opened, (5,5,5), sitk.sitkBox) - opened
    control = sitk.SmoothingRecursiveGaussian(control, (1,1,1))
    sitk.WriteImage(control, os.path.join(workdir, "i.nii.gz"))
    ws = sitk.MorphologicalWatershedFromMarkers(control, marker, True)
    return(ws==1)


def run_watershed_scalping(flair_path, workdir, outfile):
    """
    Run watershed scalping using a preprocessed FLAIR.
    Returns output mask path.
    """
    os.makedirs(workdir, exist_ok=True)
    brainmask = alignmask(flair_path, mni, mnibrainmask)
    mfile = os.path.join(workdir, "flairbrainmask.nii.gz")
    ants.image_write(brainmask, mfile)
    del(brainmask)
    result = Scalp(flair_path, mfile, workdir)
    sitk.WriteImage(result, outfile)
    return outfile
