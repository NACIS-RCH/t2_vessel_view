#!/bin/python3

import numpy as np
import nibabel as nb
import os
from scipy.spatial import ConvexHull
from scipy.spatial import Delaunay
import argparse
import SimpleITK as sitk
from . import dir_structure

test_data_dir = 'tests/test_data'
test_output_dir = 'tests/test_data/test_outputs'
mask_path = os.path.join(test_data_dir, "bet_n4_rFLAIR_0.5_mask.nii.gz")
### This script intakes a brain mask, and generates a convex hull (3d shape connecting all the outermost points on the mask, like wrapping a present). It does this by splitting the mask into 2d slices and performing hull calculations on all the non-zero voxels (which are turned into individual point coordinates) on each slice, and then joining all the 2d hulls to make a 3d one. This script was made for the purpose of modifying brain masks that don't capture the sagittal sinus. This will usually be masks generated from a 3D FLAIR. This is for the purpose of displaying 3d images where the sagittal sinus is relevant to surgical planning; i.e., where pathology or surgical view is near the midline of the brain. The output hull masks do not work as well for lateral structures, the original FLAIR based mask will probably be more appropriate in this case. There is also a 'hop hull' version generated, which removes sections of the hull mask that include eye and neck tissue. However, this will also remove the most posterior/inferior part of the sagittal sinus, so is not useful for occipital views.  


def make_hull_mask(regular_mask):

    #print(f'Loading mask {mask}')
    ## import nifti file with nibabel
    ## get path to file
    #nii_path = os.path.join(mask_dir,mask)
    
    ## load file with nibabel
    #mask_nii = nb.load(nii_path)
    mask_nii = nb.load(regular_mask)
    
    ## get the actual data from the file in an array, which is then input into the hull function as an image. It will be turned into a numpy array.
    mask_nii_data = mask_nii.get_fdata()
    
    #print(f'Making hull mask for {mask}')
    #hull_image = flood_fill_hull(mask_nii_data)[0]
    
    ## 'where' gets all the voxels that are nonzero in the image
    points = np.transpose(np.where(mask_nii_data))
    hull = ConvexHull(points)
    deln = Delaunay(points[hull.vertices])
    idx = np.stack(np.indices(mask_nii_data.shape), axis = -1)
    out_idx = np.nonzero(deln.find_simplex(idx) + 1)
    hull_image = np.zeros(mask_nii_data.shape)
    hull_image[out_idx] = 1
    
    ## save nifti output hull image
    out_nii=nb.Nifti1Image(hull_image, mask_nii.affine, mask_nii.header).to_filename(os.path.join(dir_structure.processing_mask_dir, "hull_mask.nii.gz"))
    ## if return code not zero, print saved image in location.
    
    
    ## make new array to do shadow operations on. this removes the underneath part of the hull with eyes and neck tissue etc.
    shadow = mask_nii_data.copy()
    shadow_x_size, shadow_y_size, shadow_z_size = shadow.shape
    
    #print(f'Making shadow image for {mask}')
    ## this isolates all the voxels that are in the hull mask but underneath the brain mask, and makes a new image with intensity 2 in that region
    for x in range(shadow_x_size):
        for y in range(shadow_y_size):
            for z in range(shadow_z_size):
                #print(x,y,z)
                if shadow[x,y,z] == 0:
                    shadow[x,y,z] = 2
                else:  
                    break
                  
    shadow[shadow==1]=0
    
    #print(f'Making top hull mask for {mask} by removing underneath sections of hull mask such as eye and neck tissue.')
    mask_top_hull = hull_image + shadow
    
    mask_top_hull[mask_top_hull==3]=0
    mask_top_hull[mask_top_hull==2]=0
    
    #    out_shadow_nii=nb.Nifti1Image(shadow, mask_nii.affine, mask_nii.header).to_filename(os.path.join(mask_dir, f'shadow_{mask}'))
    
    out_top_hull_nii=nb.Nifti1Image(mask_top_hull, mask_nii.affine, mask_nii.header).to_filename(os.path.join(dir_structure.processing_mask_dir, "hull_top_mask.nii.gz"))
    
    ### add section to remove sides
    
    top_hull_img = sitk.ReadImage(os.path.join(dir_structure.processing_mask_dir, "hull_top_mask.nii.gz"))
    
    ## scaling factors
    x_scale = 1.3
    y_scale = 1.0
    z_scale = 0.8
    
    ## make an affine transform
    affine_transform = sitk.AffineTransform(3)
    affine_transform.Scale([x_scale, y_scale, z_scale])
    
    ### set the output origin to the same as the input mask
    #affine_transform.SetOutputOrigin(top_hull_img.GetOrigin())
    
    ## resample using the affine transform
    squished_mask = sitk.Resample(top_hull_img, top_hull_img.GetSize(), affine_transform, sitk.sitkNearestNeighbor, top_hull_img.GetOrigin(), top_hull_img.GetSpacing(), top_hull_img.GetDirection(), 0.0, top_hull_img.GetPixelID())
    sitk.WriteImage(squished_mask, os.path.join(dir_structure.processing_mask_dir, "test_squished_mask.nii.gz"))
    
    ## another example 
    ## main_image_crop_n4_rs = sitk.Resample(main_image_crop, new_size, sitk.Transform(), sitk.sitkLinear, main_image_crop.GetOrigin(), new_spacing, main_image_crop.GetDirection(), 0.0, main_image_crop.GetPixelID())
    
    squished_multiplied_mask = sitk.Multiply(top_hull_img, squished_mask)
    sitk.WriteImage(squished_multiplied_mask, os.path.join(dir_structure.processing_mask_dir, "squished_multiplied_mask.nii.gz"))
    
    squished_multiplied_mask_float = sitk.Cast(squished_multiplied_mask, sitk.sitkFloat32)
    mask_nii_sitk = sitk.ReadImage(mask_path)
    mask_nii_sitk_float = sitk.Cast(mask_nii_sitk, sitk.sitkFloat32)
    
    test_final_hull_mask = sitk.Add(squished_multiplied_mask_float, mask_nii_sitk_float)
    test_final_hull_mask_bin = test_final_hull_mask > 0
    test_final_hull_mask_bin_float = sitk.Cast(test_final_hull_mask_bin, sitk.sitkFloat32)
    
    sitk.WriteImage(test_final_hull_mask_bin_float, os.path.join(dir_structure.processing_mask_dir, "test_final_hull_mask.nii.gz"))
    
    return out_top_hull_nii, test_final_hull_mask


