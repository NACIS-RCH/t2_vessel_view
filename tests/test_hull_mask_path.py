"""Tests that --use-hull-mask passes a NIfTI path to sitk.ReadImage."""

import os
import sys
import tempfile
import unittest
from unittest import mock

# commandline parses argv when masking imports package modules.
sys.argv = [
    "test_hull_mask_path.py",
    "-d",
    "/tmp",
    "-i",
    "/tmp/t1.nii.gz",
]

try:
    import numpy as np
    import SimpleITK as sitk
    from t2vesselviewcode import commandline
    from t2vesselviewcode import dir_structure
    from t2vesselviewcode import masking
    from t2vesselviewcode import make_mask_convex_hull
except ModuleNotFoundError as e:
    np = None
    sitk = None
    commandline = None
    dir_structure = None
    masking = None
    make_mask_convex_hull = None
    _IMPORT_ERROR = e
else:
    _IMPORT_ERROR = None


@unittest.skipIf(masking is None, f"masking import unavailable: {_IMPORT_ERROR}")
class TestHullMaskPath(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mask_dir = os.path.join(self.tmp.name, "Masks")
        os.makedirs(self.mask_dir, exist_ok=True)
        self.input_mask_path = os.path.join(self.mask_dir, "input_mask.nii.gz")
        self.hull_mask_path = os.path.join(
            self.mask_dir, "test_final_hull_mask.nii.gz"
        )
        dummy = sitk.GetImageFromArray(np.ones((8, 8, 8), dtype=np.float32))
        dummy.SetSpacing([1.0, 1.0, 1.0])
        sitk.WriteImage(dummy, self.input_mask_path)
        sitk.WriteImage(dummy, self.hull_mask_path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_use_hull_mask_passes_path_to_readimage(self):
        read_paths = []
        real_read = sitk.ReadImage

        def capturing_read(path, *args, **kwargs):
            read_paths.append(path)
            self.assertIsInstance(path, str)
            return real_read(path, *args, **kwargs)

        with mock.patch.object(commandline.args, "use_hull_mask", True), \
             mock.patch.object(
                 make_mask_convex_hull,
                 "make_hull_mask",
                 return_value=self.hull_mask_path,
             ) as mock_hull, \
             mock.patch.object(
                 dir_structure, "processing_mask_dir", self.mask_dir
             ), \
             mock.patch.object(
                 masking.sitk, "ReadImage", side_effect=capturing_read
             ):
            masking.main_mask_operations(self.input_mask_path)

        mock_hull.assert_called_once_with(self.input_mask_path)
        self.assertGreaterEqual(len(read_paths), 1)
        self.assertEqual(read_paths[0], self.hull_mask_path)
        self.assertIsInstance(read_paths[0], str)


if __name__ == "__main__":
    unittest.main()
