import os
import SimpleITK as sitk
import ants
from . import commandline

# Flag to control whether debug images are saved
save_debug_images = True

# Helper function to get output directory
def get_output_dir():
    return commandline.args.output_dir or commandline.args.mri_dir

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

# Robust ANTsPy image read function for all versions
def read_ants_image(path):
    if hasattr(ants, "image_read"):
        return ants.image_read(path)
    elif hasattr(ants, "read_image"):
        return ants.read_image(path)
    else:
        raise AttributeError("ANTsPy does not have image_read or read_image")

## 
test_data_dir = '/Users/bonniealexander/Code/NACIS-RCH/testing_t2vv/test_dataset'
test_output_dir = '/Users/bonniealexander/Code/NACIS-RCH/testing_t2vv/test_outputs'
#rxs_mask_path = os.path.join(test_data_dir, "rxs_mask.nii.gz")

