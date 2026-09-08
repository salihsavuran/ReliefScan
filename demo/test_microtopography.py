"""
Automatisierte Tests für microtopography.py
"""

import os
import unittest
import numpy as np
import pandas as pd
from microtopography import (
    DataLoader,
    CoordinateTransformer,
    GridInterpolator,
    SurfaceDetrender,
    AnomalyFilter,
    run_pipeline,
)


class TestMicrotopography(unittest.TestCase):

    def setUp(self):
        self.test_csv = "test_temp.csv"
        self.test_png = "test_out.png"

    def tearDown(self):
        for f in [self.test_csv, self.test_png, "test_kml_temp.kml"]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except OSError:
                    pass

    def test_flexible_csv_columns(self):
        """Testet verschiedene Spaltenbezeichnungen (Deutsch, Englisch, Abkürzungen, Einheiten)."""
        variations = [
            {"Breite": [48.0, 48.1, 48.2], "Länge": [11.0, 11.1, 11.2], "Höhe": [500, 502, 501]},
            {"lat_deg": [48.0, 48.1, 48.2], "lon_deg": [11.0, 11.1, 11.2], "altitude_m": [500, 502, 501]},
            {"latitude": [48.0, 48.1, 48.2], "longitude": [11.0, 11.1, 11.2], "ele (m)": [500, 502, 501]},
            {"y": [48.0, 48.1, 48.2], "x": [11.0, 11.1, 11.2], "z": [500, 502, 501]},
        ]
        for data in variations:
            df = pd.DataFrame(data)
            df.to_csv(self.test_csv, index=False)
            loaded = DataLoader.load_csv(self.test_csv)
            self.assertEqual(len(loaded), 3)
            self.assertListEqual(list(loaded.columns), ["lat", "lon", "ele"])

    def test_coordinate_transformation(self):
        """Testet die geodätische WGS84-Projektion auf Plausibilität."""
        lats = np.array([48.0, 48.01])
        lons = np.array([11.0, 11.0])
        x, y, lat0, lon0 = CoordinateTransformer.wgs84_to_local_meters(lats, lons)
        # 0.01 Grad Nord-Süd sollte bei ca. 1.113 km (1113 m) liegen
        dy = abs(y[1] - y[0])
        self.assertTrue(1110.0 < dy < 1120.0, f"Unerwarteter Abstand dy: {dy}")
        self.assertAlmostEqual(x[0], x[1], delta=0.1)

    def test_detrending_linear_exact(self):
        """Verifiziert, dass eine rein lineare geneigte Ebene ein Residuum von ca. 0 ergibt."""
        x = np.linspace(-10, 10, 20)
        y = np.linspace(-10, 10, 20)
        gx, gy = np.meshgrid(x, y)
        # Exakte Ebene: z = 0.5*x - 0.2*y + 100.0
        gz = 0.5 * gx - 0.2 * gy + 100.0

        res = SurfaceDetrender.detrend(gx, gy, gz, trend_type="linear")
        self.assertAlmostEqual(res.coefficients[0], 0.5, places=4)
        self.assertAlmostEqual(res.coefficients[1], -0.2, places=4)
        self.assertAlmostEqual(res.coefficients[2], 100.0, places=4)
        np.testing.assert_allclose(res.residuals, 0.0, atol=1e-10)

    def test_detrending_poly2_exact(self):
        """Verifiziert, dass ein 2D-Polynom 2. Grades exakt gefittet wird."""
        x = np.linspace(-10, 10, 20)
        y = np.linspace(-10, 10, 20)
        gx, gy = np.meshgrid(x, y)
        # Quadratische Wölbung
        gz = 0.01 * (gx**2) - 0.02 * (gy**2) + 0.005 * (gx * gy) + 0.1 * gx - 0.3 * gy + 50.0

        res = SurfaceDetrender.detrend(gx, gy, gz, trend_type="poly2")
        np.testing.assert_allclose(res.residuals, 0.0, atol=1e-8)

    def test_anomaly_filter(self):
        """Testet die NaN-bewusste Gauß-Glättung und symmetrische Grenzwerte."""
        arr = np.array([
            [1.0, 2.0, np.nan],
            [2.0, 10.0, 2.0],
            [np.nan, 2.0, 1.0]
        ])
        smoothed = AnomalyFilter.smooth_nan_aware(arr, sigma=1.0)
        # NaN-Positionen müssen NaN bleiben
        self.assertTrue(np.isnan(smoothed[0, 2]))
        self.assertTrue(np.isnan(smoothed[2, 0]))
        # Zentrale Spitze (10.0) muss geglättet sein
        self.assertTrue(smoothed[1, 1] < 10.0)

        vmin, vmax = AnomalyFilter.compute_symmetric_limits(smoothed)
        self.assertEqual(vmin, -vmax)

    def test_end_to_end_pipeline(self):
        """Testet die vollständige Ausführung inklusive PNG-Erzeugung."""
        # 10 Punkte Dreiecksgelände
        df = pd.DataFrame({
            "lat": [48.000, 48.001, 48.002, 48.001, 48.000, 48.002],
            "lon": [11.000, 11.000, 11.001, 11.002, 11.002, 11.001],
            "ele": [500.1, 500.4, 500.8, 500.5, 500.2, 500.6],
        })
        df.to_csv(self.test_csv, index=False)

        run_pipeline(
            input_file=self.test_csv,
            trend_type="linear",
            grid_res=5.0,
            sigma=0.5,
            unit="cm",
            output_png=self.test_png,
            show_track=True,
        )

        self.assertTrue(os.path.exists(self.test_png))
        self.assertGreater(os.path.getsize(self.test_png), 1000)


if __name__ == "__main__":
    unittest.main()
