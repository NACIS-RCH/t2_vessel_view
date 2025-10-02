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
            help='3D FLAIR or similar bright 3D image such as Mag',
            required=True,
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

#parser.add_argument('-e', type=str, action='store', nargs=argparse.REMAINDER, help='One or more extra images. This has to be the last option specified, i.e., cant put the output directory after this.', required=True, dest='files')

## add flags for save masks or not

args = parser.parse_args()


