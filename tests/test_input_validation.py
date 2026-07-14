"""
Test script for input validation module.
"""

import os
import unittest
import tempfile
import SimpleITK as sitk
import numpy as np
from pathlib import Path
import pydicom
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid

from t2vesselviewcode.input_validation import (
    detect_image_format,
    validate_image_dimensions,
    validate_image_orientation,
    validate_input_files,
    create_output_directories,
    convert_dicom_to_nifti
)

class TestInputValidation(unittest.TestCase):
    def setUp(self):
        # Create temporary directory for test files
        self.test_dir = tempfile.mkdtemp()
        
        # Create a simple test NIfTI image
        self.test_nifti_path = os.path.join(self.test_dir, "test.nii.gz")
        test_image = sitk.GetImageFromArray(np.zeros((100, 100, 100)))
        sitk.WriteImage(test_image, self.test_nifti_path)
        
        # Create a simple test DICOM image
        self.test_dicom_path = os.path.join(self.test_dir, "test.dcm")
        test_image = sitk.GetImageFromArray(np.zeros((100, 100)))
        sitk.WriteImage(test_image, self.test_dicom_path)

    def _save_metadata_dicom(self, folder, filename, series_uid, series_description):
        path = os.path.join(folder, filename)
        file_meta = FileMetaDataset()
        file_meta.FileMetaInformationVersion = b'\x00\x01'
        file_meta.MediaStorageSOPClassUID = pydicom.uid.SecondaryCaptureImageStorage
        file_meta.MediaStorageSOPInstanceUID = generate_uid()
        file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        file_meta.ImplementationClassUID = generate_uid()

        ds = FileDataset(path, {}, file_meta=file_meta, preamble=b'\0' * 128)
        ds.is_little_endian = True
        ds.is_implicit_VR = False
        ds.SOPClassUID = pydicom.uid.SecondaryCaptureImageStorage
        ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
        ds.SeriesInstanceUID = series_uid
        ds.SeriesDescription = series_description
        ds.ProtocolName = series_description
        ds.PatientID = "TEST"
        ds.PatientName = "Test^Patient"
        ds.StudyInstanceUID = generate_uid()
        pydicom.dcmwrite(path, ds, write_like_original=False)
        return path
    
    def tearDown(self):
        # Clean up temporary directory
        import shutil
        shutil.rmtree(self.test_dir)
    
    def test_detect_image_format(self):
        # Test NIfTI detection
        self.assertEqual(detect_image_format(self.test_nifti_path), 'nifti')

        # Test DICOM folder detection
        dicom_dir = os.path.join(self.test_dir, "dicom_series")
        os.makedirs(dicom_dir, exist_ok=True)
        dicom_in_dir_path = os.path.join(dicom_dir, "slice001.dcm")
        test_image = sitk.GetImageFromArray(np.zeros((100, 100)))
        sitk.WriteImage(test_image, dicom_in_dir_path)
        self.assertEqual(detect_image_format(dicom_dir), 'dicom')
        
        # Test invalid file
        with self.assertRaises(ValueError):
            detect_image_format(os.path.join(self.test_dir, "invalid.txt"))
    
    def test_validate_image_dimensions(self):
        # Create test image
        test_image = sitk.GetImageFromArray(np.zeros((100, 100, 100)))
        
        # Test valid dimensions
        is_valid, message = validate_image_dimensions(test_image)
        self.assertTrue(is_valid)
        self.assertEqual(message, "Image dimensions valid")
        
        # Test invalid dimensions (2D)
        test_image_2d = sitk.GetImageFromArray(np.zeros((100, 100)))
        is_valid, message = validate_image_dimensions(test_image_2d)
        self.assertFalse(is_valid)
        self.assertIn("Expected 3D image", message)
    
    def test_validate_image_orientation(self):
        # Create test image with valid orientation
        test_image = sitk.GetImageFromArray(np.zeros((100, 100, 100)))
        
        # Test valid orientation
        is_valid, message = validate_image_orientation(test_image)
        self.assertTrue(is_valid)
        self.assertEqual(message, "Image orientation valid")
        
        # Create test image with invalid orientation
        test_image.SetDirection([1, 0, 0, 0, 1, 0, 0, 0, 2])  # Non-orthogonal matrix
        is_valid, message = validate_image_orientation(test_image)
        self.assertFalse(is_valid)
        self.assertIn("Direction cosine matrix is not orthogonal", message)
    
    def test_validate_input_files(self):
        # Test with valid inputs
        is_valid, errors = validate_input_files(
            self.test_nifti_path,
            self.test_dir,
            {'t2': self.test_nifti_path}
        )
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)
        
        # Test with missing required file
        is_valid, errors = validate_input_files(
            "nonexistent.nii.gz",
            self.test_dir
        )
        self.assertFalse(is_valid)
        self.assertGreater(len(errors), 0)

    def test_validate_input_files_accepts_single_dicom_series_folder(self):
        dicom_dir = os.path.join(self.test_dir, "single_series")
        os.makedirs(dicom_dir, exist_ok=True)
        series_uid = generate_uid()
        self._save_metadata_dicom(dicom_dir, "slice001.dcm", series_uid, "T1_MPRAGE")
        self._save_metadata_dicom(dicom_dir, "slice002.dcm", series_uid, "T1_MPRAGE")

        is_valid, errors = validate_input_files(dicom_dir, self.test_dir)

        self.assertTrue(is_valid)
        self.assertEqual(errors, [])

    def test_validate_input_files_rejects_mixed_dicom_series_folder(self):
        dicom_dir = os.path.join(self.test_dir, "mixed_series")
        os.makedirs(dicom_dir, exist_ok=True)
        self._save_metadata_dicom(dicom_dir, "slice001.dcm", generate_uid(), "T1_MPRAGE")
        self._save_metadata_dicom(dicom_dir, "slice002.dcm", generate_uid(), "T2_FLAIR")

        is_valid, errors = validate_input_files(dicom_dir, self.test_dir)

        self.assertFalse(is_valid)
        self.assertTrue(any("multiple DICOM series" in error for error in errors))
        self.assertTrue(any("Please specify the exact DICOM series folder" in error for error in errors))
    
    def test_create_output_directories(self):
        # Test directory creation
        create_output_directories(self.test_dir)
        
        # Verify key directories were created
        expected_dirs = [
            "T2VesselView",
            "T2VesselView/Processing",
            "T2VesselView/3D_renders_png"
        ]
        for dir_name in expected_dirs:
            full_path = os.path.join(self.test_dir, dir_name)
            self.assertTrue(os.path.exists(full_path))
            self.assertTrue(os.path.isdir(full_path))

if __name__ == '__main__':
    unittest.main() 