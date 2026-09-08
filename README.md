# ReliefScan 🛰️🔍

> Automated micro-topography analysis & detrended elevation heatmap studio for detecting subtle surface anomalies from Google Earth data.

[![Python](https://img.shields.io/badge/Python-3.9+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![UI](https://img.shields.io/badge/GUI-CustomTkinter-blue)](https://github.com/TomSchimansky/CustomTkinter)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**ReliefScan** is a geostatistical terrain analysis toolkit designed to isolate micro-relief structures (such as buried ditches, ramparts, burial mounds, and foundation tracks) hidden underneath natural terrain slopes. By converting sampled GPS paths into metric grids and applying mathematical trend-removal (detrending), it surfaces centimetre-scale variations as high-contrast heatmaps.

---

## ✨ Features

- **Google Earth Integration:** Parses raw path coordinates directly from exported `.kml` files or tabular `.csv` / `.txt` files.
- **Automated Elevation Ingestion:** Built-in chunked query engine for the open-access Open-Meteo Elevation API—no API key required.
- **Geodetic Metric Transformation:** Projects geographic WGS84 coordinates into an undistorted local Euclidean coordinate system (metres) based on centroid curvature radii ($M$ and $N$).
- **Bicubic Spline Interpolation:** Reconstructs continuous, dense digital elevation models (DEM) with automatic linear boundary fallbacks (`scipy.interpolate.griddata`).
- **Macro-Slope Detrending:** Fits linear planes ($z = ax + by + c$) or 2nd-degree polynomials via least-squares optimization (`lstsq`) to subtract natural macro-topography.
- **Artefact Suppression:** Features NaN-aware normalized Gaussian convolution and symmetric percentile clipping to eliminate edge distortions.
- **Modern Desktop GUI:** Built with CustomTkinter, offering dedicated project workspace folders, non-blocking asynchronous processing threads, and real-time image preview.
- **Headless CLI:** Fully operational from the command line for automated batch pipelines and scripting.

---

## 🏗️ Architecture Pipeline

```text
[ Google Earth Pro (.kml) ] 
            │
            ▼
[ Coordinate Extractor & API Ingestion ] ──► (WGS84 Lat / Lon + Elevation)
            │
            ▼
[ Local Geodetic Transformation ]        ──► (Local Metric X/Y in Metres)
            │
            ▼
[ 2D Bicubic Spline Interpolation ]       ──► (Continuous DEM Raster)
            │
            ▼
[ Surface Detrending (Least Squares) ]   ──► (Macro Slope Subtracted)
            │
            ▼
[ Residual Filter & Color Mapping ]      ──► (High-Res 300 DPI Heatmap)

```

---

## 🚀 Getting Started

### Prerequisites

* Python 3.9 or higher installed
* Git

### Installation

1. **Clone the repository:**
```bash
git clone [https://github.com/](https://github.com/)<YOUR-USERNAME>/ReliefScan.git
cd ReliefScan

```


2. **Set up a virtual environment (recommended):**
```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

```


3. **Install dependencies:**
```bash
pip install -r requirements.txt

```



*(If you don't have a `requirements.txt` yet, install the core packages directly: `pip install numpy pandas scipy matplotlib requests Pillow customtkinter`)*

---

## 🖥️ Usage

### Option 1: Modern Desktop GUI (Recommended)

Launch the CustomTkinter studio interface:

```bash
python gui_modern.py

```

1. **Create or select a project** in the sidebar. Each project maintains its own isolated folder under `projekte/<project_name>/`.
2. **Tab 1 (Elevation Fetcher):** Select your exported Google Earth `.kml` or raw `.csv`. Click **Fetch Elevation** to automatically retrieve height data and save `messpunkte_mit_hoehen.csv`.
3. **Tab 2 (Relief Heatmap):** Adjust your parameters (Trend model, Grid resolution, Sigma smoothing) and click **Generate Heatmap**. The plot renders directly inside the interface.

---

### Option 2: Command Line Interface (CLI)

Run the analytical engine directly via `microtopography.py`:

```bash
# Run a self-contained demonstration with synthetic archaeological anomalies
python microtopography.py --demo

# Analyze custom elevation data
python microtopography.py -i messpunkte_mit_hoehen.csv -t poly2 -r 0.5 -s 1.0 -c RdBu_r -u cm -o heatmap.png

```

#### CLI Parameters

| Flag | Default | Description |
| --- | --- | --- |
| `-i`, `--input` | *None* | Path to input `.csv`, `.txt`, or `.kml` file. |
| `-t`, `--trend` | `poly2` | Trend model to subtract: `linear` (planar slope) or `poly2` (curved terrain). |
| `-r`, `--resolution` | `0.5` | Sampling grid cell size in metres (e.g. `0.25` for 25 cm). |
| `-s`, `--sigma` | `1.0` | Gaussian smoothing factor for noise reduction (`0` disables smoothing). |
| `-c`, `--cmap` | `RdBu_r` | Diverging Matplotlib colormap (`RdBu_r`, `coolwarm`, `bwr`). |
| `-u`, `--unit` | `cm` | Metric unit for anomaly scale and colorbar (`cm` or `m`). |
| `-o`, `--output` | `heatmap.png` | Destination filepath for the exported 300 DPI image. |
| `--no-track` | `False` | Hides black sampling points/track lines from the plot. |

---

## 📐 Field Sampling Guidelines (Google Earth Pro)

To minimize interpolation artefacts and ensure faithful reconstruction:

1. **Enable Terrain:** Ensure the **Terrain** layer in the lower-left panel of Google Earth Pro is checked.
2. **Reset View:** Press `R` to lock the camera to a top-down, north-facing angle.
3. **Continuous Drag:** Open the *Add Path* tool, hold the left mouse button, and drag a tight, meandering serpentine path across the target field.
4. **Buffer Margin:** Extend the path 10–15% beyond the boundaries of the field to absorb edge interpolation distortions.
5. **Export:** Right-click the path in the sidebar, select **Save Place As...**, and choose **Kml (*.kml)**.

---

## ⚠️ Data Resolution Notice

ReliefScan processes data from any elevation provider. When querying free public satellite elevation datasets (such as Copernicus DEM or SRTM via open APIs), the native horizontal resolution is typically $30 \times 30\text{ metres}$.

While the interpolation algorithms mathematically smooth these points to highlight broad topographical variations, micro-features smaller than the source sensor's resolution may represent interpolation artefacts. For centimetre-accurate archaeological feature detection, feeding official airborne **LiDAR (DGM1)** point clouds into the pipeline is recommended where open data policies permit.

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for details.
