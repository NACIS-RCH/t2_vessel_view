

## starting with mask operations, i.e., line 279 of pseudocode


import os
import argparse
import numpy as np
import pandas as pd
import nibabel as nb
import nibabel.freesurfer.mghformat as fsmgh
import gzip
import sys
import SimpleITK as sitk
from nipype.interfaces.fsl import BET

viewer = sitk.ImageViewer()
viewer.SetFileExtension('.nii.gz')
viewer.SetCommand('/group/deve2/local/focal/MRIcroGL/MRIcroGL_QT')
##viewer.Execute(file)

## 
test_data_dir = '/data/projects/NACIS/PATIENTS/DataManagement/Scripts/NACIS-RCH_github/test_dataset/487'
test_output_dir = '/data/projects/NACIS/PATIENTS/DataManagement/Scripts/NACIS-RCH_github/test_dataset/487/test_outputs'
rxs_mask_path = os.path.join(test_data_dir, "rxs_mask.nii.gz")

save_debug_images = True

def write_debug_image(image_object, output_file, output_directory = test_output_dir):
    if save_debug_images:
        path = os.path.join(test_output_dir, output_file) 
        sitk.WriteImage(image_object, path)



def main_mask_operations(resampled_mask):
    """
    Processes mask so that it can be eroded smoothly.
    
    Parameters
    ----------
    
    resampled_mask : string
        Binary mask in the space of the main image.
        
    Returns
    -------
    SimpleITK image object
        Postprocessed signed distance transform image.
    
    """
    
    rxs_mask = sitk.ReadImage(rxs_mask_path)
    ## smooth mask with gaussian kernel size 3
    smoothed_rxs_mask = sitk.DiscreteGaussian(rxs_mask, 3.0)
    write_debug_image(smoothed_rxs_mask,"smoothed_rxs_mask.nii.gz")
    
    ## Binarize the smoothed mask using a threshold of 0.5
    bin_sm_rxs_mask = sitk.BinaryThreshold(smoothed_rxs_mask, lowerThreshold=0.5, upperThreshold=1.0, insideValue=1, outsideValue=0)
    write_debug_image(bin_sm_rxs_mask,"bin_smoothed_rxs_mask.nii.gz")
    
    ## make inverse of that mask
    inv_bin_sm_rxs_mask = sitk.BinaryThreshold(smoothed_rxs_mask, lowerThreshold=0, upperThreshold=0.5, insideValue=1, outsideValue=0)
    write_debug_image(inv_bin_sm_rxs_mask,"inv_bin_smoothed_rxs_mask.nii.gz")
    
    ## get signed distance transform of upsampled mask
    sdt_rxs_mask = sitk.SignedMaurerDistanceMap(bin_sm_rxs_mask, squaredDistance=False, useImageSpacing=True)
    write_debug_image(sdt_rxs_mask,"sdt_rxs_mask.nii.gz")
    
    sdt_inv_rxs_mask = sitk.SignedMaurerDistanceMap(inv_bin_sm_rxs_mask, squaredDistance=False, useImageSpacing=True)
    write_debug_image(sdt_inv_rxs_mask,"sdt_inv_rxs_mask.nii.gz")

    ## get positive values of signed distance transform inside brain ;
    sdt_rxs_mask_image_by_minus_one = - sdt_rxs_mask
    write_debug_image(sdt_rxs_mask_image_by_minus_one,"sdt_rxs_mask_image_by_minus_one.nii.gz")

    ## this comes out as a binary mask. ?want a thresholded sdt image. multiply by image? see steps below for logic
    thresholded_img = sitk.BinaryThreshold(sdt_rxs_mask_image_by_minus_one, lowerThreshold=0, upperThreshold=50000)
    write_debug_image(thresholded_img,"thresholded_img.nii.gz")
    
    ## cast mask as float so it can be multiplied by sdt image
    thresholded_img_float = sitk.Cast(thresholded_img, sitk.sitkFloat32)
    ## multiply 
    pos_sdt_rxs_mask = sitk.Multiply(sdt_rxs_mask_image_by_minus_one, thresholded_img_float)
    write_debug_image(pos_sdt_rxs_mask,"pos_sdt_rxs_mask.nii.gz")

    ## add the inverse mask sdt to pos mask
    sdt_all = pos_sdt_rxs_mask + sdt_inv_rxs_mask
    write_debug_image(sdt_all,"sdt_all.nii.gz")

    # add 2 to dilate mask
    sdt_all_plus_2 = sdt_all + 2
    write_debug_image(sdt_all_plus_2,"sdt_all_plus_2.nii.gz")

    return sdt_all_plus_2


def mask_erosions(processed_signed_distance):
    """
    Erodes the mask at a series of depths.
    
    Parameters
    ----------
    processed_signed_distance: SimpleITK image object
    
    
    
    """
    erode_depths_list = [0.5, 1, 1.5, 2, 3]
    
    for erode_depth in erode_depths_list:
        
        ## multiply erode depths by ten so they can be zero padded
        erode_depth_times_ten = erode_depth * 10
        
        ## zero pad as string
        zero_padded_erode_depth = f'{erode_depth_times_ten:03}'
        
        ## threshold and binarise 
        
    ### could return list of image object file names or whatever useful
    

### the next part is thresholding the mask a bunch of times 
## can i store these as sitk image objects rather than writing them?

sdt_all_plus_2 = main_mask_operations(rxs_mask_path)
mask_erosions(sdt_all_plus_2)

