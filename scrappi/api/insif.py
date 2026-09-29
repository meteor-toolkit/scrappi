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

from scrappi.api.insitubase import InSituOfflineCallHandler, InSituCallHandler
from scrappi.product import ProductItem, ProductItemSet
from scrappi.utils.utils import generate_bounding_lat_lon, convert_datetime
from scrappi.fs.localfilesystem import LocalFileSystem

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
    "INSIF_INDICES"
    "INSIF_RAW",
]


class INSIFCallHandler(InSituCallHandler):
    """Online INSIF call handler.

    Use this handler to query the INSIF web API and download files. API
    credentials are provided via the scrappi context under the ``hypernets``
    configuration key.
    """

    name = "insif"
    sites: List[str] = list(HYPERNETS_DEFAULT_ROI.keys())
    DEFAULT_SITE_DEFINITIONS: dict = HYPERNETS_DEFAULT_ROI
    collections: List[str] = COLLECTIONS
    _default_geometries: Dict[str, Polygon] = {}

    def __init__(self, context: Optional[Union[str, List, Context]] = None):
        super().__init__(context, HYPERNETS_DEFAULT_ROI)
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

            print(list(geodb.get_my_collections(self.DATABASE)["collection"]))

            self.api = geodb
            
        except Exception as e:  # pragma: no cover - environment dependent
            raise RuntimeError("xcube_geodb package is required to use GeoDBClient: %s" % e)

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

    def get_insif_collection_from_query(self, query):
        """
        Function to extract collection identifier from query

        :param query: query dictionary
        :return: collection identifier
        """
        if "collection" in query and "site" in query:
            if query["collection"] == "INSIF_RADIRRREF" or query["collection"] == "INSIF_RAD" or query["collection"] == "INSIF_IRR" or query["collection"] == "INSIF_REF":
                return query["site"] + "-proc"
            elif query["collection"] == "INSIF_ALLIDX" or query["collection"] == "INSIF_FLUO" or query["collection"] == "INSIF_INDICES":
                return query["site"] + "-idx"
            elif query["collection"] == "INSIF_RAW":
                return query["site"] + "-raw"
            else:
                raise ValueError("Collection not recognised")
        else:
            raise ValueError("No collection or site provided in query")

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

    def list_sites(self) -> list:
        """
        Return list of sites available in API

        :return: list of site names
        """
        return [col for col in list(self.api.get_my_collections(self.DATABASE)["collection"]) if "-proc" in col]

    def get_sites_from_roi(self, roi):
        # get metadata of all collections and filter out those who don't intersect
        intersecting_collections = []
        collection_names = [col for col in list(self.api.get_my_collections(self.DATABASE)["collection"]) if col.endswith("-raw")]

        for col in collection_names:
            md = self.api.get_metadata(collection=col, database=self.DATABASE)
            if len(md.spatial_extent) > 1:
                # Collection does not have a valid bounding box yet
                continue
            else:
                col_bb = shapely.box(md.spatial_extent[0][0], md.spatial_extent[0][1], md.spatial_extent[0][2],
                                    md.spatial_extent[0][3])

            if col_bb.intersects(roi):
                intersecting_collections.append(col)

        return intersecting_collections

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
            'inc_rad_f', 'inc_rad_f_wl', 'inc_rad_wl', 'refl',
            'refl_f', 'refl_f_wl', 'refl_rad', 'refl_rad_f', 'refl_rad_f_wl',
            'refl_rad_wl', 'refl_wl', 'utc_time']
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
            'refl_f_unc_random', 'refl_f_unc_system_corrle',
            'refl_f_unc_system_indeple',
            'refl_rad_f_unc_random', 'refl_rad_f_unc_system',
            'refl_rad_f_unc_system_corrle', 'refl_rad_f_unc_system_indeple',
            'refl_rad_unc_random',
            'refl_rad_unc_system_corrle', 'refl_rad_unc_system_indeple',
            'refl_unc_random', 'refl_unc_system_corrle',
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

    def _perform_query(self, query):
        variables_str = "utc_time, geometry"

        where_str = ""
        where_str = "utc_time > '%s'::timestamp AND utc_time < '%s'::timestamp"%(query["start_time"],query["stop_time"])

        insif_collection = self.get_insif_collection_from_query(query)

        results = self.api.get_collection_pg(insif_collection,
                                      select=variables_str,
                                      where=where_str,
                                      database=self.DATABASE)
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

        insif_collection = self.get_insif_collection_from_query(query)

        results = self.api.get_collection_pg(insif_collection,
                                        select=variables_str,
                                        where=where_str,
                                        database=self.DATABASE)

        if self.context["insif"]["include_uncertainty"]:  
            if "variables" not in query:
                variables = self.get_default_uncertainty_variables(query["collection"])
            
            else:
                variables = [var for var in query["variables"] if var in self.get_all_uncertainty_variables(query["collection"])]
            
            variables_str = ",".join(variables)      
            results_unc = self.api.get_collection_pg(insif_collection+"-unc",
                                        select=variables_str,
                                        where=where_str,
                                        database=self.DATABASE)
            # append results pandas dataframe with results_unc pandas dataframe
            if results_unc is not None and len(results_unc) > 0:
                results = results.merge(results_unc, on="utc_time", how="left")
        
        return self.make_xarray_dataset(results)

    def make_xarray_dataset(self, results):
        """
        Convert the results of a query to an xarray dataset

        :param results: results of a query
        :return: xarray datasetl
        """
        import xarray as xr
        import pandas as pd

        df = results.copy()
        df = df.drop(columns=["geometry"])

        # Ensure utc_time is the DataFrame index so xarray treats it as the
        # primary dimension/coordinate (avoids ambiguity where 'utc_time' could
        # otherwise appear both as a data variable and as a coordinate).
        if "utc_time" in df.columns:
            df = df.set_index("utc_time")

        ds = xr.Dataset.from_dataframe(df)

        # If a data variable named 'utc_time' still exists, promote it to a
        # coordinate to avoid xarray merge ambiguity.
        if "utc_time" not in ds.coords and "utc_time" in ds.data_vars:
            ds = ds.set_coords("utc_time")

        ds = ds.assign_coords(utc_time=np.array([convert_datetime(t) for t in ds["utc_time"].values],dtype="datetime64[ns]"))

        #set wavelength dimensions
        ds = ds.assign_coords(wavelength=np.array(ds["refl_wl"].values[0],dtype="float64"))
        ds = ds.assign_coords(wavelength_full=np.array(ds["refl_f_wl"].values[0],dtype="float64"))

        # reshape all the variables to have dimensions (time, wavelength) or (time, wavelength_full) as appropriate
        for var in ds.data_vars:
            if ds[var].dtype == "O":
                if var in ["refl_wl", "refl_f_wl"]:
                    continue
                elif var in ["refl", "refl_rad", "inc_rad"]:
                    values = np.array([vals for vals in ds[var].values], dtype="float64")
                    ds[var] = xr.DataArray(values, dims=["utc_time", "wavelength"], coords={"wavelength": ds["wavelength"], "utc_time": ds["utc_time"]})        
                elif var in ["refl_f", "refl_rad_f", "inc_rad_f"]:
                    values = np.array([vals for vals in ds[var].values], dtype="float64")
                    ds[var] = xr.DataArray(values, dims=["utc_time", "wavelength_full"], coords={"wavelength_full": ds["wavelength_full"], "utc_time": ds["utc_time"]})
                else:
                    ds = ds.drop_vars(var)  # drop any other variables that are not in the default variable list

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
