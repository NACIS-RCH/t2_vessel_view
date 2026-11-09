"""Tests for Processing/Masks cleanup helpers."""

import os
import sys
import tempfile
import unittest
from unittest import mock

# commandline parses argv when masking imports package modules.
sys.argv = [
    "test_masks_cleanup.py",
    "-d",
    "/tmp",
    "-i",
    "/tmp/t1.nii.gz",
]

try:
    from t2vesselviewcode import masking
    from t2vesselviewcode import utils
except ModuleNotFoundError as e:
    masking = None
    utils = None
    _IMPORT_ERROR = e
else:
    _IMPORT_ERROR = None


@unittest.skipIf(masking is None, f"masking import unavailable: {_IMPORT_ERROR}")
class TestMasksCleanup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mask_dir = os.path.join(self.tmp.name, "Masks")
        os.makedirs(self.mask_dir, exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _touch(self, name, directory=None):
        directory = directory or self.mask_dir
        path = os.path.join(directory, name)
        parent = os.path.dirname(path)
        os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8"):
            pass
        return path

    def test_cleanup_keeps_preprocessed_mask_removes_rest(self):
        keep_path = self._touch(utils.PREPROCESSED_MASK_FILENAME)
        bet_path = self._touch("test_bet_hires_brain_mask.nii.gz")
        watershed_path = self._touch("watershed_flair_brain_mask.nii.gz")
        work_dir = os.path.join(self.mask_dir, "watershed_work")
        os.makedirs(work_dir, exist_ok=True)
        work_file = self._touch("scratch.nii.gz", directory=work_dir)

        with mock.patch.object(utils, "keep_debug_images", return_value=False):
            masking.cleanup_masks_directory(mask_dir=self.mask_dir)

        self.assertTrue(os.path.isfile(keep_path))
        self.assertFalse(os.path.isfile(bet_path))
        self.assertFalse(os.path.isfile(watershed_path))
        self.assertFalse(os.path.isdir(work_dir))
        self.assertFalse(os.path.isfile(work_file))

    def test_cleanup_skipped_when_keep_debug_images(self):
        keep_path = self._touch(utils.PREPROCESSED_MASK_FILENAME)
        bet_path = self._touch("test_bet_hires_brain_mask.nii.gz")
        work_dir = os.path.join(self.mask_dir, "watershed_work")
        os.makedirs(work_dir, exist_ok=True)

        with mock.patch.object(utils, "keep_debug_images", return_value=True):
            masking.cleanup_masks_directory(mask_dir=self.mask_dir)

        self.assertTrue(os.path.isfile(keep_path))
        self.assertTrue(os.path.isfile(bet_path))
        self.assertTrue(os.path.isdir(work_dir))

    def test_cleanup_does_not_delete_outside_masks_dir(self):
        outside_dir = tempfile.TemporaryDirectory()
        try:
            outside_file = os.path.join(outside_dir.name, "user_original_mask.nii.gz")
            with open(outside_file, "w", encoding="utf-8"):
                pass
            keep_path = self._touch(utils.PREPROCESSED_MASK_FILENAME)
            inside_file = self._touch("hull_mask.nii.gz")

            with mock.patch.object(utils, "keep_debug_images", return_value=False):
                # Only cleans children of mask_dir; outside path is never listed.
                masking.cleanup_masks_directory(mask_dir=self.mask_dir)

            self.assertTrue(os.path.isfile(outside_file))
            self.assertTrue(os.path.isfile(keep_path))
            self.assertFalse(os.path.isfile(inside_file))
        finally:
            outside_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
