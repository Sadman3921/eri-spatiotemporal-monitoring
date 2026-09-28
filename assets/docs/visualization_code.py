"""
Pine Island Bayou - ALL water-quality parameter GIFs
====================================================

One script generates the same real-map animated visualization for every
configured environmental parameter.

Input (same folder as this script):
    Pine Island bayou Refined dataset (1).xlsx

Output folder:
    Pine_Island_All_Parameters/

For every parameter the script creates:
    1) an animated GIF
    2) a final-frame PNG preview

It also creates:
    parameter_manifest.csv

Internet is needed the first time for:
    - Esri World Imagery tiles (contextily)
    - OpenStreetMap water geometry (OSMnx)

The satellite basemap and water mask are downloaded/prepared ONCE and
reused for every parameter.
"""

from pathlib import Path
import re
import warnings

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.colors import Normalize
from matplotlib.ticker import FuncFormatter
from scipy.spatial import cKDTree
from pyproj import Transformer
from shapely.geometry import LineString
from shapely.ops import unary_union
from shapely import contains_xy

import contextily as ctx
import osmnx as ox


# ============================================================
# USER SETTINGS
# ============================================================

INPUT_XLSX = "Pine Island bayou Refined dataset (1).xlsx"
OUTPUT_DIR = Path("Pine_Island_All_Parameters")

LAT_COLUMN = "Latitude"
LON_COLUMN = "Longitude"
TIME_COLUMN = "Time (HH:MM:SS)"

# ----------------------------------------------------------------
# PARAMETER CONFIGURATION
#
# column = exact Excel column name
# title  = title shown above map
# label  = colorbar label
# cmap   = a different Matplotlib heatmap palette
#
# Set "enabled": False if you do not want a specific parameter.
# ----------------------------------------------------------------
PARAMETERS = [
    {
        "column": "Turbidity FNU",
        "title": "Turbidity",
        "label": "Turbidity (FNU)",
        "cmap": "cividis",
        "enabled": True,
    },
    {
        "column": "TSS mg/L",
        "title": "Total Suspended Solids",
        "label": "TSS (mg/L)",
        "cmap": "YlOrBr",
        "enabled": True,
    },
    {
        "column": "Chlorophyll RFU",
        "title": "Chlorophyll",
        "label": "Chlorophyll (RFU)",
        "cmap": "viridis",
        "enabled": True,
    },
    {
        "column": "Chlorophyll µg/L",
        "title": "Chlorophyll",
        "label": "Chlorophyll (µg/L)",
        "cmap": "Greens",
        "enabled": True,
    },
    {
        "column": "BGA-PE RFU",
        "title": "BGA-PE",
        "label": "BGA-PE (RFU)",
        "cmap": "PuBuGn",
        "enabled": True,
    },
    {
        "column": "BGA-PE µg/L",
        "title": "BGA-PE",
        "label": "BGA-PE (µg/L)",
        "cmap": "GnBu",
        "enabled": True,
    },
    {
        "column": "Temp °C",
        "title": "Temperature",
        "label": "Temperature (°C)",
        "cmap": "plasma",
        "enabled": True,
    },
    {
        "column": "Cond µS/cm",
        "title": "Conductivity",
        "label": "Conductivity (µS/cm)",
        "cmap": "inferno",
        "enabled": True,
    },
    {
        "column": "SpCond µS/cm",
        "title": "Specific Conductivity",
        "label": "Specific Conductivity (µS/cm)",
        "cmap": "magma",
        "enabled": True,
    },
    {
        "column": "Sal psu",
        "title": "Salinity",
        "label": "Salinity (psu)",
        "cmap": "Blues",
        "enabled": True,
    },
    {
        "column": "nLF Cond µS/cm",
        "title": "nLF Conductivity",
        "label": "nLF Conductivity (µS/cm)",
        "cmap": "Purples",
        "enabled": True,
    },
    {
        "column": "TDS mg/L",
        "title": "Total Dissolved Solids",
        "label": "TDS (mg/L)",
        "cmap": "YlGnBu",
        "enabled": True,
    },
    {
        "column": "ODO % sat",
        "title": "Dissolved Oxygen Saturation",
        "label": "ODO (% saturation)",
        "cmap": "coolwarm",
        "enabled": True,
    },
    {
        "column": "ODO mg/L",
        "title": "Dissolved Oxygen",
        "label": "ODO (mg/L)",
        "cmap": "winter",
        "enabled": True,
    },
    {
        "column": "pH",
        "title": "pH",
        "label": "pH",
        "cmap": "Spectral_r",
        "enabled": True,
    },
    {
        "column": "pH mV",
        "title": "pH Electrode Potential",
        "label": "pH potential (mV)",
        "cmap": "RdPu",
        "enabled": True,
    },
    {
        "column": "Press psi a",
        "title": "Pressure",
        "label": "Pressure (psi a)",
        "cmap": "bone",
        "enabled": True,
    },
    {
        "column": "Depth m",
        "title": "Depth",
        "label": "Depth (m)",
        "cmap": "ocean",
        "enabled": True,
    },
]

# Animation.
# 5 reproduces the timing of the earlier single-parameter script.
# Increase to 10 or 15 if rendering all parameters is too slow.
FRAME_STEP = 5
FPS = 10
GIF_DPI = 105

# Map
MAP_PADDING_M = 45
SATELLITE_ZOOM = 19

# Interpolation
GRID_SIZE = 180
IDW_NEIGHBORS = 12
IDW_POWER = 2.0

# True: extrapolate IDW across the whole detected water polygon.
# False: only display up to MAX_EXTRAPOLATION_M from measured points.
FILL_ENTIRE_RIVER = True
MAX_EXTRAPOLATION_M = 30

# Water geometry search
OSM_SEARCH_MARGIN_DEG = 0.002
FALLBACK_RIVER_HALF_WIDTH_M = 18
FALLBACK_TRAJECTORY_BUFFER_M = 22

# Appearance
HEATMAP_ALPHA = 0.58
SHOW_RIVER_OUTLINE = False
SHOW_MEASURED_POINTS = False

# Optional robust color scaling.
# False = exact min/max (same behavior as your earlier script)
# True  = 1st-99th percentiles to reduce domination by outliers
USE_ROBUST_COLOR_LIMITS = False
ROBUST_LOW_PERCENTILE = 1
ROBUST_HIGH_PERCENTILE = 99


# ============================================================
# HELPERS
# ============================================================

def format_time(value):
    if pd.isna(value):
        return ""

    if hasattr(value, "strftime"):
        return value.strftime("%H:%M:%S")

    if isinstance(value, (int, float, np.number)):
        seconds = int(round(float(value) * 86400)) % 86400
        hh = seconds // 3600
        mm = (seconds % 3600) // 60
        ss = seconds % 60
        return f"{hh:02d}:{mm:02d}:{ss:02d}"

    return str(value)


def safe_filename(text):
    text = str(text).replace("µ", "u").replace("°", "deg")
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    return text.strip("_")


def get_water_polygon(west, south, east, north, trajectory_3857):
    """Get nearby OSM water polygon; fall back safely when necessary."""
    query_bbox = (
        west - OSM_SEARCH_MARGIN_DEG,
        south - OSM_SEARCH_MARGIN_DEG,
        east + OSM_SEARCH_MARGIN_DEG,
        north + OSM_SEARCH_MARGIN_DEG,
    )

    tags = {
        "natural": "water",
        "water": ["river", "stream", "canal"],
        "waterway": ["riverbank", "river", "stream", "canal"],
    }

    print("Downloading water geometry from OpenStreetMap...")

    try:
        water = ox.features_from_bbox(query_bbox, tags)
    except Exception as exc:
        warnings.warn(
            "OSM water query failed. "
            f"Using a trajectory-based fallback mask. Reason: {exc}"
        )
        return (
            trajectory_3857.buffer(FALLBACK_TRAJECTORY_BUFFER_M),
            "trajectory fallback",
        )

    if water is None or len(water) == 0:
        warnings.warn(
            "No OSM water features found. Using trajectory fallback."
        )
        return (
            trajectory_3857.buffer(FALLBACK_TRAJECTORY_BUFFER_M),
            "trajectory fallback",
        )

    water = water[water.geometry.notna()].copy()
    water = water.to_crs(epsg=3857)

    search_zone = trajectory_3857.buffer(80)

    polygon_geoms = [
        g
        for g in water.geometry
        if g.geom_type in ("Polygon", "MultiPolygon")
        and g.is_valid
        and g.intersects(search_zone)
    ]

    if polygon_geoms:
        polygon = unary_union(polygon_geoms).buffer(0)
        print("Using actual OSM water polygon.")
        return polygon, "OSM polygon"

    line_geoms = [
        g
        for g in water.geometry
        if g.geom_type in ("LineString", "MultiLineString")
        and g.is_valid
        and g.intersects(search_zone)
    ]

    if line_geoms:
        line_union = unary_union(line_geoms)
        polygon = line_union.buffer(FALLBACK_RIVER_HALF_WIDTH_M)
        print("Using buffered OSM water centerline.")
        return polygon, "buffered OSM centerline"

    warnings.warn(
        "No matching OSM geometry intersected the survey trajectory. "
        "Using trajectory fallback."
    )
    return (
        trajectory_3857.buffer(FALLBACK_TRAJECTORY_BUFFER_M),
        "trajectory fallback",
    )


def make_idw_field(sample_xy, sample_values, gx, gy, water_mask):
    """Inverse-distance-weighted interpolation inside the water mask."""
    field = np.full(gx.shape, np.nan, dtype=float)

    if len(sample_xy) == 0:
        return field

    query_xy = np.column_stack((gx[water_mask], gy[water_mask]))
    if len(query_xy) == 0:
        return field

    tree = cKDTree(sample_xy)
    k = min(IDW_NEIGHBORS, len(sample_xy))
    distances, indices = tree.query(query_xy, k=k)

    if k == 1:
        distances = distances[:, None]
        indices = indices[:, None]

    eps = 1e-9
    weights = 1.0 / np.power(distances + eps, IDW_POWER)
    neighbor_values = sample_values[indices]

    predictions = (
        np.sum(weights * neighbor_values, axis=1)
        / np.sum(weights, axis=1)
    )

    if not FILL_ENTIRE_RIVER:
        nearest_distance = distances[:, 0]
        predictions = np.where(
            nearest_distance <= MAX_EXTRAPOLATION_M,
            predictions,
            np.nan,
        )

    field[water_mask] = predictions
    return field


# ============================================================
# LOAD DATA ONCE
# ============================================================

input_path = Path(INPUT_XLSX)
if not input_path.exists():
    raise FileNotFoundError(
        f"Could not find '{INPUT_XLSX}'. Put this script and the Excel "
        "file in the same folder, or edit INPUT_XLSX."
    )

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

df = pd.read_excel(input_path)

base_required = [LAT_COLUMN, LON_COLUMN, TIME_COLUMN]
missing_base = [c for c in base_required if c not in df.columns]
if missing_base:
    raise ValueError(
        "Missing required base columns: " + ", ".join(missing_base)
    )

enabled_parameters = [p for p in PARAMETERS if p.get("enabled", True)]
available_parameters = [
    p for p in enabled_parameters if p["column"] in df.columns
]
missing_parameters = [
    p["column"] for p in enabled_parameters if p["column"] not in df.columns
]

if missing_parameters:
    print("\nSkipping parameters not found in Excel:")
    for name in missing_parameters:
        print("  -", name)

if not available_parameters:
    raise ValueError("None of the configured parameters exist in the Excel file.")

# Keep GPS/time rows. Parameter NaNs are handled separately for each animation.
df[LAT_COLUMN] = pd.to_numeric(df[LAT_COLUMN], errors="coerce")
df[LON_COLUMN] = pd.to_numeric(df[LON_COLUMN], errors="coerce")
df = df.dropna(subset=[LAT_COLUMN, LON_COLUMN]).reset_index(drop=True)

if len(df) < 3:
    raise ValueError("Not enough valid GPS measurements.")

for p in available_parameters:
    df[p["column"]] = pd.to_numeric(df[p["column"]], errors="coerce")

print(f"\nValid GPS rows: {len(df)}")
print(f"Parameters to render: {len(available_parameters)}")


# ============================================================
# PREPARE MAP / PROJECTION ONCE
# ============================================================

to_web = Transformer.from_crs(
    "EPSG:4326", "EPSG:3857", always_xy=True
)
to_gps = Transformer.from_crs(
    "EPSG:3857", "EPSG:4326", always_xy=True
)

lon = df[LON_COLUMN].to_numpy(dtype=float)
lat = df[LAT_COLUMN].to_numpy(dtype=float)

x, y = to_web.transform(lon, lat)
x = np.asarray(x, dtype=float)
y = np.asarray(y, dtype=float)

trajectory_geom = LineString(np.column_stack((x, y)))

xmin = float(x.min() - MAP_PADDING_M)
xmax = float(x.max() + MAP_PADDING_M)
ymin = float(y.min() - MAP_PADDING_M)
ymax = float(y.max() + MAP_PADDING_M)

west, south = to_gps.transform(xmin, ymin)
east, north = to_gps.transform(xmax, ymax)

print("\nDownloading/preparing shared satellite basemap...")

satellite_img, satellite_extent = ctx.bounds2img(
    xmin,
    ymin,
    xmax,
    ymax,
    zoom=SATELLITE_ZOOM,
    source=ctx.providers.Esri.WorldImagery,
    ll=False,
    use_cache=True,
    timeout=30,
)

print("Satellite basemap ready.")

river_polygon, river_source = get_water_polygon(
    west, south, east, north, trajectory_geom
)

if river_polygon.is_empty:
    raise RuntimeError("Water-mask geometry is empty.")

grid_x = np.linspace(xmin, xmax, GRID_SIZE)
grid_y = np.linspace(ymin, ymax, GRID_SIZE)
GX, GY = np.meshgrid(grid_x, grid_y)

water_mask = contains_xy(river_polygon, GX, GY)

if not np.any(water_mask):
    warnings.warn(
        "OSM water polygon did not cover the grid; using trajectory fallback."
    )
    river_polygon = trajectory_geom.buffer(
        FALLBACK_TRAJECTORY_BUFFER_M
    )
    river_source = "trajectory fallback"
    water_mask = contains_xy(river_polygon, GX, GY)

if not np.any(water_mask):
    raise RuntimeError("Could not create a usable water mask.")

print(f"Water mask source: {river_source}")
print(f"Water grid cells: {int(water_mask.sum())} / {water_mask.size}")


# ============================================================
# SHARED FRAME INDICES
# ============================================================

first_end = min(10, len(df) - 1)
frame_indices = list(range(first_end, len(df), FRAME_STEP))

if not frame_indices:
    frame_indices = [len(df) - 1]
elif frame_indices[-1] != len(df) - 1:
    frame_indices.append(len(df) - 1)

print(f"Frames per GIF: {len(frame_indices)}")
print(f"Approx. duration per GIF: {len(frame_indices) / FPS:.1f} seconds")


# ============================================================
# RENDER ONE PARAMETER
# ============================================================

def render_parameter(config):
    column = config["column"]
    title_name = config["title"]
    colorbar_label = config["label"]
    cmap_name = config["cmap"]

    values = df[column].to_numpy(dtype=float)
    valid_all = np.isfinite(values)

    n_valid = int(valid_all.sum())
    if n_valid < 3:
        print(f"\nSKIP {column}: only {n_valid} valid measurements.")
        return None

    valid_values = values[valid_all]

    if USE_ROBUST_COLOR_LIMITS:
        vmin = float(np.nanpercentile(
            valid_values, ROBUST_LOW_PERCENTILE
        ))
        vmax = float(np.nanpercentile(
            valid_values, ROBUST_HIGH_PERCENTILE
        ))
    else:
        vmin = float(np.nanmin(valid_values))
        vmax = float(np.nanmax(valid_values))

    if not np.isfinite(vmin) or not np.isfinite(vmax):
        print(f"\nSKIP {column}: invalid range.")
        return None

    # Avoid a zero-width Normalize if a parameter is constant.
    if np.isclose(vmin, vmax):
        pad = 0.5 if np.isclose(vmin, 0) else abs(vmin) * 0.01
        if pad == 0:
            pad = 0.5
        vmin -= pad
        vmax += pad

    slug = safe_filename(column)
    output_gif = OUTPUT_DIR / f"Pine_Island_{slug}.gif"
    output_preview = OUTPUT_DIR / f"Pine_Island_{slug}_final_frame.png"

    print("\n" + "=" * 70)
    print(f"Rendering: {column}")
    print(f"Valid measurements: {n_valid}")
    print(f"Range: {vmin:.4g} to {vmax:.4g}")
    print(f"Colormap: {cmap_name}")
    print("=" * 70)

    fig, ax = plt.subplots(figsize=(8.6, 7.8))

    ax.imshow(
        satellite_img,
        extent=satellite_extent,
        interpolation="bilinear",
        zorder=0,
    )

    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_aspect("equal", adjustable="box")

    cmap = plt.colormaps[cmap_name].copy()
    cmap.set_bad(alpha=0.0)

    norm = Normalize(vmin=vmin, vmax=vmax)
    empty_field = np.full((GRID_SIZE, GRID_SIZE), np.nan)

    heatmap = ax.imshow(
        empty_field,
        extent=[xmin, xmax, ymin, ymax],
        origin="lower",
        cmap=cmap,
        norm=norm,
        alpha=HEATMAP_ALPHA,
        interpolation="bilinear",
        zorder=2,
    )

    if SHOW_RIVER_OUTLINE:
        try:
            geoms = (
                list(river_polygon.geoms)
                if river_polygon.geom_type == "MultiPolygon"
                else [river_polygon]
            )
            for geom in geoms:
                bx, by = geom.exterior.xy
                ax.plot(
                    bx, by,
                    linewidth=0.8,
                    alpha=0.65,
                    zorder=3,
                )
        except Exception:
            pass

    trajectory_line, = ax.plot(
        [],
        [],
        linewidth=2.1,
        color="blue",
        label="ASV GPS trajectory",
        zorder=5,
    )

    sample_scatter = ax.scatter(
        [],
        [],
        s=8,
        c="white",
        edgecolors="black",
        linewidths=0.25,
        alpha=0.70 if SHOW_MEASURED_POINTS else 0.0,
        zorder=4,
    )

    boat_outer, = ax.plot(
        [],
        [],
        marker="o",
        linestyle="None",
        markersize=11,
        markerfacecolor="yellow",
        markeredgecolor="white",
        markeredgewidth=1.4,
        zorder=7,
        label="Current ASV position",
    )

    boat_inner, = ax.plot(
        [],
        [],
        marker="o",
        linestyle="None",
        markersize=5.5,
        markerfacecolor="red",
        markeredgecolor="red",
        zorder=8,
    )

    cbar = fig.colorbar(
        heatmap,
        ax=ax,
        orientation="horizontal",
        pad=0.075,
        fraction=0.055,
    )
    cbar.set_label(colorbar_label)

    middle_y = (ymin + ymax) / 2
    middle_x = (xmin + xmax) / 2

    def longitude_formatter(value, _pos):
        longitude, _latitude = to_gps.transform(value, middle_y)
        if longitude < 0:
            return f"{abs(longitude):.5f}°W"
        return f"{longitude:.5f}°E"

    def latitude_formatter(value, _pos):
        _longitude, latitude = to_gps.transform(middle_x, value)
        if latitude < 0:
            return f"{abs(latitude):.5f}°S"
        return f"{latitude:.5f}°N"

    ax.xaxis.set_major_formatter(
        FuncFormatter(longitude_formatter)
    )
    ax.yaxis.set_major_formatter(
        FuncFormatter(latitude_formatter)
    )

    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.grid(alpha=0.18, linewidth=0.6)

    title = ax.set_title(
        f"Pine Island Bayou — {title_name} Mapping",
        pad=12,
    )

    ax.legend(
        loc="upper right",
        fontsize=8,
        framealpha=0.88,
    )

    ax.text(
        0.008,
        0.008,
        "Imagery © Esri and contributors | "
        "Water geometry © OpenStreetMap contributors",
        transform=ax.transAxes,
        fontsize=5.5,
        color="white",
        bbox=dict(
            facecolor="black",
            alpha=0.45,
            edgecolor="none",
            pad=2,
        ),
        zorder=20,
    )

    def update(frame_number):
        end = frame_indices[frame_number]

        # ASV GPS trajectory always follows all GPS rows up to this time.
        trajectory_line.set_data(
            x[: end + 1],
            y[: end + 1],
        )
        boat_outer.set_data([x[end]], [y[end]])
        boat_inner.set_data([x[end]], [y[end]])

        # Environmental interpolation only uses valid values acquired
        # up to the current time.
        history_values = values[: end + 1]
        history_valid = np.isfinite(history_values)

        current_xy = np.column_stack(
            (
                x[: end + 1][history_valid],
                y[: end + 1][history_valid],
            )
        )
        current_values = history_values[history_valid]

        if len(current_values) > 0:
            field = make_idw_field(
                current_xy,
                current_values,
                GX,
                GY,
                water_mask,
            )
            heatmap.set_data(field)

            if SHOW_MEASURED_POINTS:
                sample_scatter.set_offsets(current_xy)
        else:
            heatmap.set_data(
                np.full((GRID_SIZE, GRID_SIZE), np.nan)
            )

        current_time = format_time(
            df.iloc[end][TIME_COLUMN]
        )

        current_value = values[end]
        if np.isfinite(current_value):
            value_text = f"{current_value:.2f}"
        else:
            value_text = "N/A"

        title.set_text(
            f"Pine Island Bayou — {title_name} Mapping\n"
            f"Time: {current_time}   |   Current: "
            f"{value_text} {colorbar_label.split('(', 1)[-1].rstrip(')') if '(' in colorbar_label else ''}".rstrip()
        )

        return (
            heatmap,
            trajectory_line,
            sample_scatter,
            boat_outer,
            boat_inner,
            title,
        )

    # Final-frame preview
    update(len(frame_indices) - 1)
    fig.savefig(
        output_preview,
        dpi=150,
        bbox_inches="tight",
    )

    animation = FuncAnimation(
        fig,
        update,
        frames=len(frame_indices),
        interval=1000 / FPS,
        blit=False,
        repeat=True,
    )

    print("Saving GIF...")

    animation.save(
        output_gif,
        writer=PillowWriter(fps=FPS),
        dpi=GIF_DPI,
    )

    plt.close(fig)

    print(f"GIF:     {output_gif}")
    print(f"Preview: {output_preview}")

    return {
        "column": column,
        "title": title_name,
        "colorbar_label": colorbar_label,
        "colormap": cmap_name,
        "valid_measurements": n_valid,
        "minimum": float(np.nanmin(valid_values)),
        "maximum": float(np.nanmax(valid_values)),
        "gif": output_gif.name,
        "preview": output_preview.name,
    }


# ============================================================
# RENDER ALL PARAMETERS
# ============================================================

manifest_rows = []

for index, config in enumerate(available_parameters, start=1):
    print(
        f"\nPARAMETER {index}/{len(available_parameters)}: "
        f"{config['column']}"
    )

    result = render_parameter(config)

    if result is not None:
        manifest_rows.append(result)


# ============================================================
# MANIFEST
# ============================================================

manifest_path = OUTPUT_DIR / "parameter_manifest.csv"

if manifest_rows:
    pd.DataFrame(manifest_rows).to_csv(
        manifest_path,
        index=False,
    )

print("\n" + "=" * 70)
print("ALL REQUESTED PARAMETERS FINISHED")
print("=" * 70)
print(f"Output folder: {OUTPUT_DIR.resolve()}")
print(f"Completed GIFs: {len(manifest_rows)}")
print(f"Manifest: {manifest_path}")
print("\nEach parameter has its own heatmap color and its own fixed")
print("parameter-specific value range, while using the same satellite")
print("map, river mask, GPS trajectory, timing, and animation style.")
