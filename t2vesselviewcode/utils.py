import os
import SimpleITK as sitk
import ants

# Flag to control whether debug images are saved
save_debug_images = True

def write_debug_image(image_object, output_file, output_directory):
    """
    Write a debug image to the specified output directory.
    Only writes if save_debug_images is True.
    
    Parameters
    ----------
    image_object : SimpleITK image
        The image to write
    output_file : str
        Name of the output file
    output_directory : str
        Directory to write the file to
    """
    if save_debug_images:
        path = os.path.join(output_directory, output_file) 
        sitk.WriteImage(image_object, path) 


# Check ANTsPy version compatibility
try:
    # Try newer version first
    ants.image_read
    def read_ants_image(path):
        return ants.image_read(path)
except AttributeError:
    # Fall back to older version
    def read_ants_image(path):
        return ants.read_image(path)        
    

    ## 
test_data_dir = '/Users/bonniealexander/Code/NACIS-RCH/testing_t2vv/test_dataset'
test_output_dir = '/Users/bonniealexander/Code/NACIS-RCH/testing_t2vv/test_outputs'
#rxs_mask_path = os.path.join(test_data_dir, "rxs_mask.nii.gz")
input_t1_path = os.path.join(test_data_dir, "T1_raw.nii.gz")
input_flair_path = os.path.join(test_data_dir, "FLAIR.nii.gz")
input_t2_sag_path = os.path.join(test_data_dir, "T2_tse_sag_l.nii.gz")
input_t2_cor_path = os.path.join(test_data_dir, "T2_tse_cor.nii.gz")
input_t2_tra_path = os.path.join(test_data_dir, "T2_tse_tra.nii.gz")
