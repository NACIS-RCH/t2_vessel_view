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

# Check if we're in test mode
TEST_MODE = os.environ.get('T2VV_TEST_MODE') == '1'



# Import package modules using relative imports
from . import dir_structure
from . import logger
from . import input_validation
from . import commandline
from . import preprocess
from . import utils

## import hull function from other script
from .make_mask_convex_hull import make_hull_mask

## test imports
#import nipype.interfaces.utility as util
#import nipype.pipeline.engine as pe
#import nipype.interfaces.io as nio

## create directory structure
dir_structure.create_directories()



viewer = sitk.ImageViewer()
viewer.SetFileExtension('.nii.gz')
viewer.SetCommand('/group/deve2/local/focal/MRIcroGL/MRIcroGL_QT')
##viewer.Execute(file)



def convert_and_reorient(raw_input_file, input_filetype_string):
    """
    Converts to nii.gz and reorients to standard orientation
    
    Parameters
    ----------
    
    raw_input_file : string
        Path to raw input file
        
    Returns
    -------
    String
        Path to converted reoriented file
    
    """
    ## use nibabel to convert to nifti if not done earlier
    
    
    ## reorient
    ## this works if not run in rstudio/reticulate. it does put the images in the same directory as the script
    ## itself sits in though. 
    ## tried to use nipype for fslreorient2std - it causes an error seemingly related to PYTHONPATH and io.py but only if run in rstudio
    reorient = fsl.Reorient2Std()
    reorient.inputs.in_file = raw_input_file
    ## this works if the output type is specified but it also outputs a file with "to_ROI" suffix in the working directory
    reorient.inputs.output_type = 'NIFTI_GZ'
    ## this line apparently needed to prevent temp files with "to_ROI" suffix being written out
    ## does not work, also no documentation.
    #reorient.inputs.generate_report = False
    reoriented_im_path = os.path.join(utils.test_output_dir, f"{input_filetype_string}_ro.nii.gz")
    reorient.inputs.out_file = reoriented_im_path
    res = reorient.run()
    
    return reoriented_im_path

## make directory structure

# ## base directory that will be from arguments
# base_directory = utils.test_output_dir
# ## define directory structure. add option to change main directory name or add suffix
# 
# ## specify output directories as variables
# main_t2vv_dir = "T2VesselView"
# eroded_nifti_dir = "T2VesselView/Eroded_nifti"
# eroded_nifti_t1_dir = "T2VesselView/Eroded_nifti/T1"
# eroded_nifti_t2_dir = "T2VesselView/Eroded_nifti/T2"
# eroded_nifti_flair_dir = "T2VesselView/Eroded_nifti/FLAIR"
# powerpoints_dir = "T2VesselView/PowerPoints"
# processing_dir = "T2VesselView/Processing"
# processing_figures_dir = "T2VesselView/Processing/Figures_for_QA"
# processing_log_dir = "T2VesselView/Processing/Log_files"
# processing_mask_dir = "T2VesselView/Processing/Masks"
# processed_t1_dir = "T2VesselView/Processing/Preprocessed_T1"
# processed_t2_dir = "T2VesselView/Processing/Preprocessed_T2"
# processed_flair_dir = "T2VesselView/Processing/Preprocessed_FLAIR"
# renders_dir = "T2VesselView/3D_renders_png"
# renders_t1_dir = "T2VesselView/3D_renders_png/T1_3D_renders"
# renders_t1_erode_dir = "T2VesselView/3D_renders_png/T1_3D_renders/by_erode_level"
# renders_t1_angle_dir = "T2VesselView/3D_renders_png/T1_3D_renders/by_angle"
# renders_t2_dir = "T2VesselView/3D_renders_png/T2_vessel_3D_renders"
# renders_t2_erode_dir = "T2VesselView/3D_renders_png/T2_vessel_3D_renders/by_erode_level"
# renders_t2_angle_dir = "T2VesselView/3D_renders_png/T2_vessel_3D_renders/by_angle"
# 
# ## specify directories to be made
# directory_structure = [
#     main_t2vv_dir,
#     eroded_nifti_dir,
#     eroded_nifti_t1_dir,
#     eroded_nifti_t2_dir,
#     eroded_nifti_flair_dir,
#     powerpoints_dir,
#     processing_dir,
#     processing_figures_dir,
#     processing_log_dir,
#     processing_mask_dir,
#     processed_t1_dir,
#     processed_t2_dir,
#     processed_flair_dir,
#     renders_dir,
#     renders_t1_dir,
#     renders_t1_erode_dir,
#     renders_t1_angle_dir,
#     renders_t2_dir,
#     renders_t2_erode_dir,
#     renders_t2_angle_dir
# ]
# 
# ## create directories
# for directory in directory_structure:
#     directory_path = os.path.join(base_directory, directory)
#     os.makedirs(directory_path, exist_ok = True)
    
## verify directory structure
#for root, dirs, files in os.walk(base_directory):
#    for dir in dirs:
#        print(os.path.join(root, dir))



def generate_mask(image_for_mask):
    """
    Runs BET on a postprocessed FLAIR or T1 to generate brain mask.
    
    Parameters
    ----------
    
    image_for_mask : string
        Path to image to generate mask from.
        
    Returns
    -------
    String
        Path to generated mask.
    
    """
    if TEST_MODE:
        # Return dummy mask for testing
        dummy_mask_path = os.path.join(utils.test_output_dir, "test_bet_hires_mask.nii.gz")
        dummy_mask = sitk.Image([100, 100, 100], sitk.sitkUInt8)
        dummy_mask.SetSpacing([1.0, 1.0, 1.0])
        sitk.WriteImage(dummy_mask, dummy_mask_path)
        return dummy_mask_path
    
    ## this BET call works, partially. tested it on a raw T1.
    btr=fsl.BET()
    btr.inputs.in_file = image_for_mask
    btr.inputs.frac = 0.5
    btr.inputs.robust = True
    btr.inputs.mask = True
    btr.inputs.outline = True
    btr.inputs.no_output = False
    btr.inputs.output_type = 'NIFTI_GZ'
    hires_brain = os.path.join(utils.test_output_dir, "test_bet_hires_brain.nii.gz")
    btr.inputs.out_file = hires_brain
    res = btr.run()
    
    ## get the mask
    hires_mask_path = os.path.join(utils.test_output_dir, "test_bet_hires_mask.nii.gz")
    return hires_mask_path

def main_mask_operations(resampled_mask): 
    """
    Performs main mask operations including erosion and optional hull mask creation.
    
    Parameters
    ----------
    resampled_mask : SimpleITK image object
        The resampled mask to process
        
    Returns
    -------
    SimpleITK image object
        Processed mask ready for erosion
    """
    # Create hull mask if requested
    if commandline.args.use_hull_mask:
        top_hull, final_hull = make_hull_mask(resampled_mask)
        mask_to_process = final_hull
    else:
        mask_to_process = resampled_mask
    
    ## check this line
    rxs_mask = sitk.ReadImage(mask_to_process)
    ## smooth mask with gaussian kernel size 3
    smoothed_rxs_mask = sitk.DiscreteGaussian(rxs_mask, 3.0)
    utils.write_debug_image(smoothed_rxs_mask,"smoothed_rxs_mask.nii.gz")
    
    ## Binarize the smoothed mask using a threshold of 0.5
    bin_sm_rxs_mask = sitk.BinaryThreshold(smoothed_rxs_mask, lowerThreshold=0.5, upperThreshold=1.0, insideValue=1, outsideValue=0)
    utils.write_debug_image(bin_sm_rxs_mask,"bin_smoothed_rxs_mask.nii.gz")
    
    ## make inverse of that mask
    inv_bin_sm_rxs_mask = sitk.BinaryThreshold(smoothed_rxs_mask, lowerThreshold=0, upperThreshold=0.5, insideValue=1, outsideValue=0)
    utils.write_debug_image(inv_bin_sm_rxs_mask,"inv_bin_smoothed_rxs_mask.nii.gz")
    
    ## get signed distance transform of upsampled mask
    sdt_rxs_mask = sitk.SignedMaurerDistanceMap(bin_sm_rxs_mask, squaredDistance=False, useImageSpacing=True)
    utils.write_debug_image(sdt_rxs_mask,"sdt_rxs_mask.nii.gz")
    
    sdt_inv_rxs_mask = sitk.SignedMaurerDistanceMap(inv_bin_sm_rxs_mask, squaredDistance=False, useImageSpacing=True)
    utils.write_debug_image(sdt_inv_rxs_mask,"sdt_inv_rxs_mask.nii.gz")

    ## get positive values of signed distance transform inside brain ;
    sdt_rxs_mask_image_by_minus_one = - sdt_rxs_mask
    utils.write_debug_image(sdt_rxs_mask_image_by_minus_one,"sdt_rxs_mask_image_by_minus_one.nii.gz")

    ## this comes out as a binary mask. ?want a thresholded sdt image. multiply by image? see steps below for logic
    thresholded_img = sitk.BinaryThreshold(sdt_rxs_mask_image_by_minus_one, lowerThreshold=0, upperThreshold=50000)
    utils.write_debug_image(thresholded_img,"thresholded_img.nii.gz")
    
    ## cast mask as float so it can be multiplied by sdt image
    thresholded_img_float = sitk.Cast(thresholded_img, sitk.sitkFloat32)
    ## multiply 
    pos_sdt_rxs_mask = sitk.Multiply(sdt_rxs_mask_image_by_minus_one, thresholded_img_float)
    utils.write_debug_image(pos_sdt_rxs_mask,"pos_sdt_rxs_mask.nii.gz")

    ## add the inverse mask sdt to pos mask
    sdt_all = pos_sdt_rxs_mask + sdt_inv_rxs_mask
    utils.write_debug_image(sdt_all,"sdt_all.nii.gz")

    # add 2 to dilate mask
    sdt_all_plus_2 = sdt_all + 2
    utils.write_debug_image(sdt_all_plus_2,"sdt_all_plus_2.nii.gz")

    return sdt_all_plus_2

def mask_erosions(processed_signed_distance):
    """
    Erodes the mask at a series of depths.
    
    Parameters
    ----------
    processed_signed_distance: SimpleITK image object
    
    
    
    """
    erode_depths_list = [0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 5, 10, 20]
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
        
        ## make file name, save in list. this is not the final mask but works as dictionary key
        eroded_mask_file_name = f'{zero_padded_erode_depth}_eroded_rxs_mask'
        
        ## threshold and binarise
        eroded_rxs_mask = processed_signed_distance > erode_depth
        eroded_rxs_mask_float = sitk.Cast(eroded_rxs_mask, sitk.sitkFloat32)
        utils.write_debug_image(eroded_rxs_mask_float,f'{zero_padded_erode_depth}_eroded_rxs_mask.nii.gz')
        
        ##smooth
        smoothed_eroded_rxs_mask = sitk.DiscreteGaussian(eroded_rxs_mask_float, 3.0)
        utils.write_debug_image(smoothed_eroded_rxs_mask,f'{zero_padded_erode_depth}_smoothed_eroded_rxs_mask.nii.gz')
        
        bin_smoothed_eroded_rxs_mask = smoothed_eroded_rxs_mask > 0.5
        bin_smoothed_eroded_rxs_mask_float = sitk.Cast(bin_smoothed_eroded_rxs_mask, sitk.sitkFloat32)

        utils.write_debug_image(bin_smoothed_eroded_rxs_mask_float,f'{zero_padded_erode_depth}_bin_smoothed_eroded_rxs_mask.nii.gz')
        
        ## put extra step in here for smoothing? 
        eroded_masks_dict[eroded_mask_file_name] = bin_smoothed_eroded_rxs_mask_float
    
    ### also save masks as files in case option chosen
    ## return dictionary with mask file names and objects, and zero padded erode depths for use in other file names
    return (eroded_masks_dict, zero_padded_erode_depths_list)

def multiply_masks_by_images(image_to_erode, filetype_string, directory_for_outputs):
    """
    Multiply masks by images.
    """
    ## Output directory from directory structure, within 'Eroded_nifti' dir
    eroded_outdir = os.path.join(utils.test_output_dir, directory_for_outputs)
    
    ## sitk image object, image to erode
    im_to_erode = image_to_erode 
    
    ## loop through erosion depths 
    for depth in zero_padded_erode_depths_list:
        ## match erode depths to keys in dictionary
        full_key = depth + "_eroded_rxs_mask"
        
        if full_key in eroded_masks_dict:
            
            mask_im = eroded_masks_dict[full_key]
            mask_im_float = sitk.Cast(mask_im, sitk.sitkFloat32)
            
            eroded_im = sitk.Multiply(im_to_erode, mask_im_float)
            
            ## save to output dir
            eroded_im_path = os.path.join(eroded_outdir, f"{depth}_eroded_{filetype_string}.nii.gz")
            sitk.WriteImage(eroded_im, eroded_im_path)
            
            
        else: 
            print(f"{full_key} not found in masks dictionary")


    return

## reorient inputs to standard orientation 
reoriented_main_image_path = convert_and_reorient(utils.input_t1_path, "t1")
reoriented_flair_path = convert_and_reorient(utils.input_flair_path, "flair")
reoriented_t2_sag_path = convert_and_reorient(utils.input_t2_sag_path, "t2_sag")
reoriented_t2_cor_path = convert_and_reorient(utils.input_t2_cor_path, "t2_cor")
reoriented_t2_tra_path = convert_and_reorient(utils.input_t2_tra_path, "t2_tra")

## preprocess t1    
preprocessed_main_image, preprocessed_main_image_path = preprocess.preprocess_main_image(reoriented_main_image_path)

## preprocess flair and register to preprocessed t1
preprocessed_flair = preprocess.preprocess_n4_reg(reoriented_flair_path, "flair", preprocessed_main_image_path)

## preprocess t2 images
preprocessed_t2_sag_path = preprocess.preprocess_n4_reg(reoriented_t2_sag_path, "t2_sag", preprocessed_main_image_path)
preprocessed_t2_cor_path = preprocess.preprocess_n4_reg(reoriented_t2_cor_path, "t2_cor", preprocessed_main_image_path)
preprocessed_t2_tra_path = preprocess.preprocess_n4_reg(reoriented_t2_tra_path, "t2_tra", preprocessed_main_image_path)

## postprocess t2 images
postprocessed_t2_sag_image = preprocess.postprocess_t2(preprocessed_t2_sag_path, "t2_sag")
postprocessed_t2_tra_image = preprocess.postprocess_t2(preprocessed_t2_tra_path, "t2_tra")
postprocessed_t2_cor_image = preprocess.postprocess_t2(preprocessed_t2_cor_path, "t2_cor")

## generate mask
mask_to_input = generate_mask(preprocessed_flair)

## process mask
sdt_all_plus_2 = main_mask_operations(mask_to_input)

## erode mask
eroded_masks_dict, zero_padded_erode_depths_list = mask_erosions(sdt_all_plus_2)

## erode nifti
res_t1 = multiply_masks_by_images(preprocessed_main_image, "t1", dir_structure.eroded_nifti_t1_dir)
res_t2_sag = multiply_masks_by_images(postprocessed_t2_sag_image, "t2_sag", dir_structure.eroded_nifti_t2_dir)
res_t2_cor = multiply_masks_by_images(postprocessed_t2_cor_image, "t2_cor", dir_structure.eroded_nifti_t2_dir)
res_t2_tra = multiply_masks_by_images(postprocessed_t2_tra_image, "t2_tra", dir_structure.eroded_nifti_t2_dir)
res_flair = multiply_masks_by_images(preprocessed_flair, "flair", dir_structure.eroded_nifti_flair_dir)

