"""Subprocess checks for CLI imports and custom config forwarding."""

import os
import subprocess
import sys
import tempfile
import unittest


class TestCliImportChecks(unittest.TestCase):
    def test_main_module_help_has_no_commandline_attribute_error(self):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "t2vesselviewcode.t2_vessel_view_main",
                "--help",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
        combined = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, combined)
        self.assertNotIn("AttributeError", combined)
        self.assertIn("--panel-config", combined)
        self.assertIn("custom_overlay_trio", combined)

    def test_render_existing_dry_run_forwards_custom_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = os.path.join(temp_dir, "T2VesselView")
            t1_dir = os.path.join(
                source_dir,
                "Processing",
                "Preprocessed_T1",
            )
            os.makedirs(t1_dir, exist_ok=True)
            t1_path = os.path.join(t1_dir, "Preprocessed_main_image.nii.gz")
            with open(t1_path, "wb") as stream:
                stream.write(b"test")
            config_path = os.path.join(temp_dir, "panel.yaml")
            with open(config_path, "w", encoding="utf-8") as stream:
                stream.write("angles: [left]\nslots: []\n")

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "t2vesselviewcode.render_existing_cli",
                    "--source-dir",
                    source_dir,
                    "--panels",
                    "custom_overlay_trio",
                    "--panel-config",
                    config_path,
                    "--dry-run",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30,
            )

        combined = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, combined)
        self.assertNotIn("AttributeError", combined)
        self.assertIn("custom_overlay_trio", combined)
        self.assertIn(config_path, combined)
        self.assertIn("Dry run requested", combined)


if __name__ == "__main__":
    unittest.main()
