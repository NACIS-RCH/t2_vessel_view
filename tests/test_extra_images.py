"""Tests for named extra T1-like structural image support."""

import argparse
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

# Main/preprocess/dir_structure imports trigger commandline parsing.
sys.argv = [
    "test_extra_images.py",
    "-d",
    "/tmp",
    "-i",
    "/tmp/t1.nii.gz",
]

from t2vesselviewcode import dir_structure
from t2vesselviewcode import extra_images
from t2vesselviewcode import masking
from t2vesselviewcode import panel_config
from t2vesselviewcode import preprocess
from t2vesselviewcode import t2_vessel_view_main


class TestExtraImages(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "T2VesselView")
        dir_structure._set_t2vv_root(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def _touch(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as stream:
            stream.write(b"test")
        return path

    def test_parse_name_path_normalizes_and_preserves_equals_in_path(self):
        path = self._touch(os.path.join(self.tmp.name, "scan=post.nii.gz"))
        parsed = extra_images.parse_extra_image_spec(f"T1_GD={path}")
        self.assertEqual(parsed, {"name": "t1_gd", "path": path})

    def test_parse_rejects_invalid_reserved_missing_and_duplicate_names(self):
        path = self._touch(os.path.join(self.tmp.name, "scan.nii.gz"))
        for value in (
            f"1prior={path}",
            f"bad name={path}",
            f"t1={path}",
            f"missing={self.tmp.name}/missing.nii.gz",
            "no_equals",
        ):
            with self.subTest(value=value):
                with self.assertRaises(argparse.ArgumentTypeError):
                    extra_images.parse_extra_image_spec(value)

        with self.assertRaisesRegex(ValueError, "Duplicate"):
            extra_images.validate_extra_image_specs([
                {"name": "t1_gd", "path": path},
                {"name": "t1_gd", "path": path},
            ])

    def test_dynamic_directories_and_preprocess_routing(self):
        args = SimpleNamespace(
            flair=None,
            t2_cor=None,
            t2_tra=None,
            t2_sag=None,
            t2_sag_left=None,
            t2_sag_right=None,
            t2_3d=None,
            extra_images=[
                {"name": "t1_gd", "path": "/tmp/gd.nii.gz"},
                {"name": "t1_prior", "path": "/tmp/prior.nii.gz"},
            ],
        )
        directories = dir_structure.modality_directories_for_args(args)
        gd_processed = os.path.join(
            dir_structure.processing_dir,
            "Preprocessed_Extra",
            "t1_gd",
        )
        prior_eroded = os.path.join(
            dir_structure.eroded_nifti_dir,
            "Extra",
            "t1_prior",
        )
        self.assertIn(gd_processed, directories)
        self.assertIn(prior_eroded, directories)
        self.assertEqual(
            preprocess.get_preprocessed_dir("extra_t1_gd"),
            gd_processed,
        )

    def test_discovers_only_named_extra_folders_with_eroded_files(self):
        gd_path = self._touch(
            os.path.join(
                dir_structure.eroded_nifti_dir,
                "Extra",
                "t1_gd",
                "035_eroded_extra_t1_gd.nii.gz",
            )
        )
        os.makedirs(
            os.path.join(
                dir_structure.eroded_nifti_dir,
                "Extra",
                "empty_extra",
            )
        )
        discovered = extra_images.discover_eroded_extras(
            dir_structure.eroded_nifti_dir
        )
        self.assertEqual(discovered, {"t1_gd": [gd_path]})

    def test_render_existing_validation_counts_discovered_extras(self):
        self._touch(
            os.path.join(
                dir_structure.eroded_nifti_dir,
                "Extra",
                "t1_gd",
                "035_eroded_extra_t1_gd.nii.gz",
            )
        )
        # A custom render-only source may contain named extras even when no
        # built-in eroded modality is required by its configured slots.
        t2_vessel_view_main._validate_render_existing_inputs(
            {"custom_overlay_panels"}
        )

    def test_panel_config_accepts_only_discovered_extra_names(self):
        config_path = os.path.join(self.tmp.name, "panel.yaml")
        with open(config_path, "w", encoding="utf-8") as stream:
            stream.write(
                "angles: [left]\n"
                "slots:\n"
                "  - base: t1\n"
                "  - base: t1_gd\n"
            )

        with self.assertRaisesRegex(ValueError, "unknown base"):
            panel_config.load_custom_overlay_panels_config(config_path)
        config = panel_config.load_custom_overlay_panels_config(
            config_path,
            extra_base_names=["t1_gd"],
        )
        self.assertEqual(
            [slot["base"] for slot in config["slots"]],
            ["t1", "t1_gd"],
        )

    def test_processing_helpers_preserve_names_and_erode_outputs(self):
        specs = [
            {"name": "t1_gd", "path": "/input/gd.nii.gz"},
            {"name": "t1_prior", "path": "/input/prior.nii.gz"},
        ]
        with mock.patch.object(
            preprocess,
            "convert_and_reorient",
            side_effect=["/ro/gd.nii.gz", "/ro/prior.nii.gz"],
        ) as convert_mock:
            reoriented = t2_vessel_view_main._reorient_extra_images(specs)
        self.assertEqual(
            [item["tag"] for item in reoriented],
            ["extra_t1_gd", "extra_t1_prior"],
        )
        self.assertEqual(convert_mock.call_count, 2)

        images = [object(), object()]
        with mock.patch.object(
            preprocess,
            "preprocess_n4_reg",
            side_effect=[
                ("/pp/gd.nii.gz", images[0]),
                ("/pp/prior.nii.gz", images[1]),
            ],
        ) as preprocess_mock:
            processed = t2_vessel_view_main._preprocess_extra_images(
                reoriented,
                "/pp/main.nii.gz",
            )
        self.assertEqual(preprocess_mock.call_count, 2)
        self.assertEqual([item["image"] for item in processed], images)

        with mock.patch.object(
            masking,
            "multiply_masks_by_images",
        ) as erode_mock:
            t2_vessel_view_main._erode_extra_images(
                processed,
                ["035"],
                {"035_eroded_rxs_mask": object()},
            )
        self.assertEqual(erode_mock.call_count, 2)
        self.assertEqual(
            erode_mock.call_args_list[0].args[1],
            "extra_t1_gd",
        )
        self.assertTrue(
            erode_mock.call_args_list[0].args[2].endswith(
                os.path.join("Extra", "t1_gd")
            )
        )


if __name__ == "__main__":
    unittest.main()
