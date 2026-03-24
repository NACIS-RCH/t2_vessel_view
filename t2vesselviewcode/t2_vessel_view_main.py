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
from . import png_postprocess


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

    # Support one or two sagittal T2 acquisitions (generic, left, right)
    reoriented_t2_sag_paths = []
    if commandline.args.t2_sag:
        reoriented_t2_sag_paths.append(
            preprocess.convert_and_reorient(commandline.args.t2_sag, "t2_sag")
        )
    if getattr(commandline.args, 't2_sag_left', None):
        reoriented_t2_sag_paths.append(
            preprocess.convert_and_reorient(commandline.args.t2_sag_left, "t2_sag_left")
        )
    if getattr(commandline.args, 't2_sag_right', None):
        reoriented_t2_sag_paths.append(
            preprocess.convert_and_reorient(commandline.args.t2_sag_right, "t2_sag_right")
        )

    reoriented_t2_cor_path = None
    if commandline.args.t2_cor:
        reoriented_t2_cor_path = preprocess.convert_and_reorient(commandline.args.t2_cor, "t2_cor")

    reoriented_t2_tra_path = None
    if commandline.args.t2_tra:
        reoriented_t2_tra_path = preprocess.convert_and_reorient(commandline.args.t2_tra, "t2_tra")

    reoriented_t2_3d_path = None
    if commandline.args.t2_3d:
        reoriented_t2_3d_path = preprocess.convert_and_reorient(commandline.args.t2_3d, "t2_3d")

    ## preprocess t1    
    preprocessed_main_image, preprocessed_main_image_path = preprocess.preprocess_main_image(reoriented_main_image_path)

    ## preprocess flair and register to preprocessed t1
    preprocessed_flair = None
    preprocessed_flair_img = None
    if reoriented_flair_path:
        preprocessed_flair, preprocessed_flair_img = preprocess.preprocess_n4_reg(reoriented_flair_path, "flair", preprocessed_main_image_path)

    ## preprocess t2 images
    preprocessed_t2_sag_paths = []
    preprocessed_t2_sag_imgs = []
    for reor_path in reoriented_t2_sag_paths:
        # Use the imagetype string embedded in the filename tag to keep outputs distinct
        # If reor_path name contains 't2_sag_left' or 't2_sag_right', preserve it; else default to 't2_sag'
        tag = 't2_sag_left' if 't2_sag_left' in os.path.basename(reor_path) else (
              't2_sag_right' if 't2_sag_right' in os.path.basename(reor_path) else 't2_sag')
        pp_path, pp_img = preprocess.preprocess_n4_reg(reor_path, tag, preprocessed_main_image_path)
        preprocessed_t2_sag_paths.append(pp_path)
        preprocessed_t2_sag_imgs.append(pp_img)

    preprocessed_t2_cor_path = None
    preprocessed_t2_cor_img = None
    if reoriented_t2_cor_path:
        preprocessed_t2_cor_path, preprocessed_t2_cor_img = preprocess.preprocess_n4_reg(reoriented_t2_cor_path, "t2_cor", preprocessed_main_image_path)

    preprocessed_t2_tra_path = None
    preprocessed_t2_tra_img = None
    if reoriented_t2_tra_path:
        preprocessed_t2_tra_path, preprocessed_t2_tra_img = preprocess.preprocess_n4_reg(reoriented_t2_tra_path, "t2_tra", preprocessed_main_image_path)

    preprocessed_t2_3d_path = None
    preprocessed_t2_3d_img = None
    if reoriented_t2_3d_path:
        preprocessed_t2_3d_path, preprocessed_t2_3d_img = preprocess.preprocess_n4_reg(reoriented_t2_3d_path, "t2_3d", preprocessed_main_image_path)

    ## postprocess t2 images
    # Keep (image, tag) pairs so tags propagate to eroded filenames
    postprocessed_t2_sag_items = []
    for pp_path in preprocessed_t2_sag_paths:
        tag = 't2_sag_left' if 't2_sag_left' in os.path.basename(pp_path) else (
              't2_sag_right' if 't2_sag_right' in os.path.basename(pp_path) else 't2_sag')
        img_obj = preprocess.postprocess_t2(pp_path, tag)
        postprocessed_t2_sag_items.append((img_obj, tag))

    postprocessed_t2_tra_image = None
    if preprocessed_t2_tra_path:
        postprocessed_t2_tra_image = preprocess.postprocess_t2(preprocessed_t2_tra_path, "t2_tra")

    postprocessed_t2_cor_image = None
    if preprocessed_t2_cor_path:
        postprocessed_t2_cor_image = preprocess.postprocess_t2(preprocessed_t2_cor_path, "t2_cor")

    postprocessed_t2_3d_image = None
    if preprocessed_t2_3d_path:
        postprocessed_t2_3d_image = preprocess.postprocess_t2(preprocessed_t2_3d_path, "t2_3d")

    ## generate automatic mask for QA (and for processing if no user mask is supplied)
    auto_method = getattr(commandline.args, "auto_mask_method", "bet")
    mask_source_path = preprocessed_flair or preprocessed_main_image_path
    auto_mask_path = ""
    auto_mask_exists = False
    auto_qa_filename = f"QA_mask_overlay_auto_mask_{auto_method}.png"

    try:
        if auto_method == "watershed":
            if not preprocessed_flair:
                raise ValueError("Watershed mask method requires a preprocessed FLAIR image.")
            auto_mask_path = masking.generate_mask_watershed(preprocessed_flair)
        else:
            auto_mask_path = masking.generate_mask(mask_source_path)
        auto_mask_exists = os.path.exists(auto_mask_path)
    except Exception as e:
        if commandline.args.user_mask:
            print(f"[WARNING] Automatic mask generation ({auto_method}) failed: {e}")
            auto_mask_exists = False
        else:
            print(f"[ERROR] Automatic mask generation ({auto_method}) failed: {e}")
            sys.exit(1)

    if not commandline.args.user_mask:
        print(
            "[INFO] No user-provided mask was supplied. This is the default. "
            f"The automatically generated {auto_method} mask will be used for processing. "
            "If manual correction of the mask is needed, or if you have a better mask than the pipeline generates, rerun the pipeline and input your preferred mask  with --user_mask."
        )
        if not auto_mask_exists:
            print(
                f"[ERROR] {auto_method} mask generation failed: no automatic mask file was found. "
                "You could try providing a user-generated mask with --user_mask and rerun."
            )
            sys.exit(1)
        mask_to_input = auto_mask_path
        try:
            auto_mask_img_for_qa = sitk.ReadImage(auto_mask_path)
        except Exception as e:
            print(f"[ERROR] Could not read generated {auto_method} mask for processing: {e}")
            sys.exit(1)
        utils.save_qa_mask_overlay(
            main_image=preprocessed_main_image,
            mask_image=auto_mask_img_for_qa,
            filename=auto_qa_filename
        )
    else:
        if not os.path.exists(commandline.args.user_mask):
            raise FileNotFoundError(f"User-provided mask not found: {commandline.args.user_mask}")
        print(
            "[INFO] User-provided mask detected. "
            "The user mask will be used for processing. "
            f"An automatic {auto_method} mask will also be generated for QA comparison."
        )
        mask_to_input = commandline.args.user_mask

        if auto_mask_exists:
            try:
                auto_mask_img_for_qa = sitk.ReadImage(auto_mask_path)
                utils.save_qa_mask_overlay(
                    main_image=preprocessed_main_image,
                    mask_image=auto_mask_img_for_qa,
                    filename=auto_qa_filename
                )
            except Exception as e:
                print(f"[WARNING] Could not generate QA overlay for automatic {auto_method} mask: {e}")
        else:
            print(f"[WARNING] Automatic {auto_method} mask was not created. Continuing with user-provided mask only.")

        user_mask_img_for_qa = sitk.ReadImage(mask_to_input)
        utils.save_qa_mask_overlay(
            main_image=preprocessed_main_image,
            mask_image=user_mask_img_for_qa,
            filename="QA_mask_overlay_user_mask.png"
        )
    
    ## process mask
    sdt_all_plus_2 = masking.main_mask_operations(mask_to_input)

    ## erode mask
    eroded_masks_dict, zero_padded_erode_depths_list = masking.mask_erosions(sdt_all_plus_2)

    ## erode nifti
    if eroded_masks_dict and zero_padded_erode_depths_list:
        if preprocessed_main_image:
            res_t1 = masking.multiply_masks_by_images(preprocessed_main_image, "t1", dir_structure.eroded_nifti_t1_dir, zero_padded_erode_depths_list, eroded_masks_dict)
        # Handle one or more sagittal T2s with explicit tags
        for t2s_img, tag in postprocessed_t2_sag_items:
            _ = masking.multiply_masks_by_images(t2s_img, tag, dir_structure.eroded_nifti_t2_sag_dir, zero_padded_erode_depths_list, eroded_masks_dict)
        if postprocessed_t2_cor_image:
            res_t2_cor = masking.multiply_masks_by_images(postprocessed_t2_cor_image, "t2_cor", dir_structure.eroded_nifti_t2_cor_dir, zero_padded_erode_depths_list, eroded_masks_dict)
        if postprocessed_t2_tra_image:
            res_t2_tra = masking.multiply_masks_by_images(postprocessed_t2_tra_image, "t2_tra", dir_structure.eroded_nifti_t2_tra_dir, zero_padded_erode_depths_list, eroded_masks_dict)
        if preprocessed_flair_img:
            res_flair = masking.multiply_masks_by_images(preprocessed_flair_img, "flair", dir_structure.eroded_nifti_flair_dir, zero_padded_erode_depths_list, eroded_masks_dict)
        if postprocessed_t2_3d_image:
            res_t2_3d = masking.multiply_masks_by_images(postprocessed_t2_3d_image, "t2_3d", dir_structure.eroded_nifti_t2_3d_dir, zero_padded_erode_depths_list, eroded_masks_dict)

    # --- Volume rendering and PNG output ---
    # Resolve MRIcroGL executable (allow override via env var)
    mricrogl_exec = os.environ.get('T2VV_MRICROGL_PATH', "/Applications/MRIcroGL.app/Contents/MacOS/MRIcroGL")
    # T1
    t1_eroded_files = glob.glob(os.path.join(dir_structure.eroded_nifti_t1_dir, '*eroded*t1*nii.gz'))
    if t1_eroded_files:
        # Compute a robust window from the series (use 2nd/80th percentiles for T1)
        t1_window = volume_rendering.compute_series_window(t1_eroded_files, low_pct=2.0, high_pct=80.0)
        # volume_rendering.render_volume_and_save_pngs_pyvista(
        #     t1_eroded_files,
        #     dir_structure.renders_t1_dir
        # )
        volume_rendering.render_volume_and_save_pngs_mricrogl(
            t1_eroded_files,
            dir_structure.renders_t1_dir,
            angles=[[90,0,'left'],[270,0,'right'],[180,0,'anterior'],[0,0,'posterior'],[0,90,'superior'],[180,-90,'inferior'],
                    [270,180,'surg_left_lat'],[90,180,'surg_right_lat'],[300,175,'surg_left_ato'],[60,175,'surg_right_ato']],
            window=t1_window,
            image_size=(1200,1200),
            mricrogl_path=mricrogl_exec,
            template_filename="mricrogl_T1_screenshot_test.py",
            camera_distance='auto'
        )
        # Post-process: crop, L/R annotate, stitch, and export PPTX for T1 overview
        try:
            png_postprocess.run_preset_t1_overview_per_depth(
                add_orientation_labels=True,
                background_rgb=[0,0,0],
                threshold=2,
                pptx_name="T1_overview"
            )
        except Exception as e:
            print(f"[WARNING] PNG post-processing (T1 overview) skipped: {e}")
    # T2 Sagittal
    t2_sag_eroded_files = glob.glob(os.path.join(dir_structure.eroded_nifti_t2_sag_dir, '*eroded*t2_sag*nii.gz'))
    if t2_sag_eroded_files:
        t2_sag_window = volume_rendering.compute_series_window(t2_sag_eroded_files, low_pct=0.3, high_pct=99.75)
        # Split into left/right/generic lists by filename tag
        t2_sag_left_files = [p for p in t2_sag_eroded_files if 't2_sag_left' in os.path.basename(p).lower()]
        t2_sag_right_files = [p for p in t2_sag_eroded_files if 't2_sag_right' in os.path.basename(p).lower()]
        t2_sag_generic_files = [p for p in t2_sag_eroded_files if ('t2_sag_left' not in os.path.basename(p).lower() and 't2_sag_right' not in os.path.basename(p).lower())]

        # Define angle subsets
        left_angles = [[90,0,'left'], [270,180,'surg_left_lat'], [300,175,'surg_left_ato']]
        right_angles = [[270,0,'right'], [90,180,'surg_right_lat'], [60,175,'surg_right_ato']]

        # Choose file lists per subset with sensible fallbacks
        files_for_left = t2_sag_left_files or t2_sag_generic_files or t2_sag_right_files
        files_for_right = t2_sag_right_files or t2_sag_generic_files or t2_sag_left_files

        # Render left subset if any files available
        if files_for_left:
            volume_rendering.render_volume_and_save_pngs_mricrogl(
                files_for_left,
                os.path.join(dir_structure.renders_t2_dir, 'T2_Sag_3D_renders'),
                angles=left_angles,
                window=t2_sag_window,
                image_size=(1200,1200),
                mricrogl_path=mricrogl_exec,
                template_filename="mricrogl_T1_screenshot_test.py",
                camera_distance='auto'
            )
        # Render right subset if any files available
        if files_for_right:
            volume_rendering.render_volume_and_save_pngs_mricrogl(
                files_for_right,
                os.path.join(dir_structure.renders_t2_dir, 'T2_Sag_3D_renders'),
                angles=right_angles,
                window=t2_sag_window,
                image_size=(1200,1200),
                mricrogl_path=mricrogl_exec,
                template_filename="mricrogl_T1_screenshot_test.py",
                camera_distance='auto'
            )
    # T2 Coronal
    t2_cor_eroded_files = glob.glob(os.path.join(dir_structure.eroded_nifti_t2_cor_dir, '*eroded*t2_cor*nii.gz'))
    if t2_cor_eroded_files:
        t2_cor_window = volume_rendering.compute_series_window(t2_cor_eroded_files, low_pct=0.3, high_pct=99.75)
        # volume_rendering.render_volume_and_save_pngs_pyvista(
        #     t2_cor_eroded_files,
        #     os.path.join(dir_structure.renders_t2_dir, 'T2_Cor_3D_renders')
        # )
        volume_rendering.render_volume_and_save_pngs_mricrogl(
            t2_cor_eroded_files,
            os.path.join(dir_structure.renders_t2_dir, 'T2_Cor_3D_renders'),
            angles=[[90,0,'left'],[270,0,'right'],[180,0,'anterior'],[0,0,'posterior'],[0,90,'superior'],[180,-90,'inferior'],
                    [270,180,'surg_left_lat'],[90,180,'surg_right_lat'],[300,175,'surg_left_ato'],[60,175,'surg_right_ato']],
            window=t2_cor_window,
            image_size=(1200,1200),
            mricrogl_path=mricrogl_exec,
            template_filename="mricrogl_T1_screenshot_test.py",
            camera_distance='auto'
        )
    # T2 Transverse
    t2_tra_eroded_files = glob.glob(os.path.join(dir_structure.eroded_nifti_t2_tra_dir, '*eroded*t2_tra*nii.gz'))
    if t2_tra_eroded_files:
        t2_tra_window = volume_rendering.compute_series_window(t2_tra_eroded_files, low_pct=0.3, high_pct=99.75)
        # volume_rendering.render_volume_and_save_pngs_pyvista(
        #     t2_tra_eroded_files,
        #     os.path.join(dir_structure.renders_t2_dir, 'T2_Tra_3D_renders')
        # )
        volume_rendering.render_volume_and_save_pngs_mricrogl(
            t2_tra_eroded_files,
            os.path.join(dir_structure.renders_t2_dir, 'T2_Tra_3D_renders'),
            angles=[[90,0,'left'],[270,0,'right'],[180,0,'anterior'],[0,0,'posterior'],[0,90,'superior'],[180,-90,'inferior'],
                    [270,180,'surg_left_lat'],[90,180,'surg_right_lat'],[300,175,'surg_left_ato'],[60,175,'surg_right_ato']],
            window=t2_tra_window,
            image_size=(1200,1200),
            mricrogl_path=mricrogl_exec,
            template_filename="mricrogl_T1_screenshot_test.py",
            camera_distance='auto'
        )
    # T2 3D
    t2_3d_eroded_files = glob.glob(os.path.join(dir_structure.eroded_nifti_t2_3d_dir, '*eroded*t2_3d*nii.gz'))
    if t2_3d_eroded_files:
        t2_3d_window = volume_rendering.compute_series_window(t2_3d_eroded_files, low_pct=0.3, high_pct=99.75)
        # volume_rendering.render_volume_and_save_pngs_pyvista(
        #     t2_3d_eroded_files,
        #     os.path.join(dir_structure.renders_t2_dir, 'T2_3D_3D_renders')
        # )
        volume_rendering.render_volume_and_save_pngs_mricrogl(
            t2_3d_eroded_files,
            os.path.join(dir_structure.renders_t2_dir, 'T2_3D_3D_renders'),
            angles=[[90,0,'left'],[270,0,'right'],[180,0,'anterior'],[0,0,'posterior'],[0,90,'superior'],[180,-90,'inferior'],
                    [270,180,'surg_left_lat'],[90,180,'surg_right_lat'],[300,175,'surg_left_ato'],[60,175,'surg_right_ato']],
            window=t2_3d_window,
            image_size=(1200,1200),
            mricrogl_path=mricrogl_exec,
            template_filename="mricrogl_T1_screenshot_test.py",
            camera_distance='auto'
        )
    # FLAIR
    flair_eroded_files = glob.glob(os.path.join(dir_structure.eroded_nifti_flair_dir, '*eroded*flair*nii.gz'))
    if flair_eroded_files:
        flair_window = volume_rendering.compute_series_window(flair_eroded_files, low_pct=7.5, high_pct=99.99)
        # volume_rendering.render_volume_and_save_pngs_pyvista(
        #     flair_eroded_files,
        #     os.path.join(dir_structure.renders_dir, 'FLAIR_3D_renders')
        # )
        volume_rendering.render_volume_and_save_pngs_mricrogl(
            flair_eroded_files,
            os.path.join(dir_structure.renders_dir, 'FLAIR_3D_renders'),
            angles=[[90,0,'left'],[270,0,'right'],[180,0,'anterior'],[0,0,'posterior'],[0,90,'superior'],[180,-90,'inferior'],
                    [270,180,'surg_left_lat'],[90,180,'surg_right_lat'],[300,175,'surg_left_ato'],[60,175,'surg_right_ato']],
            window=flair_window,
            image_size=(1200,1200),
            mricrogl_path=mricrogl_exec,
            template_filename="mricrogl_T1_screenshot_test.py",
            camera_distance='auto'
        )

    # --- Multimodal by-angle preset (one combined PPTX) ---
    try:
        png_postprocess.run_preset_multimodal_by_angle_per_depth(
            angles=['superior','inferior','left','right','anterior','posterior'],
            add_orientation_labels=True,
            background_rgb=[0,0,0],
            threshold=2,
            pptx_name="Multimodal_overview"
        )
    except Exception as e:
        print(f"[WARNING] PNG post-processing (multimodal by angle) skipped: {e}")

    # --- T2-only overview (two-row if complete, else single-row) ---
    try:
        png_postprocess.run_preset_t2_overview_per_depth(
            add_orientation_labels=True,
            background_rgb=[0,0,0],
            threshold=2,
            pptx_name="T2_overview"
        )
    except Exception as e:
        print(f"[WARNING] PNG post-processing (T2 overview) skipped: {e}")

    # --- Multimodal surgical angles ---
    try:
        png_postprocess.run_preset_multimodal_other_angles_per_depth(
            angles=['surg_left_lat','surg_right_lat','surg_left_ato','surg_right_ato'],
            add_orientation_labels=True,
            background_rgb=[0,0,0],
            threshold=2,
            pptx_name="multimodal_overview_other_angles"
        )
    except Exception as e:
        print(f"[WARNING] PNG post-processing (multimodal other angles) skipped: {e}")

    return 0

if __name__ == "__main__":
    sys.exit(main())

