#!/usr/bin/env python3
"""Plot LI-200R solar radiation versus time from the CR5000 export."""

from __future__ import annotations

import argparse
import csv
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile


NUM_SENSORS = 20
RAW_START_COL = 4
MISSING_THRESHOLD = -7990.0
DEFAULT_SHUNT_OHMS = 1000.0
DEFAULT_Y_MIN = 0.0
DEFAULT_Y_MAX = 1400.0
DEFAULT_START_MONTH = 7
DEFAULT_START_DAY = 14
DEFAULT_START_HOUR = 13
DEFAULT_START_MINUTE = 0
DEFAULT_END_MONTH = 7
DEFAULT_END_DAY = 17
DEFAULT_END_HOUR = 12
DEFAULT_END_MINUTE = 0
DEFAULT_X_TICK_HOURS = 3
DEFAULT_INPUT_FILE = Path(__file__).with_name("CSV_1474.LI1Min_2026_07_13_1614.dat")
DEFAULT_CONNECTIONS_FILE = Path(__file__).with_name("LI200R_Connections.csv")
DEFAULT_CALIBRATION_FILE = (
    Path(__file__).parent / "LICOR_Calibration" / "UofU_LiCOR200R.xlsx"
)
COLORS = [
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
    "#393b79",
    "#637939",
    "#8c6d31",
    "#843c39",
    "#7b4173",
    "#3182bd",
    "#31a354",
    "#756bb1",
    "#636363",
    "#e6550d",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plot LI200R solar radiation from the first 20 raw voltage channels."
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
        default=Path("LI200R_solar_radiation_timeseries.svg"),
        help="Output plot path",
    )
    parser.add_argument(
        "--avg-minutes",
        type=int,
        default=5,
        help="Averaging interval in minutes before plotting",
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
        help="Shunt resistor value used to convert LI200R current to voltage",
    )
    parser.add_argument(
        "--y-min",
        type=float,
        default=DEFAULT_Y_MIN,
        help="Lower y-axis limit in W/m^2",
    )
    parser.add_argument(
        "--y-max",
        type=float,
        default=DEFAULT_Y_MAX,
        help="Upper y-axis limit in W/m^2",
    )
    parser.add_argument(
        "--start",
        default=f"{DEFAULT_START_MONTH}-{DEFAULT_START_DAY} "
        f"{DEFAULT_START_HOUR:02d}:{DEFAULT_START_MINUTE:02d}",
        help="Start time as M-D HH:MM; year is taken from the data",
    )
    parser.add_argument(
        "--end",
        default=f"{DEFAULT_END_MONTH}-{DEFAULT_END_DAY} "
        f"{DEFAULT_END_HOUR:02d}:{DEFAULT_END_MINUTE:02d}",
        help="End time as M-D HH:MM; year is taken from the data",
    )
    parser.add_argument(
        "--x-tick-hours",
        type=int,
        default=DEFAULT_X_TICK_HOURS,
        help=f"Major x-axis tick spacing in hours. Default: {DEFAULT_X_TICK_HOURS}",
    )
    return parser.parse_args()


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
            if len(values) < 3:
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


def print_irradiance_summary(rows: list[list[float]]) -> None:
    values = [value for row in rows for value in row]
    if not values:
        return

    print(
        "Solar radiation range after conversion: "
        f"{min(values):.2f} to {max(values):.2f} W/m^2"
    )


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
    start_time: datetime,
    end_time: datetime,
) -> tuple[list[datetime], list[list[float]]]:
    if end_time < start_time:
        raise ValueError("End time must be at or after start time")

    filtered = [
        (timestamp, values)
        for timestamp, values in zip(timestamps, rows)
        if start_time <= timestamp <= end_time
    ]

    if not filtered:
        raise ValueError(f"No rows found from {start_time} to {end_time}")

    filtered_timestamps, filtered_rows = zip(*filtered)
    return list(filtered_timestamps), list(filtered_rows)


def read_raw_rows(path: Path) -> tuple[list[datetime], list[list[float]]]:
    timestamps: list[datetime] = []
    rows: list[list[float]] = []

    with path.open(newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
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


def average_rows(
    timestamps: list[datetime],
    rows: list[list[float]],
    interval_minutes: int,
) -> tuple[list[datetime], list[list[float]]]:
    if interval_minutes <= 1:
        return timestamps, rows

    averaged_timestamps: list[datetime] = []
    averaged_rows: list[list[float]] = []
    interval_seconds = interval_minutes * 60
    current_bucket: int | None = None
    bucket_start: datetime | None = None
    sums = [0.0] * NUM_SENSORS
    count = 0

    def flush_bucket() -> None:
        nonlocal count, sums, bucket_start
        if count == 0 or bucket_start is None:
            return
        averaged_timestamps.append(bucket_start)
        averaged_rows.append([value / count for value in sums])
        sums = [0.0] * NUM_SENSORS
        count = 0

    for timestamp, values in zip(timestamps, rows):
        bucket = int(timestamp.timestamp()) // interval_seconds
        if current_bucket is None:
            current_bucket = bucket
            bucket_start = datetime.fromtimestamp(bucket * interval_seconds)
        elif bucket != current_bucket:
            flush_bucket()
            current_bucket = bucket
            bucket_start = datetime.fromtimestamp(bucket * interval_seconds)

        for sensor_index, value in enumerate(values):
            sums[sensor_index] += value
        count += 1

    flush_bucket()

    return averaged_timestamps, averaged_rows


def percentile(sorted_values: list[float], fraction: float) -> float:
    if not sorted_values:
        raise ValueError("Cannot calculate percentile of an empty list")

    if len(sorted_values) == 1:
        return sorted_values[0]

    position = fraction * (len(sorted_values) - 1)
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    weight = position - lower_index
    return (
        sorted_values[lower_index] * (1 - weight)
        + sorted_values[upper_index] * weight
    )


def row_quartiles(rows: list[list[float]]) -> tuple[list[float], list[float], list[float]]:
    q1_values: list[float] = []
    median_values: list[float] = []
    q3_values: list[float] = []

    for values in rows:
        sorted_values = sorted(values)
        q1_values.append(percentile(sorted_values, 0.25))
        median_values.append(percentile(sorted_values, 0.50))
        q3_values.append(percentile(sorted_values, 0.75))

    return q1_values, median_values, q3_values


def write_plot(
    timestamps: list[datetime],
    rows: list[list[float]],
    output_path: Path,
    source_path: Path,
    raw_row_count: int,
    avg_minutes: int,
    labels: list[str],
    shunt_ohms: float,
    y_min: float,
    y_max: float,
    x_start: datetime,
    x_end: datetime,
    x_tick_hours: int,
) -> None:
    if y_max <= y_min:
        raise ValueError("y-max must be greater than y-min")
    if x_end < x_start:
        raise ValueError("End time must be at or after start time")
    if x_tick_hours <= 0:
        raise ValueError("x-tick-hours must be greater than zero")

    matplotlib_config_dir = Path(tempfile.gettempdir()) / "vbus-matplotlib-cache"
    matplotlib_config_dir.mkdir(exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(matplotlib_config_dir))

    try:
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
    except ModuleNotFoundError as error:
        raise ModuleNotFoundError(
            "matplotlib is required to render this plot. Install it with "
            "`python3 -m pip install matplotlib` or `conda install matplotlib`."
        ) from error

    columns = [list(series) for series in zip(*rows)]
    q1_values, median_values, q3_values = row_quartiles(rows)

    fig, (sensor_ax, summary_ax) = plt.subplots(
        2,
        1,
        figsize=(16, 10.8),
        sharex=True,
        gridspec_kw={"height_ratios": [3, 1], "hspace": 0.18},
    )

    for sensor_index, series in enumerate(columns):
        sensor_ax.plot(
            timestamps,
            series,
            color=COLORS[sensor_index % len(COLORS)],
            linewidth=1.2,
            alpha=0.9,
            label=labels[sensor_index],
        )

    summary_ax.fill_between(
        timestamps,
        q1_values,
        q3_values,
        color="#4c78a8",
        alpha=0.25,
        linewidth=0,
        label="IQR",
    )
    summary_ax.plot(
        timestamps,
        median_values,
        color="#1b4f72",
        linewidth=2.2,
        label="Median",
    )

    for axis in (sensor_ax, summary_ax):
        axis.set_xlim(x_start, x_end)
        axis.set_ylim(y_min, y_max)
        axis.set_ylabel("Solar radiation (W/m^2)")
        axis.grid(True, color="#e2e2e2", linewidth=0.8)
        axis.set_axisbelow(True)

    sensor_ax.set_title(
        f"LI200R solar radiation vs time ({avg_minutes}-min avg)",
        loc="left",
    )
    summary_ax.set_title("Median and inner quartile range", loc="left", fontsize=11)
    summary_ax.set_xlabel("Time")

    sensor_ax.legend(
        title="Sensors",
        loc="upper left",
        bbox_to_anchor=(1.01, 1.0),
        ncol=2,
        fontsize=8,
        title_fontsize=9,
        frameon=False,
    )
    summary_ax.legend(
        loc="upper left",
        bbox_to_anchor=(1.01, 1.0),
        fontsize=8,
        frameon=False,
    )

    locator = mdates.HourLocator(interval=x_tick_hours)
    formatter = mdates.DateFormatter("%m-%d %H:%M")
    summary_ax.xaxis.set_major_locator(locator)
    summary_ax.xaxis.set_major_formatter(formatter)
    for label in summary_ax.get_xticklabels():
        label.set_rotation(35)
        label.set_ha("right")

    subtitle = (
        f"{source_path.name} | valid raw rows: {raw_row_count} | "
        f"averaged points: {len(rows)} | {shunt_ohms:g} ohm shunt | "
        f"x ticks every {x_tick_hours} h | "
        f"axis: {x_start:%Y-%m-%d %H:%M:%S} to {x_end:%Y-%m-%d %H:%M:%S} | "
        f"valid data through {timestamps[-1]:%Y-%m-%d %H:%M:%S}"
    )
    fig.text(0.08, 0.965, subtitle, ha="left", va="top", fontsize=9, color="#444")
    fig.subplots_adjust(left=0.08, right=0.78, top=0.92, bottom=0.08)
    fig.savefig(output_path)
    plt.close(fig)


def main() -> None:
    args = parse_args()
    timestamps, rows = read_raw_rows(args.input_file)
    raw_row_count = len(rows)
    labels = read_sensor_labels(args.connections_file)
    calibration_constants = read_calibration_constants(args.calibration_file)
    rows = convert_rows_to_irradiance(
        rows,
        labels,
        calibration_constants,
        args.shunt_ohms,
    )
    print_irradiance_summary(rows)
    reference_year = timestamps[0].year
    start_time = parse_axis_time(args.start, reference_year)
    end_time = parse_axis_time(args.end, reference_year)
    timestamps, rows = filter_time_range(timestamps, rows, start_time, end_time)
    timestamps, rows = average_rows(timestamps, rows, args.avg_minutes)
    write_plot(
        timestamps,
        rows,
        args.output,
        args.input_file,
        raw_row_count,
        args.avg_minutes,
        labels,
        args.shunt_ohms,
        args.y_min,
        args.y_max,
        start_time,
        end_time,
        args.x_tick_hours,
    )


if __name__ == "__main__":
    main()
