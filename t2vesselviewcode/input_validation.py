"""
Input validation module for T2 Vessel View pipeline.
Handles validation of medical image inputs, format detection, and initial setup.

1. Detecting if images are in DICOM or NIfTI format
2. Validating image dimensions and orientation
3. Creating the necessary folder structure for outputs
4. Converting DICOM images to NIfTI format if needed
"""

# Import required Python libraries
import os  # For handling file paths and directory operations
import logging  # For creating log messages to track what the program is doing
import SimpleITK as sitk  # Main library for medical image processing
import nibabel as nib  # Library for reading NIfTI format images
import pydicom  # Library for reading DICOM format images
import numpy as np  # For numerical operations
from pathlib import Path  # Modern way to handle file paths
from typing import Dict, List, Optional, Tuple, Union  # Type hints for better code documentation

# Set up logging configuration
# This creates a logger that will show timestamps and message levels
logging.basicConfig(
    level=logging.INFO,  # Show all messages of INFO level and above
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'  # Format of log messages
)
logger = logging.getLogger(__name__)  # Create a logger for this specific module

def detect_image_format(file_path: str) -> str:
    """
    Detect if input file is DICOM or NIfTI format.
    
    This function tries to read the file as both DICOM and NIfTI format.
    It will return the format that successfully reads the file.
    
    Args:
        file_path: Path to the input image file (e.g., 'path/to/image.nii.gz' or 'path/to/image.dcm')
        
    Returns:
        str: Either 'dicom' or 'nifti' depending on the file format
        
    Raises:
        ValueError: If the file format cannot be determined (not DICOM or NIfTI)
    """
    try:
        # First try to read the file as a DICOM image
        pydicom.dcmread(file_path)
        return 'dicom'
    except (pydicom.errors.InvalidDicomError, IOError):
        try:
            # If DICOM reading fails, try to read as NIfTI
            nib.load(file_path)
            return 'nifti'
        except (nib.loadsave.ImageFileError, IOError):
            # If both attempts fail, the file is neither DICOM nor NIfTI
            raise ValueError(f"Could not determine format of {file_path}")

def validate_image_dimensions(image: sitk.Image) -> Tuple[bool, str]:
    """
    Validate image dimensions and orientation.
    
    This function checks if the image is 3D and has reasonable dimensions.
    Medical images should be 3D (volume) and have sufficient size for processing.
    
    Args:
        image: SimpleITK image object (the loaded medical image)
        
    Returns:
        Tuple[bool, str]: A tuple containing:
            - bool: True if dimensions are valid, False otherwise
            - str: A message explaining the validation result
    """
    # Get the number of dimensions in the image
    # Should be 3 for a 3D volume (x, y, z)
    dims = image.GetDimension()
    if dims != 3:
        return False, f"Expected 3D image, got {dims}D"
    
    # Get the size of each dimension
    # This tells us how many voxels (3D pixels) are in each direction
    size = image.GetSize()
    if any(s < 10 for s in size):
        return False, f"Image dimensions too small: {size}"
    
    return True, "Image dimensions valid"

def validate_image_orientation(image: sitk.Image) -> Tuple[bool, str]:
    """
    Validate image orientation and direction cosine matrix.
    
    This function checks if the image's orientation is valid.
    The direction cosine matrix tells us how the image is oriented in 3D space.

    
    Args:
        image: SimpleITK image object (the loaded medical image)
        
    Returns:
        Tuple[bool, str]: A tuple containing:
            - bool: True if orientation is valid, False otherwise
            - str: A message explaining the validation result
    """
    # Get the direction cosine matrix
    # This is a 3x3 matrix that describes how the image is oriented in space
    direction = image.GetDirection()
    if len(direction) != 9:
        return False, "Invalid direction cosine matrix"
    
    # Convert the direction matrix to a numpy array and reshape to 3x3
    # This makes it easier to perform matrix operations
    dir_matrix = np.array(direction).reshape(3, 3)
    
    # Check if the matrix is orthogonal
    # For a valid medical image, the axes should be perpendicular to each other
    if not np.allclose(np.dot(dir_matrix, dir_matrix.T), np.eye(3), atol=1e-6):
        return False, "Direction cosine matrix is not orthogonal"
    
    return True, "Image orientation valid"

def validate_input_files(
    t1_path: str,
    output_dir: str,
    optional_paths: Optional[Dict[str, str]] = None
) -> Tuple[bool, List[str]]:
    """
    Validate all input files and create output directory structure.
    
    This function checks:
    1. If the required T1 image exists
    2. If any optional images (T2, FLAIR) exist
    3. If all images are in a valid format
    
    Args:
        t1_path: Path to T1 image (required)
        output_dir: Base output directory where results will be saved
        optional_paths: Dictionary of optional input paths (e.g., {'t2': path, 'flair': path})
        
    Returns:
        Tuple[bool, List[str]]: A tuple containing:
            - bool: True if all validations pass, False otherwise
            - List[str]: List of any error messages encountered
    """
    errors = []  # List to store any error messages
    
    # Validate T1 image (required)
    if not os.path.exists(t1_path):
        errors.append(f"T1 image not found: {t1_path}")
    else:
        try:
            # Try to detect the format of the T1 image
            t1_format = detect_image_format(t1_path)
            logger.info(f"T1 image format: {t1_format}")
        except ValueError as e:
            errors.append(str(e))
    
    # Validate optional inputs (T2, FLAIR, etc.)
    if optional_paths:
        for modality, path in optional_paths.items():
            if path and not os.path.exists(path):
                errors.append(f"{modality.upper()} image not found: {path}")
            elif path:
                try:
                    # Try to detect the format of each optional image
                    img_format = detect_image_format(path)
                    logger.info(f"{modality.upper()} image format: {img_format}")
                except ValueError as e:
                    errors.append(str(e))
    
    # Return True if no errors were found, False otherwise
    return len(errors) == 0, errors

