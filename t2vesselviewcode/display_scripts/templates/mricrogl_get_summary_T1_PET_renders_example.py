

# TODO: add PET or other overlay capability via CLI and/or config file

####  general usage: MRIcroGL_QT script_name.py
## need to check your version of mricrogl and update the path to the mricrogl executable if necessary

## This script outputs basic summary screenshots at six different angles (superior, inferior, left sagittal, right sagittal, anterior, posterior)
## This includes erosions and also slices



## Run the current script from command line - it will open mricrogl which will then internally interpret the python script into its own language. Most of the 'gl.x' commands below are specific to mricrogl (rather than the python function gl) and are documented in its help or here: https://github.com/rordenlab/MRIcroGL12/blob/master/PYTHON.md 



import gl # type: ignore
import os
import sys
import glob

### specify that the variable name display_scripts_directory refers to the the current working directory 
display_scripts_directory=os.getcwd()
### the directory one level up from that is the main T2VesselView directory
main_t2vv_directory=os.path.dirname(display_scripts_directory)

### make output directory for screenshots
output_screenshots_directory=os.path.join(main_t2vv_directory,'3D_renders_png','T1_3D_renders')

if not os.path.isdir(output_screenshots_directory):
     os.makedirs(output_screenshots_directory, exist_ok=True)

## this gets a list of all the eroded T1s so they can be serially loaded below.
## You can change that to test out the display settings or to just display the outer non-eroded surface

imagelist=glob.glob(os.path.join(main_t2vv_directory,'Eroded_nifti','T1','*eroded*t1*'))
imagelist.sort(reverse=True)

## for each T1 image, set display preferences, load T1 and overlays
for n,i in enumerate(imagelist):

## basic settings     
     gl.resetdefaults()
     gl.backcolor(0,0,0) # can make this 200,200,200 if you want light grey background
     gl.cameradistance(0.6) # change to higher to zoom out
     gl.colorbarposition(0)
     gl.overlaymaskwithbackground(0) # this can be 0 when 'OverlaySurface' shader used
     
## Shader and parameters    
     gl.shadername('OverlaySurface') # Other shaders can show overlay outside base image.    
     gl.shaderadjust('diffuse', 0)
     gl.shaderadjust('shininess', 0)
     gl.shaderadjust('specular', 0)
     gl.shaderadjust('ambient', 1)          
     gl.shaderadjust('overlayClip', 1)
     gl.shaderadjust('overlayFuzzy', 1)  
     gl.shaderadjust('overlayDepth', 0) # 
             
## load T1  (layer '0' is the bottom layer because 0 is 1 in Python)       
     layer_number=0  # don't edit this, this is a counter so layer numbers are auto generated 
     print(i)   
     gl.loadimage(i)
     #gl.minmax(layer_number,60,330) # adjust min and max window values - we will use default values for now but will build upon this later re better windowing approaches per modality
     gl.hiddenbycutout(layer_number, 1)  
     gl.opacity(layer_number,100)     


## PET overlay 
 #    layer_number=layer_number+1
 #    gl.overlayload('../../PET_to_T1.nii.gz') # check that this points to the correct PET image that is already registered to the T1
 #    gl.hiddenbycutout(layer_number, 1)
 #    gl.opacity(layer_number,35)    
 #    gl.colorname(layer_number,'jet')   
 #    gl.minmax(layer_number,2000,23000) # check the windowing of this per individual   

      
## for a set of azimuth and elevation values, change the viewing angle and take a screenshot
     for x in [[90,0,'left'],[270,0,'right'],[0,0,'posterior'],[180,0,'anterior'],[0,90,'superior'],[180,-90,'inferior']]:
         gl.azimuthelevation(x[0],x[1])
         gl.wait(200)
         outpath_angle_subdirectory=os.path.join(output_screenshots_directory,'by_angle',x[2])
         if not os.path.isdir(outpath_angle_subdirectory):
             os.makedirs(outpath_angle_subdirectory, exist_ok=True)
         gl.savebmp(os.path.join(outpath_angle_subdirectory,'T1-{}-{}-{}-{}.png'.format(x[2],x[0],x[1],os.path.split(i)[-1].split('.')[0])))

## for a specified viewing angle, and a specified clip plane angle, and a specified range of clip plane depths, take a series of screenshots 
## this is not used in the pipeline but is included for future reference
## need to check the depths list and whether n variable there is correct based on -7
     if n==len(imagelist)-7:
         for slice_display_angle in [[90,0,270,0,'slices_sag_left'],[270,0,90,0,'slices_sag_right'],[180,0,180,0,'slices_anterior'],[0,90,0,90,'slices_superior']]:
             gl.azimuthelevation(slice_display_angle[0],slice_display_angle[1])
             slices=range(5,95,1)
             for z in slices:
                 h=z/100   
                 gl.clipazimuthelevation(h,slice_display_angle[2],slice_display_angle[3])
                 suffix=os.path.split(i)[-1].split('.')[0]
                 sliceno=f'{z:03}'
                 outpath_slice_subdirectory=os.path.join(output_screenshots_directory,slice_display_angle[4])
                 if not os.path.isdir(outpath_slice_subdirectory):
                     os.mkdir(outpath_slice_subdirectory)
                 gl.savebmp(os.path.join(outpath_slice_subdirectory,'{}-{}-{}.png'.format(slice_display_angle[4],sliceno,suffix)))     

gl.quit()


