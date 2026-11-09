"""Tests for conditional MRIcroGL dependency checks."""

import contextlib
import io
import sys
import unittest
from unittest import mock


# Importing the main module also imports the command-line parser.
sys.argv = [
    "test_dependency_preflight.py",
    "-d",
    "/tmp",
    "-i",
    "/tmp/t1.nii.gz",
]

from t2vesselviewcode import commandline
from t2vesselviewcode import t2_vessel_view_main
from t2vesselviewcode import volume_rendering


class TestDependencyPreflight(unittest.TestCase):
    """Check when MRIcroGL is optional versus required."""

    def setUp(self):
        self.original_test_mode = t2_vessel_view_main.TEST_MODE
        self.original_panels = getattr(
            commandline.args,
            "resolved_panels",
            set(),
        )
        self.original_render_existing = getattr(
            commandline.args,
            "render_existing_erosions",
            False,
        )
        t2_vessel_view_main.TEST_MODE = False
        commandline.args.resolved_panels = set()
        commandline.args.render_existing_erosions = False

    def tearDown(self):
        t2_vessel_view_main.TEST_MODE = self.original_test_mode
        commandline.args.resolved_panels = self.original_panels
        commandline.args.render_existing_erosions = (
            self.original_render_existing
        )

    @staticmethod
    def _run_preflight(mricrogl_side_effect=None, template_side_effect=None):
        output = io.StringIO()
        executable_patch = mock.patch.object(
            volume_rendering,
            "resolve_mricrogl_executable",
            return_value="/opt/MRIcroGL/MRIcroGL",
            side_effect=mricrogl_side_effect,
        )
        template_patch = mock.patch.object(
            volume_rendering,
            "resolve_mricrogl_template_path",
            return_value="/package/mricrogl_T1_renders.py",
            side_effect=template_side_effect,
        )
        fsl_patch = mock.patch.object(
            t2_vessel_view_main.shutil,
            "which",
            return_value="/opt/fsl/bin/tool",
        )
        with executable_patch, template_patch, fsl_patch, \
                contextlib.redirect_stdout(output):
            result = t2_vessel_view_main.run_dependency_preflight()
        return result, output.getvalue()

    def test_missing_mricrogl_warns_for_preprocessing_only(self):
        result, output = self._run_preflight(
            mricrogl_side_effect=FileNotFoundError("not installed"),
        )

        self.assertTrue(result)
        self.assertIn("Continuing with preprocessing and erosion only", output)
        self.assertIn("MRIcroGL rendering is unavailable", output)

    def test_missing_mricrogl_fails_when_panels_are_requested(self):
        commandline.args.resolved_panels = {"t1_overview"}

        result, output = self._run_preflight(
            mricrogl_side_effect=FileNotFoundError("not installed"),
        )

        self.assertFalse(result)
        self.assertIn("MRIcroGL not found", output)
        self.assertNotIn("Continuing with preprocessing", output)

    def test_missing_mricrogl_fails_for_render_existing_mode(self):
        commandline.args.render_existing_erosions = True

        result, output = self._run_preflight(
            mricrogl_side_effect=FileNotFoundError("not installed"),
        )

        self.assertFalse(result)
        self.assertIn("MRIcroGL not found", output)
        self.assertIn("skipping FSL dependency checks", output)

    def test_missing_template_warns_for_preprocessing_only(self):
        result, output = self._run_preflight(
            template_side_effect=FileNotFoundError("template missing"),
        )

        self.assertTrue(result)
        self.assertIn("MRIcroGL render template not found", output)
        self.assertIn("MRIcroGL rendering is unavailable", output)

    def test_available_mricrogl_passes_render_preflight(self):
        commandline.args.resolved_panels = {"t1_overview"}

        result, output = self._run_preflight()

        self.assertTrue(result)
        self.assertIn("[OK] MRIcroGL found", output)
        self.assertIn("Dependency preflight checks passed.", output)


if __name__ == "__main__":
    unittest.main()
