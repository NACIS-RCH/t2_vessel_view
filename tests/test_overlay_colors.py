"""Tests for shared overlay colour-name resolution."""

import os
import sys
import unittest

# png_postprocess imports dir_structure, which triggers commandline parsing.
sys.argv = [
    "test_overlay_colors.py",
    "-d",
    "/tmp",
    "-i",
    "/tmp/t1.nii.gz",
]

from t2vesselviewcode import overlay_colors


class TestOverlayColors(unittest.TestCase):
    """Verify CLI colour aliases resolve for MRIcroGL and colorbars."""

    def test_unprefixed_aliases_resolve_to_integer_prefixed(self):
        """green/red/blue/hot map to 2green/1red/3blue/4hot."""
        self.assertEqual(overlay_colors.resolve_overlay_color("green"), "2green")
        self.assertEqual(overlay_colors.resolve_overlay_color("red"), "1red")
        self.assertEqual(overlay_colors.resolve_overlay_color("blue"), "3blue")
        self.assertEqual(overlay_colors.resolve_overlay_color("hot"), "4hot")
        self.assertEqual(overlay_colors.resolve_overlay_color("winter"), "5winter")
        self.assertEqual(overlay_colors.resolve_overlay_color("bluegrn"), "6bluegrn")
        self.assertEqual(overlay_colors.resolve_overlay_color("warm"), "6warm")
        self.assertEqual(overlay_colors.resolve_overlay_color("cool"), "7cool")
        self.assertEqual(overlay_colors.resolve_overlay_color("redyell"), "8redyell")

    def test_exact_integer_prefixed_names(self):
        """Exact CLUT names pass through unchanged."""
        self.assertEqual(overlay_colors.resolve_overlay_color("2green"), "2green")
        self.assertEqual(overlay_colors.resolve_overlay_color("1red"), "1red")
        self.assertEqual(overlay_colors.resolve_overlay_color("3blue"), "3blue")

    def test_continuous_maps(self):
        """Non-prefixed quantitative maps resolve to canonical names."""
        self.assertEqual(overlay_colors.resolve_overlay_color("jet"), "jet")
        self.assertEqual(overlay_colors.resolve_overlay_color("electric_blue"), "electric_blue")
        self.assertEqual(overlay_colors.resolve_overlay_color("electric-blue"), "electric_blue")
        self.assertEqual(overlay_colors.resolve_overlay_color("viridis"), "Viridis")
        self.assertEqual(overlay_colors.resolve_overlay_color("plasma"), "Plasma")

    def test_unknown_name_returns_none(self):
        """Unrecognised names return None from the strict resolver."""
        self.assertIsNone(overlay_colors.resolve_overlay_color("not_a_real_lut"))
        self.assertIsNone(overlay_colors.resolve_overlay_color(""))

    def test_resolve_or_warn_falls_back_to_jet(self):
        """Unknown names fall back to jet with was_recognized=False."""
        canonical, ok = overlay_colors.resolve_or_warn("not_a_real_lut", overlay_label="overlay1")
        self.assertEqual(canonical, "jet")
        self.assertFalse(ok)
        canonical, ok = overlay_colors.resolve_or_warn("green", overlay_label="overlay1")
        self.assertEqual(canonical, "2green")
        self.assertTrue(ok)

    def test_clut_paths_exist_for_aliases(self):
        """green and 2green both point at the same existing bundled CLUT file."""
        path_alias = overlay_colors.resolve_clut_path("green")
        path_exact = overlay_colors.resolve_clut_path("2green")
        self.assertIsNotNone(path_alias)
        self.assertIsNotNone(path_exact)
        self.assertEqual(path_alias, path_exact)
        self.assertTrue(os.path.exists(path_alias))
        self.assertTrue(path_alias.endswith("2green.clut"))

    def test_png_postprocess_uses_shared_resolver(self):
        """Colorbar path helper agrees with the shared overlay colour module."""
        try:
            from t2vesselviewcode import png_postprocess
        except ModuleNotFoundError as e:
            # Local test envs may lack optional rendering deps such as pyvips.
            self.skipTest(f"png_postprocess import unavailable: {e}")

        self.assertEqual(
            png_postprocess._resolve_bundled_clut_path("green"),
            overlay_colors.resolve_clut_path("green"),
        )
        self.assertEqual(
            png_postprocess._resolve_bundled_clut_path("2green"),
            overlay_colors.resolve_clut_path("2green"),
        )


if __name__ == "__main__":
    unittest.main()
