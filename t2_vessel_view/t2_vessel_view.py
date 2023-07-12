

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

#### mask operations (done in upsampled t1 space) ---------------------------------------

## 
test_data_dir = '/data/projects/NACIS/PATIENTS/DataManagement/Scripts/NACIS-RCH_github/test_dataset/487'
test_output_dir = '/data/projects/NACIS/PATIENTS/DataManagement/Scripts/NACIS-RCH_github/test_dataset/487/test_outputs'
rxs_mask_path = os.path.join(test_data_dir, "rxs_mask.nii.gz")


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
    qa_smoothed_mask_path = os.path.join(test_output_dir, "smoothed_rxs_mask.nii.gz") ##for qa only
    sitk.WriteImage(smoothed_rxs_mask, qa_smoothed_mask_path) ##for qa only
    
    ## Binarize the smoothed mask using a threshold of 0.5
    bin_sm_rxs_mask = sitk.BinaryThreshold(smoothed_rxs_mask, lowerThreshold=0.5, upperThreshold=1.0, insideValue=1, outsideValue=0)
    qa_bin_smoothed_mask_path = os.path.join(test_output_dir, "bin_smoothed_rxs_mask.nii.gz") ##for qa only
    sitk.WriteImage(bin_sm_rxs_mask, qa_bin_smoothed_mask_path) ##for qa only
    
    ## make inverse of that mask
    inv_bin_sm_rxs_mask = sitk.BinaryThreshold(smoothed_rxs_mask, lowerThreshold=0, upperThreshold=0.5, insideValue=1, outsideValue=0)
    qa_inv_bin_smoothed_mask_path = os.path.join(test_output_dir, "inv_bin_smoothed_rxs_mask.nii.gz") ##for qa only
    sitk.WriteImage(inv_bin_sm_rxs_mask, qa_inv_bin_smoothed_mask_path) ##for qa only
    
    ## get signed distance transform of upsampled mask
    ## this seems to work well
    sdt_rxs_mask = sitk.SignedMaurerDistanceMap(bin_sm_rxs_mask, squaredDistance=False, useImageSpacing=True)
    sdt_rxs_mask_path = os.path.join(test_output_dir, "sdt_rxs_mask.nii.gz") ##for qa only
    sitk.WriteImage(sdt_rxs_mask, sdt_rxs_mask_path) ##for qa only
    
    sdt_inv_rxs_mask = sitk.SignedMaurerDistanceMap(inv_bin_sm_rxs_mask, squaredDistance=False, useImageSpacing=True)
    sdt_inv_rxs_mask_path = os.path.join(test_output_dir, "sdt_inv_rxs_mask.nii.gz") ##for qa only
    sitk.WriteImage(sdt_inv_rxs_mask, sdt_inv_rxs_mask_path) ##for qa only
    
    ## get positive values of signed distance transform inside brain ;
    sdt_rxs_mask_image_by_minus_one = sitk.Multiply(sdt_rxs_mask,-1)
    sdt_rxs_mask_image_by_minus_one_path = os.path.join(test_output_dir, "sdt_rxs_mask_image_by_minus_one.nii.gz") ##for qa only
    sitk.WriteImage(sdt_rxs_mask_image_by_minus_one, sdt_rxs_mask_image_by_minus_one_path) ##for qa only
    
    ## this comes out as a binary mask. ?want a thresholded sdt image. multiply by image? see steps below for logic
    thresholded_img = sitk.BinaryThreshold(sdt_rxs_mask_image_by_minus_one, lowerThreshold=0, upperThreshold=50000)
    thresholded_img_path = os.path.join(test_output_dir, "thresholded_img.nii.gz") ##for qa only
    sitk.WriteImage(thresholded_img, thresholded_img_path) ##for qa only
    ## cast mask as float so it can be multiplied by sdt image
    thresholded_img_float = sitk.Cast(thresholded_img, sitk.sitkFloat32)
    ## multiply 
    pos_sdt_rxs_mask = sitk.Multiply(sdt_rxs_mask_image_by_minus_one, thresholded_img_float)
    pos_sdt_rxs_mask_path = os.path.join(test_output_dir, "pos_sdt_rxs_mask.nii.gz") ##for qa only
    sitk.WriteImage(pos_sdt_rxs_mask, pos_sdt_rxs_mask_path) ##for qa only
    
    ## add the inverse mask sdt to pos mask
    sdt_all = sitk.Add(pos_sdt_rxs_mask, sdt_inv_rxs_mask)
    sdt_all_path = os.path.join(test_output_dir, "sdt_all.nii.gz") ##for qa only
    sitk.WriteImage(sdt_all, sdt_all_path) ##for qa only
    
    # add 2 to dilate mask
    sdt_all_plus_2 = sitk.Add(sdt_all, 2)
    sdt_all_plus_2_path = os.path.join(test_output_dir, "sdt_all_plus_2.nii.gz") ##for qa only
    sitk.WriteImage(sdt_all_plus_2, sdt_all_plus_2_path) ##for qa only
    
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
        zero_padded_erode_depth = 
    
    

### the next part is thresholding the mask a bunch of times 
## can i store these as sitk image objects rather than writing them?

main_mask_operations(rxs_mask_path)

