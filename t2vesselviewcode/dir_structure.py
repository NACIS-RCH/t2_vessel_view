import os
from . import commandline

## make directory structure


## use temporary dir for development
#test_output_dir = '/Users/bonniealexander/Code/NACIS-RCH/testing_t2vv/test_outputs'

## base directory is set from command line arguments: output_dir if provided, otherwise mri_dir
base_directory = commandline.args.output_dir or commandline.args.mri_dir
## define directory structure. add option to change main directory name or add suffix

## specify output directories as variables
main_t2vv_dir = os.path.join(base_directory, "T2VesselView")
eroded_nifti_dir = os.path.join(base_directory, "T2VesselView/Eroded_nifti")
eroded_nifti_t1_dir = os.path.join(base_directory, "T2VesselView/Eroded_nifti/T1")
eroded_nifti_t2_dir = os.path.join(base_directory, "T2VesselView/Eroded_nifti/T2")
eroded_nifti_t2_tra_dir = os.path.join(base_directory, "T2VesselView/Eroded_nifti/T2_Tra")
eroded_nifti_t2_cor_dir = os.path.join(base_directory, "T2VesselView/Eroded_nifti/T2_Cor")
eroded_nifti_t2_sag_dir = os.path.join(base_directory, "T2VesselView/Eroded_nifti/T2_Sag")
eroded_nifti_t2_3d_dir = os.path.join(base_directory, "T2VesselView/Eroded_nifti/T2_3D")
eroded_nifti_flair_dir = os.path.join(base_directory, "T2VesselView/Eroded_nifti/FLAIR")
powerpoints_dir = os.path.join(base_directory, "T2VesselView/PowerPoints")
processing_dir = os.path.join(base_directory, "T2VesselView/Processing")
processing_figures_dir = os.path.join(base_directory, "T2VesselView/Processing/Figures_for_QA")
processing_log_dir = os.path.join(base_directory, "T2VesselView/Processing/Log_files")
processing_mask_dir = os.path.join(base_directory, "T2VesselView/Processing/Masks")
processed_t1_dir = os.path.join(base_directory, "T2VesselView/Processing/Preprocessed_T1")
processed_t2_dir = os.path.join(base_directory, "T2VesselView/Processing/Preprocessed_T2")
processed_flair_dir = os.path.join(base_directory, "T2VesselView/Processing/Preprocessed_FLAIR")
processed_t2_tra_dir = os.path.join(base_directory, "T2VesselView/Processing/Preprocessed_T2_Tra")
processed_t2_cor_dir = os.path.join(base_directory, "T2VesselView/Processing/Preprocessed_T2_Cor")
processed_t2_sag_dir = os.path.join(base_directory, "T2VesselView/Processing/Preprocessed_T2_Sag")
processed_t2_3d_dir = os.path.join(base_directory, "T2VesselView/Processing/Preprocessed_T2_3D")
renders_dir = os.path.join(base_directory, "T2VesselView/3D_renders_png")
renders_t1_dir = os.path.join(base_directory, "T2VesselView/3D_renders_png/T1_3D_renders")
renders_t1_erode_dir = os.path.join(base_directory, "T2VesselView/3D_renders_png/T1_3D_renders/by_erode_level")
renders_t1_angle_dir = os.path.join(base_directory, "T2VesselView/3D_renders_png/T1_3D_renders/by_angle")
renders_t2_dir = os.path.join(base_directory, "T2VesselView/3D_renders_png/T2_vessel_3D_renders")
renders_t2_erode_dir = os.path.join(base_directory, "T2VesselView/3D_renders_png/T2_vessel_3D_renders/by_erode_level")
renders_t2_angle_dir = os.path.join(base_directory, "T2VesselView/3D_renders_png/T2_vessel_3D_renders/by_angle")

## specify directories to be made
directory_structure = [
    main_t2vv_dir,
    eroded_nifti_dir,
    eroded_nifti_t1_dir,
    eroded_nifti_t2_dir,
    eroded_nifti_t2_tra_dir,
    eroded_nifti_t2_cor_dir,
    eroded_nifti_t2_sag_dir,
    eroded_nifti_t2_3d_dir,
    eroded_nifti_flair_dir,
    powerpoints_dir,
    processing_dir,
    processing_figures_dir,
    processing_log_dir,
    processing_mask_dir,
    processed_t1_dir,
    processed_t2_dir,
    processed_flair_dir,
    processed_t2_tra_dir,
    processed_t2_cor_dir,
    processed_t2_sag_dir,
    processed_t2_3d_dir,
    renders_dir,
    renders_t1_dir,
    renders_t1_erode_dir,
    renders_t1_angle_dir,
    renders_t2_dir,
    renders_t2_erode_dir,
    renders_t2_angle_dir
]

def create_directories():
    """Create the directory structure."""
    for directory in directory_structure:
        os.makedirs(directory, exist_ok=True)

# Only create directories if this module is being run directly
if __name__ == "__main__":
    create_directories()
    # Verify directory structure
    #for root, dirs, files in os.walk(base_directory):
    #    for dir in dirs:
    #        print(os.path.join(root, dir))


