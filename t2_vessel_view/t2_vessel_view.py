

import os
import argparse
import numpy as np
import pandas as pd
import nibabel as nb
import nibabel.freesurfer.mghformat as fsmgh
import gzip
import sys
import SimpleITK as sitk
import nipype.interfaces.fsl as fsl
import ants
#import nipype.interfaces.utility as util
#import nipype.pipeline.engine as pe
#import nipype.interfaces.io as nio

#print(os.environ["PYTHONPATH"])

viewer = sitk.ImageViewer()
viewer.SetFileExtension('.nii.gz')
viewer.SetCommand('/group/deve2/local/focal/MRIcroGL/MRIcroGL_QT')
##viewer.Execute(file)

## 
test_data_dir = '/data/projects/NACIS/PATIENTS/DataManagement/Scripts/NACIS-RCH_github/test_dataset/487'
test_output_dir = '/data/projects/NACIS/PATIENTS/DataManagement/Scripts/NACIS-RCH_github/test_dataset/487/test_outputs'
rxs_mask_path = os.path.join(test_data_dir, "rxs_mask.nii.gz")
input_t1_path = os.path.join(test_data_dir, "T1_raw.nii.gz")
input_flair_path = os.path.join(test_data_dir, "FLAIR.nii.gz")

save_debug_images = True

def write_debug_image(image_object, output_file, output_directory = test_output_dir):
    if save_debug_images:
        path = os.path.join(test_output_dir, output_file) 
        sitk.WriteImage(image_object, path)

def preprocess_main_image(input_t1):
    """
    Processes main image.
    
    Parameters
    ----------
    
    input_t1 : string
        T1 image (here nii format but build in dicom?).
        
    Returns
    -------
    SimpleITK image object
        Preprocessed T1 image.
    
    """
    #main_image = sitk.ReadImage(input_t1)
    
    ## include crop and reorient and n4 here
    ## this works if not run in rstudio/reticulate. it does put the images in the same directory as the script
    ## itself sits in though. 
    ## tried to use nipype for fslreorient2std - it causes an error seemingly related to PYTHONPATH and io.py but only if run in rstudio
    #reorient = fsl.Reorient2Std()
    #reorient.inputs.in_file = input_t1
    ## this step does not work: it just outputs a file in the working directory
    #reorient.inputs.out_file = os.path.join(test_output_dir, "test_T1_ro.nii.gz")
    #res = reorient.run()
    
    crop = fsl.RobustFOV()
    crop.inputs.in_file = input_t1
    crop.inputs.brainsize = 160
    crop.inputs.out_roi = os.path.join(test_output_dir, "T1_crop.nii.gz")
    res = crop.run()
    
    ## sitk n4 (THIS WORKS)
    main_image_crop = sitk.ReadImage(os.path.join(test_output_dir, "T1_crop.nii.gz"))
    #main_image_crop_n4 = sitk.N4BiasFieldCorrection(main_image_crop)
    #write_debug_image(main_image_crop_n4,"main_image_crop_n4.nii.gz")
    
    ## then upsample with sitk
    ## new spacing ( could include this as a variable)
    new_spacing = [0.5, 0.5, 0.5]
    
    # Calculate the size of the resampled image based on the new spacing
    new_size = [int(sz * spacing / new_spacing[idx]) for idx, (sz, spacing) in enumerate(zip(main_image_crop.GetSize(), main_image_crop.GetSpacing()))]

    # Perform resampling
    main_image_crop_n4_rs = sitk.Resample(main_image_crop, new_size, sitk.Transform(), sitk.sitkLinear, main_image_crop.GetOrigin(), new_spacing, main_image_crop.GetDirection(), 0.0, main_image_crop.GetPixelID())
    write_debug_image(main_image_crop_n4_rs,"main_image_crop_n4_rs.nii.gz")

    return main_image_crop_n4_rs

#preprocess_main_image(input_t1_path)

def preprocess_flair(input_flair, preprocessed_main_image):
    
    ## load flair
    flair_raw = sitk.ReadImage(input_flair)
    flair_raw_float = sitk.Cast(flair_raw, sitk.sitkFloat32)
        
    ## sitk n4 flair
    flair_n4 = sitk.N4BiasFieldCorrection(flair_raw_float)
    flair_n4_path = os.path.join(test_output_dir, "flair_n4.nii.gz") 
    sitk.WriteImage(flair_n4, flair_n4_path)
    write_debug_image(flair_n4,"flair_n4_debug.nii.gz")
    

    flair_moving_image = ants.image_read(flair_n4_path)
    ## not previously written out, have to write
    preprocessed_main_image_path = os.path.join(test_output_dir, "preprocessed_main_image.nii.gz") 
    sitk.WriteImage(preprocessed_main_image, preprocessed_main_image_path)
    
    t1_fixed_image = ants.image_read(preprocessed_main_image_path)
    
    ## affine registration
    flair_to_t1_registration = ants.registration (fixed = t1_fixed_image, moving = flair_moving_image, type_of_transform = "Affine")
    
    ## apply transform
    registered_flair = ants.apply_transforms(fixed = t1_fixed_image, moving = flair_moving_image, transformlist = flair_to_t1_registration["fwdtransforms"])
    
    # save registered flair
    preprocessed_flair_path = os.path.join(test_output_dir, "preprocessed_flair.nii.gz")
    ants.image_write(registered_flair, preprocessed_flair_path)
    
    return preprocessed_flair_path

def process_t2(t2_input_path):
    ## load
    ## n4
    ## register
    ## square
    
    
    return preprocessed_t2_path
    
def image_intensity_range(image_with_raw_range):
    ## load
    ## do arithmetic as per
    ## save as sitk image?
    
    return image_with_new_intensity_range


def generate_mask(image_for_mask):
    """
    Runs BET on a postprocessed FLAIR or T1 to generate brain mask.
    
    Parameters
    ----------
    
    image_for_mask : string
        Postprocessed FLAIR or T1 image as .nii.gz.
        
    Returns
    -------
    string
        Path to binary brain mask image.
    
    """
    
    ## decide whether this is run on original or upsampled images
    
    ## this BET call works, partially. tested it on a raw T1.
    btr=fsl.BET()
    btr.inputs.in_file = image_for_mask
    btr.inputs.frac = 0.5
    ## btr.inputs.mask (this didn't work)
    ##btr.inputs.no_output (this didn't work)
    hires_brain = os.path.join(test_output_dir, "test_bet_hires_brain.nii.gz")
    btr.inputs.out_file = hires_brain
    res = btr.run()
    
    hires_brain_image = sitk.ReadImage(hires_brain)
    hires_brain_float = sitk.Cast(hires_brain_image, sitk.sitkFloat32)
    
    hires_mask = hires_brain_image > 0
    hires_mask_float = sitk.Cast(hires_mask, sitk.sitkFloat32)
    
    hires_mask_path = os.path.join(test_output_dir, "test_bet_hires_mask.nii.gz")
    sitk.WriteImage(hires_mask_float, hires_mask_path)

    
    return hires_mask_path


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
    ## check this line
    rxs_mask = sitk.ReadImage(resampled_mask)
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
    ## make list of eroded mask file names?
    eroded_masks_dict = {}
    zero_padded_erode_depths_list = []
    
    for erode_depth in erode_depths_list:
        
        ## multiply erode depths by ten so they can be zero padded
        erode_depth_times_ten = int(erode_depth * 10)
        
        ## zero pad as string
        zero_padded_erode_depth = f'{erode_depth_times_ten:03}'
        zero_padded_erode_depths_list.append(zero_padded_erode_depth)
        
        ## threshold and binarise 
        
        ## make file name, save in list maybe
        eroded_mask_file_name = f'{zero_padded_erode_depth}_eroded_rxs_mask'
        
        ## threshold and binarise
        eroded_rxs_mask = processed_signed_distance > erode_depth
        eroded_rxs_mask_float = sitk.Cast(eroded_rxs_mask, sitk.sitkFloat32)
        write_debug_image(eroded_rxs_mask_float,f'{zero_padded_erode_depth}_eroded_rxs_mask.nii.gz')
        
        ##smooth
        smoothed_eroded_rxs_mask = sitk.DiscreteGaussian(eroded_rxs_mask_float, 3.0)
        write_debug_image(smoothed_eroded_rxs_mask,f'{zero_padded_erode_depth}_smoothed_eroded_rxs_mask.nii.gz')
        
        bin_smoothed_eroded_rxs_mask = smoothed_eroded_rxs_mask > 0.5
        bin_smoothed_eroded_rxs_mask_float = sitk.Cast(bin_smoothed_eroded_rxs_mask, sitk.sitkFloat32)

        write_debug_image(bin_smoothed_eroded_rxs_mask_float,f'{zero_padded_erode_depth}_bin_smoothed_eroded_rxs_mask.nii.gz')
        
        ## put extra step in here for smoothing? 
        eroded_masks_dict[eroded_mask_file_name] = bin_smoothed_eroded_rxs_mask_float
    
    ### also save masks as files in case option chosen
    ## return dictionary with mask file names and objects, and zero padded erode depths for use in other file names
    return (eroded_masks_dict, zero_padded_erode_depths_list)

## preprocess t1    
preprocessed_main_image = preprocess_main_image(input_t1_path)

## preprocess flair and register to preprocessed t1
preprocessed_flair = preprocess_flair(input_flair_path, preprocessed_main_image)

## generate mask
mask_to_input = generate_mask(preprocessed_flair)

## process mask
sdt_all_plus_2 = main_mask_operations(mask_to_input)

## erode mask
eroded_masks_dict, zero_padded_erode_depths_list = mask_erosions(sdt_all_plus_2)



