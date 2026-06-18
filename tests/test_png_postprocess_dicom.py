"""
Tests for exporting stitched PNG panels to DICOM Secondary Capture files.
"""

import os
import sys
import tempfile
import unittest

from PIL import Image
import pydicom
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid


class TestPngPostprocessDicom(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.png_dir = os.path.join(self.test_dir, "stitched_overview")
        self.dicom_root = os.path.join(self.test_dir, "Dicom")
        os.makedirs(self.png_dir, exist_ok=True)

        # png_postprocess imports dir_structure, which parses CLI arguments at import time.
        sys.argv = [
            "test_png_postprocess_dicom.py",
            "-d",
            self.test_dir,
            "-i",
            os.path.join(self.test_dir, "dummy_t1.nii.gz"),
        ]

    def tearDown(self):
        import shutil
        shutil.rmtree(self.test_dir)

    def _save_test_png(self, name, color):
        path = os.path.join(self.png_dir, name)
        Image.new("RGB", (8, 6), color=color).save(path)
        return path

    def _save_test_metadata_dicom(self, name="metadata_source.dcm"):
        path = os.path.join(self.test_dir, name)
        sop_instance_uid = generate_uid()

        file_meta = FileMetaDataset()
        file_meta.FileMetaInformationVersion = b'\x00\x01'
        file_meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
        file_meta.MediaStorageSOPInstanceUID = sop_instance_uid
        file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        file_meta.ImplementationClassUID = generate_uid()

        ds = FileDataset(path, {}, file_meta=file_meta, preamble=b'\0' * 128)
        ds.is_little_endian = True
        ds.is_implicit_VR = False
        ds.SOPClassUID = SecondaryCaptureImageStorage
        ds.SOPInstanceUID = sop_instance_uid
        ds.PatientID = "UR12345"
        ds.PatientName = "Test^Patient"
        ds.StudyDate = "20240131"
        ds.StudyTime = "093015"
        ds.Modality = "PT"
        pydicom.dcmwrite(path, ds, write_like_original=False)
        return path

    def test_export_png_series_to_dicom_folder(self):
        from t2vesselviewcode.input_validation import extract_dicom_metadata
        from t2vesselviewcode.png_postprocess import export_png_series_to_dicom_folder

        self._save_test_png("concat_001.png", (255, 0, 0))
        self._save_test_png("concat_000.png", (0, 255, 0))
        metadata = extract_dicom_metadata(self._save_test_metadata_dicom())

        saved_paths = export_png_series_to_dicom_folder(
            self.png_dir,
            "T1_overlay_overview",
            "T1 erosion render + PET overlay",
            patient_id=metadata["patient_id"],
            patient_name=metadata["patient_name"],
            study_date=metadata["study_date"],
            study_time=metadata["study_time"],
            output_root=self.dicom_root,
        )

        self.assertEqual(len(saved_paths), 2)
        self.assertEqual([os.path.basename(p) for p in saved_paths], ["0001.dcm", "0002.dcm"])

        first = pydicom.dcmread(saved_paths[0])
        second = pydicom.dcmread(saved_paths[1])

        self.assertEqual(first.Modality, "OT")
        self.assertEqual(first.SOPClassUID.name, "Secondary Capture Image Storage")
        self.assertEqual(first.PatientID, "UR12345")
        self.assertEqual(str(first.PatientName), "Test^Patient")
        self.assertEqual(first.StudyDate, "20240131")
        self.assertEqual(first.StudyTime, "093015")
        self.assertEqual(first.SeriesDescription, "T1 erosion render + PET overlay")
        self.assertFalse(hasattr(first, "ProtocolName"))
        self.assertEqual(
            first.ImageComments,
            "Postprocessed T1 and coregistered overlay image, non-quantitative"
        )
        self.assertEqual(first.InstanceNumber, 1)
        self.assertEqual(second.InstanceNumber, 2)
        self.assertEqual(first.StudyInstanceUID, second.StudyInstanceUID)
        self.assertEqual(first.SeriesInstanceUID, second.SeriesInstanceUID)
        self.assertEqual(first.Rows, 6)
        self.assertEqual(first.Columns, 8)
        self.assertEqual(first.PhotometricInterpretation, "RGB")
        self.assertEqual(len(first.PixelData), 8 * 6 * 3)


if __name__ == "__main__":
    unittest.main()
