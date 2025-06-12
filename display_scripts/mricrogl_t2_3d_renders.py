####  general usage: MRIcroGL_QT script_name.py
## need to check your version of mricrogl and update the path to the mricrogl executable if necessary

## This script outputs basic summary screenshots at six different angles (superior, inferior, left sagittal, right sagittal, anterior, posterior)
## This includes erosions for T2 3D vessel images
## Output screenshots can be joined into a single image with screenshot_stitcher.py script that is run separately with python 
## this is python code but mricrogl uses internal language that's not python, so some elements like 'gl' don't have the same behaviour as actual python.

## Run the current script from command line - it will open mricrogl which will then internally interpret the python script into its own language. Most of the 'gl.x' commands below are specific to mricrogl (rather than the python function gl) and are documented in its help or here: https://github.com/rordenlab/MRIcroGL12/blob/master/PYTHON.md 

## Overlay filenames MUST BE EXACT OTHERWISE IT USES THE PREVIOUS PATIENT'S IMAGES 

import gl
import os
import sys
import glob

### specify that the variable name display_scripts_directory refers to the the current working directory 
display_scripts_directory=os.getcwd()
### the directory one level up from that is the main T2VesselView directory
main_t2vv_directory=os.path.dirname(display_scripts_directory)

### make output directory for screenshots
output_screenshots_directory=os.path.join(main_t2vv_directory,'3D_renders_png','T2_vessel_3D_renders')

if not os.path.isdir(output_screenshots_directory):
     os.makedirs(output_screenshots_directory, exist_ok=True)

## this gets a list of all the eroded T2 3D vessel images
imagelist=glob.glob(os.path.join(main_t2vv_directory,'Eroded_nifti','T2','*eroded*t2_3d*'))
imagelist.sort(reverse=True)

## for each T2 3D vessel image, set display preferences, load image
for n,i in enumerate(imagelist):

## basic settings     
     gl.resetdefaults()
     gl.backcolor(0,0,0) # black background for vessel visualization
     gl.cameradistance(0.6) # change to higher to zoom out
     gl.colorbarposition(0)
     gl.overlaymaskwithbackground(0)
     
## Shader and parameters for vessel visualization   
     gl.shadername('OverlaySurface')   
     gl.shaderadjust('diffuse', 0)
     gl.shaderadjust('shininess', 0)
     gl.shaderadjust('specular', 0)
     gl.shaderadjust('ambient', 1)          
     gl.shaderadjust('overlayClip', 1)
     gl.shaderadjust('overlayFuzzy', 1)  
     gl.shaderadjust('overlayDepth', 0)
             
## load T2 3D vessel image (layer '0' is the bottom layer)       
     layer_number=0
     print(i)   
     gl.loadimage(i)
     gl.hiddenbycutout(layer_number, 1)  
     gl.opacity(layer_number,100)     

      
## for a set of azimuth and elevation values, change the viewing angle and take a screenshot
     for x in [[90,0,'left'],[270,0,'right'],[0,0,'posterior'],[180,0,'anterior'],[0,90,'superior'],[180,-90,'inferior']]:
         gl.azimuthelevation(x[0],x[1])
         gl.wait(200)
         outpath_angle_subdirectory=os.path.join(output_screenshots_directory,'by_angle',x[2])
         if not os.path.isdir(outpath_angle_subdirectory):
             os.makedirs(outpath_angle_subdirectory, exist_ok=True)
         gl.savebmp(os.path.join(outpath_angle_subdirectory,'T2_3d_vessels-{}-{}-{}-{}.png'.format(x[2],x[0],x[1],os.path.split(i)[-1].split('.')[0])))

gl.quit() 