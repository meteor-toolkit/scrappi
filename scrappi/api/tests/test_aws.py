import unittest
from unittest.mock import MagicMock, patch
import datetime as dt

from scrappi.api.aws import AWSCallHandler


class TestAWSCallHandler(unittest.TestCase):
    @patch("scrappi.api.aws.boto3.resource")
    def setUp(self, mock_resource):
        self.handler = AWSCallHandler()

    def test_list_collections(self):
        expected = [
            "ESA_WorldCover",
            "Copernicus-dem-30m",
            "Copernicus-dem-90m",
        ]
        self.assertEqual(self.handler.list_collections(), expected)

    def test_set_product_type(self):
        self.assertEqual(
            self.handler._set_product_type("ESA_WorldCover"),
            "esa-worldcover",
        )
        self.assertEqual(
            self.handler._set_product_type("Copernicus-dem-30m"),
            "copernicus-dem-30m",
        )

    def test_worldcover_tiles_single_tile(self):
        tiles = self.handler._worldcover_tiles(
            min_lon=0,
            min_lat=0,
            max_lon=2,
            max_lat=2,
        )

        self.assertEqual(tiles, [["N00", "E000"]])

    def test_worldcover_tiles_multiple_tiles(self):
        tiles = self.handler._worldcover_tiles(
            min_lon=0,
            min_lat=0,
            max_lon=4,
            max_lat=4,
        )

        expected = [
            ["N00", "E000"],
            ["N00", "E003"],
            ["N03", "E000"],
            ["N03", "E003"],
        ]

        self.assertEqual(tiles, expected)

    def test_worldcover_tiles_negative_coordinates(self):
        tiles = self.handler._worldcover_tiles(
            min_lon=-4,
            min_lat=-4,
            max_lon=-1,
            max_lat=-1,
        )

        self.assertIn(["S06", "W006"], tiles)
        self.assertIn(["S03", "W003"], tiles)

    def test_set_geom_list(self):
        geom = [10, 20, 12, 22]

        result = self.handler._set_geom(geom)

        self.assertEqual(
            result,
            [
                ["N09", "E018"],
                ["N09", "E021"],
                ["N12", "E018"],
                ["N12", "E021"],
            ],
        )

    def test_set_geom_dict(self):
        geom = {
            "latitude_minimum": 10,
            "longitude_minimum": 20,
            "latitude_maximum": 12,
            "longitude_maximum": 22,
        }

        result = self.handler._set_geom(geom)

        self.assertEqual(
            result,
            [
                ["N09", "E018"],
                ["N09", "E021"],
                ["N12", "E018"],
                ["N12", "E021"],
            ],
        )

    @patch.object(AWSCallHandler, "_get_version", return_value="v100")
    @patch.object(AWSCallHandler, "_get_year", return_value=2020)
    def test_get_keys(self, mock_year, mock_version):
        tiles = [["N00E000"], ["N03E003"]]

        keys = self.handler._get_keys(tiles)

        expected = [
            "v100/2020/map/ESA_WorldCover_10m_2020_v100_['N00E000']_Map.tif",
            "v100/2020/map/ESA_WorldCover_10m_2020_v100_['N03E003']_Map.tif",
        ]

        self.assertEqual(keys, expected)

    def test_format_query_worldcover_v100(self):
        query = {
            "collection": "ESA_WorldCover",
            "version": 100,
            "geom": None,
        }

        result = self.handler._format_query(query)

        self.assertEqual(result["bucket"], "esa-worldcover")
        self.assertEqual(result["start_time"], 2020)
        self.assertEqual(result["version"], 100)

    def test_format_query_worldcover_v200(self):
        query = {
            "collection": "ESA_WorldCover",
            "version": 200,
            "geom": None,
        }

        result = self.handler._format_query(query)

        self.assertEqual(result["start_time"], 2021)

    def test_format_query_invalid_worldcover_version(self):
        query = {
            "collection": "ESA_WorldCover",
            "version": 300,
            "geom": None,
        }

        with self.assertRaises(ValueError):
            self.handler._format_query(query)

    def test_get_time_dem(self):
        key = "Copernicus_DSM_COG_10_N00_00_E000_00_DEM/file.tif"

        result = self.handler._get_time(key)

        self.assertEqual(result, dt.datetime(2021, 1, 1))

    def test_get_time_worldcover_v100(self):
        key = "v100/2020/map/ESA_WorldCover_10m_2020_v100_N00E000_Map.tif"

        result = self.handler._get_time(key)

        self.assertEqual(result, dt.datetime(2020, 1, 1))

    def test_get_time_worldcover_v200(self):
        key = "v200/2021/map/ESA_WorldCover_10m_2021_v200_N00E000_Map.tif"

        result = self.handler._get_time(key)

        self.assertEqual(result, dt.datetime(2021, 1, 1))

    def test_get_api_product_dem(self):
        key = "Copernicus_DSM_COG_10_N00_00_E000_00_DEM/file.tif"

        self.assertEqual(
            self.handler._get_api_product(key),
            "Copernicus_DSM_COG_10_N00_00_E000_00_DEM",
        )

    def test_get_api_product_worldcover(self):
        key = "v100/2020/map/ESA_WorldCover_10m_2020_v100_N00E000_Map.tif"

        self.assertEqual(
            self.handler._get_api_product(key),
            key,
        )

    def test_get_id_dem(self):
        key = "Copernicus_DSM_COG_10_N00_00_E000_00_DEM/file.tif"

        self.assertEqual(
            self.handler._get_id(key),
            "Copernicus_DSM_COG_10_N00_00_E000_00_DEM",
        )

    def test_get_id_worldcover(self):
        key = "v100/2020/map/ESA_WorldCover_10m_2020_v100_N00E000_Map.tif"

        self.assertEqual(
            self.handler._get_id(key),
            "ESA_WorldCover_10m_2020_v100_N00E000_Map.tif",
        )

    def test_get_platform_dem(self):
        obj = MagicMock()
        obj.bucket_name = "copernicus-dem-30m"

        self.assertEqual(
            self.handler.get_platform([obj]),
            "Copernicus_DEM",
        )

    def test_get_platform_worldcover(self):
        obj = MagicMock()
        obj.bucket_name = "esa-worldcover"

        self.assertEqual(
            self.handler.get_platform([obj]),
            "ESA_WorldCover",
        )

    def test_get_constellation_dem(self):
        obj = MagicMock()
        obj.bucket_name = "copernicus-dem-30m"

        self.assertEqual(
            self.handler.get_constellation([obj]),
            "Copernicus_DEM",
        )

    def test_tile_bbox_northeast(self):
        geom = self.handler.tile_bbox("Copernicus_DSM_COG_10_N10_00_E020_00_DEM")

        self.assertEqual(
            geom.bounds,
            (20.0, 10.0, 21.0, 11.0),
        )

    def test_tile_bbox_southwest(self):
        geom = self.handler.tile_bbox("Copernicus_DSM_COG_10_S10_00_W020_00_DEM")

        self.assertEqual(
            geom.bounds,
            (-20.0, -10.0, -19.0, -9.0),
        )

    def test_tile_bbox_invalid_key(self):
        with self.assertRaises(ValueError):
            self.handler.tile_bbox("invalid_key")

    def test_get_filename_dem(self):
        key = "DEM_FOLDER/sub1/sub2/file.tif"

        self.assertEqual(
            self.handler._get_filename(key),
            "sub1\\sub2\\file.tif",
        )

    def test_get_filename_worldcover(self):
        key = "v100/2020/map/ESA_WorldCover_10m_2020_v100_N00E000_Map.tif"

        self.assertEqual(
            self.handler._get_filename(key),
            key,
        )


if __name__ == "__main__":
    unittest.main()
