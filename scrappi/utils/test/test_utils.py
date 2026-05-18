"""scrappi.utils.tests.test_plot_utils - tests for scrappi.utils.plot_utils module"""

import unittest
from scrappi.utils.utils import *
import unittest.mock as mock
from shapely.geometry import Polygon, Point

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
        output_geom = {
            "latitude_minimum": 40,
            "longitude_minimum": 120,
            "latitude_maximum": 60,
            "longitude_maximum": 140,
        }
        self.assertEqual(convert_geom(input_geom), output_geom)

    def test_convert_geom_list_error(self):
        input_geom = [120, 40, 140, 60]
        self.assertRaises(ValueError, convert_geom, input_geom)

    def test_convert_geom_dict(self):
        input_geom = {
            "latitude_minimum": 40,
            "longitude_minimum": 120,
            "latitude_maximum": 60,
            "longitude_maximum": 140,
        }
        self.assertEqual(convert_geom(input_geom), input_geom)

    def test_convert_geom_dict_error(self):
        input_geom = {"LAT_AND_LON": 23498293}
        self.assertRaises(ValueError, convert_geom, input_geom)

    def test_convert_geom_shapely(self):
        input_geom = Polygon([[120, 40], [160, 40], [160, 60], [140, 60]])
        output_geom = Polygon([[120, 40], [160, 40], [160, 60], [140, 60]])
        self.assertEqual(convert_geom(input_geom), output_geom)

    def test_convert_geom_shapely_error(self):
        input_geom = Polygon([[40, 120], [40, 160], [60, 160], [60, 140]])
        self.assertRaises(ValueError, convert_geom, input_geom)

    def test_convert_geom_point(self):
        input_geom = Point(120, 40)
        self.assertEqual(convert_geom(input_geom), input_geom)

    def test_convert_geom_wktstr(self):
        input_geom = "POLYGON ((120 40, 160 40, 160 60, 140 60, 120 40))"
        output_geom = shapely.wkt.loads(
            "POLYGON ((120 40, 160 40, 160 60, 140 60, 120 40))"
        )
        self.assertEqual(convert_geom(input_geom), output_geom)

    def test_convert_geom_wktstr_error_1(self):
        input_geom = "POLY ((120 40, 160 40, 160 60, 140 60, 120 40))"
        self.assertRaises(ValueError, convert_geom, input_geom)

    def test_convert_geom_shapely_dict(self):
        input_geom = {
            "latitude_minimum": 40,
            "longitude_minimum": 120,
            "latitude_maximum": 60,
            "longitude_maximum": 160,
        }
        output_geom = shapely.wkt.loads(
            "POLYGON ((120 40, 160 40, 160 60, 120 60, 120 40))"
        )
        self.assertEqual(convert_geom_shapely(input_geom), output_geom)

    def test_convert_geom_shapely_shapely(self):
        input_geom = shapely.wkt.loads(
            "POLYGON ((120 40, 160 40, 160 60, 140 60, 120 40))"
        )
        output_geom = shapely.wkt.loads(
            "POLYGON ((120 40, 160 40, 160 60, 140 60, 120 40))"
        )
        self.assertEqual(convert_geom_shapely(input_geom), output_geom)


if __name__ == "__main__":
    unittest.main()
