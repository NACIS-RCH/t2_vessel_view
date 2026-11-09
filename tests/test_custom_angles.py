"""Tests for brand-new CLI angle parsing and T2 inference."""

import unittest
from unittest import mock

from t2vesselviewcode import custom_angles
from t2vesselviewcode import panel_config


class TestCustomAngles(unittest.TestCase):
    def test_builds_ordered_display_and_slice_rows(self):
        specs = custom_angles.build_custom_angle_specs(
            [
                ["My_View", "240", "170"],
                ["second", "10.5", "-20"],
            ],
            [
                ["my_view", "120", "0"],
                ["second", "15", "5"],
            ],
            require_slice_planes=True,
        )
        self.assertEqual(
            custom_angles.display_rows(specs),
            [
                [240.0, 170.0, "my_view"],
                [10.5, -20.0, "second"],
            ],
        )
        self.assertEqual(
            custom_angles.slice_rows(specs)[0],
            ["my_view", 240.0, 170.0, 120.0, 0.0],
        )

    def test_rejects_reserved_duplicate_and_incomplete_definitions(self):
        invalid_calls = (
            lambda: custom_angles.build_custom_angle_specs(
                [["left", "1", "2"]],
            ),
            lambda: custom_angles.build_custom_angle_specs(
                [["new", "1", "2"], ["NEW", "3", "4"]],
            ),
            lambda: custom_angles.build_custom_angle_specs(
                [["new", "1", "2"]],
                [["other", "3", "4"]],
            ),
            lambda: custom_angles.build_custom_angle_specs(
                [["new", "nan", "2"]],
            ),
            lambda: custom_angles.build_custom_angle_specs(
                [["new", "1", "2"]],
                require_slice_planes=True,
            ),
        )
        for invalid_call in invalid_calls:
            with self.subTest(invalid_call=invalid_call):
                with self.assertRaises(ValueError):
                    invalid_call()

    def test_spherical_distance_handles_wrap_and_upside_down_views(self):
        wrapped = panel_config.angular_distance_degrees(
            panel_config.viewing_direction(359, 0),
            panel_config.viewing_direction(1, 0),
        )
        self.assertAlmostEqual(wrapped, 2.0, places=6)
        upside_down_left = panel_config.angular_distance_degrees(
            panel_config.viewing_direction(270, 180),
            panel_config.viewing_direction(90, 0),
        )
        self.assertAlmostEqual(upside_down_left, 0.0, places=6)

    def test_unambiguous_nearest_family_inherits_existing_rules(self):
        result = panel_config.infer_custom_angle_t2_source(
            90,
            0,
            ["t2_sag_left", "t2_sag_generic", "t2_3d"],
        )
        self.assertFalse(result["ambiguous"])
        self.assertEqual(result["source"], "t2_sag_left")

    def test_ambiguous_ties_use_data_aware_rules(self):
        sag_tra = panel_config.infer_custom_angle_t2_source(
            90,
            45,
            ["t2_sag_left", "t2_tra", "t2_cor"],
        )
        self.assertTrue(sag_tra["ambiguous"])
        self.assertEqual(sag_tra["source"], "t2_sag_left")

        sag_tra_opposite_only = panel_config.infer_custom_angle_t2_source(
            90,
            45,
            ["t2_sag_right", "t2_tra", "t2_cor"],
        )
        self.assertEqual(sag_tra_opposite_only["source"], "t2_tra")

        tra_cor = panel_config.infer_custom_angle_t2_source(
            180,
            45,
            ["t2_tra", "t2_cor"],
        )
        self.assertEqual(tra_cor["source"], "t2_cor")

        sag_cor = panel_config.infer_custom_angle_t2_source(
            150.06305914105693,
            2.886139402585832,
            ["t2_sag_left", "t2_cor"],
        )
        self.assertEqual(sag_cor["source"], "t2_sag_left")

        prefer_3d = panel_config.infer_custom_angle_t2_source(
            90,
            45,
            ["t2_sag_left", "t2_tra", "t2_3d"],
        )
        self.assertEqual(prefer_3d["source"], "t2_3d")

    def test_left_right_sagittal_tie_disables_sagittal_without_3d(self):
        tied = {
            "distance": 90.0,
            "families": ["sag_left", "sag_right"],
            "representatives": {
                "sag_left": "left",
                "sag_right": "right",
            },
            "labels": ["left", "right"],
        }
        with mock.patch.object(
            panel_config,
            "nearest_angle_families",
            return_value=tied,
        ):
            with self.assertRaises(ValueError):
                panel_config.infer_custom_angle_t2_source(
                    0,
                    0,
                    ["t2_sag_left", "t2_sag_right", "t2_sag_generic"],
                )
            transverse = panel_config.infer_custom_angle_t2_source(
                0,
                0,
                ["t2_sag_left", "t2_sag_right", "t2_tra"],
            )
        self.assertEqual(transverse["source"], "t2_tra")

    def test_three_family_tie_uses_sagittal_then_transverse_then_coronal(self):
        tied = {
            "distance": 60.0,
            "families": ["sag_left", "tra", "cor"],
            "representatives": {
                "sag_left": "left",
                "tra": "superior",
                "cor": "anterior",
            },
            "labels": ["left", "superior", "anterior"],
        }
        with mock.patch.object(
            panel_config,
            "nearest_angle_families",
            return_value=tied,
        ):
            sagittal = panel_config.infer_custom_angle_t2_source(
                0,
                0,
                ["t2_sag_left", "t2_tra", "t2_cor"],
            )
            transverse = panel_config.infer_custom_angle_t2_source(
                0,
                0,
                ["t2_tra", "t2_cor"],
            )
            coronal = panel_config.infer_custom_angle_t2_source(
                0,
                0,
                ["t2_cor"],
            )
        self.assertEqual(sagittal["source"], "t2_sag_left")
        self.assertEqual(transverse["source"], "t2_tra")
        self.assertEqual(coronal["source"], "t2_cor")


if __name__ == "__main__":
    unittest.main()
