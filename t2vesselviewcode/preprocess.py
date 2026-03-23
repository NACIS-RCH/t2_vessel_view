import os
import SimpleITK as sitk
import nipype.interfaces.fsl as fsl
import ants
import glob
import shutil
import nibabel as nib
import numpy as np

from . import utils
from . import dir_structure
from . import commandline

TEST_MODE = os.environ.get('T2VV_TEST_MODE') == '1'

# ------------------------ Main functions ------------------------

def get_preprocessed_dir(image_type):
    """
    Returns the correct preprocessed directory for a given image type string.
    """
    t = image_type.lower()
    if t == "flair":
        return dir_structure.processed_flair_dir
    elif t == "t1":
        return dir_structure.processed_t1_dir
    elif t == "t2_tra":
        return dir_structure.processed_t2_tra_dir
    elif t == "t2_cor":
        return dir_structure.processed_t2_cor_dir
    elif t == "t2_sag":
        return dir_structure.processed_t2_sag_dir
    elif t == "t2_3d":
        return dir_structure.processed_t2_3d_dir
    elif t.startswith("t2"):
        return dir_structure.processed_t2_dir
    else:
        return utils.get_output_dir()

def convert_and_reorient(raw_input_file, input_filetype_string):
    """
    Converts DICOM to nii.gz if needed and reorients to standard orientation
    
    Parameters
    ----------
    
    raw_input_file : string
        Path to raw input file (DICOM or NIfTI)
        
    Returns
    -------
    String
        Path to converted reoriented file
    
    """
    if not raw_input_file:
        print(f"[INFO] No input provided for {input_filetype_string}, skipping.")
        return None
    
    output_dir = get_preprocessed_dir(input_filetype_string)
    print(f"[INFO] Converting DICOM to NIfTI for {input_filetype_string}")
    # Check if input is DICOM and convert to NIfTI if needed
    if os.path.isdir(raw_input_file) or raw_input_file.lower().endswith('.dcm'):
        # DICOM conversion
        try:
            reader = sitk.ImageSeriesReader()
            
            # If the input is a directory, get all DICOM files in it
            # If it's a single file, just use that file
            if os.path.isdir(raw_input_file):
                dicom_names = reader.GetGDCMSeriesFileNames(raw_input_file)
            else:
                dicom_names = [raw_input_file]
            
            # Set the file names and read the image
            reader.SetFileNames(dicom_names)
            image = reader.Execute()
            
            # Save as temporary NIfTI for processing
            # Ensure the output directory exists (avoid write failures)
            os.makedirs(output_dir, exist_ok=True)
            temp_nifti_path = os.path.join(output_dir, f"{input_filetype_string}_temp.nii.gz")
            sitk.WriteImage(image, temp_nifti_path)
            
            # Use the converted file for reorientation
            file_for_reorient = temp_nifti_path
            
        except (IOError, RuntimeError) as e:
            raise RuntimeError(f"Failed to convert DICOM to NIfTI: {str(e)}")
    else:
        # Already NIfTI, use as-is
        file_for_reorient = raw_input_file
    
    print(f"[INFO] Reorienting {input_filetype_string} image to standard RAS orientation")
    reoriented_im_path = os.path.join(output_dir, f"{input_filetype_string}_ro.nii.gz")
    # Create output directory if it does not exist
    os.makedirs(output_dir, exist_ok=True)

    # Load with nibabel, 
    img = nib.load(file_for_reorient)
    # Record the input axis codes (e.g., ('L','P','I')) for logging and QC
    pre_ax = nib.aff2axcodes(img.affine)
    try:
        # Standardise to RAS orientation (axis permutes/sign flips only; no interpolation)
        img_ras = nib.as_closest_canonical(img)
    except Exception as e:
        # Fail clearly if standardisation cannot be performed
        raise RuntimeError(f"[ERROR] Standardisation failure for {input_filetype_string}: {e}")
    # Check the axis codes after standardisation
    post_ax = nib.aff2axcodes(img_ras.affine)
    print(f"[INFO] {input_filetype_string} orientation pre→post: {pre_ax} → {post_ax}")

    # Enforce that output is RAS; this is our single canonical standard
    if post_ax != ('R', 'A', 'S'):
        raise ValueError(f"[ERROR] Expected RAS after standardisation for {input_filetype_string}, got {post_ax}")

    # Ensure sform and qform explicitly match the RAS affine (prevents downstream ambiguity)
    hdr = img_ras.header.copy()
    nib.Nifti1Header.set_sform(hdr, img_ras.affine, code=1)
    nib.Nifti1Header.set_qform(hdr, img_ras.affine, code=1)

    # Write out as float32 to keep types consistent for subsequent tools
    data = img_ras.get_fdata(dtype=np.float32)
    nib.Nifti1Image(data, img_ras.affine, header=hdr).to_filename(reoriented_im_path)

    return reoriented_im_path

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
    output_dir = get_preprocessed_dir("t1")
    if TEST_MODE:
        # Return dummy data for testing
        dummy_image = sitk.Image([100, 100, 100], sitk.sitkFloat32)
        dummy_path = os.path.join(output_dir, "Preprocessed_main_image.nii.gz")
        sitk.WriteImage(dummy_image, dummy_path)
        return dummy_image, dummy_path
    
    print("[INFO] Cropping main image using FSL RobustFOV")
    
    ## crop using fsl robustfov in nipype. 
    ## this still outputs a "to_ROI" suffix file, find how to stop that
    crop = fsl.RobustFOV()
    crop.inputs.in_file = input_t1
    crop.inputs.brainsize = 160
    ## this doesn't work but there's no documentation for an alternative
    #crop.inputs.generate_report = False
    crop.inputs.out_roi = os.path.join(output_dir, "T1_crop.nii.gz")
    res = crop.run()
    
    ## sitk n4 (THIS WORKS)
    main_image_crop = sitk.ReadImage(os.path.join(output_dir, "T1_crop.nii.gz"))
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
    
    main_image_crop_n4_rs_resc_path = os.path.join(output_dir, "Preprocessed_main_image.nii.gz")
    ## need to write this out partly because ANTS needs it 
    sitk.WriteImage(main_image_crop_n4_rs_resc, main_image_crop_n4_rs_resc_path)
    utils.write_debug_image(main_image_crop_n4_rs_resc, "main_image_crop_n4_rs_resc.nii.gz", output_dir)
    
    return main_image_crop_n4_rs_resc, main_image_crop_n4_rs_resc_path

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
    Tuple[str, SimpleITK.Image]
        Preprocessed image path and the SimpleITK image object
    """
    output_dir = get_preprocessed_dir(input_imagetype_string)
    print(f"[INFO] Applying N4 bias correction to {input_imagetype_string}")
    if TEST_MODE:
        # Return dummy data for testing
        dummy_path = os.path.join(output_dir, f"{input_imagetype_string}_registered.nii.gz")
        dummy_image = sitk.Image([100, 100, 100], sitk.sitkFloat32)
        sitk.WriteImage(dummy_image, dummy_path)
        return dummy_path, dummy_image
    
    ## load im
    im_raw = sitk.ReadImage(input_raw)
    im_raw_float = sitk.Cast(im_raw, sitk.sitkFloat32)
        
    ## sitk n4 im
    im_n4 = sitk.N4BiasFieldCorrection(im_raw_float)
    im_n4_path = os.path.join(output_dir, f"{input_imagetype_string}_n4.nii.gz") 
    sitk.WriteImage(im_n4, im_n4_path)
    utils.write_debug_image(im_n4, f"{input_imagetype_string}_n4_debug.nii.gz", output_dir)
    
    ## register to t1 using ants. have to load as new image
    im_moving_image = utils.read_ants_image(im_n4_path)
    
    ## load preprocessed t1
    t1_fixed_image = utils.read_ants_image(preprocessed_main_image_path)
    
    print(f"[INFO] Affine registering {input_imagetype_string} image to preprocessed T1")
    
    ## affine registration
    im_to_t1_registration = ants.registration (fixed = t1_fixed_image, moving = im_moving_image, type_of_transform = "Affine")
    
    ## apply transform
    registered_im = ants.apply_transforms(fixed = t1_fixed_image, moving = im_moving_image, transformlist = im_to_t1_registration["fwdtransforms"])
    
    # save registered im (this could be a temp file, see how that works)
    registered_im_path = os.path.join(output_dir, f"registered_{input_imagetype_string}.nii.gz")
    ants.image_write(registered_im, registered_im_path)
    
    
    ## rescale image intensities. needs to have sitk image loaded not ants image
    sitk_registered_im = sitk.ReadImage(registered_im_path)
    sitk_registered_im_float = sitk.Cast(sitk_registered_im, sitk.sitkFloat32)
    
    ## rescale intensity
    registered_im_resc = sitk.RescaleIntensity(sitk_registered_im_float, outputMinimum = 0, outputMaximum = 1000)
    
    preprocessed_im_path = os.path.join(output_dir, f"Preprocessed_{input_imagetype_string}.nii.gz")
    sitk.WriteImage(registered_im_resc, preprocessed_im_path)
    
    return preprocessed_im_path, registered_im_resc

def postprocess_t2(preprocessed_t2_input_path, preprocessed_imagetype_string):
    """
    Postprocesses T2 images by inverting intensity and squaring.
    
    Parameters
    ----------
    
    preprocessed_t2_path : string
        Path to preprocessed T2 image
        
    preprocessed_imagetype_string : string
        String describing image type e.g., "t2_sag"
        
    Returns
    -------
    sitk image object
        Postprocessed T2 image 
    
    """
    output_dir = get_preprocessed_dir(preprocessed_imagetype_string)
    ## load preprocessed t2
    t2_pre = sitk.ReadImage(preprocessed_t2_input_path)
    
    t2_inv = sitk.InvertIntensity(t2_pre)
    utils.write_debug_image(t2_inv, f"inv_{preprocessed_imagetype_string}.nii.gz", output_dir)
    
    t2_inv_rescale = sitk.RescaleIntensity(t2_inv, outputMinimum = 0, outputMaximum = 1000)
    utils.write_debug_image(t2_inv_rescale, f"inv_rescale_{preprocessed_imagetype_string}.nii.gz", output_dir)
    
    t2_inv_sqr = sitk.Pow(t2_inv_rescale, 2)
    utils.write_debug_image(t2_inv_sqr, f"inv_sqr_{preprocessed_imagetype_string}.nii.gz", output_dir)

    t2_inv_re_rescale = sitk.RescaleIntensity(t2_inv_sqr, outputMinimum = 0, outputMaximum = 1000)
    utils.write_debug_image(t2_inv_re_rescale, f"inv_sqr_re_rescale_{preprocessed_imagetype_string}.nii.gz", output_dir)
    
    return t2_inv_re_rescale
    