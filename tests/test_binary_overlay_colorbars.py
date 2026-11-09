"""Tests for automatic binary-overlay legend swatches."""

import os
import sys
import tempfile
import unittest
from unittest import mock

import nibabel as nib
import numpy as np
from PIL import Image

# png_postprocess imports dir_structure, which triggers commandline parsing.
sys.argv = [
    "test_binary_overlay_colorbars.py",
    "-d",
    "/tmp",
    "-i",
    "/tmp/t1.nii.gz",
]

from t2vesselviewcode import png_postprocess


class TestBinaryOverlayColorbars(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.binary_path = self._write_nifti(
            "binary.nii.gz",
            np.array([0, 1, 0, 1], dtype=np.uint8).reshape((2, 2, 1)),
        )
        self.continuous_path = self._write_nifti(
            "continuous.nii.gz",
            np.array([0, 0.5, 1, 0.25], dtype=np.float32).reshape((2, 2, 1)),
        )
        self.zero_path = self._write_nifti(
            "zero.nii.gz",
            np.zeros((2, 2, 1), dtype=np.uint8),
        )
        self.panel_path = os.path.join(self.tmp.name, "panel.png")
        Image.new("RGB", (300, 240), (0, 0, 0)).save(self.panel_path)
        png_postprocess._is_binary_overlay_cached.cache_clear()

    def tearDown(self):
        png_postprocess._is_binary_overlay_cached.cache_clear()
        self.tmp.cleanup()

    def _write_nifti(self, name, data):
        path = os.path.join(self.tmp.name, name)
        nib.Nifti1Image(data, np.eye(4)).to_filename(path)
        return path

    def test_detects_exact_visible_binary_only(self):
        self.assertTrue(
            png_postprocess._is_binary_overlay(self.binary_path)
        )
        self.assertFalse(
            png_postprocess._is_binary_overlay(self.continuous_path)
        )
        self.assertFalse(
            png_postprocess._is_binary_overlay(self.zero_path)
        )
        self.assertFalse(
            png_postprocess._is_binary_overlay("/does/not/exist.nii.gz")
        )

    def test_detection_cache_invalidates_when_file_changes(self):
        self.assertTrue(
            png_postprocess._is_binary_overlay(self.binary_path)
        )
        first_cache = (
            png_postprocess._is_binary_overlay_cached.cache_info()
        )
        self.assertTrue(
            png_postprocess._is_binary_overlay(self.binary_path)
        )
        second_cache = (
            png_postprocess._is_binary_overlay_cached.cache_info()
        )
        self.assertEqual(second_cache.hits, first_cache.hits + 1)

        old_stat = os.stat(self.binary_path)
        nib.Nifti1Image(
            np.array([0, 0.5, 1, 0], dtype=np.float32).reshape((2, 2, 1)),
            np.eye(4),
        ).to_filename(self.binary_path)
        new_mtime = max(
            old_stat.st_mtime_ns + 1_000_000,
            os.stat(self.binary_path).st_mtime_ns,
        )
        os.utime(self.binary_path, ns=(new_mtime, new_mtime))

        self.assertFalse(
            png_postprocess._is_binary_overlay(self.binary_path)
        )

    def test_foreground_value_maps_to_expected_clut_colour(self):
        position = png_postprocess._value_to_clut_intensity(1, 0, 2)
        self.assertEqual(position, 127.5)

        color_name = "jet"
        clut_path = png_postprocess._resolve_bundled_clut_path(color_name)
        nodes = png_postprocess._parse_mricrogl_clut(clut_path)
        expected = png_postprocess._interpolate_clut_rgb(nodes, position)
        swatch = png_postprocess._make_binary_clut_swatch_image(
            color_name,
            width=6,
            height=10,
            window_min=0,
            window_max=2,
        )
        self.assertIsNotNone(swatch)
        self.assertEqual(set(swatch.getdata()), {expected})

    def test_binary_legend_uses_swatch_without_endpoint_text(self):
        spec = {
            "path": self.binary_path,
            "name": "BinaryMap",
            "color": "jet",
            "min": 0,
            "max": 2,
            "opacity": 50,
        }
        fake_swatch = Image.new("RGB", (6, 6), (10, 20, 30))
        with mock.patch.object(
            png_postprocess,
            "_make_binary_clut_swatch_image",
            return_value=fake_swatch,
        ) as swatch_mock, mock.patch.object(
            png_postprocess,
            "_make_clut_colorbar_image",
        ) as gradient_mock, mock.patch.object(
            png_postprocess,
            "_draw_text_with_outline",
        ) as text_mock:
            png_postprocess.annotate_overlay_colorbars_on_png(
                self.panel_path,
                self.panel_path,
                [spec],
            )

        swatch_mock.assert_called_once()
        swatch_call = swatch_mock.call_args
        self.assertEqual(swatch_call.args[1], 12)
        self.assertEqual(swatch_call.args[1], swatch_call.args[2])
        gradient_mock.assert_not_called()
        self.assertEqual(
            [call.args[2] for call in text_mock.call_args_list],
            ["BinaryMap"],
        )

    def test_continuous_legend_keeps_gradient_and_endpoints(self):
        spec = {
            "path": self.continuous_path,
            "name": "ContinuousMap",
            "color": "jet",
            "min": 0,
            "max": 2,
            "opacity": 50,
        }
        fake_gradient = Image.new("RGB", (6, 28), (10, 20, 30))
        with mock.patch.object(
            png_postprocess,
            "_make_binary_clut_swatch_image",
        ) as swatch_mock, mock.patch.object(
            png_postprocess,
            "_make_clut_colorbar_image",
            return_value=fake_gradient,
        ) as gradient_mock, mock.patch.object(
            png_postprocess,
            "_draw_text_with_outline",
        ) as text_mock:
            png_postprocess.annotate_overlay_colorbars_on_png(
                self.panel_path,
                self.panel_path,
                [spec],
            )

        swatch_mock.assert_not_called()
        gradient_mock.assert_called_once()
        gradient_call = gradient_mock.call_args
        self.assertEqual(gradient_call.args[1], 12)
        self.assertGreater(gradient_call.args[2], gradient_call.args[1])
        self.assertEqual(
            [call.args[2] for call in text_mock.call_args_list],
            ["ContinuousMap", "2", "0"],
        )


if __name__ == "__main__":
    unittest.main()
