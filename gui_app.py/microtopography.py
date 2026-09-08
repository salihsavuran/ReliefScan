"""
Archäologische Mikro-Topografie- und Bodenanomalie-Analyse
===========================================================
Residualanalyse & Detrended Elevation Heatmap (DEM-Detrending)

Dieses Modul dient der Detektion und Visualisierung von subtilen archäologischen
Geländestrukturen (z. B. Grabhügel, Kreisgräben, Hohlwege, Wallanlagen oder
ehemalige Siedlungsspuren) im Zentimeterbereich.

Pipeline:
1. Ingestion: Flexibles Einlesen von CSV- (GPS Visualizer u. a.) oder KML-Dateien.
2. Projektion: Geodätische Transformation von WGS84 in ein lokales metrisches Koordinatensystem (Meter).
3. Interpolation: Erzeugung eines hochauflösenden regulären Rasters (scipy.interpolate.griddata).
4. Detrending: Herausrechnen des Makro-Geländehangs via 2D-Least-Squares (linear oder Polynom 2. Grades).
5. Filterung: Optionale NaN-bewusste Gauß-Glättung und Perzentil-Kappung gegen Randartefakte.
6. Visualisierung: Hochauflösender, 0-zentrierter Export mit Höhenlinien und Metrik-Skalierung (PNG, 300 DPI).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Literal, Optional, Tuple

# Konsolen-Encoding für Windows sicherstellen
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.interpolate import griddata
from scipy.ndimage import gaussian_filter



# =============================================================================
# 1. DATEN-INGESTION (CSV / KML)
# =============================================================================

class DataLoader:
    """Liest GPS- und Höhendaten aus CSV- oder KML-Dateien flexibel ein."""

    # Typische Synonyme für Koordinatenspalten (Kleinbuchstaben)
    LAT_SYNONYMS = {"lat", "latitude", "y", "breite", "lat_deg"}
    LON_SYNONYMS = {"lon", "long", "longitude", "x", "laenge", "länge", "lon_deg"}
    ELE_SYNONYMS = {"ele", "alt", "altitude", "height", "z", "elevation", "hoehe", "höhe"}

    @classmethod
    def load_file(cls, filepath: str) -> pd.DataFrame:
        """
        Lädt eine Datei (CSV oder KML) basierend auf der Dateiendung.

        Returns:
            DataFrame mit standardisierten Spalten ['lat', 'lon', 'ele']
        """
        ext = os.path.splitext(filepath)[1].lower()
        if ext == ".kml":
            return cls.load_kml(filepath)
        elif ext in [".csv", ".txt", ".tsv"]:
            return cls.load_csv(filepath)
        else:
            raise ValueError(f"Nicht unterstütztes Dateiformat: '{ext}'. Erwartet wird .csv oder .kml.")

    @staticmethod
    def _normalize_col_name(name: str) -> str:
        """Entfernt Sonderzeichen, Leerzeichen, Umlaute und Einheiten wie (m), [m], _deg etc."""
        clean = name.lower().strip()
        # Umlaute normalisieren
        clean = clean.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
        # Entferne Klammern wie (m), [m], (meters)
        clean = re.sub(r"[\(\[\{].*?[\)\]\}]", "", clean)
        # Entferne Trennzeichen wie Unterstriche, Bindestriche, Punkte
        clean = re.sub(r"[_\-\.\s]+", "", clean)
        return clean

    @classmethod
    def load_csv(cls, filepath: str) -> pd.DataFrame:
        """
        Liest eine CSV-Datei ein und erkennt Spaltennamen flexibel (auch mit Einheiten wie altitude_m).
        """
        # Trennzeichen automatisch erkennen (Komma, Semikolon, Tabulator, Leerzeichen)
        df = pd.read_csv(filepath, sep=None, engine="python")
        df.columns = [str(c).strip() for c in df.columns]

        col_map = {}
        for col in df.columns:
            norm = cls._normalize_col_name(col)

            # 1. Breitengrad (Latitude)
            if "lat" not in col_map:
                if norm in {"lat", "latitude", "breite", "y"} or norm.startswith("lat") or norm.startswith("breite"):
                    col_map["lat"] = col
                    continue

            # 2. Längengrad (Longitude)
            if "lon" not in col_map:
                if (norm in {"lon", "long", "longitude", "laenge", "x"}
                        or norm.startswith("lon") or norm.startswith("long") or norm.startswith("laenge")):
                    col_map["lon"] = col
                    continue

            # 3. Höhe / Elevation
            if "ele" not in col_map:
                if (norm in {"ele", "alt", "altitude", "height", "z", "elevation", "hoehe", "h"}
                        or any(norm.startswith(prefix) for prefix in ["alt", "ele", "elev", "hoehe", "height"])
                        or "elevation" in norm or "altitude" in norm or "hoehe" in norm):
                    col_map["ele"] = col
                    continue

        # Prüfe, ob alle 3 Spalten gefunden wurden
        missing = [req for req in ["lat", "lon", "ele"] if req not in col_map]
        if missing:
            raise KeyError(
                f"Konnte erforderliche Spalte(n) {missing} in CSV nicht finden. "
                f"Vorhandene Spalten: {list(df.columns)}. Bitte Spalten für Breite, Länge und Höhe bereitstellen."
            )

        standard_df = pd.DataFrame({
            "lat": pd.to_numeric(df[col_map["lat"]], errors="coerce"),
            "lon": pd.to_numeric(df[col_map["lon"]], errors="coerce"),
            "ele": pd.to_numeric(df[col_map["ele"]], errors="coerce"),
        }).dropna()

        if len(standard_df) < 3:
            raise ValueError("Zu wenige gültige Datenpunkte in der Datei (mindestens 3 Punkte erforderlich).")

        return standard_df

    @classmethod
    def load_kml(cls, filepath: str) -> pd.DataFrame:
        """
        Parst Koordinaten mit Z-Werten aus <coordinates>-Tags einer KML-Datei.
        Format in KML: lon,lat,alt [lon,lat,alt ...]
        """
        tree = ET.parse(filepath)
        root = tree.getroot()

        # Namespaces in KML ignorieren/abfangen
        points = []
        for elem in root.iter():
            if elem.tag.endswith("coordinates") and elem.text:
                raw_coords = elem.text.strip()
                # Splitte nach Whitespace (Leerzeichen, Zeilenumbrüche)
                for tuple_str in re.split(r"\s+", raw_coords):
                    parts = tuple_str.strip().split(",")
                    if len(parts) >= 3:
                        try:
                            lon = float(parts[0])
                            lat = float(parts[1])
                            ele = float(parts[2])
                            points.append({"lat": lat, "lon": lon, "ele": ele})
                        except ValueError:
                            continue

        if not points:
            raise ValueError(
                f"Keine 3D-Koordinaten (<coordinates> lon,lat,alt) in '{filepath}' gefunden."
            )

        df = pd.DataFrame(points).dropna()
        if len(df) < 3:
            raise ValueError("Zu wenige gültige 3D-Punkte in der KML-Datei gefunden.")

        if (df["ele"] == 0).all():
            print("[WARNUNG] Alle Höhenwerte (Z) in dieser KML-Datei sind 0.0!")
            print("          Hinweis: Google Earth speichert beim Zeichnen von Pfaden standardmäßig Z=0.")
            print("          Tipp: Lade die KML-Datei auf https://www.gpsvisualizer.com/elevation hoch,")
            print("          um reale Geländehöhen (DEM/SRTM) zuzuordnen und als CSV herunterzuladen.")

        return df


# =============================================================================
# 2. KOORDINATENTRANSFORMATION (WGS84 -> METRISCH)
# =============================================================================

class CoordinateTransformer:
    """
    Transformiert geodätische WGS84-Koordinaten (Grad) in ein lokales,
    abstandstreues 2D-Meter-Koordinatensystem relativ zum Schwerpunkt.
    """

    # WGS84 Ellipsoid-Konstanten
    WGS84_A = 6378137.0          # Große Halbachse in Metern
    WGS84_F = 1.0 / 298.257223563  # Abplattung
    WGS84_E2 = 2 * WGS84_F - WGS84_F ** 2  # Erste numerische Exzentrizität im Quadrat

    @classmethod
    def wgs84_to_local_meters(
        cls, lats: np.ndarray, lons: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, float, float]:
        """
        Berechnet lokale X/Y-Koordinaten in Metern bezogen auf den Zentroid (lat0, lon0).
        Verwendet lokale Krümmungsradien des WGS84-Ellipsoids für maximale Präzision.

        Returns:
            (x_meters, y_meters, lat0, lon0)
        """
        lat0 = float(np.mean(lats))
        lon0 = float(np.mean(lons))

        lat0_rad = np.radians(lat0)
        sin_lat = np.sin(lat0_rad)

        # Meridiankrümmungsradius (Nord-Süd)
        m_rad = cls.WGS84_A * (1.0 - cls.WGS84_E2) / (1.0 - cls.WGS84_E2 * sin_lat**2) ** 1.5
        # Querkrümmungsradius (Ost-West)
        n_rad = cls.WGS84_A / np.sqrt(1.0 - cls.WGS84_E2 * sin_lat**2)

        # Meter pro Grad bei lat0
        meters_per_deg_lat = np.radians(1.0) * m_rad
        meters_per_deg_lon = np.radians(1.0) * n_rad * np.cos(lat0_rad)

        # Lokale Koordinaten (X = Ost, Y = Nord)
        x = (lons - lon0) * meters_per_deg_lon
        y = (lats - lat0) * meters_per_deg_lat

        return x, y, lat0, lon0


# =============================================================================
# 3. RASTER-INTERPOLATION
# =============================================================================

class GridInterpolator:
    """Interpoliert unregelmäßig verteilte Höhenpunkte auf ein dichtes 2D-Gitter."""

    @staticmethod
    def create_grid(
        x: np.ndarray,
        y: np.ndarray,
        z: np.ndarray,
        resolution: float = 0.5,
        buffer_ratio: float = 0.05,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Erstellt ein 2D-Gitter und interpoliert Höhenwerte mit 'cubic' (Fallback auf 'linear').

        Args:
            x: X-Koordinaten in Metern
            y: Y-Koordinaten in Metern
            z: Z-Koordinaten (Höhe in Metern)
            resolution: Rasterweite in Metern (Standard: 0.5m)
            buffer_ratio: Kleiner Puffer um das Bounding-Box-Minimum/Maximum

        Returns:
            (grid_x, grid_y, grid_z)
        """
        x_span = x.max() - x.min()
        y_span = y.max() - y.min()
        bx = max(x_span * buffer_ratio, resolution * 2)
        by = max(y_span * buffer_ratio, resolution * 2)

        x_min, x_max = x.min() - bx, x.max() + bx
        y_min, y_max = y.min() - by, y.max() + by

        grid_x_1d = np.arange(x_min, x_max + resolution, resolution)
        grid_y_1d = np.arange(y_min, y_max + resolution, resolution)
        grid_x, grid_y = np.meshgrid(grid_x_1d, grid_y_1d)

        points = np.column_stack((x, y))

        # 1. Kubische Spline-Interpolation für stetig differenzierbare Geländeübergänge
        z_cubic = griddata(points, z, (grid_x, grid_y), method="cubic")

        # 2. Lineare Interpolation zur Füllung von Rand-NaNs (wo kubische Splines keine Rumpfableitung haben)
        z_linear = griddata(points, z, (grid_x, grid_y), method="linear")

        # Fallback: Ersetze NaN-Werte der kubischen Interpolation mit linearen Werten
        nan_mask = np.isnan(z_cubic)
        grid_z = z_cubic.copy()
        grid_z[nan_mask] = z_linear[nan_mask]

        return grid_x, grid_y, grid_z


# =============================================================================
# 4. DETRENDING (TRENDBEREINIGUNG DER MAKRO-TOPOGRAFIE)
# =============================================================================

@dataclass
class TrendResult:
    """Ergebnis des Detrendings."""
    trend_type: Literal["linear", "poly2"]
    coefficients: np.ndarray
    formula: str
    trend_grid: np.ndarray
    residuals: np.ndarray


class SurfaceDetrender:
    """
    Fittet eine 2D-Ausgleichsfläche über das Höhenmodell per Methode
    der kleinsten Quadrate (Least Squares) und isoliert lokale Residuen.
    """

    @staticmethod
    def detrend(
        grid_x: np.ndarray,
        grid_y: np.ndarray,
        grid_z: np.ndarray,
        trend_type: Literal["linear", "poly2"] = "poly2",
    ) -> TrendResult:
        """
        Berechnet den Trend und subtrahiert ihn vom DEM.

        Modelle:
        - 'linear': z = a*x + b*y + c
        - 'poly2':  z = a*x^2 + b*y^2 + c*x*y + d*x + e*y + f
        """
        # Nur valide (Nicht-NaN) Datenpunkte für den Fit verwenden
        valid = ~np.isnan(grid_z)
        if np.sum(valid) < (6 if trend_type == "poly2" else 3):
            raise ValueError("Zu wenige valide Gitterpunkte für die Trendberechnung vorhanden.")

        xv = grid_x[valid]
        yv = grid_y[valid]
        zv = grid_z[valid]

        if trend_type == "linear":
            # Designmatrix: [x, y, 1]
            A = np.column_stack((xv, yv, np.ones_like(xv)))
            coeffs, _, _, _ = np.linalg.lstsq(A, zv, rcond=None)
            a, b, c = coeffs
            formula = f"z_trend = {a:+.4f}*x {b:+.4f}*y {c:+.4f}"

            # Trend auf gesamtem Gitter auswerten
            trend_grid = a * grid_x + b * grid_y + c

        elif trend_type == "poly2":
            # Designmatrix: [x^2, y^2, x*y, x, y, 1]
            A = np.column_stack((
                xv**2,
                yv**2,
                xv * yv,
                xv,
                yv,
                np.ones_like(xv)
            ))
            coeffs, _, _, _ = np.linalg.lstsq(A, zv, rcond=None)
            a, b, c, d, e, f = coeffs
            formula = (
                f"z_trend = {a:+.5e}*x^2 {b:+.5e}*y^2 {c:+.5e}*x*y "
                f"{d:+.4f}*x {e:+.4f}*y {f:+.4f}"
            )

            trend_grid = (
                a * (grid_x**2) +
                b * (grid_y**2) +
                c * (grid_x * grid_y) +
                d * grid_x +
                e * grid_y +
                f
            )
        else:
            raise ValueError(f"Unbekannter Trend-Typ: '{trend_type}'. Unterstützt: 'linear', 'poly2'.")

        # Maskiere unberechenbare Bereiche entsprechend dem DEM
        trend_grid[~valid] = np.nan

        # Residuen = gemessene Höhe - natürlicher Makro-Hang (in Metern)
        residuals = grid_z - trend_grid

        return TrendResult(
            trend_type=trend_type,
            coefficients=coeffs,
            formula=formula,
            trend_grid=trend_grid,
            residuals=residuals,
        )


# =============================================================================
# 5. DATENBEREINIGUNG & FILTERUNG
# =============================================================================

class AnomalyFilter:
    """Filtert Rauschen und kappt Ausreißer für eine unverzerrte Farbgebung."""

    @staticmethod
    def smooth_nan_aware(data: np.ndarray, sigma: float = 1.0) -> np.ndarray:
        """
        Führt eine normalisierte Gauß-Glättung durch, die NaNs ignoriert
        und den Rand nicht abdunkelt (Normalized Convolution).
        """
        if sigma <= 0:
            return data.copy()

        nan_mask = np.isnan(data)
        data_zeroed = np.where(nan_mask, 0.0, data)
        weights = np.where(nan_mask, 0.0, 1.0)

        # Faltung von Daten und Gewichtsmaske
        smoothed_data = gaussian_filter(data_zeroed, sigma=sigma, mode="nearest")
        smoothed_weights = gaussian_filter(weights, sigma=sigma, mode="nearest")

        with np.errstate(divide="ignore", invalid="ignore"):
            result = smoothed_data / smoothed_weights

        result[nan_mask] = np.nan
        return result

    @staticmethod
    def compute_symmetric_limits(
        data: np.ndarray, p_low: float = 2.0, p_high: float = 98.0
    ) -> Tuple[float, float]:
        """
        Berechnet symmetrische Farbskalen-Grenzwerte um den Nullpunkt [-vmax, +vmax],
        damit 0 m exakt in der Mitte der divergierenden Farbskala liegt.
        """
        valid = data[~np.isnan(data)]
        if len(valid) == 0:
            return -1.0, 1.0

        q_low, q_high = np.percentile(valid, [p_low, p_high])
        abs_max = max(abs(q_low), abs(q_high))

        # Falls praktisch keine Varianz vorhanden ist
        if abs_max < 1e-6:
            abs_max = 0.01

        return -abs_max, abs_max


# =============================================================================
# 6. VISUALISIERUNG & EXPORT
# =============================================================================

class AnomalyVisualizer:
    """Erzeugt druckfähige, wissenschaftliche Heatmaps von Mikro-Topografien."""

    @staticmethod
    def plot_and_export(
        grid_x: np.ndarray,
        grid_y: np.ndarray,
        residuals: np.ndarray,
        sample_x: Optional[np.ndarray] = None,
        sample_y: Optional[np.ndarray] = None,
        unit: Literal["cm", "m"] = "cm",
        cmap: str = "RdBu_r",
        output_filepath: str = "heatmap_anomalies.png",
        title: str = "Archäologische Mikro-Topografie (Detrended Elevation Model)",
        dpi: int = 300,
        show_contours: bool = True,
        show_track: bool = True,
    ) -> None:
        """
        Erstellt die Heatmap mit Konturlinien und speichert sie als PNG.
        """
        # Skalierungsfaktor (Meter -> Zentimeter oder Meter)
        scale_factor = 100.0 if unit == "cm" else 1.0
        unit_label = "cm" if unit == "cm" else "m"

        res_scaled = residuals * scale_factor

        # Robuste Grenzen bestimmen (2% bis 98% Perzentil)
        vmin, vmax = AnomalyFilter.compute_symmetric_limits(res_scaled, 2.0, 98.0)

        # Plot initialisieren mit harmonischem Seitenverhältnis
        fig, ax = plt.subplots(figsize=(10, 8), dpi=dpi)

        # 1. Heatmap zeichnen (pcolormesh mit Shading für glatte Ränder)
        mesh = ax.pcolormesh(
            grid_x,
            grid_y,
            res_scaled,
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
            shading="auto",
        )

        # 2. Höhenlinien (Isohypsen der Anomalien)
        if show_contours:
            # 9-11 sinnvolle Niveaus wählen
            contour_levels = np.linspace(vmin, vmax, 11)
            # 0-Linie hervorheben
            cs = ax.contour(
                grid_x,
                grid_y,
                res_scaled,
                levels=contour_levels,
                colors="black",
                linewidths=0.6,
                alpha=0.6,
            )
            ax.clabel(cs, inline=True, fontsize=8, fmt=f"%1.0f {unit_label}")

        # 3. Optionale Einblendung der ursprünglichen Messpunkte/Pfadlinie
        if show_track and sample_x is not None and sample_y is not None:
            ax.scatter(
                sample_x,
                sample_y,
                color="black",
                s=2,
                alpha=0.25,
                label="Messpunkte / GPS-Pfad",
            )
            ax.legend(loc="upper right", framealpha=0.8, fontsize=8)

        # Achsen und Beschriftung
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlabel("Relativer Abstand Ost-West (Meter)", fontsize=11, fontweight="normal")
        ax.set_ylabel("Relativer Abstand Nord-Süd (Meter)", fontsize=11, fontweight="normal")
        ax.set_title(title, fontsize=13, fontweight="bold", pad=15)
        ax.grid(True, linestyle="--", alpha=0.3, color="gray")

        # Colorbar
        cbar = fig.colorbar(mesh, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_label(
            f"Relativer Höhenunterschied ({unit_label})\n[Rot = Erhebung/Wall | Blau = Senke/Graben]",
            fontsize=10,
            fontweight="normal",
        )

        # Layout straffen und speichern
        plt.tight_layout()
        os.makedirs(os.path.dirname(os.path.abspath(output_filepath)), exist_ok=True)
        plt.savefig(output_filepath, dpi=dpi, bbox_inches="tight")
        plt.close(fig)
        print(f"[OK] Visualisierung erfolgreich exportiert nach: {os.path.abspath(output_filepath)}")


# =============================================================================
# 7. DIAGNOSE & STATISTIK-VALIDIERUNG
# =============================================================================

def print_validation_report(
    raw_df: pd.DataFrame,
    grid_x: np.ndarray,
    grid_y: np.ndarray,
    trend_result: TrendResult,
    cleaned_residuals: np.ndarray,
    lat0: float,
    lon0: float,
) -> None:
    """Gibt eine umfassende wissenschaftliche Zusammenfassung auf der Konsole aus."""
    valid_res = cleaned_residuals[~np.isnan(cleaned_residuals)]

    print("\n" + "=" * 70)
    print("[REPORT] VALIDIERUNGSBERICHT: ARCHAEOLOGISCHE MIKRO-TOPOGRAFIE")
    print("=" * 70)
    print(f"Eingelesene Messpunkte:        {len(raw_df):,}")
    print(f"Zentroid (Referenzpunkt):      Lat {lat0:.6f} deg, Lon {lon0:.6f} deg")
    print(f"Ausdehnung Ost-West:           {grid_x.min():.1f} m bis {grid_x.max():.1f} m ({grid_x.max() - grid_x.min():.1f} m)")
    print(f"Ausdehnung Nord-Sued:          {grid_y.min():.1f} m bis {grid_y.max():.1f} m ({grid_y.max() - grid_y.min():.1f} m)")
    print(f"Raster-Dimension:              {grid_x.shape[1]} x {grid_x.shape[0]} Zellen")
    print("-" * 70)
    print(f"Gewaehltes Trendmodell:        {trend_result.trend_type.upper()}")
    print(f"Trendfunktion:                 {trend_result.formula}")
    print("-" * 70)
    print("Residuen-Statistik (lokale Bodenanomalien):")
    print(f"  - Minimalwert (tiefste Senke):  {np.min(valid_res) * 100:+.1f} cm ({np.min(valid_res):+.3f} m)")
    print(f"  - Maximalwert (hoechste Kuppe): {np.max(valid_res) * 100:+.1f} cm ({np.max(valid_res):+.3f} m)")
    print(f"  - Mittelwert:                   {np.mean(valid_res) * 100:+.2f} cm ({np.mean(valid_res):+.4f} m)")
    print(f"  - Standardabweichung (Sigma):   {np.std(valid_res) * 100:.1f} cm ({np.std(valid_res):.3f} m)")
    p25, p50, p75 = np.percentile(valid_res, [25, 50, 75]) * 100
    print(f"  - Quartile (25% | 50% | 75%):   {p25:+.1f} cm | {p50:+.1f} cm | {p75:+.1f} cm")
    print("=" * 70 + "\n")


# =============================================================================
# 8. SYNTHETISCHER DEMO-GENERATOR
# =============================================================================

def generate_synthetic_archaeology_data(filepath: str = "sample_data.csv") -> str:
    """
    Generiert einen realistischen archäologischen Testdatensatz mit:
    - Natürlichem Makro-Hang (geneigte Fläche + Wölbung)
    - Einem prähistorischen Grabhügel (ca. +35 cm Erhebung)
    - Einem ringförmigen Graben um den Hügel (ca. -25 cm Vertiefung)
    - Einem Hohlweg / historischen Graben (ca. -20 cm)
    - Realistischem Messrauschen (GPS-Ungenauigkeit ca. 3 cm)
    """
    np.random.seed(42)
    lat_center = 48.137154
    lon_center = 11.576124

    # Simuliere Mäander- / Raster-Begehungspfad über 60 x 60 Meter
    x_lines = np.linspace(-30, 30, 25)
    y_points = np.linspace(-30, 30, 150)
    all_x, all_y = [], []

    for i, xl in enumerate(x_lines):
        y_walk = y_points if (i % 2 == 0) else y_points[::-1]
        x_walk = xl + np.random.normal(0, 0.2, size=len(y_walk))
        all_x.extend(x_walk)
        all_y.extend(y_walk)

    x_arr = np.array(all_x)
    y_arr = np.array(all_y)

    # 1. Makro-Hang (5% Gefälle nach Nordosten + leichte Wölbung)
    z_macro = 520.0 + 0.05 * x_arr + 0.03 * y_arr - 0.0004 * (x_arr**2)

    # 2. Archäologische Anomalien:
    # A) Grabhügel im Zentrum (x=0, y=0, Radius ~ 8m, Höhe ~ +0.35m)
    dist_center = np.sqrt(x_arr**2 + y_arr**2)
    z_mound = 0.35 * np.exp(-(dist_center**2) / (2 * 4.0**2))

    # B) Kreisgraben um den Hügel (Radius r=10m, Breite ~ 2m, Tiefe ~ -0.25m)
    z_ditch = -0.25 * np.exp(-((dist_center - 10.0)**2) / (2 * 1.5**2))

    # C) Alter Hohlweg (Diagonale Rinne von Südwest nach Nordost)
    dist_road = np.abs(y_arr - 0.5 * x_arr + 15) / np.sqrt(1 + 0.5**2)
    z_road = -0.20 * np.exp(-(dist_road**2) / (2 * 2.0**2))

    # D) Messrauschen (ca. ±3 cm)
    noise = np.random.normal(0, 0.03, size=len(x_arr))

    # Gesamthöhe
    z_total = z_macro + z_mound + z_ditch + z_road + noise

    # Zurückrechnen in geodätische Koordinaten WGS84
    meters_per_deg_lat = 111132.95
    meters_per_deg_lon = 111132.95 * np.cos(np.radians(lat_center))

    lats = lat_center + (y_arr / meters_per_deg_lat)
    lons = lon_center + (x_arr / meters_per_deg_lon)

    df = pd.DataFrame({
        "latitude": np.round(lats, 7),
        "longitude": np.round(lons, 7),
        "altitude_m": np.round(z_total, 3),
    })

    df.to_csv(filepath, index=False)
    print(f"[INFO] Synthetischer Beispieldatensatz erzeugt: {filepath} ({len(df)} Messpunkte)")
    return filepath


# =============================================================================
# 9. PIPELINE-CONTROLLER
# =============================================================================

def run_pipeline(
    input_file: str,
    trend_type: Literal["linear", "poly2"] = "poly2",
    grid_res: float = 0.5,
    sigma: float = 1.0,
    unit: Literal["cm", "m"] = "cm",
    cmap: str = "RdBu_r",
    output_png: str = "heatmap_anomalies.png",
    show_track: bool = True,
) -> None:
    """
    Führt die vollständige Analyse-Pipeline aus.
    """
    print(f"\n[START] Starte Analyse fuer: {input_file}")

    # Schritt 1: Daten-Ingestion
    df = DataLoader.load_file(input_file)
    print(f"  [1/6] Ingestion: {len(df)} Punkte geladen.")

    # Schritt 2: Koordinatentransformation
    x_m, y_m, lat0, lon0 = CoordinateTransformer.wgs84_to_local_meters(
        df["lat"].to_numpy(), df["lon"].to_numpy()
    )
    z_m = df["ele"].to_numpy()
    print(f"  [2/6] Projektion: Metrisches Koordinatensystem zentriert bei ({lat0:.5f}, {lon0:.5f}).")

    # Schritt 3: Raster-Interpolation
    grid_x, grid_y, grid_z = GridInterpolator.create_grid(x_m, y_m, z_m, resolution=grid_res)
    print(f"  [3/6] Interpolation: 2D-Raster mit Auflösung {grid_res} m generiert ({grid_x.shape[1]}x{grid_x.shape[0]} Zellen).")

    # Schritt 4: Detrending (Entfernung des Makro-Hangs)
    trend_result = SurfaceDetrender.detrend(grid_x, grid_y, grid_z, trend_type=trend_type)
    print(f"  [4/6] Detrending: Makro-Hang bereinigt via '{trend_type}'.")

    # Schritt 5: Filterung & Glättung
    filtered_residuals = AnomalyFilter.smooth_nan_aware(trend_result.residuals, sigma=sigma)
    print(f"  [5/6] Filterung: NaN-bewusste Gauß-Glättung angewandt (Sigma = {sigma}).")

    # Schritt 6: Validierungsbericht
    print_validation_report(
        raw_df=df,
        grid_x=grid_x,
        grid_y=grid_y,
        trend_result=trend_result,
        cleaned_residuals=filtered_residuals,
        lat0=lat0,
        lon0=lon0,
    )

    # Schritt 7: Visualisierung & Export
    AnomalyVisualizer.plot_and_export(
        grid_x=grid_x,
        grid_y=grid_y,
        residuals=filtered_residuals,
        sample_x=x_m if show_track else None,
        sample_y=y_m if show_track else None,
        unit=unit,
        cmap=cmap,
        output_filepath=output_png,
        title=f"Archäologische Bodenanomalien (Residual-DEM, Trend: {trend_type})",
        dpi=300,
        show_contours=True,
        show_track=show_track,
    )


# =============================================================================
# 10. CLI & EINSTIEGSPUNKT
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Archäologische Mikro-Topografie- und Bodenanomalie-Analyse (Residualanalyse)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-i", "--input",
        type=str,
        default=None,
        help="Pfad zur Eingabedatei (.csv oder .kml)",
    )
    parser.add_argument(
        "-t", "--trend",
        type=str,
        choices=["linear", "poly2"],
        default="poly2",
        help="Modell für den Makro-Hang: 'linear' (Ebene) oder 'poly2' (Polynom 2. Grades)",
    )
    parser.add_argument(
        "-r", "--resolution",
        type=float,
        default=0.5,
        help="Gitterweite des Rasters in Metern (z. B. 0.5 für 50 cm Auflösung)",
    )
    parser.add_argument(
        "-s", "--sigma",
        type=float,
        default=1.0,
        help="Gauß-Filter Sigma zur Rauschunterdrückung (0 = keine Glättung)",
    )
    parser.add_argument(
        "-u", "--unit",
        type=str,
        choices=["cm", "m"],
        default="cm",
        help="Einheit der Heatmap-Farbskala ('cm' oder 'm')",
    )
    parser.add_argument(
        "-c", "--cmap",
        type=str,
        default="RdBu_r",
        help="Matplotlib Colormap (z. B. 'RdBu_r', 'coolwarm')",
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default="heatmap_anomalies.png",
        help="Dateiname für den PNG-Export",
    )
    parser.add_argument(
        "--no-track",
        action="store_true",
        help="Messpfad-Overlay im Plot ausblenden",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Erzeugt einen synthetischen archäologischen Datensatz und führt die Analyse durch",
    )

    args = parser.parse_args()

    # Demo-Modus oder regulärer Aufruf
    if args.demo or args.input is None:
        if args.input is None and not args.demo:
            print("[INFO] Keine Eingabedatei angegeben. Starte automatischen Demonstrations-Modus (--demo)...")
        demo_file = generate_synthetic_archaeology_data("sample_archaeology_data.csv")
        target_file = demo_file
    else:
        target_file = args.input

    run_pipeline(
        input_file=target_file,
        trend_type=args.trend,
        grid_res=args.resolution,
        sigma=args.sigma,
        unit=args.unit,
        cmap=args.cmap,
        output_png=args.output,
        show_track=not args.no_track,
    )


if __name__ == "__main__":
    main()
