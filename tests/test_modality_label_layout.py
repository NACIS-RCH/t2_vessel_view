"""Tests for fitting and wrapping modality/overlay labels."""

import os
import sys
import tempfile
import unittest
from unittest import mock

from PIL import Image, ImageDraw

# png_postprocess imports dir_structure, which triggers commandline parsing.
sys.argv = [
    "test_modality_label_layout.py",
    "-d",
    "/tmp",
    "-i",
    "/tmp/t1.nii.gz",
]

from t2vesselviewcode import png_postprocess


class TestModalityLabelLayout(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.width = 260
        self.height = 240
        self.margin = max(8, int(self.height * 0.02))
        self.input_path = os.path.join(self.tmp.name, "input.png")
        Image.new(
            "RGB",
            (self.width, self.height),
            (0, 0, 0),
        ).save(self.input_path)

    def tearDown(self):
        self.tmp.cleanup()

    def _layout(self, text):
        with Image.open(self.input_path) as image:
            draw = ImageDraw.Draw(image)
            return png_postprocess._layout_modality_label(
                draw,
                text,
                self.width,
                self.height,
                self.margin,
            )

    def test_short_label_keeps_existing_single_line_size(self):
        layout = self._layout("T1")
        self.assertEqual(layout["lines"], ["T1"])
        self.assertEqual(
            layout["font_size"],
            max(12, int(self.height * 0.03)),
        )

    def test_long_label_wraps_to_two_fitting_lines(self):
        layout = self._layout(
            "T1 + PET + arcuate_fasciculus + optic_radiation"
        )

        self.assertEqual(len(layout["lines"]), 2)
        self.assertTrue(layout["lines"][1].startswith("+ "))
        self.assertNotIn("_", "".join(layout["lines"]))
        self.assertEqual(
            layout["lines"][0] + " " + layout["lines"][1],
            "T1 + PET + arcuate fasciculus + optic radiation",
        )
        for width, _height in layout["line_sizes"]:
            self.assertLessEqual(width, layout["available_width"])

    def test_wrapped_lines_are_centered_and_inside_image(self):
        output_path = os.path.join(self.tmp.name, "output.png")
        with mock.patch.object(
            png_postprocess,
            "_draw_text_with_outline",
        ) as draw_mock:
            png_postprocess.annotate_modality_center_bottom(
                self.input_path,
                output_path,
                "T1 + PET + arcuate_fasciculus + optic_radiation",
            )

        self.assertEqual(draw_mock.call_count, 2)
        with Image.open(self.input_path) as image:
            measure_draw = ImageDraw.Draw(image)
            for call in draw_mock.call_args_list:
                x, y = call.args[1]
                text = call.args[2]
                font = call.kwargs["font"]
                text_width, text_height = png_postprocess._measure_text(
                    measure_draw,
                    text,
                    font,
                )
                self.assertEqual(x, (self.width - text_width) // 2)
                self.assertGreaterEqual(x, 0)
                self.assertGreaterEqual(y, 0)
                self.assertLessEqual(x + text_width, self.width)
                self.assertLessEqual(y + text_height, self.height)
        self.assertTrue(os.path.isfile(output_path))


if __name__ == "__main__":
    unittest.main()
