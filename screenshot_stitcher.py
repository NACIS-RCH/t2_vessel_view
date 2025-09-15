## Authored by Bonnie Alexander and Jupiter Haehn, 2022

#!/usr/bin/env python3
import glob
import sys
from PIL import Image as pil_image
import os
import argparse
import pyvips
from pptx import Presentation
from pptx.dml.color import ColorFormat, RGBColor
from pptx.dml.color import MSO_COLOR_TYPE, MSO_THEME_COLOR
from pptx.util import Inches, Pt

############## USAGE

## type 'conda activate auto_crop' before running this script

## python /screenshot_stitcher.py -d <patient directory> -o <output directory> -p <optional output prefix> --top1 <image directory for top row position 1> --top2 <image directory for top row position 2> --top3 <image directory for top row position > -f <optional- if you want an output powerpoint file with the concatenated image series, specify its filename (without the .pptx extension)>

## up to 4 images on top row (i.e., --top1 --top2 --top3 --top4)
## optional bottom row with up to 4 images (i.e., --bottom1 --bottom2 --bottom3 --bottom4)

#### EXAMPLE

## conda activate auto_crop 

## python /screenshot_stitcher.py -d Processing/erosion_display -o concat_3d_pet_overview --top1 mricrogl_screenshots_external_PET_renders/left --top2 mricrogl_screenshots_external_PET_renders/right --bottom1 mricrogl_screenshots_external_PET_renders/superior --bottom2 mricrogl_screenshots_external_PET_renders/inferior --bottom3 mricrogl_screenshots_external_PET_renders/anterior --bottom4 mricrogl_screenshots_external_PET_renders/posterior -f external_pet_renders


###############




## Current estimate at slide dimensions here is going by 1920x1080 display divided by 72 (default dpi of pptx file) 
PPTX_SLIDE_WIDTH=38
PPTX_SLIDE_HEIGHT=22

def initialize_parser():
    parser = argparse.ArgumentParser(description='Concatenates screenshots for display. Takes in directories with equal numbers of .png or .jpg files and loops through and joins the images together.', epilog='Version 1, Bonnie Alexander ')

    parser.add_argument('-d', action='store', help='The absolute path to the common patient directory where the subdirectories containing screenshots are. This could be patient ID directory, or an erosion directory. For example, "/group/deve2/ACTIVE/data/projects/NACIS/Converted_Data_Nifti/999_999999/PATIENT_NAME/Processing". Starts with a slash. ', required=True, dest='patient_directory')

    parser.add_argument('--top1', type=str, action='store', help='The relative path to the directory where the png screenshot images are, that you want to be placed in the top row first position. This file path needs to include all directories back to the level of the common patient directory specified in the first argument. Doesnt start with a backslash. ', required=True, dest='top1')

    parser.add_argument('--top2', type=str, action='store', help='The relative path to the directory where the png screenshot images are, that you want to be placed in the top row second position. This file path needs to include all directories back to the level of the common patient directory specified in the first argument. So could be, e.g., "screenshots_T2" or could be "PATIENT_NAME_26-11-2018/erosion_display/screenshots_T2", depending on how the main patient directory was specified on the command line. Doesn\'t start with a backslash. ', dest='top2')

    parser.add_argument('--top3', type=str, action='store', help='The relative path to the directory where the png screenshot images are, that you want to be placed in the top row third position. This file path needs to include all directories back to the level of the common patient directory specified in the first argument. So could be, e.g., "screenshots_T2" or could be "PATIENT_NAME_26-11-2018/erosion_display/screenshots_T2", depending on how the main patient directory was specified on the command line. Doesn\'t start with a backslash. ', dest='top3')

    parser.add_argument('--top4', type=str, action='store', help='The relative path to the directory where the png screenshot images are, that you want to be placed in the top row fourth position. This file path needs to include all directories back to the level of the common patient directory specified in the first argument. So could be, e.g., "screenshots_T2" or could be "PATIENT_NAME_26-11-2018/erosion_display/screenshots_T2", depending on how the main patient directory was specified on the command line. Doesn\'t start with a backslash. ', dest='top4')

    parser.add_argument('--bottom1', type=str, action='store', help='The relative path to the directory where the png screenshot images are, that you want to be placed in the bottom row first position. This file path needs to include all directories back to the level of the common patient directory specified in the first argument. So could be, e.g., "screenshots_T2" or could be "PATIENT_NAME_26-11-2016/erosion_display/screenshots_T2", depending on how the main patient directory was specified on the command line. Doesn\'t start with a backslash. ',  dest='bot1')

    parser.add_argument('--bottom2', type=str, action='store', help='The relative path to the directory where the png screenshot images are, that you want to be placed in the bottom row second position. This file path needs to include all directories back to the level of the common patient directory specified in the first argument. So could be, e.g., "screenshots_T2" or could be "PATIENT_NAME_26-11-2018/erosion_display/screenshots_T2", depending on how the main patient directory was specified on the command line. Doesn\'t start with a backslash. ', dest='bot2')

    parser.add_argument('--bottom3', type=str, action='store', help='The relative path to the directory where the png screenshot images are, that you want to be placed in the bottom row third position. This file path needs to include all directories back to the level of the common patient directory specified in the first argument. So could be, e.g., "screenshots_T2" or could be "PATIENT_NAME_26-11-2018/erosion_display/screenshots_T2", depending on how the main patient directory was specified on the command line. Doesn\'t start with a backslash. ', dest='bot3')

    parser.add_argument('--bottom4', type=str, action='store', help='The relative path to the directory where the png screenshot images are, that you want to be placed in the bottom row fourth position. This file path needs to include all directories back to the level of the common patient directory specified in the first argument. So could be, e.g., "screenshots_T2" or could be "PATIENT_NAME_26-11-2018/erosion_display/screenshots_T2", depending on how the main patient directory was specified on the command line. Doesn\'t start with a backslash. ', dest='bot4')

    parser.add_argument('-p', metavar='output prefix', type=str, action='store', help='Optional. String prefix for concatenated png images', dest='output_prefix')

    parser.add_argument('-o', type=str, action='store', help='Optional. A new directory inside the patient directory will be made. Specify path from patient base directory. If it doesn\'t exist, it will be created.', dest='output_directory')

    parser.add_argument('-r', metavar='R value for background colour', type=check_colour_val, action='store', help='Optional. The r (red) value for the background colour.', dest='r_val')
    parser.add_argument('-g', metavar='G value for background colour', type=check_colour_val, action='store', help='Optional. The g (green) value for the background colour.', dest='g_val')
    parser.add_argument('-b', metavar='B value for background colour', type=check_colour_val, action='store', help='Optional. The b (blue) value for the background colour.', dest='b_val')
    
    parser.add_argument('-f', metavar='pptx file basename', type=str, action='store', help='File name for output powerpoint file. Without the .pptx extension as this will be added automatically.', dest='pptx_file_name')

    return parser

# function to check whether rgb values are valid
def check_colour_val(value):
    ivalue=int(value)
    if not 0 <= ivalue <= 255:
        raise argparse.ArgumentTypeError("%s needs to be an integer between 0 and 255" % value)
    return ivalue

def set_background_colour(r,g,b):
    background_colour=[0,0,0]

    if r is not None:
        background_colour[0]=r
    if g is not None:
        background_colour[1]=g
    if b is not None:
        background_colour[2]=b
    return background_colour

def set_pptx_image_dimensions(width, height):
    """Calculate whether to use height or width of image to input image into pptx."""
    global image_ratio
    image_ratio = width/height
    global slide_ratio
    slide_ratio = PPTX_SLIDE_WIDTH/PPTX_SLIDE_HEIGHT            


def concat_directory_images_one_row(number_of_images, top_directory_list, output_location):
    """
    Stitching cropped images together in one row.
    
    """
    print(' ')
    print('Stitching cropped images together in one row')
    if not os.path.isdir(output_location):
        os.mkdir(output_location)
    ## number of images is gotten below by get_total_files function which lists number of *png files in each input directory and outputs that number if they all have the same number
    for n in range(number_of_images):
        ## images_list will be list of between 2 and 4 images to be concatenated in a single row
        images_list=[]
        ## directory_list here will be filled by top_dirs_list which is a list of complete file path to each .png for each input directory
        for directory_png_filepath in top_directory_list:
            images_list.append(directory_png_filepath[n])
        ## python image library package will open 2-4 images in image_list that will be joined in one row
        images = [pil_image.open(x) for x in images_list]
        ## zip is iterating 2 things at the one time, i.e., the widths and heights of each image. The star is making sure that it is doing this for each ?thing.
        widths, heights = zip(*(i.size for i in images))

        total_width = sum(widths)
        max_height = max(heights)
        set_pptx_image_dimensions(total_width, max_height)

        new_im = pil_image.new('RGB', (total_width, max_height))

        x_offset = 0

        for im in images:
            new_im.paste(im, (x_offset,0))
            x_offset += im.size[0]
       
        new_im.save(os.path.join(output_location,  f'concat_{n:03}.png'))
        
def concat_directory_images_two_rows(number_of_images, top_directory_list, bottom_directory_list, output_location):
    print(' ')
    print('Stitching cropped images together in two rows')
    if not os.path.isdir(output_location):
        os.mkdir(output_location)
    ## number of images is gotten below by get_total_files function which lists number of *png files in each input directory and outputs that number if they all have the same number
    for n in range(number_of_images):
        ## images_list will be list of between 2 and 4 images to be concatenated in a single row

        top_images_list=[]
        ## top_directory_list here will be filled by top_dirs_list which is a list of complete file path to each .png for each input directory
        for directory_png_filepath in top_directory_list:
            top_images_list.append(directory_png_filepath[n])
        ## python image library package will open 2-4 images in image_list that will be joined in one row
        top_images = [pil_image.open(x) for x in top_images_list]
        ## zip is iterating 2 things at the one time, i.e., the widths and heights of each image. The star is making sure that it is doing this for each ?thing.
        top_widths, top_heights = zip(*(i.size for i in top_images))
        
        total_top_width = sum(top_widths)
        total_top_height = max(top_heights)
        
        bottom_images_list=[]
        ## directory_list here will be filled by top_dirs_list or bottom_dirs_list which is a list of complete file path to each .png for each input directory
        for directory_png_filepath in bottom_directory_list:
            bottom_images_list.append(directory_png_filepath[n])
        ## python image library package will open 2-4 images in image_list that will be joined in one row
        bottom_images = [pil_image.open(x) for x in bottom_images_list]
        ## zip is iterating 2 things at the one time, i.e., the widths and heights of each image. The star is making sure that it is doing this for each ?thing.
        bottom_widths, bottom_heights = zip(*(i.size for i in bottom_images))
       
        total_bottom_width = sum(bottom_widths)
        total_bottom_height = max(bottom_heights)        
        
        total_width = max(total_top_width, total_bottom_width)
        total_height = total_top_height + total_bottom_height
        set_pptx_image_dimensions(total_width, total_height)
        
        new_im = pil_image.new('RGB', (total_width, total_height))
        
        x_offset = 0
        
        for im in top_images:
            new_im.paste(im, (x_offset,0))
            x_offset += im.size[0]
            
        x_offset = 0
        y_offset = total_top_height
        
        for im in bottom_images:
            new_im.paste(im, (x_offset,y_offset))
            x_offset += im.size[0]
        
        new_im.save(os.path.join(output_location,  f'concat_{n:03}.png'))        
        


## this function determines how much to crop the series of images by comparing the amount of background colour in each image with a sample image and choosing the greater amount of background
def get_crop_dimensions(images, background_colour, threshold = 2):
    print('Finding dimensions for cropping each image based on the least amount of background space in any image per directory')
    ## possibly put something in here that checks if there's anything in the sample image and if not, goes onto the next image as the sample
    
    ## 'sample' refers to a sample image against which to compare the background of other images.
    
    for sample_check in images: 
        sample = pyvips.Image.new_from_file(sample_check)
        ## get width of brain to check it exists
        test_if_brain_exists = sample.find_trim(threshold=threshold, background=background_colour)[2]
    
        if test_if_brain_exists == 0:
            continue
    
    ##trying this to check if there's an issue with it picking empty images as the sample image
    
    #sample = pyvips.Image.new_from_file(images[0])
        left, top, brain_width, brain_height = sample.find_trim(threshold=threshold, background=background_colour)
        
        break

    right = sample.width - left - brain_width
    bottom = sample.height - top - brain_height

    left_crop = left
    top_crop = top
    right_margin = right
    bottom_margin = bottom

    for entry in images:
       image = pyvips.Image.new_from_file(entry)

       if image.width != sample.width or image.height != sample.height:
           error_message=f"All images in the input directory need to be the same dimensions. {entry} is not the same height and width as other images"
           sys.exit(error_message)
       image_left, image_top, image_brain_width, image_brain_height = image.find_trim(threshold=threshold, background=background_colour)

       image_right_margin = sample.width - image_left - image_brain_width
       ## adding this next line in case there's no brain in image:
       image_right_margin = image_left if image_brain_width == 0 else image_right_margin
       image_bottom_margin = sample.height - image_top - image_brain_height
       ## also adding this in case no brain in image:
       image_bottom_margin = image_top if image_brain_height == 0 else image_bottom_margin

       left_crop =  image_left if image_left < left_crop else left_crop
       top_crop =  image_top if image_top < top_crop else top_crop
       right_margin =  image_right_margin if image_right_margin < right_margin else right_margin
       bottom_margin =  image_bottom_margin if image_bottom_margin < bottom_margin else bottom_margin


    width_crop =  sample.width - left_crop - right_margin
    height_crop =  sample.height - top_crop - bottom_margin

    return [left_crop, top_crop, width_crop, height_crop]


def get_directories(args):
    directories = []
    for dir in [args.top1, args.top2, args.top3, args.top4, args.bot1, args.bot2, args.bot3, args.bot4]:
        if dir is not None:
            if dir.startswith('/'):
                raise parser.error("Input directories must be a relative path from the patient directory")
            else:
                directories.append(dir)
    return directories

def get_total_files(directory_list):
    num_files = 0
    for dir in directory_list:
        png = glob.glob(os.path.join(args.patient_directory, dir, '*.png'))
        if num_files == 0:
            num_files = len(png)
        elif num_files != len(png):
            raise parser.error("Input directories must contain the same number of .png files as each other.")
    return num_files

## this function does the actual cropping once the crop dimensions have alrady been figured out
def auto_crop_image_series(images, output_directory, dimensions):
    print('Cropping images based on crop dimensions identified')
    outpath = os.path.join(output_directory, '0_cropped_series')
    if not os.path.isdir(outpath):
        os.mkdir(outpath)
    left, top, width, height = dimensions
    for i in images:
        image = pyvips.Image.new_from_file(i)
        try:
            image = image.crop(left, top, width, height)
        except pyvips.error.Error:
            print(f'{entry} could not be cropped')
        output_file_name = "cropped_" + i.split('/')[-1]
        image.write_to_file(os.path.join(outpath, output_file_name))
    return glob.glob(os.path.join(outpath, '*.png'))

### ---------------------------------------------------------------------------------------------
## this is first line of script because above is definitions and function definitions

## these lines are needed by argparse package that handles the input arguments
parser = initialize_parser()
args = parser.parse_args()

## the set_backround_colour function above makes a list with the colour values in it like [0,10,10] so here this is assigned to variable called background
background = set_background_colour(args.r_val, args.g_val, args.b_val)

## check for equal number of input images
dirlist = get_directories(args)
## num files is the number of files in each directory and thus also the number of output files once they have been joined
num_files = get_total_files(dirlist)
print(' ')
print(f'Number of .png images per directory = {num_files}' )

## make the output directory if it doesn't already exist
outdir=os.path.join(args.patient_directory, args.output_directory)
if not os.path.isdir(outdir):
    os.mkdir(outdir)

### top row
top_dirs_list=[]

for dir in [args.top1, args.top2, args.top3, args.top4]:
    if dir is not None:
        print(' ')
        print(f'Cropping images in top row directory {dir}:')
        i=glob.glob(os.path.join(args.patient_directory, dir,  '*.png'))
        cropped_dimensions = get_crop_dimensions(i, background)
        cropped_images = auto_crop_image_series(i, os.path.join(args.patient_directory, dir), cropped_dimensions)
        ## auto_crop_image_series function above outputs a file path that has the subject directory, image directory, and 0_cropped, and cropped .png so that is what the top_dirs_list will include for each input directory
        top_dirs_list.append(sorted(cropped_images))

### bottom row
bottom_dirs_list=[]

for dir in [args.bot1, args.bot2, args.bot3, args.bot4]:
    if dir is not None:
        print(' ')
        print(f'Cropping images in bottom row directory {dir}:')
        i=glob.glob(os.path.join(args.patient_directory, dir,  '*.png'))
        cropped_dimensions = get_crop_dimensions(i, background)
        cropped_images = auto_crop_image_series(i, os.path.join(args.patient_directory, dir), cropped_dimensions)
        bottom_dirs_list.append(sorted(cropped_images))

## based on whether the directory list of bottom directories is not empty, choose which function to use to concatenate the images
if bottom_dirs_list:
    concat_directory_images_two_rows(num_files, top_dirs_list, bottom_dirs_list, outdir)
else:
    concat_directory_images_one_row(num_files, top_dirs_list, outdir)

print(' ')
print(f'Saved concatenated image series .png files in {outdir}')

  
#### pptx stuff:    

## if there is a file name specified for an output powerpoint, make a list of concatenated images and add to a pptx file
if args.pptx_file_name is not None:
    
    screenshots_list=[]

    for image in glob.glob(os.path.join(outdir,'*.png')):
        screenshots_list.append(image)
    screenshots_list.sort(reverse=False)

    ## create ppt to put slides into
    pr1 = Presentation()
    ## adjust the presentation size in inches because the default is 11x7 or so
    pr1.slide_width = Inches(PPTX_SLIDE_WIDTH)
    pr1.slide_height = Inches(PPTX_SLIDE_HEIGHT)

    from_left = Inches(0.3)
    from_top = Inches(0.3)

    width_inside_frame = Inches(PPTX_SLIDE_WIDTH - 0.6)
    height_inside_frame = Inches(PPTX_SLIDE_WIDTH - 0.6)


    for screenshot in screenshots_list:

        ## add slide
        new_slide = pr1.slides.add_slide(pr1.slide_layouts[6])
        background = new_slide.background
        fill = background.fill
        fill.solid()
        fill.fore_color.rgb = RGBColor(0,0,0)

        ## add image    
        if image_ratio > slide_ratio:
            add_picture = new_slide.shapes.add_picture(screenshot, from_left, from_top, width=width_inside_frame)
        else:
            add_picture = new_slide.shapes.add_picture(screenshot, from_left, from_top, height=height_inside_frame)
        ##https://python-pptx.readthedocs.io/en/latest/api/image.html has picture size in pixels and dpi
    

    pr1.save(os.path.join(args.output_directory, args.pptx_file_name + ".pptx"))    
    print(' ')
    print(f'Saved concatenated image series to powerpoint file {outdir}/{args.pptx_file_name}.pptx')

print(' ')
print('Stitching complete ^_^')
print(' ')
    
