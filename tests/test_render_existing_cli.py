import importlib.util
import os
import tempfile
import unittest

HELPER_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "t2vesselviewcode",
    "render_existing_cli.py",
)
spec = importlib.util.spec_from_file_location("render_existing_cli", HELPER_PATH)
render_existing_cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render_existing_cli)

_build_command = render_existing_cli._build_command


class TestRenderExistingCli(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.source_dir = os.path.join(self.test_dir.name, "T2VesselView_old")
        os.makedirs(self.source_dir, exist_ok=True)

    def tearDown(self):
        self.test_dir.cleanup()

    def _touch(self, relative_path):
        path = os.path.join(self.source_dir, relative_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8"):
            pass
        return path

    def test_build_command_auto_fills_basic_t1(self):
        t1_path = self._touch("Processing/Preprocessed_T1/Preprocessed_main_image.nii.gz")

        cmd = _build_command(
            self.source_dir,
            ["--overlay1-path", "/tmp/overlay.nii.gz"]
        )

        self.assertIn("-i", cmd)
        self.assertEqual(cmd[cmd.index("-i") + 1], t1_path)
        self.assertIn("--render-existing-erosions", cmd)
        self.assertIn("--render-source-dir", cmd)
        self.assertEqual(cmd[cmd.index("--render-source-dir") + 1], self.source_dir)
        self.assertIn("--overlay1-path", cmd)

    def test_build_command_auto_fills_quant_map_required_inputs(self):
        flair_path = self._touch("Processing/Preprocessed_FLAIR/Preprocessed_flair.nii.gz")
        t2_path = self._touch("Processing/Preprocessed_T2_Sag/Preprocessed_t2_sag.nii.gz")
        self._touch("Processing/Preprocessed_T1/Preprocessed_main_image.nii.gz")

        cmd = _build_command(
            self.source_dir,
            ["--panel-preset", "quant_map_mm_panel"]
        )

        self.assertIn("-f", cmd)
        self.assertEqual(cmd[cmd.index("-f") + 1], flair_path)
        self.assertIn("-s", cmd)
        self.assertEqual(cmd[cmd.index("-s") + 1], t2_path)


if __name__ == "__main__":
    unittest.main()
