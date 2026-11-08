"""Tests for preprocess intermediate cleanup helpers."""

import os
import sys
import tempfile
import unittest
from unittest import mock

# commandline parses argv when preprocess imports package modules.
sys.argv = [
    "test_preprocess_cleanup.py",
    "-d",
    "/tmp",
    "-i",
    "/tmp/t1.nii.gz",
]

try:
    from t2vesselviewcode import preprocess
except ModuleNotFoundError as e:
    preprocess = None
    _IMPORT_ERROR = e
else:
    _IMPORT_ERROR = None


@unittest.skipIf(preprocess is None, f"preprocess import unavailable: {_IMPORT_ERROR}")
class TestPreprocessCleanup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.outdir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _touch(self, name):
        path = os.path.join(self.outdir, name)
        with open(path, "w", encoding="utf-8"):
            pass
        return path

    def test_cleanup_removes_intermediates_keeps_final(self):
        final_path = self._touch("Preprocessed_t2_cor.nii.gz")
        ro_path = self._touch("t2_cor_ro.nii.gz")
        n4_path = self._touch("t2_cor_n4.nii.gz")
        reg_path = self._touch("registered_t2_cor.nii.gz")

        with mock.patch.object(preprocess, "_keep_debug_images", return_value=False):
            preprocess._cleanup_preprocess_intermediates(
                self.outdir,
                paths=[ro_path, n4_path, reg_path],
                kept_label="Preprocessed_t2_cor.nii.gz",
            )

        self.assertTrue(os.path.isfile(final_path))
        self.assertFalse(os.path.isfile(ro_path))
        self.assertFalse(os.path.isfile(n4_path))
        self.assertFalse(os.path.isfile(reg_path))

    def test_cleanup_skipped_when_keep_debug_images(self):
        ro_path = self._touch("t2_cor_ro.nii.gz")
        n4_path = self._touch("t2_cor_n4.nii.gz")

        with mock.patch.object(preprocess, "_keep_debug_images", return_value=True):
            preprocess._cleanup_preprocess_intermediates(
                self.outdir,
                paths=[ro_path, n4_path],
                kept_label="Preprocessed_t2_cor.nii.gz",
            )

        self.assertTrue(os.path.isfile(ro_path))
        self.assertTrue(os.path.isfile(n4_path))

    def test_cleanup_does_not_delete_outside_processing_dir(self):
        outside_dir = tempfile.TemporaryDirectory()
        try:
            outside_file = os.path.join(outside_dir.name, "user_original.nii.gz")
            with open(outside_file, "w", encoding="utf-8"):
                pass
            inside_file = self._touch("t2_cor_ro.nii.gz")

            with mock.patch.object(preprocess, "_keep_debug_images", return_value=False):
                preprocess._cleanup_preprocess_intermediates(
                    self.outdir,
                    paths=[outside_file, inside_file],
                    kept_label="Preprocessed_t2_cor.nii.gz",
                )

            self.assertTrue(os.path.isfile(outside_file))
            self.assertFalse(os.path.isfile(inside_file))
        finally:
            outside_dir.cleanup()

    def test_remove_glob_to_roi_pattern(self):
        final_path = self._touch("Preprocessed_main_image.nii.gz")
        crop_path = self._touch("T1_crop.nii.gz")
        roi_path = self._touch("T1_crop_to_ROI.nii.gz")

        with mock.patch.object(preprocess, "_keep_debug_images", return_value=False):
            preprocess._cleanup_preprocess_intermediates(
                self.outdir,
                paths=[crop_path],
                glob_patterns=["*to_ROI*", "*_to_roi*"],
                kept_label="Preprocessed_main_image.nii.gz",
            )

        self.assertTrue(os.path.isfile(final_path))
        self.assertFalse(os.path.isfile(crop_path))
        self.assertFalse(os.path.isfile(roi_path))

    def test_robustfov_side_products_stay_in_temporary_work_dir(self):
        input_path = self._touch("t1_ro.nii.gz")
        crop = mock.Mock()
        crop.inputs = mock.Mock()
        run_details = {}

        def fake_run(cwd):
            run_details["cwd"] = cwd
            run_details["transform"] = crop.inputs.out_transform
            self.assertTrue(os.path.isdir(cwd))
            with open(crop.inputs.out_roi, "w", encoding="utf-8"):
                pass
            with open(crop.inputs.out_transform, "w", encoding="utf-8"):
                pass
            with open(
                os.path.join(cwd, "unexpected_to_ROI.nii"),
                "w",
                encoding="utf-8",
            ):
                pass

        crop.run.side_effect = fake_run
        with mock.patch.object(
            preprocess.fsl,
            "RobustFOV",
            return_value=crop,
        ):
            output_path = preprocess._run_robustfov_crop(
                input_path,
                self.outdir,
                brainsize=180,
            )

        expected_crop = os.path.join(self.outdir, "T1_crop.nii.gz")
        self.assertEqual(output_path, expected_crop)
        self.assertEqual(crop.inputs.in_file, os.path.abspath(input_path))
        self.assertEqual(crop.inputs.out_roi, expected_crop)
        self.assertEqual(crop.inputs.brainsize, 180)
        self.assertEqual(
            os.path.dirname(run_details["transform"]),
            run_details["cwd"],
        )
        self.assertTrue(run_details["transform"].endswith(".mat"))
        self.assertFalse(os.path.exists(run_details["cwd"]))
        self.assertFalse(os.path.exists(run_details["transform"]))
        self.assertFalse(
            os.path.exists(os.path.join(self.outdir, "t1_ro_to_ROI.nii"))
        )
        crop.run.assert_called_once_with(cwd=run_details["cwd"])


if __name__ == "__main__":
    unittest.main()
