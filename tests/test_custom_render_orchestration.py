"""Tests for custom slot validation and render grouping in the main pipeline."""

import os
import sys
import tempfile
import unittest
from unittest import mock

# Main imports dir_structure, which triggers commandline parsing.
sys.argv = [
    "test_custom_render_orchestration.py",
    "-d",
    "/tmp",
    "-i",
    "/tmp/t1.nii.gz",
]

from t2vesselviewcode import commandline
from t2vesselviewcode import dir_structure
from t2vesselviewcode import png_postprocess
from t2vesselviewcode import t2_vessel_view_main
from t2vesselviewcode import volume_rendering


class TestCustomRenderOrchestration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "T2VesselView")
        dir_structure._set_t2vv_root(self.root)
        commandline.args.custom_angles = []
        commandline.args.qmm_angles = None
        commandline.args.qmm_main_erode_depth = 30
        for index in range(1, 5):
            setattr(commandline.args, f"overlay{index}_path", None)
            setattr(commandline.args, f"overlay{index}_color", None)
            setattr(commandline.args, f"overlay{index}_name", f"Overlay{index}")
            setattr(commandline.args, f"overlay{index}_min", None)
            setattr(commandline.args, f"overlay{index}_max", None)
            setattr(commandline.args, f"overlay{index}_opacity", None)
        self.overlay_path = self._touch(
            os.path.join(self.tmp.name, "overlay.nii.gz")
        )
        self._touch(
            os.path.join(
                dir_structure.eroded_nifti_t1_dir,
                "035_eroded_t1.nii.gz",
            )
        )
        self._touch(
            os.path.join(
                dir_structure.eroded_nifti_t1_dir,
                "005_eroded_t1.nii.gz",
            )
        )
        self._touch(
            os.path.join(
                dir_structure.eroded_nifti_t2_sag_dir,
                "035_eroded_t2_sag.nii.gz",
            )
        )
        self._touch(
            os.path.join(
                dir_structure.eroded_nifti_t2_sag_dir,
                "005_eroded_t2_sag.nii.gz",
            )
        )

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def _touch(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as stream:
            stream.write(b"test")
        return path

    def _write_config(
        self,
        angles,
        include_structural_flair=False,
        slice_erode_depth=35,
    ):
        path = os.path.join(self.tmp.name, "panel.yaml")
        flair_slot = ""
        if include_structural_flair:
            flair_slot = "  - base: flair\n"
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(
                f"slice_erode_depth: {slice_erode_depth}\n"
                + "angles:\n"
                + "".join(f"  - {angle}\n" for angle in angles)
                + "slots:\n"
                + "  - base: t1\n"
                + "    overlays:\n"
                + f"      - {{path: {self.overlay_path}, name: MapA}}\n"
                + "  - base: t2\n"
                + "    overlays:\n"
                + f"      - {{path: {self.overlay_path}, name: MapB}}\n"
                + flair_slot
            )
        return path

    def _patch_render_dependencies(self):
        return (
            mock.patch.object(
                volume_rendering,
                "resolve_mricrogl_executable",
                return_value="/fake/MRIcroGL",
            ),
            mock.patch.object(
                volume_rendering,
                "compute_series_window",
                return_value=(0, 100),
            ),
            mock.patch.object(
                volume_rendering,
                "refine_window_vmax_by_saturation_circles",
                return_value=(0, 120),
            ),
            mock.patch.object(
                volume_rendering,
                "render_quant_map_mm_panel_slices_mricrogl",
            ),
            mock.patch.object(
                png_postprocess,
                "run_preset_custom_overlay_panels",
            ),
            mock.patch.object(
                dir_structure,
                "prune_empty_directories",
            ),
        )

    def test_groups_t2_angles_and_uses_one_composite_slice_depth(self):
        self._touch(
            os.path.join(
                dir_structure.eroded_nifti_t2_cor_dir,
                "035_eroded_t2_cor.nii.gz",
            )
        )
        commandline.args.panel_config = self._write_config(
            ["left", "anterior", "surg_left_ato"]
        )
        patches = self._patch_render_dependencies()
        with patches[0], patches[1], patches[2], \
                patches[3] as render_mock, patches[4] as stitch_mock, patches[5]:
            result = t2_vessel_view_main._run_render_outputs(
                {"custom_overlay_panels"}
            )

        self.assertEqual(result, 0)
        self.assertEqual(render_mock.call_count, 3)
        for call in render_mock.call_args_list:
            self.assertFalse(call.kwargs["slice_all_depths"])
            self.assertEqual(call.kwargs["main_erode_prefix"], "035")
            self.assertFalse(call.kwargs["save_structural_outputs"])
            self.assertTrue(call.kwargs["save_overlay_outputs"])
            self.assertEqual(call.kwargs["timeout_s"], 3600)
        t2_angle_groups = [
            [row[0] for row in call.kwargs["angles"]]
            for call in render_mock.call_args_list
            if os.path.basename(call.args[1]) == "01_t2"
        ]
        self.assertEqual(
            t2_angle_groups,
            [["left", "surg_left_ato"], ["anterior"]],
        )
        t1_call = next(
            call for call in render_mock.call_args_list
            if os.path.basename(call.args[1]) == "00_t1"
        )
        sagittal_call = next(
            call for call in render_mock.call_args_list
            if os.path.basename(call.args[1]) == "01_t2"
            and [row[0] for row in call.kwargs["angles"]]
            == ["left", "surg_left_ato"]
        )
        self.assertEqual(len(t1_call.args[0]), 2)
        self.assertEqual(len(sagittal_call.args[0]), 2)
        stitch_mock.assert_called_once()

    def test_cli_custom_angle_is_appended_to_yaml_panel(self):
        commandline.args.panel_config = self._write_config(["left"])
        commandline.args.custom_angles = [{
            "label": "my_view",
            "brain_az": 90.0,
            "brain_el": 0.0,
            "clip_az": 270.0,
            "clip_el": 0.0,
        }]
        patches = self._patch_render_dependencies()
        with patches[0], patches[1], patches[2], \
                patches[3] as render_mock, patches[4] as stitch_mock, patches[5]:
            result = t2_vessel_view_main._run_render_outputs(
                {"custom_overlay_panels"}
            )

        self.assertEqual(result, 0)
        t1_call = next(
            call for call in render_mock.call_args_list
            if os.path.basename(call.args[1]) == "00_t1"
        )
        self.assertEqual(
            [row[0] for row in t1_call.kwargs["angles"]],
            ["left", "my_view"],
        )
        t2_call = next(
            call for call in render_mock.call_args_list
            if os.path.basename(call.args[1]) == "01_t2"
        )
        self.assertEqual(
            [row[0] for row in t2_call.kwargs["angles"]],
            ["left", "my_view"],
        )
        self.assertEqual(
            stitch_mock.call_args.kwargs["angles"],
            ["left", "my_view"],
        )

    def test_standard_t1_raw_render_adds_custom_display_only(self):
        commandline.args.custom_angles = [{
            "label": "my_volume_view",
            "brain_az": 240.0,
            "brain_el": 170.0,
            "clip_az": None,
            "clip_el": None,
        }]
        with mock.patch.object(
            volume_rendering,
            "resolve_mricrogl_executable",
            return_value="/fake/MRIcroGL",
        ), mock.patch.object(
            volume_rendering,
            "compute_series_window",
            return_value=(0, 100),
        ), mock.patch.object(
            volume_rendering,
            "refine_window_vmax_by_saturation_circles",
            return_value=(0, 120),
        ), mock.patch.object(
            volume_rendering,
            "render_volume_and_save_pngs_mricrogl",
        ) as render_mock, mock.patch.object(
            png_postprocess,
            "run_preset_t1_overview_per_depth",
        ) as stitch_mock, mock.patch.object(
            dir_structure,
            "prune_empty_directories",
        ):
            result = t2_vessel_view_main._run_render_outputs(
                {"t1_overview"}
            )

        self.assertEqual(result, 0)
        self.assertEqual(render_mock.call_count, 1)
        angle_labels = [row[2] for row in render_mock.call_args.kwargs["angles"]]
        self.assertIn("my_volume_view", angle_labels)
        # Fixed overview stitching receives no custom-angle layout changes.
        stitch_mock.assert_called_once()

    def test_qmm_renders_and_stitches_custom_slice_angle(self):
        self._touch(
            os.path.join(
                dir_structure.eroded_nifti_flair_dir,
                "035_eroded_flair.nii.gz",
            )
        )
        for index in (1, 2):
            setattr(commandline.args, f"overlay{index}_path", self.overlay_path)
            setattr(commandline.args, f"overlay{index}_name", f"Map{index}")
            setattr(commandline.args, f"overlay{index}_color", "jet")
            setattr(commandline.args, f"overlay{index}_min", 0.0)
            setattr(commandline.args, f"overlay{index}_max", 10.0)
            setattr(commandline.args, f"overlay{index}_opacity", 50)
        commandline.args.qmm_main_erode_depth = 30
        commandline.args.qmm_angles = ["left"]
        commandline.args.custom_angles = [{
            "label": "my_qmm_view",
            "brain_az": 90.0,
            "brain_el": 0.0,
            "clip_az": 270.0,
            "clip_el": 0.0,
        }]

        with mock.patch.object(
            volume_rendering,
            "resolve_mricrogl_executable",
            return_value="/fake/MRIcroGL",
        ), mock.patch.object(
            volume_rendering,
            "compute_series_window",
            return_value=(0, 100),
        ), mock.patch.object(
            volume_rendering,
            "refine_window_vmax_by_saturation_circles",
            return_value=(0, 120),
        ), mock.patch.object(
            volume_rendering,
            "render_quant_map_mm_panel_slices_mricrogl",
        ) as render_mock, mock.patch.object(
            png_postprocess,
            "run_preset_quant_map_mm_panel",
        ) as stitch_mock, mock.patch.object(
            dir_structure,
            "prune_empty_directories",
        ):
            result = t2_vessel_view_main._run_render_outputs(
                {"quant_map_mm_panel"}
            )

        self.assertEqual(result, 0)
        custom_calls = [
            call for call in render_mock.call_args_list
            if call.kwargs.get("angles")
            and [row[0] for row in call.kwargs["angles"]]
            == ["my_qmm_view"]
        ]
        self.assertEqual(len(custom_calls), 3)
        self.assertIn(
            "my_qmm_view",
            stitch_mock.call_args.kwargs["qmm_angles"],
        )
        self.assertEqual(
            stitch_mock.call_args.kwargs["angle_to_t2_source"]["my_qmm_view"],
            "T2_sag",
        )

    def test_qmm_uses_matching_sagittal_source_for_each_side(self):
        self._touch(
            os.path.join(
                dir_structure.eroded_nifti_flair_dir,
                "035_eroded_flair.nii.gz",
            )
        )
        for side in ("left", "right"):
            for depth in ("005", "035"):
                self._touch(
                    os.path.join(
                        dir_structure.eroded_nifti_t2_sag_dir,
                        f"{depth}_eroded_t2_sag_{side}.nii.gz",
                    )
                )
        for index in (1, 2):
            setattr(commandline.args, f"overlay{index}_path", self.overlay_path)
            setattr(commandline.args, f"overlay{index}_name", f"Map{index}")
            setattr(commandline.args, f"overlay{index}_color", "jet")
            setattr(commandline.args, f"overlay{index}_min", 0.0)
            setattr(commandline.args, f"overlay{index}_max", 10.0)
            setattr(commandline.args, f"overlay{index}_opacity", 50)
        commandline.args.qmm_main_erode_depth = 30
        commandline.args.qmm_angles = ["left", "right"]

        with mock.patch.object(
            volume_rendering,
            "resolve_mricrogl_executable",
            return_value="/fake/MRIcroGL",
        ), mock.patch.object(
            volume_rendering,
            "compute_series_window",
            return_value=(0, 100),
        ), mock.patch.object(
            volume_rendering,
            "refine_window_vmax_by_saturation_circles",
            return_value=(0, 120),
        ), mock.patch.object(
            volume_rendering,
            "render_quant_map_mm_panel_slices_mricrogl",
        ) as render_mock, mock.patch.object(
            png_postprocess,
            "run_preset_quant_map_mm_panel",
        ) as stitch_mock, mock.patch.object(
            dir_structure,
            "prune_empty_directories",
        ):
            result = t2_vessel_view_main._run_render_outputs(
                {"quant_map_mm_panel"}
            )

        self.assertEqual(result, 0)
        sagittal_calls = [
            call for call in render_mock.call_args_list
            if os.path.basename(call.args[1]) == "T2_sag"
        ]
        self.assertEqual(len(sagittal_calls), 2)
        calls_by_angle = {
            tuple(row[0] for row in call.kwargs["angles"]): call
            for call in sagittal_calls
        }
        left_call = calls_by_angle[("left",)]
        right_call = calls_by_angle[("right",)]
        self.assertTrue(
            all("t2_sag_left" in path for path in left_call.args[0])
        )
        self.assertTrue(
            all("t2_sag_right" in path for path in right_call.args[0])
        )
        self.assertEqual(
            stitch_mock.call_args.kwargs["angle_to_t2_source"],
            {"left": "T2_sag", "right": "T2_sag"},
        )

    def test_qmm_validation_never_uses_opposite_sagittal_side(self):
        for depth in ("005", "035"):
            os.remove(
                os.path.join(
                    dir_structure.eroded_nifti_t2_sag_dir,
                    f"{depth}_eroded_t2_sag.nii.gz",
                )
            )
        self._touch(
            os.path.join(
                dir_structure.eroded_nifti_flair_dir,
                "035_eroded_flair.nii.gz",
            )
        )
        self._touch(
            os.path.join(
                dir_structure.eroded_nifti_t2_sag_dir,
                "035_eroded_t2_sag_left.nii.gz",
            )
        )
        commandline.args.qmm_angles = ["right"]

        with self.assertRaisesRegex(
            ValueError,
            r"right.*t2_sag_right, t2_sag_generic, t2_3d, t2_tra",
        ):
            t2_vessel_view_main._validate_render_existing_inputs(
                {"quant_map_mm_panel"}
            )

        self._touch(
            os.path.join(
                dir_structure.eroded_nifti_t2_tra_dir,
                "035_eroded_t2_tra.nii.gz",
            )
        )
        t2_vessel_view_main._validate_render_existing_inputs(
            {"quant_map_mm_panel"}
        )

    def test_matching_sagittal_side_is_used_for_each_angle_family(self):
        for depth in ("005", "035"):
            self._touch(
                os.path.join(
                    dir_structure.eroded_nifti_t2_sag_dir,
                    f"{depth}_eroded_t2_sag_left.nii.gz",
                )
            )
            self._touch(
                os.path.join(
                    dir_structure.eroded_nifti_t2_sag_dir,
                    f"{depth}_eroded_t2_sag_right.nii.gz",
                )
            )
        commandline.args.panel_config = self._write_config(
            [
                "left",
                "surg_left_ato",
                "right",
                "surg_right_lat",
            ]
        )
        patches = self._patch_render_dependencies()
        with patches[0], patches[1], patches[2], \
                patches[3] as render_mock, patches[4] as stitch_mock, patches[5]:
            result = t2_vessel_view_main._run_render_outputs(
                {"custom_overlay_panels"}
            )

        self.assertEqual(result, 0)
        t2_calls = [
            call for call in render_mock.call_args_list
            if os.path.basename(call.args[1]) == "01_t2"
        ]
        self.assertEqual(len(t2_calls), 2)
        calls_by_angles = {
            tuple(row[0] for row in call.kwargs["angles"]): call
            for call in t2_calls
        }
        left_call = calls_by_angles[("left", "surg_left_ato")]
        right_call = calls_by_angles[("right", "surg_right_lat")]
        self.assertTrue(
            all("t2_sag_left" in path for path in left_call.args[0])
        )
        self.assertTrue(
            all("t2_sag_right" in path for path in right_call.args[0])
        )
        self.assertFalse(
            any(
                os.path.basename(path).endswith("_t2_sag.nii.gz")
                for path in left_call.args[0] + right_call.args[0]
            )
        )
        stitch_mock.assert_called_once()

    def test_missing_t2_source_fails_before_any_render(self):
        commandline.args.panel_config = self._write_config(["left", "anterior"])
        patches = self._patch_render_dependencies()
        with patches[0], patches[1], patches[2], \
                patches[3] as render_mock, patches[4] as stitch_mock, patches[5]:
            with self.assertRaisesRegex(ValueError, "anterior"):
                t2_vessel_view_main._run_render_outputs(
                    {"custom_overlay_panels"}
                )

        render_mock.assert_not_called()
        stitch_mock.assert_not_called()

    def test_missing_configured_slice_depth_fails_before_render(self):
        commandline.args.panel_config = self._write_config(
            ["left"],
            slice_erode_depth=40,
        )
        patches = self._patch_render_dependencies()
        with patches[0], patches[1], patches[2], \
                patches[3] as render_mock, patches[4] as stitch_mock, patches[5]:
            with self.assertRaisesRegex(
                ValueError,
                r"requested 040; available 005, 035",
            ):
                t2_vessel_view_main._run_render_outputs(
                    {"custom_overlay_panels"}
                )

        render_mock.assert_not_called()
        stitch_mock.assert_not_called()

    def test_structural_only_flair_slot_renders_with_empty_overlays(self):
        self._touch(
            os.path.join(
                dir_structure.eroded_nifti_flair_dir,
                "035_eroded_flair.nii.gz",
            )
        )
        commandline.args.panel_config = self._write_config(
            ["left"],
            include_structural_flair=True,
        )
        patches = self._patch_render_dependencies()
        with patches[0], patches[1], patches[2], \
                patches[3] as render_mock, patches[4] as stitch_mock, patches[5]:
            result = t2_vessel_view_main._run_render_outputs(
                {"custom_overlay_panels"}
            )

        self.assertEqual(result, 0)
        flair_calls = [
            call for call in render_mock.call_args_list
            if os.path.basename(call.args[1]) == "02_flair"
        ]
        self.assertEqual(len(flair_calls), 1)
        self.assertEqual(flair_calls[0].kwargs["overlays"], [])
        stitched_slots = stitch_mock.call_args.kwargs["slots"]
        self.assertEqual(stitched_slots[2]["label"], "FLAIR")
        self.assertEqual(stitched_slots[2]["overlays"], [])

    def test_two_row_config_renders_each_normalized_slot_once(self):
        self._touch(
            os.path.join(
                dir_structure.eroded_nifti_flair_dir,
                "035_eroded_flair.nii.gz",
            )
        )
        config_path = os.path.join(self.tmp.name, "two_rows.yaml")
        with open(config_path, "w", encoding="utf-8") as stream:
            stream.write(
                "slice_erode_depth: 35\n"
                "pptx_name: two_row_comparison.pptx\n"
                "angles: [left]\n"
                "rows:\n"
                "  top:\n"
                "    - base: t1\n"
                "  bottom:\n"
                "    - base: t2\n"
                "    - base: flair\n"
            )
        commandline.args.panel_config = config_path
        patches = self._patch_render_dependencies()
        with patches[0], patches[1], patches[2], \
                patches[3] as render_mock, patches[4] as stitch_mock, patches[5]:
            result = t2_vessel_view_main._run_render_outputs(
                {"custom_overlay_panels"}
            )

        self.assertEqual(result, 0)
        self.assertEqual(render_mock.call_count, 3)
        slots = stitch_mock.call_args.kwargs["slots"]
        self.assertEqual(
            [
                (slot["index"], slot["row"], slot["column"], slot["base"])
                for slot in slots
            ],
            [
                (0, "top", 0, "t1"),
                (1, "bottom", 0, "t2"),
                (2, "bottom", 1, "flair"),
            ],
        )
        self.assertEqual(
            stitch_mock.call_args.kwargs["pptx_name"],
            "two_row_comparison",
        )

    def test_discovered_extra_base_renders_with_t1_windowing(self):
        for depth in ("005", "035"):
            self._touch(
                os.path.join(
                    dir_structure.eroded_nifti_dir,
                    "Extra",
                    "t1_gd",
                    f"{depth}_eroded_extra_t1_gd.nii.gz",
                )
            )
        config_path = os.path.join(self.tmp.name, "extra_panel.yaml")
        with open(config_path, "w", encoding="utf-8") as stream:
            stream.write(
                "slice_erode_depth: 35\n"
                "angles: [left]\n"
                "slots:\n"
                "  - base: t1\n"
                "  - base: t1_gd\n"
            )
        commandline.args.panel_config = config_path
        patches = self._patch_render_dependencies()
        with patches[0], patches[1] as window_mock, patches[2] as refine_mock, \
                patches[3] as render_mock, patches[4] as stitch_mock, patches[5]:
            result = t2_vessel_view_main._run_render_outputs(
                {"custom_overlay_panels"}
            )

        self.assertEqual(result, 0)
        extra_calls = [
            call for call in render_mock.call_args_list
            if os.path.basename(call.args[1]) == "01_t1_gd"
        ]
        self.assertEqual(len(extra_calls), 1)
        self.assertEqual(len(extra_calls[0].args[0]), 2)
        self.assertTrue(
            all("extra_t1_gd" in path for path in extra_calls[0].args[0])
        )
        self.assertGreaterEqual(
            window_mock.call_args_list.count(
                mock.call(
                    extra_calls[0].args[0],
                    low_pct=2.0,
                    high_pct=90.0,
                )
            ),
            1,
        )
        self.assertGreaterEqual(refine_mock.call_count, 2)
        stitched_slots = stitch_mock.call_args.kwargs["slots"]
        self.assertEqual(stitched_slots[1]["base"], "t1_gd")

    def test_custom_structural_windows_match_default_modality_rules(self):
        files = ["/tmp/035_eroded_t1.nii.gz"]
        with mock.patch.object(
            volume_rendering,
            "compute_series_window",
            return_value=(2, 90),
        ) as compute_mock, mock.patch.object(
            volume_rendering,
            "refine_window_vmax_by_saturation_circles",
            return_value=(2, 110),
        ) as refine_mock:
            t1_window = t2_vessel_view_main._custom_structural_window(
                "t1",
                files,
            )

        self.assertEqual(t1_window, (2, 110))
        compute_mock.assert_called_once_with(
            files,
            low_pct=2.0,
            high_pct=90.0,
        )
        refine_mock.assert_called_once_with(
            files,
            (2, 90),
            radius_mm=1.5,
            bright_threshold=250,
            max_valid_circle_locations=4,
            representative_slices=5,
            max_images_to_check=3,
            vmax_growth_factor=1.10,
            max_iterations=8,
        )

        with mock.patch.object(
            volume_rendering,
            "compute_series_window",
            return_value=(7, 99),
        ) as compute_mock, mock.patch.object(
            volume_rendering,
            "refine_window_vmax_by_saturation_circles",
        ) as refine_mock:
            flair_window = t2_vessel_view_main._custom_structural_window(
                "flair",
                files,
            )
        self.assertEqual(flair_window, (7, 99))
        compute_mock.assert_called_once_with(
            files,
            low_pct=7.5,
            high_pct=99.99,
        )
        refine_mock.assert_not_called()

        with mock.patch.object(
            volume_rendering,
            "compute_series_window",
            return_value=(0, 100),
        ) as compute_mock, mock.patch.object(
            volume_rendering,
            "refine_window_vmax_by_saturation_circles",
        ) as refine_mock:
            t2_window = t2_vessel_view_main._custom_structural_window(
                "t2",
                files,
            )
        self.assertEqual(t2_window, (0, 100))
        compute_mock.assert_called_once_with(
            files,
            low_pct=0.3,
            high_pct=99.75,
        )
        refine_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
