"""Tests for selective directory creation and empty-directory pruning."""

import os
import sys
import tempfile
import unittest
from types import SimpleNamespace

# commandline parses argv when dir_structure imports it.
sys.argv = [
    "test_dir_structure_cleanup.py",
    "-d",
    "/tmp",
    "-i",
    "/tmp/t1.nii.gz",
]

from t2vesselviewcode import dir_structure


class TestDirStructureCleanup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "T2VesselView")

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_directories_only_used_modalities(self):
        dir_structure._set_t2vv_root(self.root)
        args = SimpleNamespace(
            flair=None,
            t2_cor="/fake/t2_cor.nii.gz",
            t2_tra=None,
            t2_sag=None,
            t2_sag_left=None,
            t2_sag_right=None,
            t2_3d=None,
        )

        dir_structure.create_directories(args)

        self.assertTrue(os.path.isdir(dir_structure.processed_t1_dir))
        self.assertTrue(os.path.isdir(dir_structure.eroded_nifti_t1_dir))
        self.assertTrue(os.path.isdir(dir_structure.processed_t2_cor_dir))
        self.assertTrue(os.path.isdir(dir_structure.eroded_nifti_t2_cor_dir))
        self.assertFalse(os.path.isdir(dir_structure.processed_flair_dir))
        self.assertFalse(os.path.isdir(dir_structure.eroded_nifti_flair_dir))
        self.assertFalse(os.path.isdir(dir_structure.processed_t2_tra_dir))
        self.assertFalse(os.path.isdir(dir_structure.eroded_nifti_t2_tra_dir))
        self.assertFalse(os.path.isdir(dir_structure.powerpoints_dir))
        self.assertFalse(os.path.isdir(dir_structure.dicom_dir))
        self.assertFalse(os.path.isdir(dir_structure.renders_t1_dir))

    def test_create_directories_includes_sag_when_left_right(self):
        dir_structure._set_t2vv_root(self.root)
        args = SimpleNamespace(
            flair=None,
            t2_cor=None,
            t2_tra=None,
            t2_sag=None,
            t2_sag_left="/fake/left.nii.gz",
            t2_sag_right="/fake/right.nii.gz",
            t2_3d=None,
        )

        dir_structure.create_directories(args)

        self.assertTrue(os.path.isdir(dir_structure.processed_t2_sag_dir))
        self.assertTrue(os.path.isdir(dir_structure.eroded_nifti_t2_sag_dir))

    def test_prune_removes_empty_keeps_nonempty(self):
        dir_structure._set_t2vv_root(self.root)

        empty_a = os.path.join(self.root, "Processing", "Preprocessed_FLAIR")
        empty_b = os.path.join(self.root, "Dicom")
        keep_dir = os.path.join(self.root, "Eroded_nifti", "T1")
        os.makedirs(empty_a, exist_ok=True)
        os.makedirs(empty_b, exist_ok=True)
        os.makedirs(keep_dir, exist_ok=True)
        keep_file = os.path.join(keep_dir, "005_eroded_t1.nii.gz")
        with open(keep_file, "w", encoding="utf-8"):
            pass

        removed = dir_structure.prune_empty_directories(self.root)

        self.assertGreaterEqual(removed, 2)
        self.assertFalse(os.path.isdir(empty_a))
        self.assertFalse(os.path.isdir(empty_b))
        self.assertTrue(os.path.isfile(keep_file))
        self.assertTrue(os.path.isdir(self.root))

    def test_prune_does_not_remove_root(self):
        os.makedirs(self.root, exist_ok=True)
        dir_structure._set_t2vv_root(self.root)

        removed = dir_structure.prune_empty_directories(self.root)

        self.assertEqual(removed, 0)
        self.assertTrue(os.path.isdir(self.root))


if __name__ == "__main__":
    unittest.main()
