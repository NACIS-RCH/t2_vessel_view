import os
import SimpleITK as sitk
import nipype.interfaces.fsl as fsl
from contextlib import redirect_stdout, redirect_stderr


from . import utils
from . import commandline
from . import make_mask_convex_hull
from . import dir_structure

TEST_MODE = os.environ.get('T2VV_TEST_MODE') == '1'


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
        dummy_mask_path = os.path.join(dir_structure.processing_mask_dir, "test_bet_hires_mask.nii.gz")
        dummy_mask = sitk.Image([100, 100, 100], sitk.sitkUInt8)
        dummy_mask.SetSpacing([1.0, 1.0, 1.0])
        sitk.WriteImage(dummy_mask, dummy_mask_path)
        return dummy_mask_path
    
    print("[INFO] Generating brain mask")
    
    ## this BET call works, partially. tested it on a raw T1.
    btr=fsl.BET()
    btr.inputs.in_file = image_for_mask
    btr.inputs.frac = 0.5
    btr.inputs.robust = True
    btr.inputs.mask = True
    #btr.inputs.outline = True
    btr.inputs.output_type = 'NIFTI_GZ'
    hires_brain = os.path.join(dir_structure.processing_mask_dir, "test_bet_hires_brain.nii.gz")
    btr.inputs.out_file = hires_brain
    
    #try:
    #    res = btr.run()
    #except RuntimeError as e:
    #    print(f"[WARNING] BET did not save extra files but continuing: {e}")
    
    with open(os.devnull, "w") as fnull:
        with redirect_stdout(fnull), redirect_stderr(fnull):
            try:
                res = btr.run()
            except RuntimeError:
                pass  # Optionally handle the error silently
    
    ## get the mask
    hires_mask_path = os.path.join(dir_structure.processing_mask_dir, "test_bet_hires_brain_mask.nii.gz")



    return hires_mask_path


def generate_mask_watershed(flair_path):
    """
    Generate a brain mask using watershed scalping on preprocessed FLAIR.

    Parameters
    ----------
    flair_path : string
        Path to preprocessed FLAIR image in pipeline space.

    Returns
    -------
    String
        Path to generated watershed mask.
    """
    out_path = os.path.join(dir_structure.processing_mask_dir, "watershed_flair_brain_mask.nii.gz")
    workdir = os.path.join(dir_structure.processing_mask_dir, "watershed_work")

    if TEST_MODE:
        os.makedirs(dir_structure.processing_mask_dir, exist_ok=True)
        dummy_mask = sitk.Image([100, 100, 100], sitk.sitkUInt8)
        dummy_mask.SetSpacing([1.0, 1.0, 1.0])
        sitk.WriteImage(dummy_mask, out_path)
        return out_path

    if not flair_path:
        raise ValueError("Watershed mask generation requires a preprocessed FLAIR path.")

    from . import scalpFlair

    print("[INFO] Generating brain mask with watershed scalping method")
    scalpFlair.run_watershed_scalping(flair_path, workdir, out_path)
    return out_path

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
        top_hull, final_hull = make_mask_convex_hull.make_hull_mask(resampled_mask)
        mask_to_process = final_hull
    else:
        mask_to_process = resampled_mask
    
    print("[INFO] Performing main mask operations")
    print(f"[INFO] Mask to process: {mask_to_process}")

    ## check this line
    rxs_mask = sitk.ReadImage(mask_to_process)
    ## smooth mask with gaussian kernel size 3
    rxs_mask_float = sitk.Cast(rxs_mask, sitk.sitkFloat32)
    smoothed_rxs_mask = sitk.DiscreteGaussian(rxs_mask_float, 3.0)
    utils.write_debug_image(smoothed_rxs_mask, "smoothed_rxs_mask.nii.gz", dir_structure.processing_mask_dir)
    
    ## Binarize the smoothed mask using a threshold of 0.5
    bin_sm_rxs_mask = sitk.BinaryThreshold(smoothed_rxs_mask, lowerThreshold=0.5, upperThreshold=1.0, insideValue=1, outsideValue=0)
    # Always keep the cleaned binary brain mask for users (mirrors Preprocessed_*.nii.gz).
    preprocessed_mask_path = os.path.join(
        dir_structure.processing_mask_dir, utils.PREPROCESSED_MASK_FILENAME
    )
    sitk.WriteImage(bin_sm_rxs_mask, preprocessed_mask_path)
    print(f"[INFO] Saved cleaned brain mask: {preprocessed_mask_path}")
    utils.write_debug_image(bin_sm_rxs_mask, "bin_smoothed_rxs_mask.nii.gz", dir_structure.processing_mask_dir)
    
    ## make inverse of that mask
    inv_bin_sm_rxs_mask = sitk.BinaryThreshold(smoothed_rxs_mask, lowerThreshold=0, upperThreshold=0.5, insideValue=1, outsideValue=0)
    utils.write_debug_image(inv_bin_sm_rxs_mask, "inv_bin_smoothed_rxs_mask.nii.gz", dir_structure.processing_mask_dir)
    
    ## get signed distance transform of upsampled mask
    sdt_rxs_mask = sitk.SignedMaurerDistanceMap(bin_sm_rxs_mask, squaredDistance=False, useImageSpacing=True)
    utils.write_debug_image(sdt_rxs_mask, "sdt_rxs_mask.nii.gz", dir_structure.processing_mask_dir)
    
    sdt_inv_rxs_mask = sitk.SignedMaurerDistanceMap(inv_bin_sm_rxs_mask, squaredDistance=False, useImageSpacing=True)
    utils.write_debug_image(sdt_inv_rxs_mask, "sdt_inv_rxs_mask.nii.gz", dir_structure.processing_mask_dir)

    ## get positive values of signed distance transform inside brain ;
    sdt_rxs_mask_image_by_minus_one = - sdt_rxs_mask
    utils.write_debug_image(sdt_rxs_mask_image_by_minus_one, "sdt_rxs_mask_image_by_minus_one.nii.gz", dir_structure.processing_mask_dir)

    ## this comes out as a binary mask. ?want a thresholded sdt image. multiply by image? see steps below for logic
    thresholded_img = sitk.BinaryThreshold(sdt_rxs_mask_image_by_minus_one, lowerThreshold=0, upperThreshold=50000)
    utils.write_debug_image(thresholded_img, "thresholded_img.nii.gz", dir_structure.processing_mask_dir)
    
    ## cast mask as float so it can be multiplied by sdt image
    thresholded_img_float = sitk.Cast(thresholded_img, sitk.sitkFloat32)
    ## multiply 
    pos_sdt_rxs_mask = sitk.Multiply(sdt_rxs_mask_image_by_minus_one, thresholded_img_float)
    utils.write_debug_image(pos_sdt_rxs_mask, "pos_sdt_rxs_mask.nii.gz", dir_structure.processing_mask_dir)

    ## add the inverse mask sdt to pos mask
    sdt_all = pos_sdt_rxs_mask + sdt_inv_rxs_mask
    utils.write_debug_image(sdt_all, "sdt_all.nii.gz", dir_structure.processing_mask_dir)

    # add 2 to dilate mask
    sdt_all_plus_2 = sdt_all + 2
    utils.write_debug_image(sdt_all_plus_2, "sdt_all_plus_2.nii.gz", dir_structure.processing_mask_dir)

    return sdt_all_plus_2

def mask_erosions(processed_signed_distance):
    """
    Erodes the mask at a series of depths.
    
    Parameters
    ----------
    processed_signed_distance: SimpleITK image object
    
    
    
    """
    erode_depths_list = [0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5, 5.5, 6, 6.5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30]
    ## make list of eroded mask file names?
    eroded_masks_dict = {}
    zero_padded_erode_depths_list = []
    
    print("[INFO] Performing mask erosions")
    
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
        utils.write_debug_image(eroded_rxs_mask_float, f'{zero_padded_erode_depth}_eroded_rxs_mask.nii.gz', dir_structure.processing_mask_dir)
        
        ##smooth
        smoothed_eroded_rxs_mask = sitk.DiscreteGaussian(eroded_rxs_mask_float, 3.0)
        utils.write_debug_image(smoothed_eroded_rxs_mask, f'{zero_padded_erode_depth}_smoothed_eroded_rxs_mask.nii.gz', dir_structure.processing_mask_dir)
        
        bin_smoothed_eroded_rxs_mask = smoothed_eroded_rxs_mask > 0.5
        bin_smoothed_eroded_rxs_mask_float = sitk.Cast(bin_smoothed_eroded_rxs_mask, sitk.sitkFloat32)

        utils.write_debug_image(bin_smoothed_eroded_rxs_mask_float, f'{zero_padded_erode_depth}_bin_smoothed_eroded_rxs_mask.nii.gz', dir_structure.processing_mask_dir)
        
        ## put extra step in here for smoothing? 
        eroded_masks_dict[eroded_mask_file_name] = bin_smoothed_eroded_rxs_mask_float
    
    ### also save masks as files in case option chosen
    ## return dictionary with mask file names and objects, and zero padded erode depths for use in other file names
    return (eroded_masks_dict, zero_padded_erode_depths_list)

def multiply_masks_by_images(image_to_erode, filetype_string, directory_for_outputs, zero_padded_erode_depths_list, eroded_masks_dict):
    """
    Multiply masks by images.
    
    Parameters
    ----------
    image_to_erode : SimpleITK image
        The image to be masked
    filetype_string : str
        String identifier for the image type (e.g., "t1", "t2_sag")
    directory_for_outputs : str
        Directory where output files will be saved
    zero_padded_erode_depths_list : list
        List of zero-padded erosion depths
    eroded_masks_dict : dict
        Dictionary containing the eroded masks
    """
    ## Output directory from directory structure, within 'Eroded_nifti' dir
    eroded_outdir = os.path.join(dir_structure.processing_mask_dir, directory_for_outputs)
    
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


def cleanup_masks_directory(mask_dir=None):
    """
    Remove Processing/Masks intermediates after Eroded_nifti outputs exist.

    Keeps Preprocessed_mask.nii.gz (cleaned binary brain mask). Skips cleanup
    entirely when --keep-debug-images is set.
    """
    if utils.keep_debug_images():
        print("[INFO] Keeping Processing/Masks intermediates (--keep-debug-images).")
        return

    if mask_dir is None:
        mask_dir = dir_structure.processing_mask_dir
    if not mask_dir or not os.path.isdir(mask_dir):
        return

    keep_name = utils.PREPROCESSED_MASK_FILENAME
    removed_count = 0
    for name in os.listdir(mask_dir):
        if name == keep_name:
            continue
        path = os.path.join(mask_dir, name)
        if not utils.is_under_directory(path, mask_dir):
            continue
        if os.path.isfile(path):
            if utils.remove_paths([path], allowed_directory=mask_dir):
                removed_count += 1
        elif os.path.isdir(path):
            if utils.remove_tree(path, allowed_directory=mask_dir):
                removed_count += 1

    if removed_count:
        print(
            f"[INFO] Removed {removed_count} mask intermediate(s) from {mask_dir} "
            f"(kept {keep_name})."
        )
    elif os.path.isfile(os.path.join(mask_dir, keep_name)):
        print(f"[INFO] Mask cleanup complete (kept {keep_name}).")
