"""Tests for opt-in display panel resolution."""

import unittest

from t2vesselviewcode import panel_registry


class TestPanelRegistry(unittest.TestCase):
    def test_default_empty(self):
        self.assertEqual(panel_registry.resolve_requested_panels(None), set())
        self.assertEqual(panel_registry.resolve_requested_panels([]), set())

    def test_standard_alias(self):
        panels = panel_registry.resolve_requested_panels(["standard"])
        self.assertEqual(
            panels,
            {
                "t1_overview",
                "t2_overview",
                "multimodal_overview",
                "multimodal_overview_other_angles",
            },
        )

    def test_all_alias(self):
        panels = panel_registry.resolve_requested_panels(["all"])
        expected = set(panel_registry.PANEL_IDS) - {"custom_overlay_panels"}
        self.assertEqual(panels, expected)

    def test_custom_overlay_panels_raw_need(self):
        self.assertEqual(
            panel_registry.raw_renders_needed({"custom_overlay_panels"}),
            {"custom_panels"},
        )

    def test_panel_preset_shim(self):
        panels = panel_registry.resolve_requested_panels(
            [],
            panel_preset="quant_map_mm_panel",
        )
        self.assertEqual(panels, {"quant_map_mm_panel"})

    def test_raw_renders_needed(self):
        self.assertEqual(
            panel_registry.raw_renders_needed({"t1_overview"}),
            {"t1"},
        )
        self.assertEqual(
            panel_registry.raw_renders_needed({"t1_overlay_overview"}),
            {"t1_overlay"},
        )
        self.assertIn(
            "t2_flair",
            panel_registry.raw_renders_needed({"multimodal_overview"}),
        )
        self.assertEqual(
            panel_registry.raw_renders_needed({"quant_map_mm_panel"}),
            {"qmm"},
        )

    def test_unknown_panel_raises(self):
        with self.assertRaises(ValueError):
            panel_registry.resolve_requested_panels(["not_a_panel"])


if __name__ == "__main__":
    unittest.main()
