"""Tests for physical-unit morphology radii in watershed masking."""

import unittest

import SimpleITK as sitk

from t2vesselviewcode.scalpFlair import _radius_mm_to_voxels


class TestScalpFlairSpacing(unittest.TestCase):
    def test_one_mm_spacing_preserves_original_radii(self):
        image = sitk.Image([8, 8, 8], sitk.sitkUInt8)
        image.SetSpacing((1.0, 1.0, 1.0))

        self.assertEqual(_radius_mm_to_voxels(image, 19.0), (19, 19, 19))
        self.assertEqual(_radius_mm_to_voxels(image, 5.0), (5, 5, 5))
        self.assertEqual(_radius_mm_to_voxels(image, 3.0), (3, 3, 3))

    def test_half_mm_spacing_doubles_voxel_radii(self):
        image = sitk.Image([8, 8, 8], sitk.sitkUInt8)
        image.SetSpacing((0.5, 0.5, 0.5))

        self.assertEqual(_radius_mm_to_voxels(image, 19.0), (38, 38, 38))
        self.assertEqual(_radius_mm_to_voxels(image, 5.0), (10, 10, 10))
        self.assertEqual(_radius_mm_to_voxels(image, 3.0), (6, 6, 6))

    def test_anisotropic_spacing_produces_per_axis_radii(self):
        image = sitk.Image([8, 8, 8], sitk.sitkUInt8)
        image.SetSpacing((0.5, 1.0, 2.0))

        self.assertEqual(_radius_mm_to_voxels(image, 5.0), (10, 5, 3))

    def test_nonpositive_radius_is_rejected(self):
        image = sitk.Image([8, 8, 8], sitk.sitkUInt8)

        with self.assertRaises(ValueError):
            _radius_mm_to_voxels(image, 0)


if __name__ == "__main__":
    unittest.main()
