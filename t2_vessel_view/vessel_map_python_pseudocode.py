
##    plan:
## use current erosion with vessel map code 
## translate as much as possible into python tools
## leave things that can't be wrapped as is and figure out later
## use argparse even though probably going to use a config script, 
## can take it out later if needed


## inputs: 
## T1, FLAIR or other bright image including a 3d T2, T2(s)
## Outputs:
## Eroded nifti files
## .png files containing screenshots at standard angles
## .pptx file containing the .png files
## QA screenshots of preprocessing, including picture of brain mask

## Steps:
## Import data
### currently use arguments/argparse
### probably want to use config file instead
### could try to make a small GUI - python package tkinter?? 
## Convert file types? It should ideally read nii, nii.gz, dicom, .mgz, other? 
## Define functions (see screenshot stitcher script)
## preprocess t2
## preprocess FLAIR/bright image
## make and process mask (do at this point so can QA it)
## take QA screenshot of mask overlaid on FLAIR/bright image?

## upsample T1
## register all images to upsampled T1
## rescale image intensities

### SDT (sitk?)
### other operations incl thresholding
## multiply all images by mask and save them as .nii.gz


## ?? make calls to external code to take screenshots??
## ?? make the code check for the presence of the right amount of screenshots

## ??? if it finds it, then put them into a pptx

## ----------------------------------------------------------------------------

## import packages

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
from pptx import Presentation
from pptx.dml.color import ColorFormat, RGBColor
from pptx.dml.color import MSO_COLOR_TYPE, MSO_THEME_COLOR
from pptx.util import Inches, Pt

def initialize_parser():
    parser = argparse.ArgumentParser(description='T2VesselView. Displays brain vasculature based on T2-weighted MRI.', epilog='Version 1, Bonnie Alexander ')

    parser.add_argument('-d', action='store', help='Full or absolute path to where the MRI images are', required=True, dest='patient_directory')
    parser.add_argument('-o', type=str, action='store', help='Required. Full path to where the output T2VesselView directory should be created.', required=True, dest='output_directory')
    parser.add_argument('-i', type=str, action='store', help='T1 brain MRI image', required=True, dest='input_t1')
    parser.add_argument('-f', type=str, action='store', help='3D FLAIR brain MRI image or other 3D bright image such as T2_space or MAG', dest='input_flair')
    parser.add_argument('-t', type=str, action='store', help='2D transverse T2-weighted image', dest='input_t2_tra')
    parser.add_argument('-c', type=str, action='store', help='2D coronal T2-weighted image', dest='input_t2_cor')
    parser.add_argument('-s', type=str, action='store', help='2D sagittal T2-weighted image', dest='input_t2_sag')
    parser.add_argument('-b', type=str, action='store', help='3D T2-weighted image', dest='input_t2_sag')
    parser.add_argument('-m', type=str, action='store', help='Optional. User-supplied brain mask. Can be used if automatically generated mask is suboptimal.', dest='input_mask')
    parser.add_argument('-v', type=str, action='store', help='Optional. Specify a name for the output T2VesselView folder which will be newly created. E.g., VesselView_2023. This folder will be created.', dest='new_vesselview_dirname')
    parser.add_argument('-p', metavar='pptx file basename', type=str, action='store', help='File name for output powerpoint slide. Without the .pptx extension as this will be added automatically.', dest='pptx_file_name')
    parser.add_argument('-n', '--saveniftis', action='store_true', help='Save processed nifti files (uses more space)')
    
    return parser

## these two lines needed by argparse
parser = initialize_parser()
args = parser.parse_args()


def rescale_image_intensities():
    ## do i need to do this to an array or to an image?
    ## check this later
    




## add checks here for whether file paths exist and files exist??
## add checks for file format of mri images to check that they are in a format readable by nibabel? 


patient_directory = args.patient_directory
if not os.path.isdir(patient_directory):
    print(f'Patient directory specified (i.e., {patient_directory}) could not be found or is not a directory. Please specify the directory that contains the MRI images.')
    sys.exit()
    
output_dir = args.output_directory
if not os.path.isdir(output_dir):
    print(f'Output directory specified (i.e., {output_dir}) could not be found or is not a directory. Please check the file path to where you want the T2vesselview directory to be made.')
    sys.exit()

## check whether the main output directory to be created already exists
## and if not, create it
if args.new_vesselview_dirname is not None:
    vesselview_dir = os.path.join(output_dir, args.new_vesselview_dirname)
else:
    vesselview_dir = os.path.join(output_dir, 'T2vesselview')

if os.path.isdir(vesselview_dir):
    print(f"T2vesselview directory already exists here: {vesselview_dir}. Please delete or rename existing directory, or rerun this script and specify a new unique folder name (e.g., vesselview_2023) for output vesselview folder using optional argument -v.")
    sys.exit()
else:
    os.mkdir(vesselview_dir)

## create output directory structure
## directories inside main directory
renders_png_dir = os.path.join(vesselview_dir, '3D_renders_png')
os.mkdir(renders_png_dir)        
eroded_nifti_dir = os.path.join(vesselview_dir, 'Eroded_nifti')
os.mkdir(eroded_nifti_dir)
powerpoints_dir = os.path.join(vesselview_dir, 'Powerpoints')
os.mkdir(powerpoints_dir)
processing_dir = os.path.join(vesselview_dir, 'Processing')
os.mkdir(processing_dir)

## subdirectories. surely can do this more effectively somehow
renders_subdirs = ["T1_3D_renders", "T2_vessel_3D_renders"]
for subdir in renders_subdirs:
    os.mkdir(os.path.join(renders_png_dir, subdir))
    
eroded_nifti_subdirs = ["T1", "T2", "FLAIR"]
for subdir in eroded_nifti_subdirs:
    os.mkdir(os.path.join(eroded_nifti_dir, subdir))
    
processing_subdirs = ["Figures_for_QA", "Log_files", "Masks", "Preprocessed_T1", "Preprocessed_T2", "Preprocessed_FLAIR"]
for subdir in processing_subdirs:
    os.mkdir(os.path.join(processing_dir, subdir))
    


## assign variables to input files and ?load them? -------------------------------------
## how to manage different files types? just assume .nii.gz for now
t1_path = os.path.join(patient_directory, args.input_t1)
t1_image = nb.load(t1_path)
t1_data = t1_image.get_fdata()

if args.input_flair is not None:
    flair_path = os.path.join(patient_directory, args.input_flair)
    flair_image = nb.load(flair_path)
    flair_data = flair_image.get_fdata()
    
## add inputs for t2 images. do in for loop?


## add input for optional mask file
## ?? need a way to specify on command line which space this mask is in - maybe specify pair of [mask, corresponding structural image]??

if args.input_mask is not None: 
    mask_path = os.path.join(patient_directory, args.input_mask)
    mask_image = nb.load(mask_path)
    mask_data = mask_image.get_fdata()
else:
    ## generate mask based on input flair or T1
    
### make mask based on flair/bright image part ---------------------------------------

## preprocess flair
## apply n4
## seems like could do this with sitk or nipype 
## both of these require image to be input in ?nii format
## sitk example:

## simpleitk: (assuming this is a .nii.gz already)
sitk_flair_raw = sitk.ReadImage(flair_path)
## bias correct (?how to get options?)
sitk_flair_n4 = sitk.N4BiasFieldCorrection(sitk_flair_raw)
## save n4 image (does it need to be saved?**? assume so for use by bet)
sitk_flair_n4_image = os.path.join(patient_directory, "sitk_FLAIR_n4.nii.gz")
sitk.WriteImage(sitk_flair_n4, sitk_flair_n4_image)

## this would be how to get data as a numpy array from the sitk image object:
# flair_raw_nparray = sitk.GetArrayFromImage(image)


## calling BET via nipype interface for this tool specifically

## input file from sitk call above
## probably want to get more than one mask with different thresholds. 
## just try one for now
## got this from miykael.github.io/nipype_tutorial/notebooks/basic_interfaces.html
flair_mask = os.path.join(patient_directory, "bet_FLAIR_mask.nii.gz")
bet = BET(in_file = sitk_flair_n4_image, out_file = flair_mask, mask = True, no_output = True, frac = 0.5)
res = bet.run()

## generate output screenshot for QA of mask

## Load mask image
flair_mask_image = sitk.ReadImage(flair_mask)

## check some of this suggested syntax:
## Overlay mask on T1 image with specified color and opacity
overlay_img = sitk.LabelOverlay(sitk_flair_n4, flair_mask_image, opacity=0.4, backgroundValue=0, colormap='autumn')

## Create axial lightbox view of the overlay image
sitk.Show(sitk.Tile(overlay_img[:,:,sitk_flair_n4.GetSize()[2]//2], (1,1,0)))

## Save axial lightbox view as PNG file - not sure this is still a lightbox view :) edit this to include above
sitk.WriteImage(overlay_img[:,:,sitk_flair_n4.GetSize()[2]//2], os.path.join(processing_dir, 'Figures_for_QA', 'mask_for_QA.png'))


### upsampling and registration part ----------------------------------------------------

## (check that this upsampling is still necessary with mricroGL's )***
## probably also include option to not upsample data (would effectively downsample 2d t2s though - maybe only allow if no t2s)
## upsample T1 using sitk
sitk_t1 = sitk.Readimage(t1_path)
output_spacing = [0.5, 0.5, 0.5]
resampler = sitk.ResampleImageFilter()
resampler.SetOutputSpacing(output_spacing)
## change below from linear?
resampler.SetInterpolator(sitk.sitkLinear)
output_image = resampler.Execute()
upsampled_T1_image = os.path.join(patient_directory, "rxs_T1.nii.gz")
sitk.WriteImage(output_image, upsampled_T1_image) ## possibly not need saved image ultimately?

### register all images to upsampled T1
## start w T2?
## should write these as separate functions for the 

## check this suggested syntax for registration.
## unsure of the method here and whether this can replace ants affine transform, check this

# Load T2_cor image
t2_cor_image = sitk.ReadImage("T2_cor.nii.gz")

# Affine register T2_cor image to upsampled T1 image
t2_cor_registration = sitk.ImageRegistrationMethod()
t2_cor_registration.SetMetricAsMattesMutualInformation(numberOfHistogramBins=50)
t2_cor_registration.SetMetricSamplingStrategy(t2_cor_registration.RANDOM)
t2_cor_registration.SetMetricSamplingPercentage(0.01)
t2_cor_registration.SetInterpolator(sitk.sitkLinear)
t2_cor_registration.SetOptimizerAsGradientDescent(learningRate=1.0, numberOfIterations=100, convergenceMinimumValue=1e-6, convergenceWindowSize=10)
t2_cor_registration.SetOptimizerScalesFromPhysicalShift()
transform = sitk.AffineTransform(3)
t2_cor_registration.SetInitialTransform(transform, True)
t2_cor_registration.SetShrinkFactorsPerLevel([4, 2, 1])
t2_cor_registration.SetSmoothingSigmasPerLevel([2, 1, 0])
t2_cor_registration.AddCommand(sitk.sitkIterationEvent, lambda: print(f"Iteration: {t2_cor_registration.GetOptimizerIteration()}, Metric value: {t2_cor_registration.GetMetricValue()}"))
transform = t2_cor_registration.Execute(upsampled_T1_image, t2_cor_image)

# Load T2_tra image
t2_tra_image = sitk.ReadImage("T2_tra.nii.gz")

# Affine register T2_tra image to upsampled T1 image
t2_tra_registration = sitk.ImageRegistrationMethod()
t2_tra_registration.SetMetricAsMattesMutualInformation(numberOfHistogramBins=50)
t2_tra_registration.SetMetricSamplingStrategy(t2_tra_registration.RANDOM)
t2_tra_registration.SetMetricSamplingPercentage(0.01)
t2_tra_registration.SetInterpolator(sitk.sitkLinear)
t2_tra_registration.SetOptimizerAsGradientDescent(learningRate=1.0, numberOfIterations=100, convergenceMinimumValue=1e-6, convergenceWindowSize=10)
t2_tra_registration.SetOptimizerScalesFromPhysicalShift()
transform = sitk.AffineTransform(3)
t2_tra_registration.SetInitialTransform(transform, True)
t2_tra_registration.SetShrinkFactorsPerLevel([4, 2, 1])
t2_tra_registration.SetSmoothingSigmasPerLevel([2, 1, 0])
t2_tra_registration.AddCommand(sitk.sitkIterationEvent, lambda: print(f"Iteration: {t2_tra_registration.GetOptimizerIteration()}, Metric value: {t2_tra_registration.GetMetricValue()}"))
transform = t2_tra_registration.Execute(upsampled_T1_image, t2_tra_image)
## code is not saving transformed images, prob don't need to at this point

## register the flair
## register the flair-based mask to the upsampled t1 here (making rxs_mask)

#### mask operations (done in upsampled t1 space) ---------------------------------------

## smooth mask with gaussian kernel size 3
smoothed_rxs_mask = sitk.DiscreteGaussian(rxs_mask, 3.0)

## Binarize the smoothed mask using a threshold of 0.5
bin_sm_rxs_mask = sitk.BinaryThreshold(smoothed_rxs_mask, lowerThreshold=0.5, upperThreshold=1.0, insideValue=1, outsideValue=0)
## make inverse of that mask
inv_bin_sm_rxs_mask = sitk.BinaryThreshold(smoothed_rxs_mask, lowerThreshold=0.5, upperThreshold=1.0, insideValue=0, outsideValue=1)


## Save the binarized smoothed upsampled mask
#sitk.WriteImage(bin_sm_rxs_mask, "binarized_mask.nii.gz")

## get signed distance transform of upsampled mask
## suggested syntax - not sure of this metric, check this
sdt_rxs_mask = sitk.SignedMaurerDistanceMap(bin_sm_rxs_mask, squaredDistance=False, useImageSpacing=True)
sdt_inv_rxs_mask = sitk.SignedMaurerDistanceMap(inv_bin_sm_rxs_mask, squaredDistance=False, useImageSpacing=True)

# Save the distance transform - not needed? 
#sitk.WriteImage(dist_img, 'distance_transform.nii.gz')


## get positive values of signed distance transform inside brain ;

# Load the image
sdt_rxs_mask_data = sitk.GetArrayFromImage(sdt_rxs_mask)

## multiply it by -1 somehow (does this work?)
sdt_rxs_mask_data_by_minus_one = sdt_rxs_mask_data * -1 

# Threshold the image (this is thresholding it as a numpy array if I'm understanding correctly)
thresholded_data = sitk.BinaryThreshold(sdt_rxs_mask_data_by_minus_one, lowerThreshold=0, upperThreshold=sitk.sitkInf, insideValue=sdt_rxs_mask_data_by_minus_one, outsideValue=0)

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

### -------------------------------------------------------------------------------
# 
#  
### and then multiplying it by all the structural images (is this better done as np arrays or as sitk image objects? )


### then would be calls to mricrogl via a python script that would get created? 


### then put screenshots in a powerpoint.
