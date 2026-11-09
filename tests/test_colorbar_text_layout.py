"""Tests for larger, wrapped colorbar names and values."""

import os
import sys
import tempfile
import unittest
from unittest import mock

from PIL import Image, ImageDraw

# png_postprocess imports dir_structure, which triggers commandline parsing.
sys.argv = [
    "test_colorbar_text_layout.py",
    "-d",
    "/tmp",
    "-i",
    "/tmp/t1.nii.gz",
]

from t2vesselviewcode import png_postprocess


class TestColorbarTextLayout(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def _panel(self, name, size=(400, 1000)):
        path = os.path.join(self.tmp.name, name)
        Image.new("RGB", size, (0, 0, 0)).save(path)
        return path

    @staticmethod
    def _spec(name):
        return {
            "path": "/missing/continuous.nii.gz",
            "name": name,
            "color": "jet",
            "min": 0,
            "max": 10,
            "opacity": 50,
        }

    def test_short_and_wrapped_name_layout(self):
        image = Image.new("RGB", (300, 240), (0, 0, 0))
        draw = ImageDraw.Draw(image)
        font = png_postprocess._load_annotation_font(12)

        short = png_postprocess._layout_colorbar_name(
            draw,
            "PET",
            font,
            max_width=100,
            line_gap=2,
        )
        self.assertEqual(short["lines"], ["PET"])

        wrapped = png_postprocess._layout_colorbar_name(
            draw,
            "arcuate_fasciculus",
            font,
            max_width=80,
            line_gap=2,
        )
        self.assertEqual(wrapped["lines"], ["arcuate", "fasciculus"])
        self.assertLessEqual(len(wrapped["lines"]), 2)
        for width, _height in wrapped["line_sizes"]:
            self.assertLessEqual(width, 80)

    def test_seventeen_character_threshold_and_hyphenated_word_break(self):
        image = Image.new("RGB", (400, 240), (0, 0, 0))
        draw = ImageDraw.Draw(image)
        font = png_postprocess._load_annotation_font(12)

        exactly_seventeen = png_postprocess._layout_colorbar_name(
            draw,
            "12345678901234567",
            font,
            max_width=300,
            line_gap=2,
        )
        self.assertEqual(exactly_seventeen["lines"], ["12345678901234567"])

        word_wrapped = png_postprocess._layout_colorbar_name(
            draw,
            "corticospinal tract",
            font,
            max_width=300,
            line_gap=2,
        )
        self.assertEqual(word_wrapped["lines"], ["corticospinal", "tract"])

        hyphenated = png_postprocess._layout_colorbar_name(
            draw,
            "abcdefghijklmnopqr",
            font,
            max_width=300,
            line_gap=2,
        )
        self.assertEqual(len(hyphenated["lines"]), 2)
        self.assertTrue(hyphenated["lines"][0].endswith("-"))
        self.assertTrue(
            all(len(line) <= 17 for line in hyphenated["lines"])
        )

    def test_single_and_multiple_overlay_font_sizes(self):
        original_loader = png_postprocess._load_annotation_font

        single_sizes = []
        single_path = self._panel("single.png")
        with mock.patch.object(
            png_postprocess,
            "_load_annotation_font",
            side_effect=lambda size: (
                single_sizes.append(size) or original_loader(size)
            ),
        ):
            png_postprocess.annotate_overlay_colorbars_on_png(
                single_path,
                single_path,
                [self._spec("PET")],
            )
        self.assertEqual(single_sizes[:2], [23, 18])

        multiple_sizes = []
        multiple_path = self._panel("multiple.png")
        with mock.patch.object(
            png_postprocess,
            "_load_annotation_font",
            side_effect=lambda size: (
                multiple_sizes.append(size) or original_loader(size)
            ),
        ):
            png_postprocess.annotate_overlay_colorbars_on_png(
                multiple_path,
                multiple_path,
                [
                    self._spec("PET"),
                    self._spec("arcuate_fasciculus"),
                    self._spec("optic_radiation"),
                ],
            )
        self.assertEqual(multiple_sizes[:2], [20, 15])

    def test_three_overlay_names_wrap_and_stay_inside_image(self):
        panel_path = self._panel("three.png", size=(300, 300))
        with mock.patch.object(
            png_postprocess,
            "_draw_text_with_outline",
        ) as draw_mock:
            png_postprocess.annotate_overlay_colorbars_on_png(
                panel_path,
                panel_path,
                [
                    self._spec("PET"),
                    self._spec("arcuate_fasciculus"),
                    self._spec("optic_radiation"),
                ],
            )

        drawn_text = [call.args[2] for call in draw_mock.call_args_list]
        self.assertIn("arcuate", drawn_text)
        self.assertIn("fasciculus", drawn_text)
        self.assertIn("optic radiation", drawn_text)
        with Image.open(panel_path) as image:
            for call in draw_mock.call_args_list:
                x, y = call.args[1]
                text = call.args[2]
                font = call.kwargs["font"]
                draw = ImageDraw.Draw(image)
                width, height = png_postprocess._measure_text(draw, text, font)
                self.assertGreaterEqual(x, 0)
                self.assertGreaterEqual(y, 0)
                self.assertLessEqual(x + width, image.width)
                self.assertLessEqual(y + height, image.height)


if __name__ == "__main__":
    unittest.main()
