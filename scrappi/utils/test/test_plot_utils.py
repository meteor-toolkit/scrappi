"""scrappi.utils.tests.test_plot_utils - tests for scrappi.utils.plot_utils module"""

import unittest
from scrappi.utils.plot_utils import pad_plot_bounds

__author__ = "Sam Hunt <sam.hunt@npl.co.uk>"


class TestPlotUtils(unittest.TestCase):
    def test_pad_plot_bounds_rel_2(self):
        obj_bounds = (4, 3, 6, 9)

        plot_bounds = pad_plot_bounds(obj_bounds, padding_type="rel", padding_val=2)

        self.assertEqual(plot_bounds[0], 0)
        self.assertEqual(plot_bounds[1], -9)
        self.assertEqual(plot_bounds[2], 10)
        self.assertEqual(plot_bounds[3], 21)

    def test_pad_plot_bounds_abs_3(self):
        obj_bounds = (4, 3, 6, 9)

        plot_bounds = pad_plot_bounds(obj_bounds, padding_type="abs", padding_val=3)

        self.assertEqual(plot_bounds[0], 1)
        self.assertEqual(plot_bounds[1], 0)
        self.assertEqual(plot_bounds[2], 9)
        self.assertEqual(plot_bounds[3], 12)

    def test_pad_plot_bounds_None(self):
        obj_bounds = (4, 3, 6, 9)

        plot_bounds = pad_plot_bounds(obj_bounds, padding_type=None)

        self.assertEqual(plot_bounds[0], 4)
        self.assertEqual(plot_bounds[1], 3)
        self.assertEqual(plot_bounds[2], 6)
        self.assertEqual(plot_bounds[3], 9)

    def test_pad_plot_bounds_region_global(self):
        obj_bounds = (4, 3, 6, 9)

        plot_bounds = pad_plot_bounds(
            obj_bounds, padding_type="region", padding_val="global"
        )

        self.assertEqual(plot_bounds[0], -180)
        self.assertEqual(plot_bounds[1], -90)
        self.assertEqual(plot_bounds[2], 180)
        self.assertEqual(plot_bounds[3], 90)

    def test_pad_plot_bounds_region_invalid(self):
        obj_bounds = (4, 3, 6, 9)

        self.assertRaises(
            ValueError,
            pad_plot_bounds,
            obj_bounds,
            padding_type="region",
            padding_val="wrong",
        )

    def test_pad_plot_bounds_type_invalid(self):
        obj_bounds = (4, 3, 6, 9)

        self.assertRaises(ValueError, pad_plot_bounds, obj_bounds, padding_type="wrong")


if __name__ == "__main__":
    unittest.main()
