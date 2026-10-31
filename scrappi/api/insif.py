"""HYPERNETS API handlers for in-situ product discovery and download.

This module contains both online and offline HYPERNETS call handlers which
implement the `InSituCallHandler` interface to query HYPERNETS catalogues
and resolve product downloads.
"""

import os

import shapely
from shapely.geometry import Polygon
from typing import Any, Dict, Optional, Union, List
from processor_tools import Context
import numpy as np
import warnings
import xarray as xr
import pandas as pd
from pathlib import Path
import json

from scrappi.api.insitubase import InSituOfflineCallHandler, InSituCallHandler
from scrappi.product import ProductItem, ProductItemSet
from scrappi.utils.utils import generate_bounding_lat_lon, convert_datetime
from scrappi.fs.localfilesystem import LocalFileSystem
from scrappi import ScrappiContext

__author__ = [
    "Pieter De Vis <pieter.de.vis@npl.co.uk",
]
__all__ = ["HYPERNETSOfflineCallHandler"]



COLLECTIONS = [
    "INSIF_RADIRRREF",
    "INSIF_RAD",
    "INSIF_IRR",
    "INSIF_REF",
    "INSIF_ALLIDX",
    "INSIF_FLUO",
    "INSIF_INDICES",
    "INSIF_RAW",
]


class INSIFCallHandler(InSituCallHandler):
    """Online INSIF call handler.

    Use this handler to query the INSIF web API and download files. API
    credentials are provided via the scrappi context under the ``hypernets``
    configuration key.
    """

    name = "insif"
    collections: List[str] = COLLECTIONS
    _default_geometries: Dict[str, Polygon] = {}

    def __init__(self, context: Optional[Union[str, List, Context]] = None):
        if isinstance(context, ScrappiContext):
            self.context = context
        else:
            self.context = ScrappiContext(context)
        # lazy import of GeoDBClient
        try:
            from xcube_geodb.core.geodb import GeoDBClient
            os.environ["GEODB_AUTH_DOMAIN"] = "https://winchester.production.brockmann-consult.de/winchester"

            server_url = "http://80.158.77.185"
            server_port = 80

            username = self.context["insif"]["credentials"]["username"]
            password = self.context["insif"]["credentials"]["password"]

            self.DATABASE = "deflox"

            geodb = GeoDBClient(client_id=username,
                                client_secret=password,
                                server_url=server_url,
                                server_port=server_port)
            geodb.whoami

            self.api = geodb
            
        except Exception as e:  # pragma: no cover - environment dependent
            raise RuntimeError("xcube_geodb package is required to use GeoDBClient: %s" % e)

        self.site_meta=self.metadata_sites()
        self.current_site_meta = {}
        self.DEFAULT_SITE_DEFINITIONS = self._generate_roi_dict()
        super().__init__(context, self.DEFAULT_SITE_DEFINITIONS)

    def get_constellation(self, prod_dict: dict) -> str:
        """
        Function to extract constellation identifier

        :param prod_dict: product dictionary
        :return: constellation identifier
        """
        return "INSIF"

    def list_collections(self, fetch_update: Optional[bool] = False) -> List[str]:
        """
        Function to extract collection identifier

        :param fetch_update: unused; included for API compatibility
        :return: collection identifier
        """
        return self.collections

    def get_insif_collections_from_query(self, query)-> List[str]:
        """
        Function to extract collection identifier from query

        :param query: query dictionary
        :return: collection identifier
        """
        flox_sn = None

        if "flox_sn" in query:
            if isinstance(query["flox_sn"], list):
                flox_sn = query["flox_sn"]
            else:
                flox_sn = [query["flox_sn"]]

        elif "site" in query:
            flox_sn = self.get_flox_sn_from_site(query["site"], query.get("start_time"), query.get("stop_time"))
            if "flox_sn" in query and query["flox_sn"] != flox_sn:
                raise ValueError(
                    "Query site '{}' does not match provided flox_sn '{}'".format(
                        query["site"], query["flox_sn"]
                    )
                )

        elif "geom" in query:
            intersecting_flox_sn = self.get_flox_sn_from_roi(query["geom"])
            if len(intersecting_flox_sn) == 0:
                raise ValueError(
                    "No collections found intersecting provided geometry"
                )
            flox_sn = intersecting_flox_sn

        if flox_sn is None:
            raise ValueError("No collection or site provided in query")
        if not isinstance(flox_sn, list):
            flox_sn = [flox_sn]

        if flox_sn[0] not in self.site_meta:
            raise ValueError("No collection found for flox_sn {} in the INSIF API".format(flox_sn[0]))

        self.current_site_meta = self.site_meta[flox_sn[0]][0]

        if "collection" in query:
            if query["collection"] == "INSIF_RADIRRREF" or query["collection"] == "INSIF_RAD" or query["collection"] == "INSIF_IRR" or query["collection"] == "INSIF_REF":
                return [f"{site}-proc" for site in flox_sn]
            elif query["collection"] == "INSIF_ALLIDX" or query["collection"] == "INSIF_FLUO" or query["collection"] == "INSIF_INDICES":
                return [f"{site}-idx" for site in flox_sn]
            elif query["collection"] == "INSIF_RAW":
                return [f"{site}-raw" for site in flox_sn]
            else:
                raise ValueError("Collection not recognised")
        else:
            raise ValueError("No collection or site provided in query")

    def get_flox_sn_from_site(self, site, start_time=None, stop_time=None):
        """
        Function to extract flox_sn from site

        :param site: site identifier
        :param start_time: optional start time for the query
        :param stop_time: optional stop time for the query
        :return: flox_sn identifier
        """
        flox_sn_list = []
        for flox_sn in self.site_meta.keys():
            site_periods = self.site_meta[flox_sn]
            for site_data in site_periods:
                if site_data["site_id"] == site:
                    if self.check_datetime_overlap(site_data, start_time, stop_time):
                        flox_sn_list.append(flox_sn)
                    
        if len(flox_sn_list) == 0:
            raise ValueError("No flox_sn found for site {}".format(site))
        elif len(flox_sn_list) > 1:
            raise NotImplementedError("Multiple flox_sn ({}) found for site {} within query period. This functionality is not yet implemented. please separate your query by date or flox_sn.".format(flox_sn_list, site))
        
        return flox_sn_list

    def get_site_from_flox_sn(self, flox_sn, start_time=None, stop_time=None):
        """
        Function to extract site from flox_sn

        :param flox_sn: flox_sn identifier
        :param start_time: optional start time for the query
        :param stop_time: optional stop time for the query
        :return: site identifier
        """
        if flox_sn not in self.site_meta:
            raise ValueError("No site found for flox_sn {}".format(flox_sn))
        
        site_periods = self.site_meta[flox_sn]
        matching_sites = []
        for site_data in site_periods:
            if self.check_datetime_overlap(site_data, start_time, stop_time):
                matching_sites.append(site_data["site_id"])
        
        if len(matching_sites) == 0:
            raise ValueError("No site found for flox_sn {} within query period".format(flox_sn))
        elif len(matching_sites) > 1:
            raise NotImplementedError("Multiple sites ({}) found for flox_sn {} within query period. This functionality is not yet implemented. please separate your query by date or site.".format(matching_sites, flox_sn))
        
        return matching_sites[0]

    # def _get_product_type(self, query_collection: str) -> tuple:
    #     """
    #     Get the product type associated with collection.
    #     Returns collection if collection is a valid product type for the api.

    #     :param query_collection: collection id of the query
    #     :return: site id, collection id if valid (else ValueError is raised)
    #     """
    #     # first check if query_collection is one of the site names
    #     if query_collection in self.sites:
    #         return query_collection, query_collection
    #     # Next check if the start of the collection is site name
    #     elif query_collection[0:4] in self.sites:
    #         return query_collection[0:4], query_collection
    #     elif "HYPERNETS" in query_collection:
    #         return "HYPERNETS", query_collection
    #     else:
    #         raise ValueError(
    #             "Selected Dataset '{}' not found in {} api.".format(
    #                 query_collection, self.name
    #             )
    #         )

    @staticmethod
    def _as_netcdf_attr(value):
        """Convert metadata values to NetCDF-safe scalar or 1D attributes."""
        if value is None:
            return None
        if isinstance(value, dict):
            return json.dumps(value, sort_keys=True, default=str)
        if isinstance(value, (list, tuple, np.ndarray, pd.Series)):
            flat = np.asarray(value, dtype=object)
            if flat.ndim > 1:
                flat = flat.ravel()
            normalized = []
            for item in flat.tolist():
                if isinstance(item, dict):
                    normalized.append(json.dumps(item, sort_keys=True, default=str))
                elif isinstance(item, (list, tuple, np.ndarray, pd.Series)):
                    nested = INSIFCallHandler._as_netcdf_attr(item)
                    if isinstance(nested, list):
                        normalized.extend(nested)
                    else:
                        normalized.append(nested)
                elif isinstance(item, np.generic):
                    normalized.append(item.item())
                else:
                    normalized.append(item)
            return normalized
        if isinstance(value, np.generic):
            return value.item()
        return value

    def metadata_sites(self) -> dict:
        """
        Return list of sites available in API

        :return: list of site names
        """
        sites={}
        for col in list(self.api.get_my_collections(self.DATABASE)["collection"]):
             if col.endswith("-raw"):
                md = self.api.get_metadata(collection=col, database=self.DATABASE)
                summaries = getattr(md, "summaries", {})
                sites[col[:-4]] = [{"site_id": col[:-4], "flox_sn": col[:-4], "spatial_extent": getattr(md, "spatial_extent", []), "start_datetime": "2023-09-01", "end_datetime": None, "summaries": summaries}]

        return sites

    def _generate_roi_dict(self) -> dict:
        roi_dict={}
        for flox_sn in self.site_meta.keys():
            site_periods = self.site_meta[flox_sn]
            for site_data in site_periods:
                site = site_data["site_id"]
                roi = site_data["spatial_extent"]
                if site in roi_dict and roi_dict[site] != roi:
                    warnings.warn(
                        f"Multiple ROIs found for site {site}. Using the last one found."
                    )
                
                roi_dict[site] = roi

        return roi_dict

    def get_flox_sn_from_roi(self, roi, start_time=None, stop_time=None):
        intersecting_flox_sn = []
        for flox_sn in self.site_meta.keys():
            site_periods = self.site_meta[flox_sn]
            for site_data in site_periods:
                site = site_data["site_id"]
                site_roi = site_data["spatial_extent"]
                col_bb = shapely.box(site_roi[0][0], site_roi[0][1], site_roi[0][2], site_roi[0][3])
                if col_bb.intersects(roi):
                    if self.check_datetime_overlap(site_data, start_time, stop_time):
                        intersecting_flox_sn.append(flox_sn)

        return intersecting_flox_sn

    def check_datetime_overlap(self, site_data, start_time=None, stop_time=None):
        """
        Check if the provided start_time and stop_time overlap with the site periods

        :param site_data: site data dictionary containing start_datetime and end_datetime
        :param start_time: optional start time for the query
        :param stop_time: optional stop time for the query
        :return: True if overlap, False otherwise
        """
        if start_time is not None:
            if site_data["end_datetime"] is not None:
                site_end_time = convert_datetime(site_data["end_datetime"])
                start_time_dt = convert_datetime(start_time)
                if start_time_dt > site_end_time:
                    return False
        if stop_time is not None:
            if site_data["start_datetime"] is not None:
                site_start_time = convert_datetime(site_data["start_datetime"])
                stop_time_dt = convert_datetime(stop_time)
                if stop_time_dt < site_start_time:
                    return False
        return True

    def get_all_variables(self, collection):
        if collection=="INSIF_RADIRRREF":
            properties = self.api.get_properties(collection="JB-010-ES-proc-unc", database=self.DATABASE)
            properties = properties[["column_name", "data_type"]]
            properties = properties.rename(columns={"column_name": "variable_name"})
            return list(properties["variable_name"])
        elif collection=="INSIF_ALLIDX":
            properties = self.api.get_properties(collection="JB-010-ES-idx", database=self.DATABASE)
            properties = properties[["column_name", "data_type"]]
            properties = properties.rename(columns={"column_name": "variable_name"})
            return list(properties["variable_name"])
        elif collection=="INSIF_RAW":
            properties = self.api.get_properties(collection="JB-010-ES-raw", database=self.DATABASE)
            properties = properties[["column_name", "data_type"]]
            properties = properties.rename(columns={"column_name": "variable_name"})
            return list(properties["variable_name"])

    def get_all_uncertainty_variables(self, collection):
        if collection=="INSIF_RADIRRREF":
            properties = self.api.get_properties(collection="JB-010-ES-proc-unc", database=self.DATABASE)
            properties = properties[["column_name", "data_type"]]
            properties = properties.rename(columns={"column_name": "variable_name"})
            return list(properties["variable_name"])
        elif collection=="INSIF_ALLIDX":
            properties = self.api.get_properties(collection="JB-010-ES-idx-unc", database=self.DATABASE)
            properties = properties[["column_name", "data_type"]]
            properties = properties.rename(columns={"column_name": "variable_name"})
            return list(properties["variable_name"])        
        elif collection=="INSIF_RAW":
            return []

    def get_default_variables(self, collection):
        if collection=="INSIF_RADIRRREF":
            return ['geometry', 'gps_lat', 'gps_lon', 'inc_rad',
            'inc_rad_f', 'refl',
            'refl_f', 'refl_f_wl', 'refl_rad', 'refl_rad_f',
            'refl_wl', 'utc_time']
        elif collection=="INSIF_RAD":
            return ['refl_rad', 'refl_rad_f', 'refl_rad_f_wl',
            'refl_rad_wl', 'utc_time']
        elif collection=="INSIF_IRR":
            return ['inc_rad', 'inc_rad_f', 'inc_rad_f_wl', 'inc_rad_wl',
            'utc_time']
        elif collection=="INSIF_REF":
            return ['refl', 'refl_f', 'refl_f_wl', 'refl_wl', 'utc_time']
        elif collection=="INSIF_ALLIDX":
            return ['apar', 'ari', 'bsf_aod', 'bsf_f_o2a', 'bsf_f_o2b', 'cci', 'check',
            'chlre', 'cl705', 'created_at', 'cri', 'cvi', 'cyclenr',
            'day_fract', 'dc', 'dc_full', 'dcl', 'dcl_full', 'dre', 'dre_full',
            'drl', 'drl_full', 'e_stability', 'e_stability_full', 'ein750',
            'ein750_full', 'einpar', 'evi', 'fcvi', 'fluo_a', 'fluo_b',
            'geometry', 'gi', 'gps_cpu', 'gpslat', 'gpslon', 'hin', 'hout',
            'id', 'index', 'l800', 'lin687', 'lin750', 'lin750_full', 'lin760',
            'linpar', 'mari', 'mcari2', 'mcri', 'modified_at', 'mtci', 'ndre',
            'ndvi', 'ndvigreen', 'nirvref', 'pan', 'pri', 'psri', 'r750',
            'r760', 'redcl', 'rep', 'sfm_conv_a', 'sfm_conv_b', 'sfm_fld_o2a',
            'sfm_fld_o2b', 'sipi', 'sr', 'sshift', 'sv', 'sv_e', 'sv_e2',
            'sv_e2_full', 'sv_e_full', 'sv_full', 'sza', 'tcari', 'temp1',
            'temp2', 'temp3', 'temp4', 'tilt', 'utc_time', 'veg_cpu',
            'voltage', 'wr_cpu']
        elif collection=="INSIF_FLUO":
            return ['bsf_aod', 'bsf_f_o2a', 'bsf_f_o2b', 'fluo_a', 'fluo_b',
            'sfm_conv_a', 'sfm_conv_b', 'sfm_fld_o2a',
            'sfm_fld_o2b']
        elif collection=="INSIF_INDICES":
            return ['apar', 'ari', 'cci',
            'chlre', 'cl705', 'cri', 'cvi',
            'ein750','ein750_full', 'einpar', 'evi', 'fcvi', 
            'gi', 'l800', 'lin687', 'lin750', 'lin750_full', 'lin760',
            'linpar', 'mari', 'mcari2', 'mcri', 'mtci', 'ndre',
            'ndvi', 'ndvigreen', 'nirvref', 'pan', 'pri', 'psri', 'r750',
            'r760', 'redcl', 'rep', 'sfm_conv_a', 'sfm_conv_b', 'sfm_fld_o2a',
            'sfm_fld_o2b', 'sipi', 'sr', 'sshift', 'sv', 'sv_e', 'sv_e2',
            'sv_e2_full', 'sv_e_full', 'sv_full', 'sza', 'tcari', 'temp1',
            'temp2', 'temp3', 'temp4', 'tilt', 'utc_time', 'veg_cpu',
            'voltage', 'wr_cpu']
        elif collection=="INSIF_RAW":
            return ['chamber_humidity', 'chamber_temp[c]', 'check', 'cooling_active',
            'created_at', 'cycle_duration[ms]', 'cycleno', 'dc_veg', 'dc_wr',
            'flox_identifier', 'geometry', 'gps_cpu', 'gps_date', 'gps_lat',
            'gps_lon', 'gps_time_utc', 'heating_active', 'id', 'it_veg[us]',
            'it_wr[us]', 'local_datetime', 'mainboard_humidity',
            'mainboard_temp[c]', 'modified_at', 'multical', 'ptu_pan',
            'ptu_tilt', 'qepro_ccd[c]', 'qepro_frame[c]', 'temp0', 'temp1',
            'temp2', 'utc_datetime', 'veg', 'veg_cpu', 'voltage', 'wr', 'wr2',
            'wr2_cpu', 'wr_cpu']
        else:
            raise ValueError("Collection not recognised")

    def get_default_uncertainty_variables(self, collection):
        if collection=="INSIF_RADIRRREF":
                    return ['idx_id',
                    'inc_rad_f_unc_random', 'inc_rad_f_unc_system_corrle',
                    'inc_rad_f_unc_system_indeple',
                    'inc_rad_unc_random', 'inc_rad_unc_system_corrle',
                    'inc_rad_unc_system_indeple',
                    'refl_f_unc_random',
                    'refl_f_unc_system_indeple',
                    'refl_rad_f_unc_random', 'refl_rad_f_unc_system',
                    'refl_rad_f_unc_system_corrle', 'refl_rad_f_unc_system_indeple',
                    'refl_rad_unc_random',
                    'refl_rad_unc_system_corrle', 'refl_rad_unc_system_indeple',
                    'refl_unc_random',
                    'refl_unc_system_indeple', 'utc_time', 'wavelength',
                    'wavelength_unc']
                    # return ['idx_id',
                    # 'inc_rad_f_unc',
                    # 'inc_rad_unc',
                    # 'refl_f_unc', 'refl_rad_f_unc', 'refl_rad_unc', 'refl_unc',
                    # 'utc_time', 'wavelength']
        elif collection=="INSIF_RAD":
                    return ['idx_id',
                    'inc_rad_f_unc_random', 'inc_rad_f_unc_system_corrle',
                    'inc_rad_f_unc_system_indeple',
                    'inc_rad_unc_random', 'inc_rad_unc_system_corrle',
                    'inc_rad_unc_system_indeple',
                    'utc_time', 'wavelength',
                    'wavelength_unc']
        elif collection=="INSIF_IRR":
                    return ['idx_id',
                    'refl_rad_f_unc_random', 'refl_rad_f_unc_system',
                    'refl_rad_f_unc_system_corrle', 'refl_rad_f_unc_system_indeple',
                    'refl_rad_unc_random',
                    'refl_rad_unc_system_corrle', 'refl_rad_unc_system_indeple',
                    'utc_time', 'wavelength',
                    'wavelength_unc']
        if collection=="INSIF_RADIRRREF":
                    return ['idx_id',
                    'refl_f_unc_random',
                    'refl_f_unc_system_indeple',
                    'refl_unc_random',
                    'refl_unc_system_indeple', 'utc_time', 'wavelength',
                    'wavelength_unc']
        elif collection=="INSIF_ALLIDX":
            return ['created_at', 'geometry', 'idx_id', 'modified_at', 'u_apar',
            'u_apar_random', 'u_apar_systematic', 'u_ari', 'u_ari_random',
            'u_ari_systematic', 'u_bsf_aod', 'u_bsf_f_o2a', 'u_bsf_f_o2b',
            'u_cci', 'u_cci_random', 'u_cci_systematic', 'u_chlre',
            'u_chlre_random', 'u_chlre_systematic', 'u_cl705',
            'u_cl705_random', 'u_cl705_systematic', 'u_cri', 'u_cri_random',
            'u_cri_systematic', 'u_cvi', 'u_cvi_random', 'u_cvi_systematic',
            'u_dc', 'u_dc_full', 'u_dc_full_random', 'u_dc_random', 'u_dcl',
            'u_dcl_full', 'u_dcl_full_random', 'u_dcl_random', 'u_dre',
            'u_dre_full', 'u_drl', 'u_drl_full', 'u_e2in750_full_random',
            'u_e2in750_full_systematic', 'u_e2in750_random',
            'u_e2in750_systematic', 'u_e_stability', 'u_e_stability_full',
            'u_ein750', 'u_ein750_full', 'u_ein750_full_random',
            'u_ein750_full_systematic', 'u_ein750_random',
            'u_ein750_systematic', 'u_einpar', 'u_einpar_random',
            'u_einpar_systematic', 'u_evi', 'u_evi_random', 'u_evi_systematic',
            'u_fcvi', 'u_fcvi_random', 'u_fcvi_systematic', 'u_fluo_a',
            'u_fluo_a_random', 'u_fluo_a_systematic', 'u_fluo_b',
            'u_fluo_b_random', 'u_fluo_b_systematic', 'u_gi', 'u_gi_random',
            'u_gi_systematic', 'u_gps_cpu', 'u_l800', 'u_l800_random',
            'u_l800_systematic', 'u_lin687', 'u_lin687_random',
            'u_lin687_systematic', 'u_lin750', 'u_lin750_full',
            'u_lin750_full_random', 'u_lin750_full_systematic',
            'u_lin750_random', 'u_lin750_systematic', 'u_lin760',
            'u_lin760_random', 'u_lin760_systematic', 'u_linpar',
            'u_linpar_random', 'u_linpar_systematic', 'u_mari',
            'u_mari_random', 'u_mari_systematic', 'u_mcari2',
            'u_mcari2_random', 'u_mcari2_systematic', 'u_mtci',
            'u_mtci_random', 'u_mtci_systematic', 'u_ndre', 'u_ndre_random',
            'u_ndre_systematic', 'u_ndvi', 'u_ndvi_random',
            'u_ndvi_systematic', 'u_ndvigreen', 'u_ndvigreen_random',
            'u_ndvigreen_systematic', 'u_nirvref', 'u_nirvref_random',
            'u_nirvref_systematic', 'u_pri', 'u_pri_random',
            'u_pri_systematic', 'u_psri', 'u_psri_random', 'u_psri_systematic',
            'u_r750', 'u_r760', 'u_r_true_a_random', 'u_r_true_a_systematic',
            'u_r_true_b_random', 'u_r_true_b_systematic', 'u_redcl',
            'u_redcl_random', 'u_redcl_systematic', 'u_rep', 'u_rep_random',
            'u_rep_systematic', 'u_sfm_conv_a', 'u_sfm_conv_b',
            'u_sfm_fld_o2a', 'u_sfm_fld_o2a_random',
            'u_sfm_fld_o2a_systematic', 'u_sfm_fld_o2b',
            'u_sfm_fld_o2b_random', 'u_sfm_fld_o2b_systematic', 'u_sipi',
            'u_sipi_random', 'u_sipi_systematic', 'u_sr_random',
            'u_sr_systematic', 'u_sshift', 'u_sv', 'u_sv_e', 'u_sv_e2',
            'u_sv_e2_full', 'u_sv_e_full', 'u_sv_full', 'u_tcari',
            'u_tcari_random', 'u_tcari_systematic', 'u_veg_cpu', 'u_wr_cpu',
            'utc_time']
        elif collection=="INSIF_RAW":
            return []
        else:
            raise ValueError("Collection not recognised")

    def _perform_query(self, query)-> Any:
        """internal function to perform query and return results as pandas dataframe
        :param query: catalogue query
        :returns: pandas dataframe with results
        """
        variables_str = "utc_time, geometry"

        where_str = ""
        where_str = "utc_time > '%s'::timestamp AND utc_time < '%s'::timestamp"%(query["start_time"],query["stop_time"])

        insif_collection_list = self.get_insif_collections_from_query(query)

        results = self.api.get_collection_pg(insif_collection_list[0],
                                      select=variables_str,
                                      where=where_str,
                                      database=self.DATABASE)
        if len(insif_collection_list) > 1:
            for insif_collection in insif_collection_list[1:]:
                results_temp = self.api.get_collection_pg(insif_collection,
                                      select=variables_str,
                                      where=where_str,
                                      database=self.DATABASE)
                results = results.merge(results_temp, on="utc_time", how="left")
            
        return results

    def perform_query(
        self,
        query: dict,
    ) -> ProductItemSet:
        """
        Return ProductItemSet containing ProductItems that satisfy query

        :param query: catalogue query
        :returns: ProductItemSet
        """

        if "platform" in query.keys() and "site" not in query.keys():
            query["site"] = query.pop("platform")

        insif_results = self._perform_query(query)

        if len(insif_results) == 0:
            warnings.warn("No INSIF records found for the selected query window.")
            return ProductItemSet([])

        if "site" not in query.keys():
            query["site"] = self.get_site_from_flox_sn(query["flox_sn"], query.get("start_time"), query.get("stop_time"))
        
        #convert geometry to be the intersection of the geometries in the results
        geometry_shapely = shapely.ops.unary_union(insif_results["geometry"]) 
        start_time=self._get_datetime(insif_results["utc_time"].min())
        stop_time=self._get_datetime(insif_results["utc_time"].max())

        prod = ProductItem(
                    constellation="INSIF",
                    platform=query["site"],
                    collection=query["collection"],
                    id=self.generate_product_id(collection=query["collection"], site=query["site"], start_time=start_time, stop_time=stop_time),
                    geometry= geometry_shapely,
                    start_time=start_time,
                    stop_time=stop_time,
                    prod_dict=query,
                    url=query.get("url", ""),
                    quicklook="",
                    api=self,
                    context=self.context,
                )
            
        return ProductItemSet([prod])

    def generate_product_id(self, collection, site, start_time, stop_time):
        """
        Generate a product id based on site, collection and results

        :param site: site name
        :param collection: collection name
        :param start_time: start time of the product
        :param stop_time: stop time of the product
        :return: product id
        """
        return f"{collection}_{site}_{start_time.strftime('%Y%m%dT%H%M%S')}_{stop_time.strftime('%Y%m%dT%H%M%S')}.nc"

    def generate_file(self, query):

        if "variables" not in query:
            variables = self.get_default_variables(query["collection"])
        
        else:
            variables = [var for var in query["variables"] if var in self.get_all_variables(query["collection"])]

        variables_str = ",".join(variables)

        where_str = ""
        where_str = "utc_time > '%s'::timestamp AND utc_time < '%s'::timestamp"%(query["start_time"],query["stop_time"])

        insif_collection = self.get_insif_collections_from_query(query)[0]

        results = self.api.get_collection_pg(insif_collection,
                                        select=variables_str,
                                        where=where_str,
                                        limit=500,
                                        database=self.DATABASE)
        n=1
        while True:
            results_add = self.api.get_collection_pg(insif_collection,
                                                    select=variables_str,
                                                    where=where_str,
                                                    limit=500,
                                                    offset=n*len(results),
                                                    database=self.DATABASE)
            if results_add is None or len(results_add) == 0:
                break
            results = pd.concat([results, results_add], ignore_index=True)
            n+=1

        if self.context["insif"]["include_uncertainty"]:  
            if "variables" not in query:
                variables = self.get_default_uncertainty_variables(query["collection"])
            
            else:
                variables = [var for var in query["variables"] if var in self.get_all_uncertainty_variables(query["collection"])]
            
            variables_str = ",".join(variables)      
            results_unc = self.api.get_collection_pg(insif_collection+"-unc",
                                        select=variables_str,
                                        where=where_str,
                                        limit=500,
                                        database=self.DATABASE)

            n=1
            while True:
                results_add = self.api.get_collection_pg(insif_collection+"-unc",
                                                        select=variables_str,
                                                        where=where_str,
                                                        limit=500,
                                                        offset=n*len(results_unc),
                                                        database=self.DATABASE)
                if results_add is None or len(results_add) == 0:
                    break
                results_unc = pd.concat([results_unc, results_add], ignore_index=True)
                n+=1
            # append results pandas dataframe with results_unc pandas dataframe
            if results_unc is not None and len(results_unc) > 0:
                results = results.merge(results_unc, on="utc_time", how="left")
                results = results.rename(columns={"refl_f_unc_system_indeple": "refl_f_unc_systematic", "refl_unc_system_indeple": "refl_unc_systematic"})

            else:
                warnings.warn("No uncertainties were found in the database for this collection.")
        return self.make_xarray_dataset(results)

    def make_xarray_dataset(self, results):
        """Build an xarray dataset directly from the dataframe columns.
        """
        if results is None or results.empty:
            raise ValueError("No INSIF records available for the selected query window.")

        df = results.copy()
        if "geometry" in df.columns:
            df = df.drop(columns=["geometry"])
        if "utc_time" not in df.columns:
            raise ValueError("INSIF results must include a utc_time column.")

        df = df.dropna(subset=["utc_time"]).copy()
        if df.empty:
            raise ValueError("INSIF results contain no valid utc_time values.")

        df["utc_time"] = pd.to_datetime(df["utc_time"], errors="coerce")
        df = df.dropna(subset=["utc_time"]).copy()
        if df.empty:
            raise ValueError("INSIF results contain no valid utc_time values.")

        time_values = (pd.to_datetime(df["utc_time"], utc=True).astype("int64") // 1_000_000_000).astype(np.int64)

        variable_attrs = {
            "inc_rad": {"long_name": "Incoming (downwelling) radiance for FLUO sensor", "standard_name": "incoming_radiance_fluo", "units": "W m^-2 nm", "unc_comps": ["inc_rad_unc_random", "inc_rad_unc_system_indeple", "inc_rad_unc_system_corrle"]},
            "refl_rad": {"long_name": "Reflected (upwelling) radiance for FLUO sensor", "standard_name": "reflected_radiance_fluo", "units": "W m^-2 nm sr^-1", "unc_comps": ["refl_rad_unc_random", "refl_rad_unc_system_indeple", "refl_rad_unc_system_corrle"]},
            "refl": {"long_name": "Apparent reflectance for FLUO sensor", "standard_name": "apparent_reflectance_fluo", "units": "", "unc_comps": ["refl_unc_random", "refl_unc_systematic"]},
            "inc_rad_f": {"long_name": "Incoming (downwelling) radiance for FULL sensor", "standard_name": "incoming_radiance_full", "units": "W m^-2 nm", "unc_comps": ["inc_rad_f_unc_random", "inc_rad_f_unc_system_indeple", "inc_rad_f_unc_system_corrle"]},
            "refl_rad_f": {"long_name": "Reflected (upwelling) radiance for FULL sensor", "standard_name": "reflected_radiance_full", "units": "W m^-2 nm sr^-1", "unc_comps": ["refl_rad_f_unc_random", "refl_rad_f_unc_system_indeple", "refl_rad_f_unc_system_corrle"]},
            "refl_f": {"long_name": "Apparent reflectance for FULL sensor", "standard_name": "apparent_reflectance_full", "units": "", "unc_comps": ["refl_f_unc_random","refl_f_unc_systematic"]},
        }
        variable_attrs_unc_comps = {       
            "inc_rad_unc_random": {"long_name": "Uncertainty in incoming (downwelling) radiance with random error correlation for FLUO sensor", "standard_name": "uncertainty_incoming_radiance_random", "units": "W m^-2 nm"},
            "inc_rad_unc_system_indeple": {"long_name": "Uncertainty in incoming (downwelling) radiance with systematic temporal error correlation (independent between radiance and irradiance) for FLUO sensor", "standard_name": "uncertainty_incoming_radiance_systematic_indeple", "units": "W m^-2 nm"},
            "inc_rad_unc_system_corrle": {"long_name": "Uncertainty in incoming (downwelling) radiance with systematic temporal error correlation (correlated between radiance and irradiance) for FLUO sensor", "standard_name": "uncertainty_incoming_radiance_systematic_corrle", "units": "W m^-2 nm"},
            "refl_rad_unc_random": {"long_name": "Uncertainty in reflected (upwelling) radiance with random error correlation for FLUO sensor", "standard_name": "uncertainty_reflected_radiance_random", "units": "W m^-2 nm sr^-1"},
            "refl_rad_unc_system_indeple": {"long_name": "Uncertainty in reflected (upwelling) radiance with systematic temporal error correlation (independent between radiance and irradiance) for FLUO sensor", "standard_name": "uncertainty_reflected_radiance_systematic_indeple", "units": "W m^-2 nm sr^-1"},
            "refl_rad_unc_system_corrle": {"long_name": "Uncertainty in reflected (upwelling) radiance with systematic temporal error correlation (correlated between radiance and irradiance) for FLUO sensor", "standard_name": "uncertainty_reflected_radiance_systematic_corrle", "units": "W m^-2 nm sr^-1"},
            "refl_unc_random": {"long_name": "Uncertainty in apparent reflectance with random error correlation for FLUO sensor", "standard_name": "uncertainty_apparent_reflectance_random", "units": ""},
            "refl_unc_systematic": {"long_name": "Uncertainty in apparent reflectance with systematic temporal error correlation for FLUO sensor", "standard_name": "uncertainty_apparent_reflectance_systematic", "units": ""},
            "inc_rad_f_unc_random": {"long_name": "Uncertainty in incoming (downwelling) radiance with random error correlation for FULL sensor", "standard_name": "uncertainty_incoming_radiance_random", "units": "W m^-2 nm"},
            "inc_rad_f_unc_system_indeple": {"long_name": "Uncertainty in incoming (downwelling) radiance with systematic temporal error correlation (independent between radiance and irradiance) for FULL sensor", "standard_name": "uncertainty_incoming_radiance_systematic_indeple", "units": "W m^-2 nm"},
            "inc_rad_f_unc_system_corrle": {"long_name": "Uncertainty in incoming (downwelling) radiance with systematic temporal error correlation (correlated between radiance and irradiance) for FULL sensor", "standard_name": "uncertainty_incoming_radiance_systematic_corrle", "units": "W m^-2 nm"},
            "refl_rad_f_unc_random": {"long_name": "Uncertainty in reflected (upwelling) radiance with random error correlation for FULL sensor", "standard_name": "uncertainty_reflected_radiance_random", "units": "W m^-2 nm sr^-1"},
            "refl_rad_f_unc_system_indeple": {"long_name": "Uncertainty in reflected (upwelling) radiance with systematic temporal error correlation (independent between radiance and irradiance) for FULL sensor", "standard_name": "uncertainty_reflected_radiance_systematic_indeple", "units": "W m^-2 nm sr^-1"},
            "refl_rad_f_unc_system_corrle": {"long_name": "Uncertainty in reflected (upwelling) radiance with systematic temporal error correlation (correlated between radiance and irradiance) for FULL sensor", "standard_name": "uncertainty_reflected_radiance_systematic_corrle", "units": "W m^-2 nm sr^-1"},
            "refl_f_unc_random": {"long_name": "Uncertainty in apparent reflectance with random error correlation for FULL sensor", "standard_name": "uncertainty_apparent_reflectance_random", "units": ""},
            "refl_f_unc_systematic": {"long_name": "Uncertainty in apparent reflectance with systematic temporal error correlation for FULL sensor", "standard_name": "uncertainty_apparent_reflectance_systematic", "units": ""},
            "err_corr_inc_rad_system_indeple": {"long_name": "Spectral error correlation matrix for incoming (downwelling) radiance with systematic temporal error correlation (independent between radiance and irradiance) for FLUO sensor", "standard_name": "error_correlation_downwelling_irradiance_systematic_indeple", "units": "-"},
            "err_corr_inc_rad_system_corrle": {"long_name": "Spectral error correlation matrix for incoming (downwelling) radiance with systematic temporal error correlation (correlated between radiance and irradiance) for FLUO sensor", "standard_name": "error_correlation_downwelling_irradiance_systematic_corrle", "units": "-"},
            "err_corr_refl_rad_system_indeple": {"long_name": "Spectral error correlation matrix for reflected (upwelling) radiance with systematic temporal error correlation (independent between radiance and irradiance) for FLUO sensor", "standard_name": "error_correlation_upwelling_radiance_systematic_indeple", "units": "-"},
            "err_corr_refl_rad_system_corrle": {"long_name": "Spectral error correlation matrix for reflected (upwelling) radiance with systematic temporal error correlation (correlated between radiance and irradiance) for FLUO sensor", "standard_name": "error_correlation_upwelling_radiance_systematic_corrle", "units": "-"},
            "err_corr_refl_systematic": {"long_name": "Spectral error correlation matrix for apparent reflectance with systematic temporal error correlation for FLUO sensor", "standard_name": "error_correlation_apparent_reflectance_systematic", "units": "-"},
            "err_corr_inc_rad_f_system_indeple": {"long_name": "Spectral error correlation matrix for incoming (downwelling) radiance with systematic temporal error correlation (independent between radiance and irradiance) for FULL sensor", "standard_name": "error_correlation_downwelling_irradiance_systematic_indeple_full", "units": "-"},
            "err_corr_inc_rad_f_system_corrle": {"long_name": "Spectral error correlation matrix for incoming (downwelling) radiance with systematic temporal error correlation (correlated between radiance and irradiance) for FULL sensor", "standard_name": "error_correlation_downwelling_irradiance_systematic_corrle_full", "units": "-"},
            "err_corr_refl_rad_f_system_indeple": {"long_name": "Spectral error correlation matrix for reflected (upwelling) radiance with systematic temporal error correlation (independent between radiance and irradiance) for FULL sensor", "standard_name": "error_correlation_upwelling_radiance_systematic_indeple_full", "units": "-"},
            "err_corr_refl_rad_f_system_corrle": {"long_name": "Spectral error correlation matrix for reflected (upwelling) radiance with systematic temporal error correlation (correlated between radiance and irradiance) for FULL sensor", "standard_name": "error_correlation_upwelling_radiance_systematic_corrle_full", "units": "-"},
            "err_corr_refl_f_systematic": {"long_name": "Spectral error correlation matrix for apparent reflectance with systematic temporal error correlation for FULL sensor", "standard_name": "error_correlation_apparent_reflectance_systematic_full", "units": "-"},
        }

        err_corr_attrs = {"random" : {"err_corr_1_dim": ["wavelength", "utc_time"],
                                    "err_corr_1_form": "random",
                                    "err_corr_1_units": "",
                                    "err_corr_1_params": "", 
                                    "pdf_shape": "gaussian"},
                          "system_corrle" : {"err_corr_1_dim": "utc_time",
                                    "err_corr_1_form": "systematic",
                                    "err_corr_1_units": "",
                                    "err_corr_1_params": "",
                                    "err_corr_2_dim": "wavelength",
                                    "err_corr_2_form": "err_corr_matrix",
                                    "err_corr_2_units": "",
                                    "err_corr_2_params": "",
                                    "pdf_shape": "gaussian"},
                          "system_indeple" : {"err_corr_1_dim": "utc_time",
                                    "err_corr_1_form": "systematic",
                                    "err_corr_1_units": "",
                                    "err_corr_1_params": "",
                                    "err_corr_2_dim": "wavelength",
                                    "err_corr_2_form": "err_corr_matrix",
                                    "err_corr_2_units": "",
                                    "err_corr_2_params": "",
                                    "pdf_shape": "gaussian"}
                        }

        wavelength_size = 1024
        
        ds = xr.Dataset(
            coords={
                "utc_time": time_values,
                "wavelength": results["refl_wl"][0],
                "wavelength_full": results["refl_f_wl"][0],
                "wavelength_": results["refl_wl"][0],
                "wavelength_full_": results["refl_f_wl"][0],
            }
        )
        
        def _coerce_value_array(value):
            if value is None:
                return np.asarray([np.nan], dtype="float32")
            if isinstance(value, (list, tuple, np.ndarray, pd.Series)):
                arr = np.asarray(value, dtype="float32")
                return arr.reshape(-1)
            return np.asarray([value], dtype="float32")

        def _pad_or_truncate(arr):
            arr = arr.reshape(-1)
            if arr.size > wavelength_size:
                return arr[:wavelength_size]
            if arr.size < wavelength_size:
                return np.pad(arr, (0, wavelength_size - arr.size), constant_values=np.nan)
            return arr

        unc_present=False
        for column in df.columns:
            if column in {"utc_time", "geometry", "local_time"}:
                continue
            if column not in variable_attrs and column not in variable_attrs_unc_comps and not column.startswith("err_corr_"):
                continue

            values = []
            for value in df[column]:
                arr = _coerce_value_array(value)
                values.append(_pad_or_truncate(arr))

            if "_full" in column or "_f_" in column or column.endswith("_f"):
                dim_name = "wavelength_full"
            else:
                dim_name = "wavelength"

            # if column.startswith("err_corr_"):
            #     data = values[0] if values else np.ones((wavelength_size, wavelength_size), dtype="float32")
            #     attrs = dict(variable_attrs.get(column, {}))
            #     ds[column] = xr.DataArray(data, dims=(dim_name, dim_name), coords={dim_name: ds[dim_name].values}, attrs=attrs)
            #     continue

            if "_unc_" in column:
                data = np.stack(values, axis=-1) if values else np.ones(wavelength_size, dtype="float32")
                attrs = dict(variable_attrs_unc_comps.get(column, {}))
                for key in err_corr_attrs.keys():
                    if key in column:
                        attrs.update(err_corr_attrs.get(key, {}))
                if "_unc_system" in column:
                    attrs["err_corr_2_params"] = "err_corr_" + column.replace("_unc_", "_")
                ds[column] = xr.DataArray(data, dims=(dim_name, "utc_time"), coords={dim_name: ds[dim_name].values}, attrs=attrs)
                unc_present = True
                continue

            stack = np.stack(values, axis=-1)
            ds[column] = xr.DataArray(
                stack,
                dims=(dim_name, "utc_time"),
                coords={dim_name: ds[dim_name].values, "utc_time": ds["utc_time"].values},
                attrs=dict(variable_attrs.get(column, {})),
            )

        if unc_present:
            for err_name, base_name in [
                ("err_corr_inc_rad_system_indeple", "inc_rad"),
                ("err_corr_inc_rad_system_corrle", "inc_rad"),
                ("err_corr_refl_rad_system_indeple", "refl_rad"),
                ("err_corr_refl_rad_system_corrle", "refl_rad"),
                ("err_corr_refl_systematic", "refl"),
                ("err_corr_inc_rad_f_system_indeple", "inc_rad_f"),
                ("err_corr_inc_rad_f_system_corrle", "inc_rad_f"),
                ("err_corr_refl_rad_f_system_indeple", "refl_rad_f"),
                ("err_corr_refl_rad_f_system_corrle", "refl_rad_f"),
                ("err_corr_refl_f_systematic", "refl_f"),
            ]:
                if err_name in ds:
                    continue
                if base_name not in ds:
                    continue
                dim_name = "wavelength_full" if base_name.endswith("_f") else "wavelength"
                data = np.ones((ds[base_name].sizes[dim_name],ds[base_name].sizes[dim_name]), dtype="float32")
                ds[err_name] = xr.DataArray(data, dims=(dim_name,dim_name+"_"), coords={dim_name: ds[dim_name].values, dim_name+"_": ds[dim_name+"_"].values}, attrs=dict(variable_attrs_unc_comps.get(err_name, {})))

        for base_name, full_name in [("inc_rad", "inc_rad_f"), ("refl_rad", "refl_rad_f"), ("refl", "refl_f")]:
            if base_name not in ds or full_name in ds:
                continue
            base_data = ds[base_name].astype("float32")
            if "utc_time" in base_data.dims:
                data = base_data.values.copy()
                ds[full_name] = xr.DataArray(
                    data,
                    dims=("wavelength_full", "utc_time"),
                    coords={"wavelength_full": ds["wavelength_full"].values, "utc_time": ds["utc_time"].values},
                    attrs=dict(variable_attrs.get(full_name, {})),
                )
            else:
                ds[full_name] = xr.DataArray(
                    base_data.values.copy(),
                    dims=("wavelength_full",),
                    coords={"wavelength_full": ds["wavelength_full"].values},
                    attrs=dict(variable_attrs.get(full_name, {})),
                )

        coord_attrs = {
                    "utc_time": {"long_name": "UTC Acquisition time in seconds since 1970-01-01 00:00:00", "standard_name": "UTC_time", "units": "seconds since 1970-01-01"},
                    "wavelength": {"long_name": "Wavelength for FLUO sensor", "standard_name": "wavelength", "units": "nm"},
                    "wavelength_full": {"long_name": "Wavelength for FULL sensor", "standard_name": "wavelength_full", "units": "nm"},
                }
        
        ds.attrs.update({
            key: self._as_netcdf_attr(value)
            for key, value in self.current_site_meta.items()
        })
        ds.attrs["start_datetime"] = self._get_datetime(df["utc_time"].min()).strftime("%Y-%m-%dT%H:%M:%SZ")
        ds.attrs["end_datetime"] = self._get_datetime(df["utc_time"].max()).strftime("%Y-%m-%dT%H:%M:%SZ")

        ds["utc_time"].attrs.update(coord_attrs["utc_time"])
        ds["wavelength"].attrs.update(coord_attrs["wavelength"])
        ds["wavelength_full"].attrs.update(coord_attrs["wavelength_full"])
        ds["wavelength_"].attrs.update(coord_attrs["wavelength"])
        ds["wavelength_full_"].attrs.update(coord_attrs["wavelength_full"])
        ds["wavelength_"].attrs.update({"long_name": "Wavelength for FLUO sensor (duplicate coordinate for error correlation matrices)", "standard_name": "wavelength", "units": "nm"})
        ds["wavelength_full_"].attrs.update({"long_name": "Wavelength for FULL sensor (duplicate coordinate for error correlation matrices)", "standard_name": "wavelength", "units": "nm"})
            
        for name in ds.data_vars:
            if name.startswith("err_corr_"):
                ds[name].encoding.update({"dtype": "int8", "scale_factor": 0.01, "add_offset": 0})
            else:
                ds[name].encoding.update({"dtype": "float32"})

        return ds

    def download_file(
        self, prod: Union[str, ProductItem], dest: Optional[Union[str, Any]] = None
    ) -> Optional[Union[list, str]]:
        """
        Download the file matching the productitem variables into destination folder. If the file already exists, it will not be downloaded again.
        :param prod: INSIF ProductItem
        :param dest: destination folder for downloaded file
        """
        if not isinstance(prod, ProductItem):
            raise TypeError("prod must be a ProductItem")
        if dest is None:
            raise ValueError("dest must be provided")

        if hasattr(prod, "prod_dict") and prod.prod_dict is not None:
            query = prod.prod_dict

        else:
            query = {
                "site": prod.platform,
                "collection": prod.collection,
                "start_time": prod.start_time,
                "stop_time": prod.stop_time,
            }

        ds = self.generate_file(query)
        if not os.path.exists(os.path.dirname(dest)):
            os.makedirs(os.path.dirname(dest))
        ds.to_netcdf(dest)
        return dest
