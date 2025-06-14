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
from . import masking


## test imports
#import nipype.interfaces.utility as util
#import nipype.pipeline.engine as pe
#import nipype.interfaces.io as nio

## validate input files before processing
print("Validating input files...")
is_valid, errors = input_validation.validate_input_files(
    commandline.args.t1, 
    commandline.args.mri_dir,
    {
        't2_sag': commandline.args.t2_sag,
        't2_cor': commandline.args.t2_cor,
        't2_tra': commandline.args.t2_tra,
        'flair': commandline.args.flair
    }
)

if not is_valid:
    print("Input validation failed:")
    for error in errors:
        print(f"  - {error}")
    sys.exit(1)
else:
    print("All input files validated successfully!")

## create directory structure
dir_structure.create_directories()

viewer = sitk.ImageViewer()
viewer.SetFileExtension('.nii.gz')
viewer.SetCommand('/group/deve2/local/focal/MRIcroGL/MRIcroGL_QT')
##viewer.Execute(file)



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



## reorient inputs to standard orientation 
reoriented_main_image_path = preprocess.convert_and_reorient(commandline.args.t1, "t1")
reoriented_flair_path = preprocess.convert_and_reorient(commandline.args.flair, "flair")
reoriented_t2_sag_path = preprocess.convert_and_reorient(commandline.args.t2_sag, "t2_sag")
reoriented_t2_cor_path = preprocess.convert_and_reorient(commandline.args.t2_cor, "t2_cor")
reoriented_t2_tra_path = preprocess.convert_and_reorient(commandline.args.t2_tra, "t2_tra")

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
mask_to_input = masking.generate_mask(preprocessed_flair)

## process mask
sdt_all_plus_2 = masking.main_mask_operations(mask_to_input)

## erode mask
eroded_masks_dict, zero_padded_erode_depths_list = masking.mask_erosions(sdt_all_plus_2)

## erode nifti
res_t1 = masking.multiply_masks_by_images(preprocessed_main_image, "t1", dir_structure.eroded_nifti_t1_dir, zero_padded_erode_depths_list, eroded_masks_dict)
res_t2_sag = masking.multiply_masks_by_images(postprocessed_t2_sag_image, "t2_sag", dir_structure.eroded_nifti_t2_dir, zero_padded_erode_depths_list, eroded_masks_dict)
res_t2_cor = masking.multiply_masks_by_images(postprocessed_t2_cor_image, "t2_cor", dir_structure.eroded_nifti_t2_dir, zero_padded_erode_depths_list, eroded_masks_dict)
res_t2_tra = masking.multiply_masks_by_images(postprocessed_t2_tra_image, "t2_tra", dir_structure.eroded_nifti_t2_dir, zero_padded_erode_depths_list, eroded_masks_dict)
res_flair = masking.multiply_masks_by_images(preprocessed_flair, "flair", dir_structure.eroded_nifti_flair_dir, zero_padded_erode_depths_list, eroded_masks_dict)

