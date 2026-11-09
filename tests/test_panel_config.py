"""Tests for the dependency-light custom panel YAML loader."""

import os
import tempfile
import unittest

from t2vesselviewcode import panel_config


class TestPanelConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config_dir = os.path.join(self.tmp.name, "config")
        os.makedirs(self.config_dir, exist_ok=True)
        self.overlay_a = self._touch("overlay_a.nii.gz")
        self.overlay_b = self._touch("overlay_b.nii.gz")

    def tearDown(self):
        self.tmp.cleanup()

    def _touch(self, name):
        path = os.path.join(self.config_dir, name)
        with open(path, "wb") as stream:
            stream.write(b"test")
        return path

    def _write_yaml(self, text):
        path = os.path.join(self.config_dir, "panel.yaml")
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(text)
        return path

    def test_loads_valid_config_and_resolves_relative_paths(self):
        path = self._write_yaml(
            """
angles:
  - superior
  - left
  - superior
slots:
  - base: t1
    overlays:
      - path: overlay_a.nii.gz
        color: green
        name: PET
        opacity: 60
        min: 0.5
        max: 12.5
  - base: t2
    overlays:
      - path: overlay_b.nii.gz
        color: hot
        name: fMRI
        opacity: 50
"""
        )

        config = panel_config.load_custom_overlay_panels_config(path)

        self.assertEqual(config["angles"], ["superior", "left"])
        self.assertEqual(config["slice_erode_depth"], 35)
        self.assertEqual(config["slice_erode_prefix"], "035")
        self.assertEqual(config["pptx_name"], "custom_overlay_panels")
        self.assertEqual([slot["base"] for slot in config["slots"]], ["t1", "t2"])
        self.assertEqual(
            [(slot["row"], slot["column"]) for slot in config["slots"]],
            [("top", 0), ("top", 1)],
        )
        self.assertEqual(config["rows"]["bottom"], [])
        overlay = config["slots"][0]["overlays"][0]
        self.assertEqual(overlay["path"], self.overlay_a)
        self.assertEqual(overlay["color"], "2green")
        self.assertEqual(overlay["opacity"], 60)
        self.assertEqual(overlay["min"], 0.5)
        self.assertEqual(overlay["max"], 12.5)
        auto_window_overlay = config["slots"][1]["overlays"][0]
        self.assertNotIn("min", auto_window_overlay)
        self.assertNotIn("max", auto_window_overlay)

    def test_repeated_bases_are_allowed(self):
        path = self._write_yaml(
            """
angles: [left]
slots:
  - base: t1
    overlays:
      - {path: overlay_a.nii.gz, name: First}
  - base: t1
    overlays:
      - {path: overlay_b.nii.gz, name: Second}
"""
        )
        config = panel_config.load_custom_overlay_panels_config(path)
        self.assertEqual([slot["base"] for slot in config["slots"]], ["t1", "t1"])

    def test_slice_erode_depth_override_and_validation(self):
        path = self._write_yaml(
            """
slice_erode_depth: "040"
angles: [left]
slots:
  - {base: t1}
  - {base: flair}
"""
        )
        config = panel_config.load_custom_overlay_panels_config(path)
        self.assertEqual(config["slice_erode_depth"], 40)
        self.assertEqual(config["slice_erode_prefix"], "040")

        invalid_values = (True, -1, 35.5, "not-a-depth")
        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "non-negative integer"):
                    panel_config.parse_slice_erode_depth(value)

    def test_custom_pptx_name_override_and_validation(self):
        path = self._write_yaml(
            """
pptx_name: "Longitudinal comparison.pptx"
angles: [left]
slots:
  - {base: t1}
  - {base: flair}
"""
        )
        config = panel_config.load_custom_overlay_panels_config(path)
        self.assertEqual(
            config["pptx_name"],
            "Longitudinal comparison",
        )

        for invalid_name in ("", "../outside", "folder/name", "bad:name"):
            with self.subTest(invalid_name=invalid_name):
                with self.assertRaises(ValueError):
                    panel_config.parse_custom_pptx_name(invalid_name)

    def test_structural_only_slot_accepts_omitted_null_or_empty_overlays(self):
        structural_forms = (
            "  - base: flair\n",
            "  - base: flair\n    overlays:\n",
            "  - base: flair\n    overlays: []\n",
        )
        for structural_slot in structural_forms:
            with self.subTest(structural_slot=structural_slot):
                path = self._write_yaml(
                    "angles: [left]\n"
                    "slots:\n"
                    "  - base: t1\n"
                    "    overlays:\n"
                    "      - {path: overlay_a.nii.gz, name: Map}\n"
                    + structural_slot
                )
                config = panel_config.load_custom_overlay_panels_config(path)
                flair_slot = config["slots"][1]
                self.assertEqual(flair_slot["base"], "flair")
                self.assertEqual(flair_slot["overlays"], [])
                self.assertEqual(flair_slot["label"], "FLAIR")

    def test_two_row_layout_normalizes_top_then_bottom(self):
        path = self._write_yaml(
            """
angles: [left]
rows:
  top:
    - {base: t1}
    - {base: flair}
    - {base: t2}
    - {base: t1}
  bottom:
    - {base: flair}
    - {base: t1}
"""
        )
        config = panel_config.load_custom_overlay_panels_config(path)
        self.assertEqual(
            [
                (slot["index"], slot["row"], slot["column"], slot["base"])
                for slot in config["slots"]
            ],
            [
                (0, "top", 0, "t1"),
                (1, "top", 1, "flair"),
                (2, "top", 2, "t2"),
                (3, "top", 3, "t1"),
                (4, "bottom", 0, "flair"),
                (5, "bottom", 1, "t1"),
            ],
        )
        self.assertEqual(
            [slot["index"] for slot in config["rows"]["top"]],
            [0, 1, 2, 3],
        )
        self.assertEqual(
            [slot["index"] for slot in config["rows"]["bottom"]],
            [4, 5],
        )

    def test_rejects_invalid_or_mixed_row_layouts(self):
        invalid_layouts = (
            """
angles: [left]
slots: [{base: t1}, {base: flair}]
rows:
  top: [{base: t1}]
  bottom: [{base: flair}]
""",
            """
angles: [left]
rows:
  top: [{base: t1}]
""",
            """
angles: [left]
rows:
  top: [{base: t1}]
  bottom: [{base: flair}]
  middle: [{base: t2}]
""",
            """
angles: [left]
rows:
  top: []
  bottom: [{base: flair}]
""",
            """
angles: [left]
rows:
  top:
    - {base: t1}
    - {base: t1}
    - {base: t1}
    - {base: t1}
    - {base: t1}
  bottom: [{base: flair}]
""",
        )
        for text in invalid_layouts:
            with self.subTest(text=text):
                path = self._write_yaml(text)
                with self.assertRaises(ValueError):
                    panel_config.load_custom_overlay_panels_config(path)

    def test_rejects_non_list_overlays_value(self):
        path = self._write_yaml(
            """
angles: [left]
slots:
  - {base: t1, overlays: [{path: overlay_a.nii.gz}]}
  - base: flair
    overlays: {path: overlay_b.nii.gz}
"""
        )
        with self.assertRaisesRegex(ValueError, "overlays must be a list"):
            panel_config.load_custom_overlay_panels_config(path)

    def test_rejects_unknown_angle(self):
        path = self._write_yaml(
            """
angles: [diagonal]
slots:
  - {base: t1, overlays: [{path: overlay_a.nii.gz}]}
  - {base: flair, overlays: [{path: overlay_b.nii.gz}]}
"""
        )
        with self.assertRaises(ValueError):
            panel_config.load_custom_overlay_panels_config(path)

    def test_rejects_slot_count_outside_two_to_four(self):
        path = self._write_yaml(
            """
angles: [left]
slots:
  - {base: t1, overlays: [{path: overlay_a.nii.gz}]}
"""
        )
        with self.assertRaises(ValueError):
            panel_config.load_custom_overlay_panels_config(path)

    def test_rejects_old_plane_specific_t2_base(self):
        path = self._write_yaml(
            """
angles: [left]
slots:
  - {base: t1, overlays: [{path: overlay_a.nii.gz}]}
  - {base: t2_sag, overlays: [{path: overlay_b.nii.gz}]}
"""
        )
        with self.assertRaises(ValueError):
            panel_config.load_custom_overlay_panels_config(path)

    def test_rejects_unpaired_or_reversed_window(self):
        missing_max = self._write_yaml(
            """
angles: [left]
slots:
  - base: t1
    overlays:
      - {path: overlay_a.nii.gz, min: 1}
  - {base: flair, overlays: [{path: overlay_b.nii.gz}]}
"""
        )
        with self.assertRaisesRegex(ValueError, "provided together"):
            panel_config.load_custom_overlay_panels_config(missing_max)

        reversed_window = self._write_yaml(
            """
angles: [left]
slots:
  - base: t1
    overlays:
      - {path: overlay_a.nii.gz, min: 5, max: 2}
  - {base: flair, overlays: [{path: overlay_b.nii.gz}]}
"""
        )
        with self.assertRaisesRegex(ValueError, "greater than min"):
            panel_config.load_custom_overlay_panels_config(reversed_window)

    def test_rejects_non_integer_or_out_of_range_opacity(self):
        for opacity in ("50.5", 101, -1):
            path = self._write_yaml(
                f"""
angles: [left]
slots:
  - base: t1
    overlays:
      - {{path: overlay_a.nii.gz, opacity: {opacity}}}
  - {{base: flair, overlays: [{{path: overlay_b.nii.gz}}]}}
"""
            )
            with self.subTest(opacity=opacity):
                with self.assertRaisesRegex(ValueError, "integer from 0 to 100"):
                    panel_config.load_custom_overlay_panels_config(path)

    def test_rejects_missing_overlay_and_name_with_spaces(self):
        missing = self._write_yaml(
            """
angles: [left]
slots:
  - {base: t1, overlays: [{path: missing.nii.gz}]}
  - {base: flair, overlays: [{path: overlay_b.nii.gz}]}
"""
        )
        with self.assertRaises(FileNotFoundError):
            panel_config.load_custom_overlay_panels_config(missing)

        bad_name = self._write_yaml(
            """
angles: [left]
slots:
  - base: t1
    overlays:
      - {path: overlay_a.nii.gz, name: "Has spaces"}
  - {base: flair, overlays: [{path: overlay_b.nii.gz}]}
"""
        )
        with self.assertRaisesRegex(ValueError, "must not contain spaces"):
            panel_config.load_custom_overlay_panels_config(bad_name)

    def test_surgical_angle_rows_have_requested_camera_and_clip_values(self):
        rows = panel_config.angle_rows(
            [
                "surg_left_lat",
                "surg_right_lat",
                "surg_left_ato",
                "surg_right_ato",
            ]
        )
        self.assertEqual(
            rows,
            [
                ["surg_left_lat", 270, 180, 90, 180],
                ["surg_right_lat", 90, 180, 270, 180],
                ["surg_left_ato", 300, 175, 225, 0],
                ["surg_right_ato", 60, 175, 125, 0],
            ],
        )

    def test_t2_source_preferences_and_fallbacks(self):
        self.assertEqual(
            panel_config.resolve_t2_sources(
                [
                    "left",
                    "right",
                    "anterior",
                    "superior",
                    "surg_left_ato",
                    "surg_right_lat",
                ],
                [
                    "t2_sag_left",
                    "t2_sag_right",
                    "t2_sag_generic",
                    "t2_cor",
                    "t2_tra",
                    "t2_3d",
                ],
            ),
            {
                "left": "t2_sag_left",
                "right": "t2_sag_right",
                "anterior": "t2_cor",
                "superior": "t2_tra",
                "surg_left_ato": "t2_sag_left",
                "surg_right_lat": "t2_sag_right",
            },
        )
        self.assertEqual(
            panel_config.resolve_t2_sources(
                ["left", "right", "surg_left_ato", "surg_right_ato"],
                ["t2_sag_generic", "t2_3d", "t2_tra"],
            ),
            {
                "left": "t2_sag_generic",
                "right": "t2_sag_generic",
                "surg_left_ato": "t2_sag_generic",
                "surg_right_ato": "t2_sag_generic",
            },
        )
        self.assertEqual(
            panel_config.resolve_t2_sources(
                ["left", "anterior", "superior", "surg_left_ato"],
                ["t2_3d", "t2_tra"],
            ),
            {
                "left": "t2_3d",
                "anterior": "t2_3d",
                "superior": "t2_tra",
                "surg_left_ato": "t2_3d",
            },
        )

    def test_opposite_sagittal_side_is_never_used(self):
        self.assertEqual(
            panel_config.resolve_t2_sources(
                ["right"],
                ["t2_sag_left", "t2_tra"],
            ),
            {"right": "t2_tra"},
        )
        with self.assertRaisesRegex(
            ValueError,
            r"surg_right_lat.*t2_sag_right, t2_sag_generic, t2_3d",
        ):
            panel_config.resolve_t2_sources(
                ["surg_right_lat"],
                ["t2_sag_left", "t2_tra"],
            )

    def test_t2_source_resolution_fails_before_partial_render(self):
        with self.assertRaisesRegex(ValueError, "anterior.*t2_cor, t2_3d"):
            panel_config.resolve_t2_sources(
                ["left", "anterior"],
                ["t2_sag_left", "t2_tra"],
            )

    def test_groups_angles_by_resolved_t2_source(self):
        angles = ["superior", "left", "anterior", "surg_right_lat"]
        resolved = panel_config.resolve_t2_sources(
            angles,
            [
                "t2_sag_left",
                "t2_sag_generic",
                "t2_cor",
                "t2_tra",
            ],
        )
        self.assertEqual(
            panel_config.group_angles_by_t2_source(angles, resolved),
            [
                {"source": "t2_tra", "angles": ["superior"]},
                {"source": "t2_sag_left", "angles": ["left"]},
                {"source": "t2_cor", "angles": ["anterior"]},
                {"source": "t2_sag_generic", "angles": ["surg_right_lat"]},
            ],
        )


if __name__ == "__main__":
    unittest.main()
