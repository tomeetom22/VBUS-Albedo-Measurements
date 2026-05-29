from pathlib import Path
import re

import pandas as pd
import matplotlib.pyplot as plt

# Folder containing Campbell TOA5 data files exported from the logger.
data_folder = Path("./Data")


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


# Load every TOA5 file in the Data folder into one table with named columns.
data = read_toa5_folder(data_folder)

# Print a quick preview so you can confirm the file was read correctly.
print(data.head())
print(data.columns)

# Calculate the reference median from physically reasonable albedo values only.
# Values above this threshold are treated as skewed/outlier points.
median_albedo_max = 1.2
median_data = data.loc[data["Albedo_Avg"] <= median_albedo_max, "Albedo_Avg"].dropna()
median_albedo = median_data.median()

# Plot calculated albedo over time.
plt.figure(figsize=(10, 5))
plt.plot(data["TIMESTAMP"], data["Albedo_Avg"], marker=".", linestyle="-")
if pd.notna(median_albedo):
    plt.axhline(
        median_albedo,
        color="tab:red",
        linestyle="--",
        linewidth=1.5,
        label=f"Median albedo <= {median_albedo_max:g} = {median_albedo:.3f}",
    )
    plt.annotate(
        f"Median: {median_albedo:.3f}",
        xy=(data["TIMESTAMP"].iloc[-1], median_albedo),
        xytext=(-10, 8),
        textcoords="offset points",
        ha="right",
        va="bottom",
        color="tab:red",
    )
plt.xlabel("Time")
plt.ylabel("Albedo")
plt.title("Albedo vs Time")
plt.legend()
plt.grid(True)
plt.tight_layout()

# Plot average incoming and reflected shortwave radiation on the same axes.
plt.figure(figsize=(10, 5))
plt.plot(
    data["TIMESTAMP"],
    data["SW_Down_Avg"],
    marker=".",
    linestyle="-",
    label="SW Down Avg",
)
plt.plot(
    data["TIMESTAMP"],
    data["SW_Up_Avg"],
    marker=".",
    linestyle="-",
    label="SW Up Avg",
)
plt.xlabel("Time")
plt.ylabel("Shortwave radiation (W/m^2)")
plt.title("Average shortwave radiation")
plt.legend()
plt.grid(True)
plt.tight_layout()

# Display all figures.
plt.show()
