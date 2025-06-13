import os
import SimpleITK as sitk
import ants
import nipype.interfaces.fsl as fsl

from . import dir_structure
from . import utils

TEST_MODE = os.environ.get('T2VV_TEST_MODE') == '1'


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
    if TEST_MODE:
        # Return dummy data for testing
        dummy_image = sitk.Image([100, 100, 100], sitk.sitkFloat32)
        dummy_path = os.path.join(utils.test_output_dir, "Preprocessed_main_image.nii.gz")
        sitk.WriteImage(dummy_image, dummy_path)
        return dummy_image, dummy_path
    
    ## crop using fsl robustfov in nipype. 
    ## this still outputs a "to_ROI" suffix file, find how to stop that
    crop = fsl.RobustFOV()
    crop.inputs.in_file = input_t1
    crop.inputs.brainsize = 160
    ## this doesn't work but there's no documentation for an alternative
    #crop.inputs.generate_report = False
    crop.inputs.out_roi = os.path.join(utils.test_output_dir, "T1_crop.nii.gz")
    res = crop.run()
    
    ## sitk n4 (THIS WORKS)
    main_image_crop = sitk.ReadImage(os.path.join(utils.test_output_dir, "T1_crop.nii.gz"))
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
    
    main_image_crop_n4_rs_resc_path = os.path.join(utils.test_output_dir, "Preprocessed_main_image.nii.gz")
    ## need to write this out partly because ANTS needs it 
    sitk.WriteImage(main_image_crop_n4_rs_resc, main_image_crop_n4_rs_resc_path)

    utils.write_debug_image(main_image_crop_n4_rs_resc,"main_image_crop_n4_rs_resc.nii.gz")

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
    String
        Preprocessed image path
    
    """
    if TEST_MODE:
        # Return dummy data for testing
        dummy_path = os.path.join(utils.test_output_dir, f"{input_imagetype_string}_registered.nii.gz")
        dummy_image = sitk.Image([100, 100, 100], sitk.sitkFloat32)
        sitk.WriteImage(dummy_image, dummy_path)
        return dummy_path
    
    ## load im
    im_raw = sitk.ReadImage(input_raw)
    im_raw_float = sitk.Cast(im_raw, sitk.sitkFloat32)
        
    ## sitk n4 im
    im_n4 = sitk.N4BiasFieldCorrection(im_raw_float)
    im_n4_path = os.path.join(utils.test_output_dir, f"{input_imagetype_string}_n4.nii.gz") 
    sitk.WriteImage(im_n4, im_n4_path)
    utils.write_debug_image(im_n4,f"{input_imagetype_string}_n4_debug.nii.gz")
    
    ## register to t1 using ants. have to load as new image
    im_moving_image = utils.read_ants_image(im_n4_path)
    
    ## load preprocessed t1
    t1_fixed_image = utils.read_ants_image(preprocessed_main_image_path)
    
    ## affine registration
    im_to_t1_registration = ants.registration (fixed = t1_fixed_image, moving = im_moving_image, type_of_transform = "Affine")
    
    ## apply transform
    registered_im = ants.apply_transforms(fixed = t1_fixed_image, moving = im_moving_image, transformlist = im_to_t1_registration["fwdtransforms"])

    
    # save registered im (this could be a temp file, see how that works)
    registered_im_path = os.path.join(utils.test_output_dir, f"registered_{input_imagetype_string}.nii.gz")
    ants.image_write(registered_im, registered_im_path)
    
     
    ## rescale image intensities. needs to have sitk image loaded not ants image
    sitk_registered_im = sitk.ReadImage(registered_im_path)
    sitk_registered_im_float = sitk.Cast(sitk_registered_im, sitk.sitkFloat32)
    registered_im_resc = sitk.RescaleIntensity(sitk_registered_im_float, outputMinimum = 0, outputMaximum = 1000)
    
    preprocessed_im_path = os.path.join(utils.test_output_dir, f"Preprocessed_{input_imagetype_string}.nii.gz")
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
    utils.write_debug_image(t2_inv,f"inv_{preprocessed_imagetype_string}.nii.gz")
    
    t2_inv_rescale = sitk.RescaleIntensity(t2_inv, outputMinimum = 0, outputMaximum = 1000)
    utils.write_debug_image(t2_inv_rescale,f"inv_rescale_{preprocessed_imagetype_string}.nii.gz")
    
    t2_inv_sqr = sitk.Pow(t2_inv_rescale, 2)
    utils.write_debug_image(t2_inv_sqr,f"inv_sqr_{preprocessed_imagetype_string}.nii.gz")

    t2_inv_re_rescale = sitk.RescaleIntensity(t2_inv_sqr, outputMinimum = 0, outputMaximum = 1000)
    utils.write_debug_image(t2_inv_re_rescale,f"inv_sqr_re_rescale_{preprocessed_imagetype_string}.nii.gz")
    
    return t2_inv_rescale
    