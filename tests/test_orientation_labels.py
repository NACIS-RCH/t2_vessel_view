"""Tests for angle-specific anatomical orientation annotations."""

import os
import sys
import tempfile
import unittest
from unittest import mock

from PIL import Image

# png_postprocess imports dir_structure, which triggers commandline parsing.
sys.argv = [
    "test_orientation_labels.py",
    "-d",
    "/tmp",
    "-i",
    "/tmp/t1.nii.gz",
]

from t2vesselviewcode import png_postprocess


class TestOrientationLabels(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.input_path = os.path.join(self.tmp.name, "input.png")
        Image.new("RGB", (200, 100), (0, 0, 0)).save(self.input_path)

    def tearDown(self):
        self.tmp.cleanup()

    def _draw_calls_for_angle(self, angle):
        output_path = os.path.join(self.tmp.name, f"{angle}.png")
        with mock.patch.object(
            png_postprocess,
            "_load_annotation_font",
            return_value=object(),
        ), mock.patch.object(
            png_postprocess,
            "_draw_text_with_outline",
        ) as draw_mock:
            png_postprocess.annotate_by_angle_on_png(
                self.input_path,
                output_path,
                angle,
            )
        self.assertTrue(os.path.isfile(output_path))
        return [
            (call.args[1], call.args[2])
            for call in draw_mock.call_args_list
        ]

    def test_left_surgical_views_match_regular_left(self):
        regular = self._draw_calls_for_angle("left")
        self.assertEqual(len(regular), 1)
        self.assertEqual(regular[0][1], "L")
        for angle in ("surg_left_lat", "surg_left_ato"):
            with self.subTest(angle=angle):
                self.assertEqual(self._draw_calls_for_angle(angle), regular)

    def test_right_surgical_views_match_regular_right(self):
        regular = self._draw_calls_for_angle("right")
        self.assertEqual(len(regular), 1)
        self.assertEqual(regular[0][1], "R")
        for angle in ("surg_right_lat", "surg_right_ato"):
            with self.subTest(angle=angle):
                self.assertEqual(self._draw_calls_for_angle(angle), regular)

    def test_cardinal_orientation_rules_are_unchanged(self):
        self.assertEqual(
            [text for _position, text in self._draw_calls_for_angle("superior")],
            ["L", "R"],
        )
        self.assertEqual(
            [text for _position, text in self._draw_calls_for_angle("posterior")],
            ["L", "R"],
        )
        self.assertEqual(
            [text for _position, text in self._draw_calls_for_angle("inferior")],
            ["R", "L"],
        )
        self.assertEqual(
            [text for _position, text in self._draw_calls_for_angle("anterior")],
            ["R", "L"],
        )

    def test_unknown_angle_draws_no_orientation_text(self):
        self.assertEqual(self._draw_calls_for_angle("unknown_view"), [])


if __name__ == "__main__":
    unittest.main()
