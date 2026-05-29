"""Plot albedo time series and a GPS-colored spatial albedo map."""

from pathlib import Path
import math
import re

import pandas as pd
import matplotlib.pyplot as plt

try:
    import contextily as ctx
except ImportError:
    ctx = None


# Folder containing Campbell TOA5 data files exported from the logger.
data_folder = Path("./Data")

# Save the spatial figure here. Set to None if you only want the interactive
# Matplotlib window.
output_path = Path("Albedo_Spatial.png")

# The current 10-second logger files already contain averages. Future 1 Hz files
# will contain raw samples. Keep averaging off for now; turn it on later if you
# want the plot to display averaged bins instead of every raw point.
average_data = False
average_interval = "10s"

# Optional plot filters. Leave as None to show every valid albedo point.
albedo_min = None
albedo_max = None

# Bounds for the albedo time-series median reference line.
median_albedo_min = 0
median_albedo_max = 1

# Column names differ between the older averaged table and the newer 1 Hz
# table. The first non-missing value from these candidate columns is used.
albedo_columns = ["Albedo_Avg", "Albedo"]
sw_down_columns = ["SW_Down_Avg", "SW_Down"]
sw_up_columns = ["SW_Up_Avg", "SW_Up"]


def read_toa5(path):
    """Read a Campbell Scientific TOA5 data file into a DataFrame."""
    return pd.read_csv(
        path,
        # TOA5 files include metadata, units, and processing rows before the data.
        # Row 1 has column names, so keep it and skip the other header rows.
        skiprows=[0, 2, 3],
        # Convert the timestamp strings into real datetime values for plotting.
        parse_dates=["TIMESTAMP"],
        # Campbell files may write missing numeric values as the string "NAN".
        na_values=["NAN"],
    )


def measure_sort_key(path):
    """Sort files like measure_1.dat, measure_2.dat, etc. in numeric order."""
    match = re.search(r"measure_(\d+)", path.stem)
    if match:
        return (0, int(match.group(1)))
    return (1, path.name)


def read_toa5_folder(folder):
    """Read every TOA5 .dat file in a folder and append them into one DataFrame."""
    # Only .dat files directly in Data are read; files in subfolders such as
    # Data/Unconverted are intentionally ignored.
    data_files = sorted(folder.glob("*.dat"), key=measure_sort_key)

    if not data_files:
        raise FileNotFoundError(f"No .dat files found in {folder}")

    print("Reading files:")
    for data_file in data_files:
        print(f"  {data_file}")

    data_frames = [read_toa5(data_file) for data_file in data_files]
    data = pd.concat(data_frames, ignore_index=True)

    # Sort by timestamp in case files are added out of order later.
    data = data.sort_values("TIMESTAMP").reset_index(drop=True)

    return data


def combined_numeric_column(data, candidates):
    """Return one numeric series filled from the first available candidate columns."""
    combined = None

    for column in candidates:
        if column not in data.columns:
            continue

        values = pd.to_numeric(data[column], errors="coerce")
        if combined is None:
            combined = values.copy()
        else:
            # Fill gaps from alternate table formats without overwriting values
            # that were already found in the preferred column.
            combined = combined.combine_first(values)

    if combined is None:
        raise KeyError(f"None of these columns were found: {', '.join(candidates)}")

    return combined


def gps_degrees_minutes_to_decimal(degrees, minutes):
    """Convert Campbell GPS degree/minute columns to signed decimal degrees."""
    degrees = pd.to_numeric(degrees, errors="coerce")
    minutes = pd.to_numeric(minutes, errors="coerce")
    # Campbell stores each coordinate as signed degrees plus signed minutes.
    # If the degrees part is zero, use the minutes sign so near-zero positions
    # still keep the correct hemisphere.
    sign = degrees.where(degrees != 0, minutes).apply(lambda value: -1 if value < 0 else 1)
    return sign * (degrees.abs() + minutes.abs() / 60)


def add_decimal_gps_columns(data):
    """Add Latitude and Longitude columns in decimal degrees."""
    data = data.copy()
    data["Latitude"] = gps_degrees_minutes_to_decimal(
        data["Latitude_A"],
        data["Latitude_B"],
    )
    data["Longitude"] = gps_degrees_minutes_to_decimal(
        data["Longitude_A"],
        data["Longitude_B"],
    )
    return data


def average_spatial_data(data, interval):
    """Average numeric columns into time bins for cleaner spatial plotting."""
    numeric_data = data.set_index("TIMESTAMP").select_dtypes("number")
    averaged = numeric_data.resample(interval).mean().dropna(how="all")
    averaged = averaged.reset_index()

    # Recompute decimal GPS positions after averaging the raw degree/minute fields.
    if {"Latitude_A", "Latitude_B", "Longitude_A", "Longitude_B"}.issubset(averaged.columns):
        averaged = add_decimal_gps_columns(averaged)

    return averaged


def prepare_spatial_data(data, average=False, interval="10s"):
    """Prepare albedo and GPS columns for spatial plotting."""
    data = add_decimal_gps_columns(data)

    if average:
        data = average_spatial_data(data, interval)

    plot_data = data.copy()
    plot_data["Plot_Albedo"] = combined_numeric_column(plot_data, albedo_columns)

    if "FixQual" in plot_data.columns:
        # FixQual <= 0 indicates no valid GPS fix, so those points are left off
        # the map even if the logger recorded albedo data at that timestamp.
        plot_data = plot_data[plot_data["FixQual"] > 0]

    # Missing GPS coordinates or albedo values cannot be drawn on the spatial
    # map, but the time-series plots above still include their non-GPS data.
    plot_data = plot_data.dropna(subset=["Latitude", "Longitude", "Plot_Albedo"])

    if albedo_min is not None:
        plot_data = plot_data[plot_data["Plot_Albedo"] >= albedo_min]
    if albedo_max is not None:
        plot_data = plot_data[plot_data["Plot_Albedo"] <= albedo_max]

    return plot_data


def plot_albedo_over_time(data):
    """Plot calculated albedo over time with a median reference line."""
    plot_data = data.copy()
    plot_data["Plot_Albedo"] = combined_numeric_column(plot_data, albedo_columns)

    median_data = plot_data.loc[
        (plot_data["Plot_Albedo"] > median_albedo_min)
        & (plot_data["Plot_Albedo"] < median_albedo_max),
        "Plot_Albedo",
    ].dropna()
    median_albedo = median_data.median()

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(
        plot_data["TIMESTAMP"],
        plot_data["Plot_Albedo"],
        marker=".",
        linestyle="-",
    )

    if pd.notna(median_albedo):
        ax.axhline(
            median_albedo,
            color="tab:red",
            linestyle="--",
            linewidth=1.5,
            label=(
                f"Median {median_albedo_min:g} < albedo < "
                f"{median_albedo_max:g} = {median_albedo:.3f}"
            ),
        )
        ax.annotate(
            f"Median: {median_albedo:.3f}",
            xy=(plot_data["TIMESTAMP"].iloc[-1], median_albedo),
            xytext=(-10, 8),
            textcoords="offset points",
            ha="right",
            va="bottom",
            color="tab:red",
        )
        ax.legend()

    ax.set_xlabel("Time")
    ax.set_ylabel("Albedo")
    ax.set_title("Albedo vs Time")
    ax.grid(True)
    fig.tight_layout()

    return fig, ax


def plot_shortwave_radiation(data):
    """Plot incoming and reflected shortwave radiation on the same axes."""
    plot_data = data.copy()
    plot_data["Plot_SW_Down"] = combined_numeric_column(plot_data, sw_down_columns)
    plot_data["Plot_SW_Up"] = combined_numeric_column(plot_data, sw_up_columns)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(
        plot_data["TIMESTAMP"],
        plot_data["Plot_SW_Down"],
        marker=".",
        linestyle="-",
        label="SW Down Avg",
    )
    ax.plot(
        plot_data["TIMESTAMP"],
        plot_data["Plot_SW_Up"],
        marker=".",
        linestyle="-",
        label="SW Up Avg",
    )

    ax.set_xlabel("Time")
    ax.set_ylabel("Shortwave radiation (W/m^2)")
    ax.set_title("Average shortwave radiation")
    ax.legend()
    ax.grid(True)
    fig.tight_layout()

    return fig, ax


def lonlat_to_web_mercator(longitudes, latitudes):
    """Convert lon/lat decimal degrees to Web Mercator meters for tile basemaps."""
    radius = 6378137
    max_latitude = 85.05112878
    x_values = []
    y_values = []

    for longitude, latitude in zip(longitudes, latitudes):
        clipped_latitude = max(min(latitude, max_latitude), -max_latitude)
        x_values.append(radius * math.radians(longitude))
        y_values.append(
            radius
            * math.log(math.tan(math.pi / 4 + math.radians(clipped_latitude) / 2))
        )

    return x_values, y_values


def add_satellite_basemap(ax):
    """Add an Esri satellite basemap if contextily is installed and online."""
    if ctx is None:
        print("contextily is not installed; plotting points without satellite imagery.")
        return

    try:
        ctx.add_basemap(
            ax,
            source=ctx.providers.Esri.WorldImagery,
            attribution_size=6,
        )
    except Exception as error:
        print(f"Could not load satellite imagery: {error}")


def plot_spatial_albedo(plot_data):
    """Plot albedo points over optional satellite imagery."""
    if plot_data.empty:
        raise ValueError("No valid GPS/albedo points were found to plot.")

    x_values, y_values = lonlat_to_web_mercator(
        plot_data["Longitude"],
        plot_data["Latitude"],
    )

    fig, ax = plt.subplots(figsize=(9, 8))
    scatter = ax.scatter(
        x_values,
        y_values,
        c=plot_data["Plot_Albedo"],
        cmap="viridis",
        s=28,
        edgecolors="black",
        linewidths=0.2,
        alpha=0.9,
        label="Albedo",
    )

    x_padding = max((max(x_values) - min(x_values)) * 0.1, 5)
    y_padding = max((max(y_values) - min(y_values)) * 0.1, 5)
    ax.set_xlim(min(x_values) - x_padding, max(x_values) + x_padding)
    ax.set_ylim(min(y_values) - y_padding, max(y_values) + y_padding)

    add_satellite_basemap(ax)

    colorbar = fig.colorbar(scatter, ax=ax)
    colorbar.set_label("Albedo")
    ax.set_title("Spatial Albedo")
    ax.set_xlabel("Web Mercator X (m)")
    ax.set_ylabel("Web Mercator Y (m)")
    ax.set_aspect("equal", adjustable="box")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    if output_path is not None:
        fig.savefig(output_path, dpi=300)
        print(f"Saved {output_path}")

    return fig, ax


# Load every TOA5 file in the Data folder into one table with named columns.
data = read_toa5_folder(data_folder)

# Print a quick preview so you can confirm the file was read correctly.
print(data.head())
print(data.columns)

plot_albedo_over_time(data)
plot_shortwave_radiation(data)

spatial_data = prepare_spatial_data(
    data,
    average=average_data,
    interval=average_interval,
)
print(f"Spatial points to plot: {len(spatial_data)}")

plot_spatial_albedo(spatial_data)

# Display all figures.
plt.show()
