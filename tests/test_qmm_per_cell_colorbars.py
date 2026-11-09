"""Tests for per-cell QMM colorbar assignment."""

import os
import sys
import tempfile
import unittest
from unittest import mock

from PIL import Image, ImageDraw

# png_postprocess imports dir_structure, which triggers commandline parsing.
sys.argv = [
    "test_qmm_per_cell_colorbars.py",
    "-d",
    "/tmp",
    "-i",
    "/tmp/t1.nii.gz",
]

from t2vesselviewcode import dir_structure
from t2vesselviewcode import png_postprocess


class TestQmmPerCellColorbars(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "T2VesselView")
        self.raw_root = os.path.join(self.tmp.name, "raw")
        dir_structure._set_t2vv_root(self.root)
        self.overlay_a = {
            "path": "/tmp/map_a.nii.gz",
            "name": "MapA",
            "color": "jet",
            "min": 0,
            "max": 10,
            "opacity": 50,
        }
        self.overlay_b = {
            "path": "/tmp/map_b.nii.gz",
            "name": "MapB",
            "color": "2green",
            "min": 1,
            "max": 5,
            "opacity": 60,
        }

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def _write_png(path, color):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        image = Image.new("RGB", (80, 60), (0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rectangle((12, 8, 67, 51), fill=color)
        image.save(path)

    def _build_qmm_raw_tree(self):
        sources = (
            ("T1", (180, 60, 60)),
            ("T2_sag", (60, 180, 60)),
            ("FLAIR", (60, 60, 180)),
        )
        tags = ("overlay", "structural")
        for source, color in sources:
            for tag in tags:
                self._write_png(
                    os.path.join(
                        self.raw_root,
                        source,
                        f"left_slices_{tag}",
                        f"left_slices_{tag}-005-030_eroded_{source}.png",
                    ),
                    color,
                )
                self._write_png(
                    os.path.join(
                        self.raw_root,
                        source,
                        f"left_erosion_{tag}",
                        f"left_erosion_{tag}_030_eroded_{source}.png",
                    ),
                    color,
                )

    def test_qmm_colorbars_follow_visible_composite_overlays(self):
        self._build_qmm_raw_tree()
        with mock.patch.object(
            png_postprocess,
            "annotate_overlay_colorbars_on_png",
        ) as colorbar_mock, mock.patch.object(
            png_postprocess,
            "export_pptx_from_folder",
        ):
            png_postprocess.run_preset_quant_map_mm_panel(
                raw_root=self.raw_root,
                angle_to_t2_source={"left": "T2_sag"},
                qmm_angles=["left"],
                overlay_names=["MapA", "MapB"],
                overlay_specs=[self.overlay_a, self.overlay_b],
            )

        self.assertEqual(colorbar_mock.call_count, 6)
        t1_calls = [
            call for call in colorbar_mock.call_args_list
            if "t1_overlay" in call.args[0]
        ]
        t2_calls = [
            call for call in colorbar_mock.call_args_list
            if "t2_overlay" in call.args[0]
        ]
        flair_calls = [
            call for call in colorbar_mock.call_args_list
            if "flair_overlay" in call.args[0]
        ]
        self.assertEqual(len(t1_calls), 2)
        self.assertEqual(len(t2_calls), 2)
        self.assertEqual(len(flair_calls), 2)
        for call in t1_calls:
            self.assertEqual(call.args[2], [self.overlay_a, self.overlay_b])
        for call in t2_calls + flair_calls:
            self.assertEqual(call.args[2], [self.overlay_a])
        self.assertFalse(
            any("struct" in call.args[0] for call in colorbar_mock.call_args_list)
        )

    def test_qmm_t2_labels_describe_the_selected_source(self):
        expected_labels = {
            "T2_sag": "T2 sag (inv)",
            "T2_sag_left": "T2 sag (inv)",
            "T2_sag_right": "T2 sag (inv)",
            "T2_cor": "T2 cor (inv)",
            "T2_tra": "T2 tra (inv)",
            "T2_3d": "T2 3D (inv)",
        }

        for source, expected in expected_labels.items():
            with self.subTest(source=source):
                self.assertEqual(
                    png_postprocess._qmm_t2_modality_label(source),
                    expected,
                )

    def test_qmm_t2_overlay_and_structural_pngs_use_source_label(self):
        self._build_qmm_raw_tree()
        with mock.patch.object(
            png_postprocess,
            "annotate_modality_center_bottom",
        ) as modality_mock, mock.patch.object(
            png_postprocess,
            "export_pptx_from_folder",
        ):
            png_postprocess.run_preset_quant_map_mm_panel(
                raw_root=self.raw_root,
                angle_to_t2_source={"left": "T2_sag"},
                qmm_angles=["left"],
                overlay_names=["MapA", "MapB"],
                overlay_specs=[self.overlay_a, self.overlay_b],
            )

        labels = [call.args[2] for call in modality_mock.call_args_list]
        self.assertIn("T2 sag (inv)", labels)
        self.assertIn("T2 sag (inv) + MapA", labels)
        self.assertNotIn("T2 (inv)", labels)
        self.assertNotIn("T2 (inv) + MapA", labels)

    def test_t1_overview_global_series_helper_is_unchanged(self):
        folder = os.path.join(self.tmp.name, "global")
        image_path = os.path.join(folder, "concat_000.png")
        self._write_png(image_path, (100, 100, 100))
        specs = [self.overlay_a, dict(self.overlay_a)]

        with mock.patch.object(
            png_postprocess,
            "annotate_overlay_colorbars_on_png",
        ) as colorbar_mock:
            png_postprocess.annotate_overlay_colorbar_series(folder, specs)

        colorbar_mock.assert_called_once_with(image_path, image_path, specs)


if __name__ == "__main__":
    unittest.main()
