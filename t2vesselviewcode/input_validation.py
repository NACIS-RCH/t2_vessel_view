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

# TODO: check OS?

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
    # DICOM folders need special handling because pydicom.dcmread reads one file,
    # not a directory. Inspect candidate files and stop as soon as one is valid.
    for candidate_path in _dicom_candidate_paths(file_path):
        try:
            pydicom.dcmread(candidate_path, stop_before_pixels=True)
            return 'dicom'
        except (pydicom.errors.InvalidDicomError, IOError, IsADirectoryError):
            continue
    
    try:
        # If DICOM reading fails, try to read the original path as NIfTI.
        nib.load(file_path)
        return 'nifti'
    except (nib.loadsave.ImageFileError, IOError):
        # If both attempts fail, the path is neither DICOM nor NIfTI.
        raise ValueError(f"Could not determine format of {file_path}")


def _dicom_candidate_paths(input_path: str) -> List[str]:
    """Return candidate file paths from a DICOM file or folder."""
    if os.path.isdir(input_path):
        candidate_paths = []
        for root, _, files in os.walk(input_path):
            for filename in sorted(files):
                candidate_paths.append(os.path.join(root, filename))
        return candidate_paths
    return [input_path]


def _read_dicom_series_identity(file_path: str) -> Optional[Dict[str, str]]:
    """Read DICOM series identity metadata from one file."""
    try:
        # Read only the header metadata; pixel data is not needed for validation.
        ds = pydicom.dcmread(file_path, stop_before_pixels=True)
    except Exception:
        # Non-DICOM files can exist in exported folders, so skip unreadable files.
        return None

    # SeriesInstanceUID is the strict DICOM identifier for one acquisition series.
    series_uid = str(getattr(ds, "SeriesInstanceUID", "") or "UNKNOWN_SERIES_UID")
    # Description/protocol are used only to make error messages readable.
    series_description = str(getattr(ds, "SeriesDescription", "") or "")
    protocol_name = str(getattr(ds, "ProtocolName", "") or "")
    # Prefer the scanner series description, then protocol name, then a fallback.
    label = series_description or protocol_name or "Unnamed series"
    return {
        "series_uid": series_uid,
        "series_description": series_description,
        "protocol_name": protocol_name,
        "label": label,
    }


def _short_uid(uid: str) -> str:
    """Return a readable suffix for long DICOM UIDs."""
    # Short UIDs are already readable enough to show in full.
    if len(uid) <= 12:
        return uid
    # Long DICOM UIDs are hard to scan, so show the final characters with ellipsis.
    return "..." + uid[-12:]


def validate_dicom_folder_single_series(input_path: str, modality_label: str = "Input") -> Tuple[bool, str]:
    """Validate that a DICOM folder contains exactly one SeriesInstanceUID."""
    # A single DICOM file is already an exact input, so no folder-level check is needed.
    if not os.path.isdir(input_path):
        return True, "DICOM file input"

    # Store one readable metadata example for each SeriesInstanceUID found.
    series_by_uid = {}
    # Walk all files in the folder, including nested subfolders from scanner exports.
    for candidate_path in _dicom_candidate_paths(input_path):
        identity = _read_dicom_series_identity(candidate_path)
        # Skip non-DICOM/read-failed files; many exports include sidecar files.
        if identity is None:
            continue
        # Group by SeriesInstanceUID, the strict DICOM identifier for one series.
        uid = identity["series_uid"]
        if uid not in series_by_uid:
            series_by_uid[uid] = identity

    # If nothing readable was found, this folder is not usable as a DICOM input.
    if not series_by_uid:
        return False, f"{modality_label} DICOM folder contains no readable DICOM files: {input_path}"

    # Exactly one UID means the folder appears to contain one acquisition series.
    if len(series_by_uid) == 1:
        identity = next(iter(series_by_uid.values()))
        return True, f"Single DICOM series detected: {identity['label']} ({identity['series_uid']})"

    # Multiple UIDs means the folder is ambiguous, usually a study-level folder.
    series_labels = []
    for identity in series_by_uid.values():
        # Include a readable label plus shortened UID so users can identify the series.
        series_labels.append(
            f"{identity['label']} (SeriesInstanceUID {_short_uid(identity['series_uid'])})"
        )
    # Fail early with guidance to point each CLI input at one exact series.
    return (
        False,
        f"{modality_label} DICOM folder contains multiple DICOM series: "
        f"{', '.join(series_labels)}. Please specify the exact DICOM series folder "
        "or a single DICOM file path for this input."
    )


def extract_dicom_metadata(input_path: str) -> Dict[str, str]:
    """Return PatientID, PatientName, StudyDate, and StudyTime from a DICOM file or folder."""
    for path in _dicom_candidate_paths(input_path):
        try:
            ds = pydicom.dcmread(path, stop_before_pixels=True)
            return {
                "patient_id": str(getattr(ds, "PatientID", "") or ""),
                "patient_name": str(getattr(ds, "PatientName", "") or ""),
                "study_date": str(getattr(ds, "StudyDate", "") or ""),
                "study_time": str(getattr(ds, "StudyTime", "") or ""),
                "study_instance_uid": str(getattr(ds, "StudyInstanceUID", "") or ""),
            }
        except Exception:
            continue
    raise ValueError(f"Could not read DICOM metadata from: {input_path}")


def extract_dicom_patient_id(input_path: str) -> Optional[str]:
    """Return PatientID from a DICOM file or folder, if one is available."""
    try:
        metadata = extract_dicom_metadata(input_path)
        patient_id = metadata.get("patient_id", "")
        return patient_id if patient_id else None
    except ValueError:
        return None

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
            if t1_format == 'dicom':
                series_ok, series_message = validate_dicom_folder_single_series(t1_path, "T1")
                if not series_ok:
                    errors.append(series_message)
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
                    if img_format == 'dicom':
                        series_ok, series_message = validate_dicom_folder_single_series(
                            path,
                            modality.upper()
                        )
                        if not series_ok:
                            errors.append(series_message)
                except ValueError as e:
                    errors.append(str(e))
    
    # Return True if no errors were found, False otherwise
    return len(errors) == 0, errors


def validate_mask_voxel_dimensions(
    mask_path: str,
    reference_image: sitk.Image,
    spacing_tolerance: float = 1e-3
) -> Tuple[bool, str]:
    """
    Validate that a user mask has compatible voxel dimensions with the main image.

    This function intentionally checks only voxel dimensions and image grid size:
    - spacing (voxel size) must match within tolerance
    - grid size must match exactly
    It does NOT check registration/alignment (origin, direction, transform quality).

    Parameters
    ----------
    mask_path : str
        Path to the user-provided mask file.
    reference_image : sitk.Image
        The reference main image (preprocessed main image in this pipeline).
    spacing_tolerance : float
        Absolute tolerance for spacing comparison in mm.

    Returns
    -------
    Tuple[bool, str]
        (True, message) if compatible; otherwise (False, error_message).
    """
    if not os.path.exists(mask_path):
        return False, f"Mask file not found: {mask_path}"

    try:
        mask_image = sitk.ReadImage(mask_path)
    except Exception as e:
        return False, f"Could not read mask file: {e}"

    # Check image dimensionality first (must both be 3D in this pipeline).
    if mask_image.GetDimension() != reference_image.GetDimension():
        return (
            False,
            "Voxel dimensions of mask do not match those of main image: "
            f"mask dimension={mask_image.GetDimension()}D, "
            f"main image dimension={reference_image.GetDimension()}D."
        )

    # Check voxel spacing with a strict tolerance.
    mask_spacing = tuple(float(v) for v in mask_image.GetSpacing())
    ref_spacing = tuple(float(v) for v in reference_image.GetSpacing())
    spacing_matches = np.allclose(mask_spacing, ref_spacing, atol=spacing_tolerance, rtol=0.0)
    if not spacing_matches:
        return (
            False,
            "Voxel dimensions of mask do not match those of main image. "
            f"Mask spacing={mask_spacing}, main image spacing={ref_spacing}."
        )

    # Check grid size because downstream overlay/multiplication expects same voxel grid shape.
    if mask_image.GetSize() != reference_image.GetSize():
        return (
            False,
            "Mask grid size does not match main image grid size. "
            f"Mask size={mask_image.GetSize()}, main image size={reference_image.GetSize()}."
        )

    return True, "Mask voxel dimensions are compatible with main image."

