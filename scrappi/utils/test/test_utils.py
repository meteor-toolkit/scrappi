"""scrappi.utils.tests.test_plot_utils - tests for scrappi.utils.plot_utils module"""

import unittest
import shapely
import shapely.wkt
import unittest.mock as mock
from shapely.geometry import Polygon, Point
from scrappi.utils.utils import (
    list_keys,
    key_present,
    get_value_gen,
    get_value,
    get_nested_value,
    get_dict_path,
    convert_geom,
    convert_geom_and_check,
    convert_geom_shapely,
    generate_bounding_lat_lon,
)

__author__ = [
    "Pieter De Vis <pieter.de.vis@npl.co.uk",
    "Jacob Fahy <jacob.fahy@npl.co.uk>",
    "Sam Hunt <sam.hunt@npl.co.uk>",
    "Matthew Scholes <matthew.scholes@npl.co.uk>",
    "Mattea Goalen <mattea.goalen@npl.co.uk>",
]


class TestPlotUtils(unittest.TestCase):
    def test_list_keys(self):
        input_dict = {
            "Ground_Floor": {
                "@floor_id": 0,
                "Science": {"Room_Numbers": [1, 2, 3, 4], "Capacity": [20, 20, 20, 20]},
                "Art": {"Room_Numbers": [5, 6, 7, 8], "Capacity": [25, 20, 24, 24]},
                "Geography": {
                    "Room_Numbers": [9, 10, 11, 12],
                    "Capacity": [20, 20, 30, 30],
                },
            }
        }
        output_list = [
            "Art",
            "Capacity",
            "Geography",
            "Ground_Floor",
            "Room_Numbers",
            "Science",
        ]
        self.assertEqual(list_keys(input_dict), output_list)

    def test_key_present(self):
        test_dict = {
            "B": {
                "B1": [
                    {
                        "C1": {"C10": ["c", "c", "c"]},
                        "C3": {"C30": [{"C300": [{"C3000": "ccc"}]}]},
                    }
                ],
                "B2": {
                    "E": {"E1": {"E10": {"E100": [1, 2, 3]}}},
                },
            }
        }
        keys = ["B", "B1", "C1", "E100", "C30", "C300", "C3000"]
        for k in keys:
            self.assertEqual(key_present(test_dict, k), True, k)

        self.assertEqual(key_present(test_dict, keys), True)

        self.assertEqual(
            key_present(test_dict, "A"),
            False,
            "'A' determined to be present when not in dictionary",
        )

    def test_get_value_gen(self):
        input_1 = {"Rooms": {"Ground_Floor": "A1"}}
        output_1 = [("Ground_Floor", "A1")]

        self.assertEqual(list(get_value_gen(input_1, "Ground_Floor")), output_1)

        input_2 = {"Rooms": {"Ground_Floor": "A1"}, "Labs": {"Ground_Floor": "L1"}}
        output_2 = [("Ground_Floor", "A1"), ("Ground_Floor", "L1")]

        self.assertEqual(list(get_value_gen(input_2, "Ground_Floor")), output_2)

        input_3 = {
            "Building": {
                "Rooms": {"Ground_Floor": "A1"},
                "Labs": {"Ground_Floor": "L1"},
            }
        }
        output_3 = [("Ground_Floor", "A1"), ("Ground_Floor", "L1")]

        self.assertEqual(list(get_value_gen(input_3, "Ground_Floor")), output_3)

        input_4 = {
            "Main_Building": {
                "Rooms": {"Ground_Floor": "A1"},
                "Labs": {"Ground_Floor": "L1"},
            },
            "Sports_Hall": {"Ground_Floor": "Changing_Rooms"},
        }
        output_4 = [
            ("Ground_Floor", "A1"),
            ("Ground_Floor", "L1"),
            ("Ground_Floor", "Changing_Rooms"),
        ]

        self.assertEqual(list(get_value_gen(input_4, "Ground_Floor")), output_4)

        input_5 = {
            "Labs": {
                "Ground_Floor": [{"Science": "G1", "Art": []}],
                "First_Floor": [{"Science": "F1", "Art": []}],
            }
        }
        output_5 = [("Science", "G1"), ("Science", "F1")]

        self.assertEqual(list(get_value_gen(input_5, "Science")), output_5)

        input_6 = {
            "Labs": {
                "Ground_Floor": [{"Science": "G1", "Art": []}],
                "First_Floor": [{"Science": "F1", "Art": []}],
            },
            "Subjects": {"Science": "Triple"},
        }
        output_6 = [("Science", "G1"), ("Science", "F1"), ("Science", "Triple")]

        self.assertEqual(list(get_value_gen(input_6, "Science")), output_6)

    @mock.patch("scrappi.utils.utils.get_value_gen", autospec=False)
    def test_get_value_multiple_values(self, mm):
        input_1 = {
            "Labs": {
                "Ground_Floor": [{"Science": "G1", "Art": []}],
                "First_Floor": [{"Science": "F1", "Art": []}],
            }
        }
        output_1 = [("Science", "G1"), ("Science", "F1")]

        def fake(input, key):
            yield from output_1

        mm.side_effect = fake
        self.assertEqual(get_value(input_1, "Science"), output_1)

    @mock.patch("scrappi.utils.utils.get_value_gen", autospec=True)
    def test_get_value_multiple_levels(self, mm):
        input_1 = {
            "Main_Building": {
                "Rooms": {"Ground_Floor": "A1"},
                "Labs": {"Ground_Floor": "L1"},
            },
            "Sports_Hall": {"Ground_Floor": "Changing_Rooms"},
        }
        output_1 = [
            ("Ground_Floor", "A1"),
            ("Ground_Floor", "L1"),
            ("Ground_Floor", "Changing_Rooms"),
        ]

        def fake(input, key):
            yield from output_1

        mm.side_effect = fake
        self.assertEqual(get_value(input_1, "Ground_Floor"), output_1)

    @mock.patch("scrappi.utils.utils.get_value_gen", autospec=True)
    def test_get_value_single_value(self, mm):
        input_1 = {"Main_Building": {"Labs": {"Ground_Floor": "L1"}}}
        output_1 = {"Ground_Floor": "L1"}
        iter_obj = [("Labs", output_1)]

        def fake(input, key):
            yield from iter_obj

        mm.side_effect = fake
        self.assertEqual(get_value(input_1, "Labs"), output_1)

    @mock.patch("scrappi.utils.utils.get_value_gen", autospec=True)
    def test_get_value_duplicate_value(self, mm):
        input_1 = {"Main_Building": {"Height": "5 m"}, "Sports_Hall": {"Height": "5 m"}}
        output_1 = "5 m"
        iter_obj = [("Height", "5 m"), ("Height", "5 m")]

        def fake(input, key):
            yield from iter_obj

        mm.side_effect = fake
        self.assertEqual(get_value(input_1, "Height"), output_1)

    @mock.patch("scrappi.utils.utils.get_value_gen", autospec=True)
    def test_get_value_nonexistent_key(self, mm):
        input_1 = {"Main_Building": {"Labs": {"Ground_Floor": "L1"}}}

        def fake(input, key):
            yield from []

        mm.side_effect = fake
        self.assertEqual(get_value(input_1, "Storage"), None)

    def test_get_nested_value(self):
        input_dict = {
            "Ground_Floor": {
                "@floor_id": 0,
                "Science": {"Room_Numbers": [1, 2, 3, 4], "Capacity": [20, 20, 20, 20]},
                "Art": {"Room_Numbers": [5, 6, 7, 8], "Capacity": [25, 20, 24, 24]},
                "Geography": {
                    "Room_Numbers": [9, 10, 11, 12],
                    "Capacity": [20, 20, 30, 30],
                },
            }
        }
        input_keys = ["Science", "Capacity"]

        self.assertTrue(get_nested_value(input_dict, input_keys), [20, 20, 20, 20])

    def test_get_dict_path(self):
        input_dict = {"Main_Building": {"Labs": {"Ground_Floor": "L1"}}}
        output_list = ["Main_Building", "Labs"]

        self.assertEqual(get_dict_path(input_dict, "Ground_Floor"), output_list)

    def test_convert_geom_list(self):
        input_geom = [40, 120, 60, 140]
        output_geom = Polygon([(120, 40), (140, 40), (140, 60), (120, 60), (120, 40)])
        self.assertTrue(convert_geom_and_check(input_geom).equals(output_geom))

    def test_convert_geom_list_error(self):
        input_geom = [120, 40, 140, 60]
        self.assertRaises(ValueError, convert_geom_and_check, input_geom)

    def test_convert_geom_dict(self):
        input_geom = {
            "latitude_minimum": 40,
            "longitude_minimum": 120,
            "latitude_maximum": 60,
            "longitude_maximum": 140,
        }
        output_geom = Polygon([(120, 40), (140, 40), (140, 60), (120, 60), (120, 40)])
        self.assertTrue(convert_geom_and_check(input_geom).equals(output_geom))

    def test_convert_geom_dict_error(self):
        input_geom = {"LAT_AND_LON": 23498293}
        self.assertRaises(ValueError, convert_geom_and_check, input_geom)

    def test_convert_geom_shapely(self):
        input_geom = Polygon([[120, 40], [160, 40], [160, 60], [140, 60]])
        output_geom = Polygon([[120, 40], [160, 40], [160, 60], [140, 60]])
        self.assertEqual(convert_geom_and_check(input_geom), output_geom)

    def test_convert_geom_shapely_error(self):
        input_geom = Polygon([[40, 120], [40, 160], [60, 160], [60, 140]])
        self.assertRaises(ValueError, convert_geom_and_check, input_geom)

    def test_convert_geom_point(self):
        input_geom = Point(120, 40)
        self.assertEqual(convert_geom_and_check(input_geom), input_geom)

    def test_convert_geom_wktstr(self):
        input_geom = "POLYGON ((120 40, 160 40, 160 60, 140 60, 120 40))"
        output_geom = shapely.wkt.loads("POLYGON ((120 40, 160 40, 160 60, 140 60, 120 40))")
        self.assertEqual(convert_geom_and_check(input_geom), output_geom)

    def test_convert_geom_wktstr_error_1(self):
        input_geom = "POLY ((120 40, 160 40, 160 60, 140 60, 120 40))"
        self.assertRaises(ValueError, convert_geom_and_check, input_geom)

    def test_convert_geom_shapely_dict(self):
        input_geom = {
            "latitude_minimum": 40,
            "longitude_minimum": 120,
            "latitude_maximum": 60,
            "longitude_maximum": 160,
        }
        output_geom = shapely.wkt.loads("POLYGON ((120 40, 160 40, 160 60, 120 60, 120 40))")
        self.assertEqual(convert_geom_shapely(input_geom), output_geom)

    def test_convert_geom_shapely_shapely(self):
        input_geom = shapely.wkt.loads("POLYGON ((120 40, 160 40, 160 60, 140 60, 120 40))")
        output_geom = shapely.wkt.loads("POLYGON ((120 40, 160 40, 160 60, 140 60, 120 40))")
        self.assertEqual(convert_geom_shapely(input_geom), output_geom)


class TestGenerateBoundingLatLon(unittest.TestCase):
    """Tests for generate_bounding_lat_lon's default local-projection behaviour.

    Regression coverage for a bug where the function defaulted to a single
    fixed CRS (EPSG:32630, UTM zone 30N) for buffering *any* point by a
    metre distance -- accurate only near that zone's own meridian, and badly
    distorted far from it (a RadCalNet site ~118 degrees of longitude away
    had its nominal 1000m x 1000m ROI come out ~960m x ~190m). The fix uses a
    local Azimuthal Equidistant projection centred on the point itself, which
    preserves true ground distance from the centre in every direction
    regardless of location.
    """

    @staticmethod
    def _box_dimensions_m(bounds):
        """Return (width_m, height_m) of a [miny, minx, maxy, maxx] box, measured geodesically."""
        from pyproj import Geod

        geod = Geod(ellps="WGS84")
        miny, minx, maxy, maxx = bounds
        _, _, width_m = geod.inv(minx, (miny + maxy) / 2, maxx, (miny + maxy) / 2)
        _, _, height_m = geod.inv((minx + maxx) / 2, miny, (minx + maxx) / 2, maxy)
        return width_m, height_m

    def test_produces_a_true_square_far_from_greenwich(self):
        """Regression test for the exact RVUS-shaped bug: a site ~118 degrees
        of longitude from UTM zone 30N must still get an accurate square."""
        bounds = generate_bounding_lat_lon(38.497, -115.690, 500)  # RVUS, half-side 500m
        width_m, height_m = self._box_dimensions_m(bounds)
        self.assertAlmostEqual(width_m, 1000.0, delta=1.0)
        self.assertAlmostEqual(height_m, 1000.0, delta=1.0)

    def test_produces_a_true_square_in_the_southern_hemisphere(self):
        bounds = generate_bounding_lat_lon(-23.600201, 15.119556, 250)  # GONA, half-side 250m
        width_m, height_m = self._box_dimensions_m(bounds)
        self.assertAlmostEqual(width_m, 500.0, delta=1.0)
        self.assertAlmostEqual(height_m, 500.0, delta=1.0)

    def test_produces_a_true_square_near_equator_and_prime_meridian(self):
        bounds = generate_bounding_lat_lon(0, 0, 100)
        width_m, height_m = self._box_dimensions_m(bounds)
        self.assertAlmostEqual(width_m, 200.0, delta=1.0)
        self.assertAlmostEqual(height_m, 200.0, delta=1.0)

    def test_explicit_crs_override_is_still_honoured(self):
        """Passing an explicit crs must still use that CRS rather than the
        local-projection default -- reproducing the old (distorted, for a
        point far from the zone) behaviour on request."""
        bounds = generate_bounding_lat_lon(38.497, -115.690, 500, crs="EPSG:32630")
        width_m, height_m = self._box_dimensions_m(bounds)
        # Same distortion as the pre-fix default (960.9m x 190.8m, not 1000m x
        # 1000m) -- proves the override path still reaches the requested CRS
        # rather than being ignored.
        self.assertAlmostEqual(width_m, 960.9, delta=1.0)
        self.assertAlmostEqual(height_m, 190.8, delta=1.0)

    def test_return_value_order(self):
        """Return order is [miny_wgs84, minx_wgs84, maxy_wgs84, maxx_wgs84]."""
        miny, minx, maxy, maxx = generate_bounding_lat_lon(10.0, 20.0, 100)
        self.assertLess(miny, maxy)
        self.assertLess(minx, maxx)
        self.assertLess(miny, 10.0)
        self.assertGreater(maxy, 10.0)
        self.assertLess(minx, 20.0)
        self.assertGreater(maxx, 20.0)


if __name__ == "__main__":
    unittest.main()
