"""Synthetic PNG tests for custom overlay panel stitching."""

import glob
import os
import sys
import tempfile
import unittest
from unittest import mock

from PIL import Image, ImageDraw

# png_postprocess imports dir_structure, which triggers commandline parsing.
sys.argv = [
    "test_custom_panel_stitch.py",
    "-d",
    "/tmp",
    "-i",
    "/tmp/t1.nii.gz",
]

from t2vesselviewcode import png_postprocess


class TestCustomPanelStitch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raw_root = os.path.join(self.tmp.name, "raw")
        self.stitched_root = os.path.join(self.tmp.name, "stitched")

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def _write_png(path, color):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        image = Image.new("RGB", (80, 60), (0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rectangle((12, 8, 67, 51), fill=color)
        image.save(path)

    def _build_slot(
        self,
        index,
        base,
        color,
        erosion_depths,
        slice_keys,
        overlays=None,
        row="top",
        column=None,
    ):
        slot_dir = os.path.join(self.raw_root, f"{index:02d}_{base}")
        erosion_dir = os.path.join(slot_dir, "left_erosion_overlay")
        slice_dir = os.path.join(slot_dir, "left_slices_overlay")
        for depth in erosion_depths:
            self._write_png(
                os.path.join(
                    erosion_dir,
                    f"left_erosion_overlay_{depth}_eroded_{base}.nii.png",
                ),
                color,
            )
        for erode_depth, slice_number in slice_keys:
            self._write_png(
                os.path.join(
                    slice_dir,
                    f"left_slices_overlay-{slice_number}-"
                    f"{erode_depth}_eroded_{base}.nii.png",
                ),
                color,
            )
        return {
            "index": index,
            "row": row,
            "column": index if column is None else column,
            "base": base,
            "label": base.upper(),
            "overlays": list(overlays or []),
        }

    def test_erode_slice_map_keys_include_both_numbers(self):
        paths = [
            "/tmp/left_slices_overlay-015-005_eroded_t1.nii.png",
            "/tmp/left_slices_overlay-005-010_eroded_t1.nii.png",
        ]
        self.assertEqual(
            list(png_postprocess._build_erode_and_slice_map(paths)),
            ["010:005", "005:015"],
        )
        mapped = png_postprocess._build_erode_and_slice_map(paths)
        self.assertEqual(
            png_postprocess._sort_erode_and_slice_keys(set(mapped)),
            ["005:015", "010:005"],
        )

    def test_two_slot_stitch_intersects_depth_and_slice_keys(self):
        slots = [
            self._build_slot(
                0,
                "t1",
                (180, 60, 60),
                ["005", "010"],
                [("005", "005"), ("005", "010"), ("010", "005")],
            ),
            self._build_slot(
                1,
                "flair",
                (60, 120, 180),
                ["005", "010", "015"],
                [("005", "005"), ("005", "010"), ("015", "005")],
            ),
        ]

        with mock.patch.object(
            png_postprocess,
            "export_pptx_from_folder",
        ) as export_mock:
            png_postprocess.run_preset_custom_overlay_panels(
                raw_root=self.raw_root,
                stitched_root=self.stitched_root,
                slots=slots,
                angles=["left"],
                pptx_name="test_custom",
            )

        erosion_panels = glob.glob(
            os.path.join(
                self.stitched_root,
                "by_angle",
                "left",
                "erosions_stitched",
                "concat_*.png",
            )
        )
        slice_panels = glob.glob(
            os.path.join(
                self.stitched_root,
                "by_angle",
                "left",
                "slices_stitched",
                "concat_*.png",
            )
        )
        combined = sorted(
            glob.glob(
                os.path.join(
                    self.stitched_root,
                    "_combined_for_pptx",
                    "concat_*.png",
                )
            )
        )
        self.assertEqual(len(erosion_panels), 2)
        self.assertEqual(len(slice_panels), 2)
        self.assertEqual(len(combined), 4)
        export_mock.assert_called_once()

    def test_custom_colorbars_are_applied_per_slot_before_stitching(self):
        overlay_a = {
            "path": "/tmp/map_a.nii.gz",
            "name": "MapA",
            "color": "jet",
            "min": 0,
            "max": 10,
            "opacity": 50,
        }
        overlay_b = {
            "path": "/tmp/map_b.nii.gz",
            "name": "MapB",
            "color": "2green",
            "min": 1,
            "max": 5,
            "opacity": 60,
        }
        slots = [
            self._build_slot(
                0,
                "t1",
                (180, 60, 60),
                ["005"],
                [("005", "005")],
                overlays=[overlay_a, dict(overlay_a), overlay_b],
            ),
            self._build_slot(
                1,
                "t2",
                (60, 180, 60),
                ["005"],
                [("005", "005")],
                overlays=[overlay_a],
            ),
            self._build_slot(
                2,
                "flair",
                (60, 60, 180),
                ["005"],
                [("005", "005")],
                overlays=[],
                row="bottom",
                column=0,
            ),
        ]

        with mock.patch.object(
            png_postprocess,
            "annotate_overlay_colorbars_on_png",
        ) as colorbar_mock, mock.patch.object(
            png_postprocess,
            "annotate_overlay_colorbar_series",
        ) as global_colorbar_mock, mock.patch.object(
            png_postprocess,
            "export_pptx_from_folder",
        ):
            png_postprocess.run_preset_custom_overlay_panels(
                raw_root=self.raw_root,
                stitched_root=self.stitched_root,
                slots=slots,
                angles=["left"],
            )

        self.assertEqual(colorbar_mock.call_count, 4)
        global_colorbar_mock.assert_not_called()
        slot_zero_calls = [
            call for call in colorbar_mock.call_args_list
            if f"{os.sep}00_t1{os.sep}" in call.args[0]
        ]
        slot_one_calls = [
            call for call in colorbar_mock.call_args_list
            if f"{os.sep}01_t2{os.sep}" in call.args[0]
        ]
        slot_two_calls = [
            call for call in colorbar_mock.call_args_list
            if f"{os.sep}02_flair{os.sep}" in call.args[0]
        ]
        self.assertEqual(len(slot_zero_calls), 2)
        self.assertEqual(len(slot_one_calls), 2)
        self.assertEqual(slot_two_calls, [])
        for call in slot_zero_calls:
            self.assertEqual(call.args[2], [overlay_a, overlay_b])
        for call in slot_one_calls:
            self.assertEqual(call.args[2], [overlay_a])

    def test_four_structural_only_slots_produce_one_wide_row(self):
        slots = [
            self._build_slot(
                index,
                base,
                color,
                ["005"],
                [("005", "005")],
            )
            for index, (base, color) in enumerate(
                [
                    ("t1", (180, 60, 60)),
                    ("t2", (60, 180, 60)),
                    ("flair", (60, 60, 180)),
                    ("t1", (180, 180, 60)),
                ]
            )
        ]

        with mock.patch.object(
            png_postprocess,
            "export_pptx_from_folder",
        ):
            png_postprocess.run_preset_custom_overlay_panels(
                raw_root=self.raw_root,
                stitched_root=self.stitched_root,
                slots=slots,
                angles=["left"],
            )

        panel_path = os.path.join(
            self.stitched_root,
            "by_angle",
            "left",
            "erosions_stitched",
            "concat_000.png",
        )
        with Image.open(panel_path) as panel:
            self.assertGreater(panel.width, panel.height * 3)

    def _build_two_row_slots(self, top_count, bottom_count):
        colors = [
            (180, 60, 60),
            (60, 180, 60),
            (60, 60, 180),
            (180, 180, 60),
            (180, 60, 180),
            (60, 180, 180),
            (140, 100, 60),
            (100, 60, 140),
        ]
        slots = []
        index = 0
        for row_name, count in (("top", top_count), ("bottom", bottom_count)):
            for column in range(count):
                slots.append(
                    self._build_slot(
                        index,
                        "t1",
                        colors[index],
                        ["005"],
                        [("005", "005")],
                        row=row_name,
                        column=column,
                    )
                )
                index += 1
        return slots

    def _render_two_row_panel(self, top_count, bottom_count):
        slots = self._build_two_row_slots(top_count, bottom_count)
        with mock.patch.object(
            png_postprocess,
            "export_pptx_from_folder",
        ):
            png_postprocess.run_preset_custom_overlay_panels(
                raw_root=self.raw_root,
                stitched_root=self.stitched_root,
                slots=slots,
                angles=["left"],
            )
        return os.path.join(
            self.stitched_root,
            "by_angle",
            "left",
            "erosions_stitched",
            "concat_000.png",
        )

    def test_four_top_two_bottom_rows_are_left_aligned(self):
        panel_path = self._render_two_row_panel(4, 2)
        with Image.open(panel_path) as panel:
            top_y = panel.height // 4
            bottom_y = (panel.height * 3) // 4
            self.assertNotEqual(
                panel.getpixel((panel.width // 8, bottom_y)),
                (0, 0, 0),
            )
            self.assertEqual(
                panel.getpixel((panel.width - 2, bottom_y)),
                (0, 0, 0),
            )
            self.assertNotEqual(
                panel.getpixel((panel.width - panel.width // 8, top_y)),
                (0, 0, 0),
            )

    def test_two_top_four_bottom_rows_are_left_aligned(self):
        panel_path = self._render_two_row_panel(2, 4)
        with Image.open(panel_path) as panel:
            top_y = panel.height // 4
            bottom_y = (panel.height * 3) // 4
            self.assertNotEqual(
                panel.getpixel((panel.width // 8, top_y)),
                (0, 0, 0),
            )
            self.assertEqual(
                panel.getpixel((panel.width - 2, top_y)),
                (0, 0, 0),
            )
            self.assertNotEqual(
                panel.getpixel((panel.width - panel.width // 8, bottom_y)),
                (0, 0, 0),
            )


if __name__ == "__main__":
    unittest.main()
