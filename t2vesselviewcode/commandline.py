import argparse

parser = argparse.ArgumentParser(description='A tool for generating Vessel Maps using T2-weighted MRI', 
            epilog='Version 1, Bonnie Alexander 2023')

parser.add_argument('-d', 
            metavar='mri_directory', 
            type=str, 
            action='store', 
            help='The path to the directory where the input MRI images are', 
            required=True, 
            dest='mri_dir')

parser.add_argument('-o', 
            metavar='output directory', 
            type=str, 
            action='store', 
            help='Optional. The directory to save the Vessel Map outputs to. Otherwise it will be saved to the MRI directory.', 
            dest='output_dir')
            
parser.add_argument('-i', 
            metavar='Main image T1 or similar', 
            type=str, 
            action='store', 
            help='Required T1 or similar main image that other images will be registered to.',
            required=True,
            dest='t1')

parser.add_argument('-f', 
            metavar='flair', 
            type=str, 
            action='store', 
            help='Optional 3D FLAIR or similar bright 3D image such as Mag.This will usually substantially help with segmentation of the brain parenchyma (FLAIR) and intracranial structures including venous sinuses (Mag). Also needed if you want to run the flair watershed segmentation option.',
            dest='flair')

parser.add_argument('-c', 
            metavar='t2_coronal', 
            type=str, 
            action='store', 
            help='2D coronal T2-weighted MRI image',
            dest='t2_cor')

parser.add_argument('-s', 
            metavar='t2_sagittal', 
            type=str, 
            action='store', 
            help='2D sagittal T2-weighted MRI image. Can include single hemisphere acquisitions.',
            dest='t2_sag')

# Optional separate sagittal acquisitions per hemisphere (advanced use)
parser.add_argument('--t2_sag_left', 
            metavar='t2_sagittal_left', 
            type=str, 
            action='store', 
            help='Left-hemisphere sagittal T2 (unilateral acquisition). If provided with --t2_sag_right, both will be processed.',
            dest='t2_sag_left')

parser.add_argument('--t2_sag_right', 
            metavar='t2_sagittal_right', 
            type=str, 
            action='store', 
            help='Right-hemisphere sagittal T2 (unilateral acquisition). If provided with --t2_sag_left, both will be processed.',
            dest='t2_sag_right')

parser.add_argument('-t', 
            metavar='t2_transverse', 
            type=str, 
            action='store', 
            help='2D transverse T2-weighted MRI image.',
            dest='t2_tra')
            
parser.add_argument('-p', 
            metavar='t2_3d', 
            type=str, 
            action='store', 
            help='3D T2-weighted MRI image such as t2 space.',
            dest='t2_3d')

parser.add_argument('-m', 
            metavar='user_mask', 
            type=str, 
            action='store', 
            help='User-provided brain mask to use if automatically generated mask is suboptimal.',
            dest='user_mask')

parser.add_argument('-n', 
            metavar='user_mask_structural', 
            type=str, 
            action='store', 
            help='Structural image that the user-provided mask was based on - i.e., has the same image dimensions as the mask. Needed for registration of mask to other images.',
            dest='user_mask_structural')

parser.add_argument('--use-hull-mask',
            action='store_true',
            help='Use convex hull mask to include sagittal sinus (may affect cortical surface morphology)',
            dest='use_hull_mask')

parser.add_argument('--auto-mask-method',
            metavar='auto_mask_method',
            type=str,
            choices=['bet', 'watershed'],
            action='store',
            help='Automatic mask method: "bet" (default) or "watershed" (FLAIR-based scalping).',
            default='bet',
            dest='auto_mask_method')

# Optional MRIcroGL overlays (registered to T1; rendered directly in MRIcroGL)
parser.add_argument('--overlay1-path',
            metavar='overlay1_path',
            type=str,
            action='store',
            help='Optional path to first overlay image registered to T1 (e.g., PET_to_T1). If omitted, overlay rendering is skipped.',
            dest='overlay1_path')

parser.add_argument('--overlay1-color',
            metavar='overlay1_color',
            type=str,
            action='store',
            help='MRIcroGL colorname for first overlay (for example: jet, red, blue, hot).',
            default='jet',
            dest='overlay1_color')

parser.add_argument('--overlay1-min',
            metavar='overlay1_min',
            type=float,
            action='store',
            help='Optional minimum window value for first overlay. Strongly recommended to set explicitly for clinical use.',
            dest='overlay1_min')

parser.add_argument('--overlay1-max',
            metavar='overlay1_max',
            type=float,
            action='store',
            help='Optional maximum window value for first overlay. Strongly recommended to set explicitly for clinical use.',
            dest='overlay1_max')

parser.add_argument('--overlay1-opacity',
            metavar='overlay1_opacity',
            type=int,
            action='store',
            help='Opacity for first overlay layer (0-100). Default: 35.',
            default=35,
            dest='overlay1_opacity')

parser.add_argument('--overlay2-path',
            metavar='overlay2_path',
            type=str,
            action='store',
            help='Optional path to second overlay image registered to T1.',
            dest='overlay2_path')

parser.add_argument('--overlay2-color',
            metavar='overlay2_color',
            type=str,
            action='store',
            help='MRIcroGL colorname for second overlay.',
            default='red',
            dest='overlay2_color')

parser.add_argument('--overlay2-min',
            metavar='overlay2_min',
            type=float,
            action='store',
            help='Optional minimum window value for second overlay. Strongly recommended to set explicitly for clinical use.',
            dest='overlay2_min')

parser.add_argument('--overlay2-max',
            metavar='overlay2_max',
            type=float,
            action='store',
            help='Optional maximum window value for second overlay. Strongly recommended to set explicitly for clinical use.',
            dest='overlay2_max')

parser.add_argument('--overlay2-opacity',
            metavar='overlay2_opacity',
            type=int,
            action='store',
            help='Opacity for second overlay layer (0-100). Default: 35.',
            default=35,
            dest='overlay2_opacity')

#parser.add_argument('-e', type=str, action='store', nargs=argparse.REMAINDER, help='One or more extra images. This has to be the last option specified, i.e., cant put the output directory after this.', required=True, dest='files')

## add flags for save masks or not

args = parser.parse_args()

# Basic CLI validation for overlay parameters
for overlay_idx in (1, 2):
    path_val = getattr(args, f'overlay{overlay_idx}_path', None)
    min_val = getattr(args, f'overlay{overlay_idx}_min', None)
    max_val = getattr(args, f'overlay{overlay_idx}_max', None)
    opacity_val = getattr(args, f'overlay{overlay_idx}_opacity', 35)

    if opacity_val is not None and not (0 <= int(opacity_val) <= 100):
        parser.error(f'--overlay{overlay_idx}-opacity must be between 0 and 100.')

    # If user provided one bound, require both so intent is explicit.
    if path_val and ((min_val is None) ^ (max_val is None)):
        parser.error(
            f'--overlay{overlay_idx}-min and --overlay{overlay_idx}-max must be provided together, '
            f'or both omitted for automatic estimation.'
        )

    if path_val and min_val is not None and max_val is not None and float(max_val) <= float(min_val):
        parser.error(f'--overlay{overlay_idx}-max must be greater than --overlay{overlay_idx}-min.')


