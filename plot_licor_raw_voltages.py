#!/usr/bin/env python3
"""Plot LI-200R solar radiation correlations for one sensor against the others."""

from __future__ import annotations

import argparse
import csv
import math
import os
import statistics
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile


os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "matplotlib"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


NUM_SENSORS = 20
# Change this default if you usually want a different x-axis sensor.
# Use -1 to make the x axis the median across all sensors.
DEFAULT_REFERENCE_SENSOR = -1
RAW_START_COL = 4
MISSING_THRESHOLD = -7990.0
DEFAULT_SHUNT_OHMS = 1000.0
DEFAULT_DAYLIGHT_START_HOUR = 6
DEFAULT_DAYLIGHT_END_HOUR = 20
# Change these dates here to limit the plotted period. Use M-D HH:MM.
DEFAULT_START_CUTOFF = "7-15 14:00"
DEFAULT_END_CUTOFF = "7-15 18:30"
DEFAULT_INPUT_FILE = Path(__file__).with_name("CSV_1474.LI1Min_2026_07_13_1614.dat")
DEFAULT_CONNECTIONS_FILE = Path(__file__).with_name("LI200R_Connections.csv")
DEFAULT_CALIBRATION_FILE = (
    Path(__file__).parent / "LICOR_Calibration" / "UofU_LiCOR200R.xlsx"
)
ACTIVE_SENSOR_SERIAL_NUMBERS = {
    "PY103194",
    "PY105989",
    "PY103193",
    "PY105650",
    "PY105863",
    "PY105697",
    "PY105678",
    "PY105646",
    "PY105862",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a correlation plot of one LI200R sensor against the other "
            "solar-radiation channels in a Campbell export."
        )
    )
    parser.add_argument(
        "input_file",
        type=Path,
        nargs="?",
        default=DEFAULT_INPUT_FILE,
        help=f"Path to the .dat file. Default: {DEFAULT_INPUT_FILE.name}",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("LI200R_solar_radiation_correlations.png"),
        help="Output image path",
    )
    parser.add_argument(
        "--max-points",
        type=int,
        default=200,
        help="Maximum number of time steps to draw per subplot",
    )
    parser.add_argument(
        "-r",
        "--reference-sensor",
        type=int,
        default=DEFAULT_REFERENCE_SENSOR,
        help=(
            "Sensor number to use as the x axis, from 1 to "
            f"{NUM_SENSORS}. Default: {DEFAULT_REFERENCE_SENSOR}"
            "; use -1 for the median of all sensors."
        ),
    )
    parser.add_argument(
        "--connections-file",
        type=Path,
        default=DEFAULT_CONNECTIONS_FILE,
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
        help=f"First hour to include, 0-23. Default: {DEFAULT_DAYLIGHT_START_HOUR}",
    )
    parser.add_argument(
        "--daylight-end-hour",
        type=int,
        default=DEFAULT_DAYLIGHT_END_HOUR,
        help=(
            "First hour to exclude, 1-24. "
            f"Default: {DEFAULT_DAYLIGHT_END_HOUR}"
        ),
    )
    parser.add_argument(
        "--start",
        default=DEFAULT_START_CUTOFF,
        help="Optional start cutoff as M-D HH:MM; year is taken from the data",
    )
    parser.add_argument(
        "--end",
        default=DEFAULT_END_CUTOFF,
        help="Optional end cutoff as M-D HH:MM; year is taken from the data",
    )
    return parser.parse_args()


def validate_daylight_hours(start_hour: int, end_hour: int) -> None:
    if not 0 <= start_hour <= 23:
        raise ValueError(
            f"daylight start hour must be between 0 and 23; got {start_hour}"
        )
    if not 1 <= end_hour <= 24:
        raise ValueError(
            f"daylight end hour must be between 1 and 24; got {end_hour}"
        )
    if start_hour >= end_hour:
        raise ValueError(
            "daylight start hour must be earlier than daylight end hour; "
            f"got {start_hour} and {end_hour}"
        )


def row_hour(row: list[str]) -> int | None:
    try:
        hhmm = int(float(row[2]))
    except (IndexError, TypeError, ValueError):
        return None

    hour = hhmm // 100
    minute = hhmm % 100
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return None
    return hour


def is_daylight_row(row: list[str], start_hour: int, end_hour: int) -> bool:
    hour = row_hour(row)
    return hour is not None and start_hour <= hour < end_hour


def parse_timestamp(year_text: str, doy_text: str, hhmm_text: str, sec_text: str) -> datetime:
    year = int(float(year_text))
    day_of_year = int(float(doy_text))
    hhmm = f"{int(float(hhmm_text)):04d}"
    seconds = int(float(sec_text))
    hour = int(hhmm[:2])
    minute = int(hhmm[2:])
    return datetime(year, 1, 1, hour, minute, seconds) + timedelta(days=day_of_year - 1)


def parse_axis_time(axis_text: str, reference_year: int) -> datetime:
    date_text, time_text = axis_text.split()
    month_text, day_text = date_text.split("-")
    hour_text, minute_text = time_text.split(":")
    return datetime(
        reference_year,
        int(month_text),
        int(day_text),
        int(hour_text),
        int(minute_text),
    )


def filter_time_range(
    timestamps: list[datetime],
    rows: list[list[float]],
    start_time: datetime | None,
    end_time: datetime | None,
) -> tuple[list[datetime], list[list[float]]]:
    if start_time is not None and end_time is not None and end_time < start_time:
        raise ValueError("End time must be at or after start time")

    filtered = [
        (timestamp, values)
        for timestamp, values in zip(timestamps, rows)
        if (start_time is None or timestamp >= start_time)
        and (end_time is None or timestamp <= end_time)
    ]

    if not filtered:
        raise ValueError("No rows found in the requested date/time cutoff")

    filtered_timestamps, filtered_rows = zip(*filtered)
    return list(filtered_timestamps), list(filtered_rows)


def reference_sensor_index(sensor_number: int) -> int:
    if sensor_number == -1:
        return sensor_number

    if not 1 <= sensor_number <= NUM_SENSORS:
        raise ValueError(
            f"reference sensor must be -1 or between 1 and {NUM_SENSORS}; "
            f"got {sensor_number}"
        )
    return sensor_number - 1


def reference_details(
    rows: list[list[float]],
    sampled_rows: list[list[float]],
    labels: list[str],
    reference_sensor: int,
) -> tuple[list[int], str, str, str, list[float], list[float]]:
    if reference_sensor == -1:
        compared_sensors = list(range(NUM_SENSORS))
        reference_values = [statistics.median(values) for values in rows]
        sampled_reference_values = [
            statistics.median(values) for values in sampled_rows
        ]
        return (
            compared_sensors,
            "median",
            "Median of all sensors",
            "median of all sensors",
            reference_values,
            sampled_reference_values,
        )

    reference_number = reference_sensor + 1
    reference_label = labels[reference_sensor]
    compared_sensors = [
        sensor for sensor in range(NUM_SENSORS) if sensor != reference_sensor
    ]
    reference_values = [values[reference_sensor] for values in rows]
    sampled_reference_values = [
        values[reference_sensor] for values in sampled_rows
    ]
    return (
        compared_sensors,
        f"sensor {reference_number:02d}",
        f"Sensor {reference_number:02d}: {reference_label}",
        f"sensor {reference_number:02d}",
        reference_values,
        sampled_reference_values,
    )


def read_sensor_labels(path: Path) -> list[str]:
    labels = [f"S{sensor:02d}" for sensor in range(1, NUM_SENSORS + 1)]

    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                sensor_number = int(row["Number"])
            except (KeyError, TypeError, ValueError):
                continue

            if not 1 <= sensor_number <= NUM_SENSORS:
                continue

            serial_number = (row.get("Li-Corr") or "").strip()
            if serial_number:
                labels[sensor_number - 1] = serial_number

    return labels


def normalize_serial_number(serial_number: str) -> str:
    return "".join(serial_number.split()).upper()


def is_active_sensor(label: str) -> bool:
    return normalize_serial_number(label) in ACTIVE_SENSOR_SERIAL_NUMBERS


def xlsx_shared_strings(archive: ZipFile) -> list[str]:
    try:
        xml_bytes = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []

    root = ElementTree.fromstring(xml_bytes)
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    strings: list[str] = []
    for item in root.findall("x:si", namespace):
        parts = [text.text or "" for text in item.findall(".//x:t", namespace)]
        strings.append("".join(parts))
    return strings


def xlsx_sheet_path(archive: ZipFile, sheet_name: str) -> str:
    workbook_root = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    rels_root = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    main_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    package_rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"
    rel_targets = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels_root.findall(f"{{{package_rel_ns}}}Relationship")
    }

    for sheet in workbook_root.findall(f".//{{{main_ns}}}sheet"):
        if sheet.attrib.get("name") == sheet_name:
            rel_id = sheet.attrib[f"{{{rel_ns}}}id"]
            return f"xl/{rel_targets[rel_id].lstrip('/')}"

    raise ValueError(f"Sheet {sheet_name!r} not found in calibration workbook")


def xlsx_cell_value(cell: ElementTree.Element, shared_strings: list[str]) -> str | float | None:
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    cell_type = cell.attrib.get("t")

    if cell_type == "inlineStr":
        parts = [text.text or "" for text in cell.findall(".//x:t", namespace)]
        return "".join(parts)

    value = cell.find("x:v", namespace)
    if value is None or value.text is None:
        return None

    if cell_type == "s":
        return shared_strings[int(value.text)]

    try:
        return float(value.text)
    except ValueError:
        return value.text


def read_calibration_constants(path: Path) -> dict[str, float]:
    constants: dict[str, float] = {}
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

    with ZipFile(path) as archive:
        shared_strings = xlsx_shared_strings(archive)
        sheet_path = xlsx_sheet_path(archive, "LiCor Li200R")
        root = ElementTree.fromstring(archive.read(sheet_path))

        for row in root.findall(".//x:sheetData/x:row", namespace):
            values = [
                xlsx_cell_value(cell, shared_strings)
                for cell in row.findall("x:c", namespace)
            ]
            if len(values) < 2:
                continue

            serial_number = values[0]
            calibration_constant = values[1]
            if isinstance(serial_number, str) and isinstance(calibration_constant, float):
                constants[normalize_serial_number(serial_number)] = calibration_constant

    return constants


def millivolts_to_watts_per_square_meter(
    millivolts: float,
    calibration_constant: float,
    shunt_ohms: float,
) -> float:
    current_microamps = (millivolts / 1000.0) / shunt_ohms * 1_000_000.0
    return current_microamps / calibration_constant * 1000.0


def convert_rows_to_irradiance(
    rows: list[list[float]],
    labels: list[str],
    calibration_constants: dict[str, float],
    shunt_ohms: float,
) -> list[list[float]]:
    constants: list[float] = []
    missing_labels: list[str] = []

    for label in labels:
        constant = calibration_constants.get(normalize_serial_number(label))
        if constant is None:
            missing_labels.append(label)
        else:
            constants.append(constant)

    if missing_labels:
        missing_text = ", ".join(missing_labels)
        raise ValueError(f"Missing calibration constants for: {missing_text}")

    return [
        [
            millivolts_to_watts_per_square_meter(
                millivolts,
                constants[sensor_index],
                shunt_ohms,
            )
            for sensor_index, millivolts in enumerate(values)
        ]
        for values in rows
    ]


def read_raw_rows(
    path: Path,
    daylight_start_hour: int,
    daylight_end_hour: int,
) -> tuple[list[datetime], list[list[float]]]:
    timestamps: list[datetime] = []
    rows: list[list[float]] = []

    with path.open(newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            if not is_daylight_row(row, daylight_start_hour, daylight_end_hour):
                continue

            if len(row) < RAW_START_COL + NUM_SENSORS:
                continue

            try:
                timestamp = parse_timestamp(row[0], row[1], row[2], row[3])
                values = [
                    float(row[RAW_START_COL + sensor]) for sensor in range(NUM_SENSORS)
                ]
            except ValueError:
                continue

            if any(value <= MISSING_THRESHOLD for value in values):
                continue

            timestamps.append(timestamp)
            rows.append(values)

    if not rows:
        raise ValueError(f"No valid LI200R raw-voltage rows found in {path}")

    return timestamps, rows


def evenly_sample(rows: list[list[float]], max_points: int) -> list[list[float]]:
    if max_points <= 0 or len(rows) <= max_points:
        return rows

    if max_points == 1:
        return [rows[len(rows) // 2]]

    step = (len(rows) - 1) / (max_points - 1)
    return [rows[round(index * step)] for index in range(max_points)]


def correlation(x_values: list[float], y_values: list[float]) -> float | None:
    if len(x_values) != len(y_values) or len(x_values) < 2:
        return None

    x_mean = sum(x_values) / len(x_values)
    y_mean = sum(y_values) / len(y_values)
    numerator = sum(
        (x_value - x_mean) * (y_value - y_mean)
        for x_value, y_value in zip(x_values, y_values)
    )
    x_variance = sum((x_value - x_mean) ** 2 for x_value in x_values)
    y_variance = sum((y_value - y_mean) ** 2 for y_value in y_values)
    denominator = math.sqrt(x_variance * y_variance)

    if denominator == 0:
        return None
    return numerator / denominator


def comparison_metrics(
    x_values: list[float],
    y_values: list[float],
) -> tuple[float | None, float | None, float | None]:
    """Return r^2, y scale factor, and RMSE after scaling y to x."""
    if len(x_values) != len(y_values) or len(x_values) < 2:
        return None, None, None

    y_squared = sum(y_value**2 for y_value in y_values)
    if y_squared == 0:
        y_scale = None
    else:
        y_scale = sum(
            x_value * y_value for x_value, y_value in zip(x_values, y_values)
        ) / y_squared

    r_value = correlation(x_values, y_values)
    r_squared = None if r_value is None else r_value**2
    if y_scale is None:
        scaled_rmse = None
    else:
        scaled_rmse = math.sqrt(
            sum(
                (x_value - y_scale * y_value) ** 2
                for x_value, y_value in zip(x_values, y_values)
            )
            / len(x_values)
        )
    return r_squared, y_scale, scaled_rmse


def write_plot(
    rows: list[list[float]],
    sampled_rows: list[list[float]],
    output_path: Path,
    source_path: Path,
    labels: list[str],
    reference_sensor: int,
    daylight_start_hour: int,
    daylight_end_hour: int,
    start_time: datetime | None,
    end_time: datetime | None,
) -> None:
    (
        compared_sensors,
        title_reference,
        x_axis_reference,
        footer_reference,
        reference_values,
        sampled_reference_values,
    ) = reference_details(rows, sampled_rows, labels, reference_sensor)
    columns = 5
    rows_count = math.ceil(len(compared_sensors) / columns)

    # Use identical limits across every panel so comparisons are made in the
    # same coordinate system and the one-to-one line has the same meaning.
    x_low = min(sampled_reference_values)
    x_high = max(sampled_reference_values)

    def padded_limits(low: float, high: float) -> tuple[float, float]:
        span = high - low
        padding = 0.05 * span if span else max(abs(low) * 0.05, 1.0)
        return low - padding, high + padding

    x_limits = padded_limits(x_low, x_high)
    y_limits = (0.0, 1200.0)

    figure, axes = plt.subplots(
        rows_count,
        columns,
        figsize=(16, 10),
        sharex=True,
        sharey=True,
        constrained_layout=True,
    )
    axes_list = list(axes.flat)

    figure.suptitle(
        f"LI200R solar-radiation correlations vs {title_reference}",
        fontsize=18,
    )
    figure.supxlabel(f"{x_axis_reference} solar radiation (W/m^2)")
    figure.supylabel("Comparison sensor solar radiation (W/m^2)")

    for axis, sensor in zip(axes_list, compared_sensors):
        y_values = [values[sensor] for values in rows]
        sampled_y_values = [values[sensor] for values in sampled_rows]
        r_squared, y_scale, scaled_rmse = comparison_metrics(
            reference_values,
            y_values,
        )
        if r_squared is None:
            scale_label = "y scale = n/a"
            annotation_label = "r^2 = n/a\nscaled RMSE = n/a"
        else:
            scale_label = f"y scale = {y_scale:.3f}"
            annotation_label = (
                f"r^2 = {r_squared:.3f}\n"
                f"scaled RMSE = {scaled_rmse:.1f} W/m^2"
            )

        axis.scatter(
            sampled_reference_values,
            sampled_y_values,
            s=12,
            alpha=0.35,
            linewidths=0,
            color="#1f77b4",
        )
        axis.set_xlim(x_limits)
        axis.set_ylim(y_limits)
        title_options = {"fontsize": 10}
        if HIGHLIGHT_ACTIVE_SENSORS and is_active_sensor(labels[sensor]):
            title_options.update(
                {
                    "fontweight": "bold",
                    "color": "#111111",
                    "bbox": {
                        "facecolor": "#fff2a8",
                        "edgecolor": "#c49102",
                        "boxstyle": "round,pad=0.25",
                    },
                }
            )
        axis.set_title(f"{labels[sensor]}  {scale_label}", **title_options)
        axis.text(
            0.03,
            0.96,
            annotation_label,
            transform=axis.transAxes,
            va="top",
            ha="left",
            fontsize=8,
            color="#444444",
            bbox={
                "facecolor": "white",
                "edgecolor": "none",
                "alpha": 0.7,
                "pad": 2,
            },
        )
        axis.grid(True, alpha=0.25, linewidth=0.7)

        low = max(x_limits[0], y_limits[0])
        high = min(x_limits[1], y_limits[1])
        if high > low:
            axis.plot(
                [low, high],
                [low, high],
                color="#cc4c4c",
                linewidth=0.9,
                alpha=0.7,
            )
        axis.set_xlim(x_limits)
        axis.set_ylim(y_limits)

    for axis in axes_list[len(compared_sensors) :]:
        axis.set_visible(False)

    cutoff_text = ""
    if start_time is not None or end_time is not None:
        cutoff_start = "start" if start_time is None else start_time.strftime("%m-%d %H:%M")
        cutoff_end = "end" if end_time is None else end_time.strftime("%m-%d %H:%M")
        cutoff_text = f" | cutoff: {cutoff_start} to {cutoff_end}"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=200)
    plt.close(figure)


def main() -> None:
    args = parse_args()
    reference_sensor = reference_sensor_index(args.reference_sensor)
    validate_daylight_hours(args.daylight_start_hour, args.daylight_end_hour)
    timestamps, rows = read_raw_rows(
        args.input_file,
        args.daylight_start_hour,
        args.daylight_end_hour,
    )
    reference_year = timestamps[0].year
    start_time = parse_axis_time(args.start, reference_year) if args.start else None
    end_time = parse_axis_time(args.end, reference_year) if args.end else None
    timestamps, rows = filter_time_range(timestamps, rows, start_time, end_time)
    labels = read_sensor_labels(args.connections_file)
    calibration_constants = read_calibration_constants(args.calibration_file)
    rows = convert_rows_to_irradiance(
        rows,
        labels,
        calibration_constants,
        args.shunt_ohms,
    )
    sampled_rows = evenly_sample(rows, args.max_points)
    write_plot(
        rows,
        sampled_rows,
        args.output,
        args.input_file,
        labels,
        reference_sensor,
        args.daylight_start_hour,
        args.daylight_end_hour,
        start_time,
        end_time,
    )


if __name__ == "__main__":
    main()
