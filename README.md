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