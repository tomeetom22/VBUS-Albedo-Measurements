#!/usr/bin/env python3
"""Compare commonly centered LI-200R distributions with the median.

The plotted interval defaults to the same start and end cutoffs used by
``plot_licor_raw_voltages.py``. Each panel contains a shaded KDE for one
calibrated sensor and a shaded KDE for the per-timestamp median of all sensors.
All distributions use the same centering value: the interval median of the
across-sensor median series.
"""

from __future__ import annotations

import argparse
import math
import os
import tempfile
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "matplotlib"))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import gaussian_kde

from plot_licor_raw_voltages import (
    DEFAULT_CALIBRATION_FILE,
    DEFAULT_DAYLIGHT_END_HOUR,
    DEFAULT_DAYLIGHT_START_HOUR,
    DEFAULT_END_CUTOFF,
    DEFAULT_INPUT_FILE,
    DEFAULT_SHUNT_OHMS,
    DEFAULT_START_CUTOFF,
    convert_rows_to_irradiance,
    filter_time_range,
    parse_axis_time,
    read_calibration_constants,
    read_raw_rows,
    read_sensor_labels,
)


DEFAULT_BIN_COUNT = 200
DEFAULT_X_MIN = -500.0
DEFAULT_X_MAX = 400.0
SENSOR_COLOR = "#1f77b4"
MEDIAN_COLOR = "#d95f02"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plot calibrated LI-200R KDEs for each sensor and compare them "
            "with the across-sensor median."
        )
    )
    parser.add_argument(
        "input_file",
        type=Path,
        nargs="?",
        default=DEFAULT_INPUT_FILE,
        help=f"Path to the .dat file (default: {DEFAULT_INPUT_FILE.name})",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("LI200R_windowed_pdfs.png"),
        help="Output image path",
    )
    parser.add_argument(
        "--bins",
        type=int,
        default=DEFAULT_BIN_COUNT,
        help=(
            "Number of x-axis evaluation points used to draw each KDE "
            f"(default: {DEFAULT_BIN_COUNT})"
        ),
    )
    parser.add_argument(
        "--connections-file",
        type=Path,
        default=Path(__file__).with_name("LI200R_Connections.csv"),
        help="CSV mapping LI200R sensor numbers to serial numbers",
    )
    parser.add_argument(
        "--calibration-file",
        type=Path,
        default=DEFAULT_CALIBRATION_FILE,
        help="XLSX file with LI200R calibration constants",
    )
    parser.add_argument(
        "--shunt-ohms",
        type=float,
        default=DEFAULT_SHUNT_OHMS,
        help="Shunt resistor value used to convert voltage to sensor current",
    )
    parser.add_argument(
        "--daylight-start-hour",
        type=int,
        default=DEFAULT_DAYLIGHT_START_HOUR,
        help="First daylight hour to include",
    )
    parser.add_argument(
        "--daylight-end-hour",
        type=int,
        default=DEFAULT_DAYLIGHT_END_HOUR,
        help="First daylight hour to exclude",
    )
    parser.add_argument(
        "--start",
        default=DEFAULT_START_CUTOFF,
        help="Start cutoff as M-D HH:MM; year is taken from the data",
    )
    parser.add_argument(
        "--end",
        default=DEFAULT_END_CUTOFF,
        help="End cutoff as M-D HH:MM; year is taken from the data",
    )
    return parser.parse_args()


def kde_values(values: np.ndarray, x_grid: np.ndarray) -> np.ndarray:
    """Evaluate a Gaussian KDE, including the constant-value edge case."""
    if len(values) < 2:
        raise ValueError("At least two values are required to estimate a KDE")

    if np.ptp(values) == 0:
        # scipy's covariance estimate is singular for a constant sample.  A
        # narrow Gaussian gives the expected visual representation instead.
        width = max(abs(values[0]) * 1e-6, 1e-3)
        density = np.exp(-0.5 * ((x_grid - values[0]) / width) ** 2)
        return density / (width * math.sqrt(2 * math.pi))

    return gaussian_kde(values)(x_grid)


def add_distribution(
    axis: plt.Axes,
    values: np.ndarray,
    x_grid: np.ndarray,
    color: str,
    label: str,
) -> None:
    density = kde_values(values, x_grid)
    median = float(np.median(values))
    standard_deviation = float(np.std(values))

    axis.plot(x_grid, density, color=color, linewidth=1.6, label=label)
    axis.fill_between(x_grid, density, color=color, alpha=0.20)
    axis.axvline(
        median,
        color=color,
        linestyle="--",
        linewidth=1.2,
        label=f"{label} median",
    )
    axis.axvline(
        median - standard_deviation,
        color=color,
        linestyle=":",
        linewidth=1.0,
        alpha=0.85,
    )
    axis.axvline(
        median + standard_deviation,
        color=color,
        linestyle=":",
        linewidth=1.0,
        alpha=0.85,
        label=f"{label} median ± 1 SD",
    )


def write_plot(
    rows: list[list[float]],
    labels: list[str],
    output_path: Path,
    start_time_text: str,
    end_time_text: str,
    grid_points: int,
) -> None:
    data = np.asarray(rows, dtype=float)
    median_values = np.median(data, axis=1)

    # Use one common centering value so sensor-to-sensor offsets are preserved.
    # This places the median distribution around zero without independently
    # shifting each sensor.
    center_value = np.median(median_values)
    data = data - center_value
    median_values = median_values - center_value
    x_limits = (DEFAULT_X_MIN, DEFAULT_X_MAX)
    x_grid = np.linspace(x_limits[0], x_limits[1], grid_points)

    figure, axes = plt.subplots(
        4,
        5,
        figsize=(16, 11),
        sharex=True,
        sharey=True,
        constrained_layout=True,
    )
    axes_list = list(axes.flat)

    figure.suptitle(
        "LI200R commonly centered solar-radiation distributions\n"
        f"{start_time_text} to {end_time_text}",
        fontsize=17,
    )
    figure.supxlabel("Solar radiation relative to interval median (W/m²)")
    figure.supylabel("Density")

    for sensor_index, (axis, label) in enumerate(zip(axes_list, labels)):
        sensor_values = data[:, sensor_index]
        add_distribution(axis, sensor_values, x_grid, SENSOR_COLOR, "Sensor")
        add_distribution(axis, median_values, x_grid, MEDIAN_COLOR, "All-sensor median")

        axis.set_title(f"S{sensor_index + 1:02d}  {label}", fontsize=10)
        axis.set_xlim(x_limits)
        axis.grid(True, alpha=0.25, linewidth=0.7)

    # A single figure-level legend keeps the small panels uncluttered.
    handles, legend_labels = axes_list[0].get_legend_handles_labels()
    figure.legend(handles, legend_labels, loc="upper right", fontsize=9)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=200)
    plt.close(figure)


def main() -> None:
    args = parse_args()
    if args.bins < 2:
        raise ValueError("--bins must be at least 2")

    timestamps, raw_rows = read_raw_rows(
        args.input_file,
        args.daylight_start_hour,
        args.daylight_end_hour,
    )
    reference_year = timestamps[0].year
    start_time = parse_axis_time(args.start, reference_year) if args.start else None
    end_time = parse_axis_time(args.end, reference_year) if args.end else None
    timestamps, raw_rows = filter_time_range(
        timestamps,
        raw_rows,
        start_time,
        end_time,
    )

    labels = read_sensor_labels(args.connections_file)
    calibration_constants = read_calibration_constants(args.calibration_file)
    rows = convert_rows_to_irradiance(
        raw_rows,
        labels,
        calibration_constants,
        args.shunt_ohms,
    )
    write_plot(
        rows,
        labels,
        args.output,
        args.start or "start",
        args.end or "end",
        args.bins,
    )
    print(f"Wrote {args.output} using {len(rows)} time steps")


if __name__ == "__main__":
    main()
