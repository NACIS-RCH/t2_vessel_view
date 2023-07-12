

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

## Save the binarized smoothed upsampled mask
#sitk.WriteImage(bin_sm_rxs_mask, "binarized_mask.nii.gz")

## get signed distance transform of upsampled mask
## suggested syntax - not sure of this metric, check this
sdt_rxs_mask = sitk.SignedMaurerDistanceMap(bin_sm_rxs_mask, squaredDistance=False, useImageSpacing=True)
sdt_rxs_mask_path = os.path.join(test_output_dir, "sdt_rxs_mask.nii.gz") ##for qa only
sitk.WriteImage(sdt_rxs_mask, sdt_rxs_mask_path) ##for qa only

sdt_inv_rxs_mask = sitk.SignedMaurerDistanceMap(inv_bin_sm_rxs_mask, squaredDistance=False, useImageSpacing=True)
sdt_inv_rxs_mask_path = os.path.join(test_output_dir, "sdt_inv_rxs_mask.nii.gz") ##for qa only
sitk.WriteImage(sdt_inv_rxs_mask, sdt_inv_rxs_mask_path) ##for qa only



# Save the distance transform - not needed? 
#sitk.WriteImage(dist_img, 'distance_transform.nii.gz')


## get positive values of signed distance transform inside brain ;

# Load the image as ndarray
sdt_rxs_mask_data = sitk.GetArrayFromImage(sdt_rxs_mask)

## multiply it by -1 somehow (does this work?)
sdt_rxs_mask_data_by_minus_one = sdt_rxs_mask_data * -1 

# Threshold the image (this is thresholding it as a numpy array if I'm understanding correctly)
## check if needs to be converted to image first
thresholded_data = sitk.BinaryThreshold(sdt_rxs_mask_data_by_minus_one, lowerThreshold=0, upperThreshold=50000, insideValue=sdt_rxs_mask_data_by_minus_one, outsideValue=0)

# Save the thresholded image
thresholded_img = sitk.GetImageFromArray(thresholded_data)
thresholded_img.CopyInformation(t1_img)
sitk.WriteImage(thresholded_img, 'thresholded_.nii.gz')


## (not sure if this needs to be done in sitk or as a numpy array)

## from bash script:
# fslmaths mask_processing/sdt_rxs_${mask} -mul -1 -thr 0 mask_processing/pos_sdt_rxs_${mask}
# add the inverse mask signed distance transform to it ;
# fslmaths mask_processing/pos_sdt_rxs_${mask} -add mask_processing/sdt_inv_rxs_${mask} mask_processing/sdt_all.nii.gz
# echo add 2 so that the mask dilates by 2 so that the vessels on the surface may be captured ;
# fslmaths mask_processing/sdt_all.nii.gz -add 2 mask_processing/sdt_all_plus_2.nii.gz


### the next part is thresholding the mask a bunch of times 
## can i store these as sitk image objects rather than writing them?
