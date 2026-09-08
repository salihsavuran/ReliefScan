import pandas as pd
import requests

input_file = "test-scan1.csv"
output_file = "test-scan1-with-ele.csv"

# 1. Daten laden
df = pd.read_csv(input_file, sep=r"\s+|\t|,", engine="python")
lats = df["latitude"].tolist()
lons = df["longitude"].tolist()

print(f"[INFO] Frage Höhendaten für {len(lats)} Punkte ab...")

# 2. Batch-Abfrage an freie Open-Meteo Elevation API (Chunks à 1000 Punkte)
elevations = []
chunk_size = 1000

for i in range(0, len(lats), chunk_size):
    lat_chunk = ",".join(map(str, lats[i:i + chunk_size]))
    lon_chunk = ",".join(map(str, lons[i:i + chunk_size]))
    url = f"https://api.open-meteo.com/v1/elevation?latitude={lat_chunk}&longitude={lon_chunk}"
    
    response = requests.get(url)
    if response.status_code == 200:
        elevations.extend(response.json().get("elevation", []))
    else:
        raise RuntimeError(f"API-Fehler: {response.status_code} - {response.text}")

# 3. Spalte 'ele' ergänzen und speichern
df["ele"] = elevations
df.to_csv(output_file, index=False)
print(f"[OK] Gespeichert als '{output_file}' mit Spalte 'ele'.")