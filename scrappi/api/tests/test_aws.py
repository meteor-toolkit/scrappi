import unittest
from unittest.mock import Mock, MagicMock, patch
import datetime as dt

from scrappi.api.aws import AWSCallHandler


class TestAWSCallHandler(unittest.TestCase):
    @patch("scrappi.api.aws.boto3.resource")
    def setUp(self, mock_resource):
        mock_resource.return_value = Mock()
        self.handler = AWSCallHandler()

    def test_list_collections(self):
        expected = [
            "ESA_WorldCover",
            "copernicus_dem_30m",
            "copernicus_dem_90m",
        ]
        self.assertEqual(self.handler.list_collections(), expected)

    def test_set_product_type(self):
        self.assertEqual(
            self.handler._set_product_type("ESA_WorldCover"),
            "esa-worldcover",
        )

    def test_get_tiles_single_tile(self):
        tiles = self.handler._get_tiles(
            min_lon=0,
            min_lat=0,
            max_lon=2,
            max_lat=2,
            tile_size=3,
        )

        self.assertEqual(tiles, [["N00", "E000"]])

    def test_get_tiles_multiple_tiles(self):
        tiles = self.handler._get_tiles(
            min_lon=0,
            min_lat=0,
            max_lon=4,
            max_lat=4,
            tile_size=3,
        )

        self.assertIn(["N00", "E000"], tiles)
        self.assertIn(["N03", "E003"], tiles)

    def test_set_geom_list(self):
        geom = [0, 0, 2, 2]

        tiles = self.handler._set_geom(
            geom,
            "ESA_WorldCover",
        )

        self.assertEqual(tiles, [["N00", "E000"]])

    def test_set_geom_dict(self):
        geom = {
            "latitude_minimum": 0,
            "longitude_minimum": 0,
            "latitude_maximum": 2,
            "longitude_maximum": 2,
        }

        tiles = self.handler._set_geom(
            geom,
            "copernicus_dem_30m",
        )

        self.assertEqual(
            tiles,
            [
                ["N00", "E000"],
                ["N00", "E001"],
                ["N00", "E002"],
                ["N01", "E000"],
                ["N01", "E001"],
                ["N01", "E002"],
                ["N02", "E000"],
                ["N02", "E001"],
                ["N02", "E002"],
            ],
        )

    def test_set_geom_invalid_type(self):
        with self.assertRaises(TypeError):
            self.handler._set_geom("invalid", "ESA_WorldCover")

    def test_format_query_worldcover(self):
        query = {
            "collection": "ESA_WorldCover",
            "version": 100,
            "geom": [0, 0, 2, 2],
        }

        result = self.handler._format_query(query)

        self.assertEqual(result["bucket"], "esa-worldcover")
        self.assertEqual(result["version"], 100)
        self.assertEqual(result["start_time"], 2020)
        self.assertIn("tiles", result)

    def test_format_query_invalid_worldcover_version(self):
        query = {
            "collection": "ESA_WorldCover",
            "version": 999,
            "geom": None,
        }

        with self.assertRaises(ValueError):
            self.handler._format_query(query)

    def test_get_time_dem(self):
        key = "Copernicus_DSM_COG_10_N00_00_E001_00_DEM/file.tif"

        self.assertEqual(
            self.handler._get_time(key),
            dt.datetime(2021, 1, 1),
        )

    def test_get_time_worldcover(self):
        key = "v100/2020/map/ESA_WorldCover_10m_2020_v100_N00E003_Map.tif"

        self.assertEqual(
            self.handler._get_time(key),
            dt.datetime(2020, 1, 1),
        )

    def test_get_id_dem(self):
        key = "Copernicus_DSM_COG_10_N00_00_E001_00_DEM/file.tif"

        self.assertEqual(self.handler._get_id(key), "Copernicus_DSM_COG_10_N00_00_E001_00_DEM")

    def test_get_id_worldcover(self):
        key = "v100/2020/map/ESA_WorldCover_10m_2020_v100_N00E003_Map.tif"

        self.assertEqual(self.handler._get_id(key), "ESA_WorldCover_10m_2020_v100_N00E003_Map.tif")

    def test_get_api_product_dem(self):
        key = "Copernicus_DSM_COG_10_N00_00_E001_00_DEM/file.tif"

        self.assertEqual(self.handler._get_api_product(key), "Copernicus_DSM_COG_10_N00_00_E001_00_DEM")

    def test_get_api_product_worldcover(self):
        key = "v100/2020/map/ESA_WorldCover_10m_2020_v100_N00E003_Map.tif"

        self.assertEqual(self.handler._get_api_product(key), key)

    def test_get_platform_worldcover(self):
        obj = Mock()
        obj.bucket_name = "esa-worldcover"

        self.assertEqual(
            self.handler.get_platform([obj]),
            "ESA_WorldCover",
        )

    def test_get_platform_dem(self):
        obj = Mock()
        obj.bucket_name = "copernicus-dem-30m"

        self.assertEqual(
            self.handler.get_platform([obj]),
            "Copernicus_DEM",
        )

    def test_get_constellation_worldcover(self):
        obj = Mock()
        obj.bucket_name = "esa-worldcover"

        self.assertEqual(
            self.handler.get_constellation([obj]),
            "ESA_WorldCover",
        )

    def test_get_constellation_dem(self):
        obj = Mock()
        obj.bucket_name = "copernicus-dem-30m"

        self.assertEqual(
            self.handler.get_constellation([obj]),
            "Copernicus_DEM",
        )

    def test_tile_bbox(self):
        bbox = self.handler.tile_bbox(
            "Copernicus_DSM_COG_10_N00_00_E003_00_DEM",
            tile_size=1,
        )

        self.assertEqual(bbox.bounds, (3.0, 0.0, 4.0, 1.0))

    def test_tile_bbox_invalid_key(self):
        with self.assertRaises(ValueError):
            self.handler.tile_bbox("invalid_key")

    def test_get_tile_size_worldcover(self):
        self.assertEqual(
            self.handler._get_tile_size("ESA_WorldCover"),
            3,
        )

    def test_get_tile_size_dem(self):
        self.assertEqual(
            self.handler._get_tile_size("copernicus_dem_30m"),
            1,
        )

    def test_get_tile_size_invalid(self):
        with self.assertRaises(ValueError):
            self.handler._get_tile_size("unknown")

    def test_get_filename_dem(self):
        key = "Copernicus_DSM_COG_10_N00_00_E001_00_DEM/DEM.tif"

        self.assertEqual(
            self.handler._get_filename(key),
            "DEM.tif",
        )

    def test_get_filename_worldcover(self):
        key = "v100/2020/map/ESA_WorldCover_10m_2020_v100_N00E003_Map.tif"

        self.assertEqual(
            self.handler._get_filename(key),
            key,
        )

    @patch("scrappi.api.aws.boto3.resource")
    def test_constructor_handles_boto_exception(self, mock_resource):
        mock_resource.side_effect = Exception("AWS unavailable")

        handler = AWSCallHandler()

        self.assertIsNone(handler.s3_resource)

    def test_perform_query_without_s3_resource(self):
        self.handler.s3_resource = None

        with self.assertRaises(RuntimeError):
            self.handler._perform_query({"collection": "ESA_WorldCover"})


if __name__ == "__main__":
    unittest.main()
