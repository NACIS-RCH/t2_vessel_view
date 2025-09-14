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
import glob

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
from . import volume_rendering


def main():
    # Validate input files before processing
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

    # Create directory structure
    dir_structure.create_directories()

    viewer = sitk.ImageViewer()
    viewer.SetFileExtension('.nii.gz')
    viewer.SetCommand('/group/deve2/local/focal/MRIcroGL/MRIcroGL_QT')
    ##viewer.Execute(file)


    ## reorient inputs to standard orientation 
    reoriented_main_image_path = preprocess.convert_and_reorient(commandline.args.t1, "t1")
    reoriented_flair_path = None
    if commandline.args.flair:
        reoriented_flair_path = preprocess.convert_and_reorient(commandline.args.flair, "flair")

    reoriented_t2_sag_path = None
    if commandline.args.t2_sag:
        reoriented_t2_sag_path = preprocess.convert_and_reorient(commandline.args.t2_sag, "t2_sag")

    reoriented_t2_cor_path = None
    if commandline.args.t2_cor:
        reoriented_t2_cor_path = preprocess.convert_and_reorient(commandline.args.t2_cor, "t2_cor")

    reoriented_t2_tra_path = None
    if commandline.args.t2_tra:
        reoriented_t2_tra_path = preprocess.convert_and_reorient(commandline.args.t2_tra, "t2_tra")

    ## preprocess t1    
    preprocessed_main_image, preprocessed_main_image_path = preprocess.preprocess_main_image(reoriented_main_image_path)

    ## preprocess flair and register to preprocessed t1
    preprocessed_flair = None
    preprocessed_flair_img = None
    if reoriented_flair_path:
        preprocessed_flair, preprocessed_flair_img = preprocess.preprocess_n4_reg(reoriented_flair_path, "flair", preprocessed_main_image_path)

    ## preprocess t2 images
    preprocessed_t2_sag_path = None
    preprocessed_t2_sag_img = None
    if reoriented_t2_sag_path:
        preprocessed_t2_sag_path, preprocessed_t2_sag_img = preprocess.preprocess_n4_reg(reoriented_t2_sag_path, "t2_sag", preprocessed_main_image_path)

    preprocessed_t2_cor_path = None
    preprocessed_t2_cor_img = None
    if reoriented_t2_cor_path:
        preprocessed_t2_cor_path, preprocessed_t2_cor_img = preprocess.preprocess_n4_reg(reoriented_t2_cor_path, "t2_cor", preprocessed_main_image_path)

    preprocessed_t2_tra_path = None
    preprocessed_t2_tra_img = None
    if reoriented_t2_tra_path:
        preprocessed_t2_tra_path, preprocessed_t2_tra_img = preprocess.preprocess_n4_reg(reoriented_t2_tra_path, "t2_tra", preprocessed_main_image_path)

    ## postprocess t2 images
    postprocessed_t2_sag_image = None
    if preprocessed_t2_sag_path:
        postprocessed_t2_sag_image = preprocess.postprocess_t2(preprocessed_t2_sag_path, "t2_sag")

    postprocessed_t2_tra_image = None
    if preprocessed_t2_tra_path:
        postprocessed_t2_tra_image = preprocess.postprocess_t2(preprocessed_t2_tra_path, "t2_tra")

    postprocessed_t2_cor_image = None
    if preprocessed_t2_cor_path:
        postprocessed_t2_cor_image = preprocess.postprocess_t2(preprocessed_t2_cor_path, "t2_cor")

    postprocessed_t2_3d_image = None
    if commandline.args.t2_3d:
        postprocessed_t2_3d_image = preprocess.postprocess_t2(commandline.args.t2_3d, "t2_3d")

    ## generate mask
    mask_to_input = masking.generate_mask(preprocessed_flair)

    # --- Save QA overlay of generated mask on main image (all axes) ---
    mask_img_for_qa = sitk.ReadImage(mask_to_input)
    utils.save_qa_mask_overlay(
        main_image=preprocessed_main_image,
        mask_image=mask_img_for_qa,
        filename="QA_mask_overlay_initial.png"
    )
    
    ## process mask
    sdt_all_plus_2 = masking.main_mask_operations(mask_to_input)

    ## erode mask
    eroded_masks_dict, zero_padded_erode_depths_list = masking.mask_erosions(sdt_all_plus_2)

    ## erode nifti
    if eroded_masks_dict and zero_padded_erode_depths_list:
        if preprocessed_main_image:
            res_t1 = masking.multiply_masks_by_images(preprocessed_main_image, "t1", dir_structure.eroded_nifti_t1_dir, zero_padded_erode_depths_list, eroded_masks_dict)
        if postprocessed_t2_sag_image:
            res_t2_sag = masking.multiply_masks_by_images(postprocessed_t2_sag_image, "t2_sag", dir_structure.eroded_nifti_t2_sag_dir, zero_padded_erode_depths_list, eroded_masks_dict)
        if postprocessed_t2_cor_image:
            res_t2_cor = masking.multiply_masks_by_images(postprocessed_t2_cor_image, "t2_cor", dir_structure.eroded_nifti_t2_cor_dir, zero_padded_erode_depths_list, eroded_masks_dict)
        if postprocessed_t2_tra_image:
            res_t2_tra = masking.multiply_masks_by_images(postprocessed_t2_tra_image, "t2_tra", dir_structure.eroded_nifti_t2_tra_dir, zero_padded_erode_depths_list, eroded_masks_dict)
        if preprocessed_flair_img:
            res_flair = masking.multiply_masks_by_images(preprocessed_flair_img, "flair", dir_structure.eroded_nifti_flair_dir, zero_padded_erode_depths_list, eroded_masks_dict)
        if postprocessed_t2_3d_image:
            res_t2_3d = masking.multiply_masks_by_images(postprocessed_t2_3d_image, "t2_3d", dir_structure.eroded_nifti_t2_3d_dir, zero_padded_erode_depths_list, eroded_masks_dict)

    # --- Volume rendering and PNG output ---
    # T1
    t1_eroded_files = glob.glob(os.path.join(dir_structure.eroded_nifti_t1_dir, '*eroded*t1*nii.gz'))
    if t1_eroded_files:
        # volume_rendering.render_volume_and_save_pngs_pyvista(
        #     t1_eroded_files,
        #     dir_structure.renders_t1_dir
        # )
        volume_rendering.render_volume_and_save_pngs_mricrogl(
            t1_eroded_files,
            dir_structure.renders_t1_dir,
            angles=[[90,0,'left'],[270,0,'right'],[180,0,'anterior'],[0,0,'posterior'],[0,90,'superior'],[180,-90,'inferior']],
            window=(0,1000),
            image_size=(1200,1200),
            mricrogl_path="/Applications/MRIcroGL.app/Contents/MacOS/MRIcroGL",
            template_filename="mricrogl_T1_screenshot_test.py"
        )
    # T2 Sagittal
    t2_sag_eroded_files = glob.glob(os.path.join(dir_structure.eroded_nifti_t2_sag_dir, '*eroded*t2_sag*nii.gz'))
    if t2_sag_eroded_files:
        # volume_rendering.render_volume_and_save_pngs_pyvista(
        #     t2_sag_eroded_files,
        #     os.path.join(dir_structure.renders_t2_dir, 'T2_Sag_3D_renders')
        # )
        volume_rendering.render_volume_and_save_pngs_mricrogl(
            t2_sag_eroded_files,
            os.path.join(dir_structure.renders_t2_dir, 'T2_Sag_3D_renders'),
            angles=[[90,0,'left'],[270,0,'right'],[180,0,'anterior'],[0,0,'posterior'],[0,90,'superior'],[180,-90,'inferior']],
            window=(0,1000),
            image_size=(1200,1200),
            mricrogl_path="/Applications/MRIcroGL.app/Contents/MacOS/MRIcroGL",
            template_filename="mricrogl_T1_screenshot_test.py"
        )
    # T2 Coronal
    t2_cor_eroded_files = glob.glob(os.path.join(dir_structure.eroded_nifti_t2_cor_dir, '*eroded*t2_cor*nii.gz'))
    if t2_cor_eroded_files:
        # volume_rendering.render_volume_and_save_pngs_pyvista(
        #     t2_cor_eroded_files,
        #     os.path.join(dir_structure.renders_t2_dir, 'T2_Cor_3D_renders')
        # )
        volume_rendering.render_volume_and_save_pngs_mricrogl(
            t2_cor_eroded_files,
            os.path.join(dir_structure.renders_t2_dir, 'T2_Cor_3D_renders'),
            angles=[[90,0,'left'],[270,0,'right'],[180,0,'anterior'],[0,0,'posterior'],[0,90,'superior'],[180,-90,'inferior']],
            window=(0,1000),
            image_size=(1200,1200),
            mricrogl_path="/Applications/MRIcroGL.app/Contents/MacOS/MRIcroGL",
            template_filename="mricrogl_T1_screenshot_test.py"
        )
    # T2 Transverse
    t2_tra_eroded_files = glob.glob(os.path.join(dir_structure.eroded_nifti_t2_tra_dir, '*eroded*t2_tra*nii.gz'))
    if t2_tra_eroded_files:
        # volume_rendering.render_volume_and_save_pngs_pyvista(
        #     t2_tra_eroded_files,
        #     os.path.join(dir_structure.renders_t2_dir, 'T2_Tra_3D_renders')
        # )
        volume_rendering.render_volume_and_save_pngs_mricrogl(
            t2_tra_eroded_files,
            os.path.join(dir_structure.renders_t2_dir, 'T2_Tra_3D_renders'),
            angles=[[90,0,'left'],[270,0,'right'],[180,0,'anterior'],[0,0,'posterior'],[0,90,'superior'],[180,-90,'inferior']],
            window=(0,1000),
            image_size=(1200,1200),
            mricrogl_path="/Applications/MRIcroGL.app/Contents/MacOS/MRIcroGL",
            template_filename="mricrogl_T1_screenshot_test.py"
        )
    # T2 3D
    t2_3d_eroded_files = glob.glob(os.path.join(dir_structure.eroded_nifti_t2_3d_dir, '*eroded*t2_3d*nii.gz'))
    if t2_3d_eroded_files:
        # volume_rendering.render_volume_and_save_pngs_pyvista(
        #     t2_3d_eroded_files,
        #     os.path.join(dir_structure.renders_t2_dir, 'T2_3D_3D_renders')
        # )
        volume_rendering.render_volume_and_save_pngs_mricrogl(
            t2_3d_eroded_files,
            os.path.join(dir_structure.renders_t2_dir, 'T2_3D_3D_renders'),
            angles=[[90,0,'left'],[270,0,'right'],[180,0,'anterior'],[0,0,'posterior'],[0,90,'superior'],[180,-90,'inferior']],
            window=(0,1000),
            image_size=(1200,1200),
            mricrogl_path="/Applications/MRIcroGL.app/Contents/MacOS/MRIcroGL",
            template_filename="mricrogl_T1_screenshot_test.py"
        )
    # FLAIR
    flair_eroded_files = glob.glob(os.path.join(dir_structure.eroded_nifti_flair_dir, '*eroded*flair*nii.gz'))
    if flair_eroded_files:
        # volume_rendering.render_volume_and_save_pngs_pyvista(
        #     flair_eroded_files,
        #     os.path.join(dir_structure.renders_dir, 'FLAIR_3D_renders')
        # )
        volume_rendering.render_volume_and_save_pngs_mricrogl(
            flair_eroded_files,
            os.path.join(dir_structure.renders_dir, 'FLAIR_3D_renders'),
            angles=[[90,0,'left'],[270,0,'right'],[180,0,'anterior'],[0,0,'posterior'],[0,90,'superior'],[180,-90,'inferior']],
            window=(0,1000),
            image_size=(1200,1200),
            mricrogl_path="/Applications/MRIcroGL.app/Contents/MacOS/MRIcroGL",
            template_filename="mricrogl_T1_screenshot_test.py"
        )

    return 0

if __name__ == "__main__":
    sys.exit(main())

