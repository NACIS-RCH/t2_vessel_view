"""Compatibility tests for custom angle and slice-render support."""

import inspect
import os
import sys
import tempfile
import unittest
from unittest import mock

import nibabel as nib
import numpy as np

# volume_rendering imports dir_structure, which triggers commandline parsing.
sys.argv = [
    "test_custom_slice_render.py",
    "-d",
    "/tmp",
    "-i",
    "/tmp/t1.nii.gz",
]

from t2vesselviewcode import panel_config
from t2vesselviewcode import volume_rendering


class TestCustomSliceRender(unittest.TestCase):
    def test_qmm_default_angle_rows_are_unchanged(self):
        self.assertEqual(
            volume_rendering._normalize_slice_angle_rows(),
            [
                ["left", 90, 0, 270, 0],
                ["right", 270, 0, 90, 0],
                ["anterior", 180, 0, 180, 0],
                ["posterior", 0, -10, 0, -10],
                ["superior", 0, 90, 0, 90],
                ["inferior", 180, -90, 0, -90],
            ],
        )

    def test_custom_surgical_rows_are_accepted(self):
        rows = panel_config.angle_rows(["surg_left_lat", "surg_right_ato"])
        self.assertEqual(
            volume_rendering._normalize_slice_angle_rows(rows),
            rows,
        )

    def test_invalid_angle_row_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "brain_az"):
            volume_rendering._normalize_slice_angle_rows([["left", 90, 0]])

    def test_new_options_preserve_qmm_defaults(self):
        signature = inspect.signature(
            volume_rendering.render_quant_map_mm_panel_slices_mricrogl
        )
        self.assertIsNone(signature.parameters["angles"].default)
        self.assertFalse(signature.parameters["slice_all_depths"].default)
        self.assertTrue(signature.parameters["save_structural_outputs"].default)
        self.assertTrue(signature.parameters["save_overlay_outputs"].default)
        self.assertEqual(signature.parameters["timeout_s"].default, 600)

    def test_template_supports_all_depths_and_surgical_midline(self):
        template_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "t2vesselviewcode",
            "display_scripts",
            "templates",
            "mricrogl_quant_map_mm_panel_slices.py",
        )
        with open(template_path, encoding="utf-8") as stream:
            template = stream.read()
        self.assertIn("SLICE_ALL_DEPTHS = __SLICE_ALL_DEPTHS__", template)
        self.assertIn(
            "SAVE_STRUCTURAL_OUTPUTS = __SAVE_STRUCTURAL_OUTPUTS__",
            template,
        )
        self.assertIn(
            "SAVE_OVERLAY_OUTPUTS = __SAVE_OVERLAY_OUTPUTS__",
            template,
        )
        self.assertIn('"surg_left_lat"', template)
        self.assertIn('"surg_right_ato"', template)
        self.assertIn("bool(SLICE_ALL_DEPTHS)", template)

    def test_generated_script_injects_custom_composite_only_depth(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            nifti_path = os.path.join(temp_dir, "035_eroded_t1.nii.gz")
            nib.Nifti1Image(
                np.ones((3, 3, 3), dtype=np.float32),
                np.eye(4),
            ).to_filename(nifti_path)
            captured = {}

            def fake_run(command, **_kwargs):
                with open(command[-1], encoding="utf-8") as stream:
                    captured["script"] = stream.read()
                return "", ""

            with mock.patch.object(
                volume_rendering,
                "resolve_mricrogl_executable",
                return_value="/fake/MRIcroGL",
            ), mock.patch.object(
                volume_rendering,
                "_configure_mricrogl_ini_preferences",
            ), mock.patch.object(
                volume_rendering,
                "_run_mricrogl_command",
                side_effect=fake_run,
            ):
                volume_rendering.render_quant_map_mm_panel_slices_mricrogl(
                    [nifti_path],
                    os.path.join(temp_dir, "renders"),
                    overlays=[],
                    angles=panel_config.angle_rows(["surg_left_lat"]),
                    main_erode_prefix="035",
                    slice_all_depths=False,
                    save_structural_outputs=False,
                    save_overlay_outputs=True,
                )

        script = captured["script"]
        self.assertIn("MAIN_ERODE_PREFIX = \"035\"", script)
        self.assertIn("SLICE_ALL_DEPTHS = False", script)
        self.assertIn("SAVE_STRUCTURAL_OUTPUTS = False", script)
        self.assertIn("SAVE_OVERLAY_OUTPUTS = True", script)
        self.assertIn(
            "['surg_left_lat', 270, 180, 90, 180]",
            script,
        )
        self.assertNotIn("__SLICE_ALL_DEPTHS__", script)
        self.assertNotIn("__SLICE_ANGLES__", script)
        self.assertNotIn("__SAVE_STRUCTURAL_OUTPUTS__", script)
        self.assertNotIn("__SAVE_OVERLAY_OUTPUTS__", script)

    def test_generated_qmm_script_keeps_default_depth_behavior(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            nifti_path = os.path.join(temp_dir, "030_eroded_t1.nii.gz")
            nib.Nifti1Image(
                np.ones((3, 3, 3), dtype=np.float32),
                np.eye(4),
            ).to_filename(nifti_path)
            captured = {}

            def fake_run(command, **_kwargs):
                with open(command[-1], encoding="utf-8") as stream:
                    captured["script"] = stream.read()
                return "", ""

            with mock.patch.object(
                volume_rendering,
                "resolve_mricrogl_executable",
                return_value="/fake/MRIcroGL",
            ), mock.patch.object(
                volume_rendering,
                "_configure_mricrogl_ini_preferences",
            ), mock.patch.object(
                volume_rendering,
                "_run_mricrogl_command",
                side_effect=fake_run,
            ):
                volume_rendering.render_quant_map_mm_panel_slices_mricrogl(
                    [nifti_path],
                    os.path.join(temp_dir, "renders"),
                    overlays=[],
                )

        script = captured["script"]
        self.assertIn("SLICE_ALL_DEPTHS = False", script)
        self.assertIn("SAVE_STRUCTURAL_OUTPUTS = True", script)
        self.assertIn("SAVE_OVERLAY_OUTPUTS = True", script)
        self.assertIn("MAIN_ERODE_PREFIX = \"030\"", script)
        self.assertIn("['left', 90, 0, 270, 0]", script)
        self.assertIn("['inferior', 180, -90, 0, -90]", script)

    def test_rejects_render_with_no_output_family_enabled(self):
        with self.assertRaisesRegex(ValueError, "At least one"):
            volume_rendering.render_quant_map_mm_panel_slices_mricrogl(
                [],
                "/tmp/not-used",
                overlays=[],
                save_structural_outputs=False,
                save_overlay_outputs=False,
            )

    def test_timeout_reports_partial_batch_and_keeps_outputs(self):
        class TimedOutProcess:
            pid = 4242

            def communicate(self, timeout=None):
                raise volume_rendering.subprocess.TimeoutExpired(
                    cmd=["MRIcroGL"],
                    timeout=timeout,
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            first_output = os.path.join(temp_dir, "first.png")
            second_output = os.path.join(temp_dir, "second.png")

            def stop_one_partial_batch(_process):
                with open(first_output, "wb") as stream:
                    stream.write(b"png")
                return "", ""

            with mock.patch.object(
                volume_rendering.subprocess,
                "Popen",
                return_value=TimedOutProcess(),
            ), mock.patch.object(
                volume_rendering,
                "_stop_process_group",
                side_effect=stop_one_partial_batch,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "1 of 2 expected screenshots",
                ):
                    volume_rendering._run_mricrogl_command(
                        ["MRIcroGL", "-s", "script.py"],
                        timeout_s=120,
                        output_dir=temp_dir,
                        expected_outputs=[first_output, second_output],
                    )

            self.assertTrue(os.path.isfile(first_output))
            self.assertFalse(os.path.exists(second_output))

    def test_timeout_after_all_outputs_treats_batch_as_complete(self):
        class TimedOutProcess:
            pid = 4242

            def communicate(self, timeout=None):
                raise volume_rendering.subprocess.TimeoutExpired(
                    cmd=["MRIcroGL"],
                    timeout=timeout,
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            expected_outputs = [
                os.path.join(temp_dir, "first.png"),
                os.path.join(temp_dir, "second.png"),
            ]

            def stop_complete_batch(_process):
                for path in expected_outputs:
                    with open(path, "wb") as stream:
                        stream.write(b"png")
                return "", ""

            with mock.patch.object(
                volume_rendering.subprocess,
                "Popen",
                return_value=TimedOutProcess(),
            ), mock.patch.object(
                volume_rendering,
                "_stop_process_group",
                side_effect=stop_complete_batch,
            ):
                result = volume_rendering._run_mricrogl_command(
                    ["MRIcroGL", "-s", "script.py"],
                    timeout_s=120,
                    output_dir=temp_dir,
                    expected_outputs=expected_outputs,
                )

            self.assertEqual(result, ("", ""))


if __name__ == "__main__":
    unittest.main()
