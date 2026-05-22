"""scrappi.utils.plot_utils - utility functions for plotting"""

from typing import Tuple, Union, Optional
import matplotlib.ticker as mticker
from matplotlib.axes import Axes
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from cartopy.mpl.gridliner import LONGITUDE_FORMATTER, LATITUDE_FORMATTER
import numpy as np

__author__ = "Sam Hunt <sam.hunt@npl.co.uk>"
__all__ = ["pad_plot_bounds"]


def pad_plot_bounds(
    obj_bounds: Tuple[float, float, float, float],
    padding_type: Optional[str] = None,
    padding_val: Optional[Union[float, str]] = None,
):
    """
    Determines plot bounds in lat/lon for object in map plot

    :param obj_bounds: lat/lon extent of object in plot as `(latitude_minimum, longitude_minimum, latitude_maximum, longitude_maximum)`
    :param padding_type: type of padding to apply either: `"rel"`, fraction of object width, `"abs"` absolute value in degrees, `None` for no padding, or `"region"` to define regional window
    :param padding_val: value for padding type, float for `"rel"` or `"abs"`, for `"region"` must be one of `["global"]`

    :return: lat/lon extent of plot as `(latitude_minimum, longitude_mininum, latitude_maximum, longitude_maximum)`
    """
    # Define plot boundaries
    geom_lon_min, geom_lat_min, geom_lon_max, geom_lat_max = obj_bounds

    if padding_type != "region":
        if padding_type == "rel":
            if isinstance(padding_val, float) or isinstance(padding_val, int):
                lat_diff = (geom_lat_max + 90) - (geom_lat_min + 90)
                lon_diff = (geom_lon_max + 180) - (geom_lon_min + 180)

                abs_lat_pad = np.abs(padding_val * lat_diff)
                abs_lon_pad = np.abs(padding_val * lon_diff)

            else:
                raise TypeError("'padding_val' must be either type float or int if 'padding_type' is 'rel'")

        elif padding_type == "abs":
            if isinstance(padding_val, float) or isinstance(padding_val, int):
                abs_lat_pad = padding_val
                abs_lon_pad = padding_val

            else:
                raise TypeError("'padding_val' must be either type float or int if 'padding_type' is 'abs'")

        elif padding_type is None:
            abs_lat_pad = 0
            abs_lon_pad = 0

        else:
            raise ValueError("'padding_type' must be either [None, 'region', 'rel',  'abs'] - not " + str(padding_type))

        plot_longitude_minimum = geom_lon_min - abs_lon_pad
        plot_latitude_minimum = geom_lat_min - abs_lat_pad
        plot_longitude_maximum = geom_lon_max + abs_lon_pad
        plot_latitude_maximum = geom_lat_max + abs_lat_pad

        if plot_longitude_minimum < -180:
            plot_longitude_minimum = -180
        if plot_longitude_maximum > 180:
            plot_longitude_maximum = 180
        if plot_latitude_minimum < -90:
            plot_latitude_minimum = -90
        if plot_latitude_maximum > 90:
            plot_latitude_maximum = 90
    else:
        if padding_val == "global":
            plot_longitude_minimum = -180
            plot_latitude_minimum = -90
            plot_longitude_maximum = 180
            plot_latitude_maximum = 90

        else:
            raise ValueError("'padding_val' for 'region' type must be either ['global'] - not" + str(padding_val))

    return (
        plot_longitude_minimum,
        plot_latitude_minimum,
        plot_longitude_maximum,
        plot_latitude_maximum,
    )


def prepare_map_plot(ax: Axes, tick_step: Optional[float] = None, redo=False) -> None:
    """
    Configures style of plot on map

    :param ax: plot axes object
    :param tick_step: plot lat, lon axis tick separation, if not provided, it is automatically determined
    :param redo: force the style to be added again, even if an xaxis label was set previously
    """

    # only update style of plot if xaxis label not set before (avoid duplicate labels and grids)
    if len(ax.texts) == 0 or redo:
        # Get plot extent

        plot_lon_min, plot_lon_max, plot_lat_min, plot_lat_max = ax.get_extent()

        # Add map details
        ax.coastlines()
        ax.add_feature(cfeature.LAND)

        if tick_step is None:
            tick_step_lon = 0.001
            for step in [10, 5, 1, 0.5, 0.1, 0.05, 0.01]:
                if (plot_lon_max - plot_lon_min) / step > 2:
                    tick_step_lon = step
                    break

            tick_step_lat = 0.001
            for step in [10, 5, 1, 0.5, 0.1, 0.05, 0.01]:
                if (plot_lat_max - plot_lat_min) / step > 2:
                    tick_step_lat = step
                    break

        else:
            tick_step_lat = tick_step
            tick_step_lon = tick_step

        # Format tick marks
        x_tick_locs = np.arange(
            plot_lon_min - plot_lon_min % tick_step_lon + tick_step_lon,
            plot_lon_max,
            tick_step_lon,
        )
        y_tick_locs = np.arange(
            plot_lat_min - plot_lat_min % tick_step_lat + tick_step_lat,
            plot_lat_max,
            tick_step_lat,
        )

        gl = ax.gridlines(
            crs=ccrs.PlateCarree(),
            draw_labels=True,
            linewidth=0,
            color="gray",
            alpha=0.5,
            linestyle="--",
        )
        gl.xlabels_top = False
        gl.ylabels_right = False
        gl.xlines = False
        gl.ylines = False
        gl.xformatter = LONGITUDE_FORMATTER
        gl.yformatter = LATITUDE_FORMATTER

        gl.xlocator = mticker.FixedLocator(x_tick_locs)
        gl.ylocator = mticker.FixedLocator(y_tick_locs)

        # Add labels
        ax.text(
            -0.12,
            0.55,
            "Latitude",
            va="bottom",
            ha="center",
            rotation="vertical",
            rotation_mode="anchor",
            transform=ax.transAxes,
        )
        ax.text(
            0.5,
            -0.15,
            "Longitude",
            va="bottom",
            ha="center",
            rotation="horizontal",
            rotation_mode="anchor",
            transform=ax.transAxes,
        )


if __name__ == "__main__":
    pass
