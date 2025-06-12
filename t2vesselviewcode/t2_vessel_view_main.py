
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

## import hull function from other script
#from t2vesselviewcode.make_mask_convex_hull import make_hull_mask

## test imports
#import nipype.interfaces.utility as util
#import nipype.pipeline.engine as pe
#import nipype.interfaces.io as nio

## import modules within current package            

## below import had some issues, see
#https://stackoverflow.com/questions/43728431/relative-imports-modulenotfounderror-no-module-named-x

#THIS WORKED previously before renaming from 't2vesselview'. ! BUT WHY. Perhaps issues with two packages called same thing? see .txt file with top level defined as 't2vesselview'
## now gives error, "no module namesd t2_vessel_viewcode" - this was from init file typo which didn't match with dir name here
## i had reinstalled the package using 't2vesselviewcode' as the top directory and this seems to work
## cannot uncomment the __init__ file at this level because it runs this whole script on the hard coded files included
## this works now but will have to reinstall on upper directory later

from t2vesselviewcode import dir_structure
#from . import dir_structure

# This still does not work. it gives error saying, "attempted relative import with no known parent package"
## something to do with pythonpath??
#from . import dir_structure

#print(os.environ["PYTHONPATH"])

viewer = sitk.ImageViewer()
viewer.SetFileExtension('.nii.gz')
viewer.SetCommand('/group/deve2/local/focal/MRIcroGL/MRIcroGL_QT')
##viewer.Execute(file)


## 
test_data_dir = '/data/projects/NACIS/PATIENTS/DataManagement/Scripts/NACIS-RCH_github/test_dataset/487'
test_output_dir = '/data/projects/NACIS/PATIENTS/DataManagement/Scripts/NACIS-RCH_github/test_dataset/487/test_outputs'
#rxs_mask_path = os.path.join(test_data_dir, "rxs_mask.nii.gz")
input_t1_path = os.path.join(test_data_dir, "T1_raw.nii.gz")
input_flair_path = os.path.join(test_data_dir, "FLAIR.nii.gz")
input_t2_sag_path = os.path.join(test_data_dir, "T2_tse_sag_l.nii.gz")
input_t2_cor_path = os.path.join(test_data_dir, "T2_tse_cor.nii.gz")
input_t2_tra_path = os.path.join(test_data_dir, "T2_tse_tra.nii.gz")


save_debug_images = True

def write_debug_image(image_object, output_file, output_directory = test_output_dir):
    if save_debug_images:
        path = os.path.join(test_output_dir, output_file) 
        sitk.WriteImage(image_object, path)




## here something like
## if inputvariable is not None:
## append string descriptor and file path to dictionary
## then do something like for string, path in dictionary, preprocess things

## check file exists in location
## check file type?
## check image dimensions?
## for testing, use hard coded version


#images_to_input = {
#    "flair": input_flair_path,
#    "t2_sag": input_t2_sag_path,
#    "t2_tra": input_t2_tra_path,
#    "t2_cor": input_t2_cor_path
#}

## handle input files
## check if nifti or dicom or otherwise
## convert to nii.gz
## reorient2std




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
    reoriented_im_path = os.path.join(test_output_dir, f"{input_filetype_string}_ro.nii.gz")
    reorient.inputs.out_file = reoriented_im_path
    res = reorient.run()
    
    return reoriented_im_path

## make directory structure

# ## base directory that will be from arguments
# base_directory = test_output_dir
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
    
    ## crop using fsl robustfov in nipype. 
    ## this still outputs a "to_ROI" suffix file, find how to stop that
    crop = fsl.RobustFOV()
    crop.inputs.in_file = input_t1
    crop.inputs.brainsize = 160
    ## this doesn't work but there's no documentation for an alternative
    #crop.inputs.generate_report = False
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
    
    main_image_crop_n4_rs_resc = sitk.RescaleIntensity(main_image_crop_n4_rs, outputMinimum = 0, outputMaximum = 1000)
    
    main_image_crop_n4_rs_resc_path = os.path.join(test_output_dir, "Preprocessed_main_image.nii.gz")
    ## need to write this out partly because ANTS needs it 
    sitk.WriteImage(main_image_crop_n4_rs_resc, main_image_crop_n4_rs_resc_path)

    write_debug_image(main_image_crop_n4_rs_resc,"main_image_crop_n4_rs_resc.nii.gz")

    return main_image_crop_n4_rs_resc, main_image_crop_n4_rs_resc_path

#preprocess_main_image(input_t1_path)

def preprocess_n4_reg(input_raw, input_imagetype_string, preprocessed_main_image_path):
    """
    Preprocesses images other than the main image using bias correction, and registration to main image.
    
    Parameters
    ----------
    
    input_raw : string
        input image path
        
    input_imagetype_string : string
        string describing image type e.g., "flair", "t2_sag"
        
    Returns
    -------
    String
        Preprocessed image path
    
    """
    ## load im
    im_raw = sitk.ReadImage(input_raw)
    im_raw_float = sitk.Cast(im_raw, sitk.sitkFloat32)
        
    ## sitk n4 im
    im_n4 = sitk.N4BiasFieldCorrection(im_raw_float)
    im_n4_path = os.path.join(test_output_dir, f"{input_imagetype_string}_n4.nii.gz") 
    sitk.WriteImage(im_n4, im_n4_path)
    write_debug_image(im_n4,f"{input_imagetype_string}_n4_debug.nii.gz")
    
    ## register to t1 using ants. have to load as new image
    im_moving_image = ants.image_read(im_n4_path)
    
    ## load preprocessed t1
    t1_fixed_image = ants.image_read(preprocessed_main_image_path)
    
    ## affine registration
    im_to_t1_registration = ants.registration (fixed = t1_fixed_image, moving = im_moving_image, type_of_transform = "Affine")
    
    ## apply transform
    registered_im = ants.apply_transforms(fixed = t1_fixed_image, moving = im_moving_image, transformlist = im_to_t1_registration["fwdtransforms"])

    
    # save registered im (this could be a temp file, see how that works)
    registered_im_path = os.path.join(test_output_dir, f"registered_{input_imagetype_string}.nii.gz")
    ants.image_write(registered_im, registered_im_path)
    
     
    ## rescale image intensities. needs to have sitk image loaded not ants image
    sitk_registered_im = sitk.ReadImage(registered_im_path)
    sitk_registered_im_float = sitk.Cast(sitk_registered_im, sitk.sitkFloat32)
    registered_im_resc = sitk.RescaleIntensity(sitk_registered_im_float, outputMinimum = 0, outputMaximum = 1000)
    
    preprocessed_im_path = os.path.join(test_output_dir, f"Preprocessed_{input_imagetype_string}.nii.gz")
    sitk.WriteImage(registered_im_resc, preprocessed_im_path)
    
    return preprocessed_im_path

def postprocess_t2(preprocessed_t2_input_path, preprocessed_imagetype_string):
    """
    Postprocesses T2 images: arithmetic operations.
    
    Parameters
    ----------
    
    t2_input_path : string
        Path to T2 image
        
    Returns
    -------
    String
        Postprocessed T2 image path
    
    """
    ## load preprocessed t2
    t2_pre = sitk.ReadImage(preprocessed_t2_input_path)
    
    t2_inv = sitk.InvertIntensity(t2_pre)
    write_debug_image(t2_inv,f"inv_{preprocessed_imagetype_string}.nii.gz")
    
    t2_inv_rescale = sitk.RescaleIntensity(t2_inv, outputMinimum = 0, outputMaximum = 1000)
    write_debug_image(t2_inv_rescale,f"inv_rescale_{preprocessed_imagetype_string}.nii.gz")
    
    t2_inv_sqr = sitk.Pow(t2_inv_rescale, 2)
    write_debug_image(t2_inv_sqr,f"inv_sqr_{preprocessed_imagetype_string}.nii.gz")

    t2_inv_re_rescale = sitk.RescaleIntensity(t2_inv_sqr, outputMinimum = 0, outputMaximum = 1000)
    write_debug_image(t2_inv_re_rescale,f"inv_sqr_re_rescale_{preprocessed_imagetype_string}.nii.gz")
    
    return t2_inv_rescale
    

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
    ## this can only seem to output non-binary brain extracted image
    btr.inputs.out_file = hires_brain
    res = btr.run()
    
    hires_brain_image = sitk.ReadImage(hires_brain)
    hires_brain_float = sitk.Cast(hires_brain_image, sitk.sitkFloat32)
    ## binarise 
    hires_mask = hires_brain_image > 0
    ## make float
    hires_mask_float = sitk.Cast(hires_mask, sitk.sitkFloat32)
    
    ## perform hull operations on mask
    ## **check this imported function works
    # hires_hull_mask = make_hull_mask(hires_mask_float)[1]
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
        
        ## make file name, save in list. this is not the final mask but works as dictionary key
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

def multiply_masks_by_images(image_to_erode, filetype_string, directory_for_outputs):
    """
    Multiplies processed images by processed masks to generate eroded nifti images

    Parameters
    ----------

    image_to_erode : simple itk image object
        preprocessed main image sitk object
        
    filetype_string : string
        String descriptor of image modality, e.g., "T1", "T2_sag".

    Returns
    -------
    ?String
        ? path

    """

    ## Output directory from directory structure, within 'Eroded_nifti' dir
    eroded_outdir = os.path.join(test_output_dir, directory_for_outputs)
    
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
reoriented_main_image_path = convert_and_reorient(input_t1_path, "t1")
reoriented_flair_path = convert_and_reorient(input_flair_path, "flair")
reoriented_t2_sag_path = convert_and_reorient(input_t2_sag_path, "t2_sag")
reoriented_t2_cor_path = convert_and_reorient(input_t2_cor_path, "t2_cor")
reoriented_t2_tra_path = convert_and_reorient(input_t2_tra_path, "t2_tra")

## preprocess t1    
preprocessed_main_image, preprocessed_main_image_path = preprocess_main_image(reoriented_main_image_path)

## preprocess flair and register to preprocessed t1
preprocessed_flair = preprocess_n4_reg(reoriented_flair_path, "flair", preprocessed_main_image_path)

## preprocess t2 images
preprocessed_t2_sag_path = preprocess_n4_reg(reoriented_t2_sag_path, "t2_sag", preprocessed_main_image_path)
preprocessed_t2_cor_path = preprocess_n4_reg(reoriented_t2_cor_path, "t2_cor", preprocessed_main_image_path)
preprocessed_t2_tra_path = preprocess_n4_reg(reoriented_t2_tra_path, "t2_tra", preprocessed_main_image_path)

## postprocess t2 images
postprocessed_t2_sag_image = postprocess_t2(preprocessed_t2_sag_path, "t2_sag")
postprocessed_t2_tra_image = postprocess_t2(preprocessed_t2_tra_path, "t2_tra")
postprocessed_t2_cor_image = postprocess_t2(preprocessed_t2_cor_path, "t2_cor")

## generate mask
mask_to_input = generate_mask(preprocessed_flair)

#for image_type, image_type_path in images_to_register.items():

## process mask
sdt_all_plus_2 = main_mask_operations(mask_to_input)

## erode mask
eroded_masks_dict, zero_padded_erode_depths_list = mask_erosions(sdt_all_plus_2)

## erode nifti
res_t1 = multiply_masks_by_images(preprocessed_main_image, "t1", eroded_nifti_t1_dir)
res_t2_sag = multiply_masks_by_images(postprocessed_t2_sag_image, "t2_sag", eroded_nifti_t2_dir)
## other t2s? in same or separate dirs?

