import os
import sys
import threading
import subprocess
import xml.etree.ElementTree as ET
import pandas as pd
import requests
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECTS_ROOT = os.path.join(BASE_DIR, "projekte")
os.makedirs(PROJECTS_ROOT, exist_ok=True)


class BodenanalyseGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Bodenanalyse & Mikro-Topografie Studio")
        self.geometry("980x780")
        self.minsize(850, 650)

        # Style
        self.style = ttk.Style(self)
        self.style.theme_use("clam")

        self.current_project_dir = None
        self.preview_image_ref = None

        self._build_project_header()
        self._build_notebook()
        self.refresh_project_list()

    # -------------------------------------------------------------
    # 1. PROJEKTVERWALTUNG
    # -------------------------------------------------------------
    def _build_project_header(self):
        frame = ttk.LabelFrame(self, text=" 1. Projektverwaltung ", padding=10)
        frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(frame, text="Aktives Projekt:").pack(side=tk.LEFT, padx=5)

        self.cb_projects = ttk.Combobox(frame, state="readonly", width=30)
        self.cb_projects.pack(side=tk.LEFT, padx=5)
        self.cb_projects.bind("<<ComboboxSelected>>", self.on_project_selected)

        btn_new = ttk.Button(frame, text="Neues Projekt erstellen", command=self.create_new_project)
        btn_new.pack(side=tk.LEFT, padx=5)

        btn_open_folder = ttk.Button(frame, text="Projektordner im Explorer öffnen", command=self.open_current_folder)
        btn_open_folder.pack(side=tk.LEFT, padx=5)

    def refresh_project_list(self):
        projects = [d for d in os.listdir(PROJECTS_ROOT) if os.path.isdir(os.path.join(PROJECTS_ROOT, d))]
        projects.sort()
        self.cb_projects["values"] = projects
        if projects:
            self.cb_projects.current(0)
            self.on_project_selected()
        else:
            self.cb_projects.set("")
            self.current_project_dir = None

    def create_new_project(self):
        dialog = tk.Toplevel(self)
        dialog.title("Neues Projekt anlegen")
        dialog.geometry("350x130")
        dialog.resizable(False, False)
        dialog.transient(self)

        ttk.Label(dialog, text="Projektname (z.B. Feld_Sued_2026):").pack(pady=10)
        entry = ttk.Entry(dialog, width=35)
        entry.pack(pady=5)
        entry.focus()

        def confirm():
            name = entry.get().strip().replace(" ", "_")
            if not name:
                return
            proj_path = os.path.join(PROJECTS_ROOT, name)
            if os.path.exists(proj_path):
                messagebox.showerror("Fehler", "Ein Projekt mit diesem Namen existiert bereits!")
                return
            os.makedirs(proj_path, exist_ok=True)
            dialog.destroy()
            self.refresh_project_list()
            self.cb_projects.set(name)
            self.on_project_selected()

        ttk.Button(dialog, text="Erstellen", command=confirm).pack(pady=10)

    def on_project_selected(self, event=None):
        selected = self.cb_projects.get()
        if selected:
            self.current_project_dir = os.path.join(PROJECTS_ROOT, selected)
            self.log(f"[PROJEKT] Gewechselt zu: {selected} ({self.current_project_dir})")
            
            # Automatisch vorhandene CSV für Tab 2 vorauswählen
            ele_csv = os.path.join(self.current_project_dir, "messpunkte_mit_hoehen.csv")
            if os.path.exists(ele_csv):
                self.entry_analysis_input.delete(0, tk.END)
                self.entry_analysis_input.insert(0, ele_csv)

    def open_current_folder(self):
        if self.current_project_dir and os.path.exists(self.current_project_dir):
            os.startfile(self.current_project_dir)
        else:
            messagebox.showwarning("Hinweis", "Bitte zuerst ein Projekt auswählen!")

    # -------------------------------------------------------------
    # 2. TABS: HÖHEN-API & ANALYSE
    # -------------------------------------------------------------
    def _build_notebook(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Tab 1: Elevation Fetcher
        tab_ele = ttk.Frame(notebook, padding=10)
        notebook.add(tab_ele, text="1. Höhendaten abrufen (API)")
        self._build_elevation_tab(tab_ele)

        # Tab 2: Relief-Analyse
        tab_analysis = ttk.Frame(notebook, padding=10)
        notebook.add(tab_analysis, text="2. Heatmap & Relief-Analyse")
        self._build_analysis_tab(tab_analysis)

        # Gemeinsame Konsole / Log-Ausgabe unten
        log_frame = ttk.LabelFrame(self, text=" Konsolenausgabe / Status ", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=False, padx=10, pady=5)
        
        self.log_text = tk.Text(log_frame, height=8, wrap=tk.WORD, bg="#1e1e1e", fg="#ffffff", font=("Consolas", 9))
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)

    def log(self, message):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)

    # -------------------------------------------------------------
    # TAB 1: ELEVATION FETCHER
    # -------------------------------------------------------------
    def _build_elevation_tab(self, parent):
        box = ttk.LabelFrame(parent, text="Quelldatei aus Google Earth wählen", padding=10)
        box.pack(fill=tk.X, pady=5)

        ttk.Label(box, text="KML- oder CSV-Datei ohne Höhen:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.entry_raw_input = ttk.Entry(box, width=70)
        self.entry_raw_input.grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(box, text="Durchsuchen...", command=self.browse_raw_file).grid(row=0, column=2, padx=5, pady=5)

        self.btn_fetch_ele = ttk.Button(parent, text="▶ Höhendaten via Open-Meteo API abrufen", command=self.start_elevation_fetch)
        self.btn_fetch_ele.pack(pady=15)

        self.lbl_ele_status = ttk.Label(parent, text="Bereit.", font=("Arial", 9, "italic"))
        self.lbl_ele_status.pack()

    def browse_raw_file(self):
        path = filedialog.askopenfilename(filetypes=[("Google Earth / Tabellen", "*.kml;*.csv;*.txt"), ("Alle", "*.*")])
        if path:
            self.entry_raw_input.delete(0, tk.END)
            self.entry_raw_input.insert(0, path)

    def start_elevation_fetch(self):
        if not self.current_project_dir:
            messagebox.showerror("Fehler", "Bitte erst ein Projekt erstellen oder auswählen!")
            return
        input_path = self.entry_raw_input.get().strip()
        if not input_path or not os.path.exists(input_path):
            messagebox.showerror("Fehler", "Bitte eine gültige KML- oder CSV-Datei auswählen!")
            return

        self.btn_fetch_ele.config(state=tk.DISABLED)
        threading.Thread(target=self._run_fetch_elevation_worker, args=(input_path,), daemon=True).start()

    def _run_fetch_elevation_worker(self, input_path):
        try:
            self.log(f"[API] Lese Koordinaten aus: {input_path}")
            lats, lons = [], []

            if input_path.lower().endswith(".kml"):
                tree = ET.parse(input_path)
                root = tree.getroot()
                coord_text = ""
                for elem in root.iter():
                    if elem.tag.endswith("coordinates"):
                        coord_text += " " + (elem.text or "")
                
                raw_coords = coord_text.strip().split()
                for c in raw_coords:
                    parts = c.split(",")
                    if len(parts) >= 2:
                        lons.append(float(parts[0]))
                        lats.append(float(parts[1]))
            else:
                df = pd.read_csv(input_path, sep=r"\s+|\t|,", engine="python")
                df.columns = [c.strip().lower() for c in df.columns]
                lat_col = [c for c in df.columns if "lat" in c or "y" in c][0]
                lon_col = [c for c in df.columns if "lon" in c or "x" in c][0]
                lats = df[lat_col].astype(float).tolist()
                lons = df[lon_col].astype(float).tolist()

            total_pts = len(lats)
            self.log(f"[API] {total_pts} Koordinatenpaare geladen. Starte Online-Abfrage...")

            elevations = []
            chunk_size = 1000
            for i in range(0, total_pts, chunk_size):
                chunk_lats = ",".join(map(str, lats[i:i + chunk_size]))
                chunk_lons = ",".join(map(str, lons[i:i + chunk_size]))
                url = f"https://api.open-meteo.com/v1/elevation?latitude={chunk_lats}&longitude={chunk_lons}"
                
                resp = requests.get(url, timeout=30)
                if resp.status_code != 200:
                    raise RuntimeError(f"API Fehler ({resp.status_code}): {resp.text}")
                elevations.extend(resp.json().get("elevation", []))
                self.log(f"[API] Fortschritt: {min(i + chunk_size, total_pts)}/{total_pts} Punkte geladen")

            # DataFrame zusammenbauen und im Projektordner ablegen
            out_df = pd.DataFrame({"latitude": lats, "longitude": lons, "ele": elevations})
            out_file = os.path.join(self.current_project_dir, "messpunkte_mit_hoehen.csv")
            out_df.to_csv(out_file, index=False)

            self.log(f"[OK] Höhen erfolgreich ermittelt! Gespeichert in:\n     {out_file}")
            
            # Automatisch in Tab 2 übernehmen
            self.entry_analysis_input.delete(0, tk.END)
            self.entry_analysis_input.insert(0, out_file)
            messagebox.showinfo("Erfolg", f"{total_pts} Höhenpunkte erfolgreich im Projektordner gespeichert!")

        except Exception as e:
            self.log(f"[FEHLER] Elevation API: {str(e)}")
            messagebox.showerror("Fehler bei Abfrage", str(e))
        finally:
            self.btn_fetch_ele.config(state=tk.NORMAL)

    # -------------------------------------------------------------
    # TAB 2: RELIEF-ANALYSE
    # -------------------------------------------------------------
    def _build_analysis_tab(self, parent):
        # Eingabedatei
        frame_input = ttk.LabelFrame(parent, text="Eingabedaten", padding=8)
        frame_input.pack(fill=tk.X, pady=5)
        
        ttk.Label(frame_input, text="CSV mit Höhen (ele):").grid(row=0, column=0, sticky=tk.W)
        self.entry_analysis_input = ttk.Entry(frame_input, width=70)
        self.entry_analysis_input.grid(row=0, column=1, padx=5)
        ttk.Button(frame_input, text="Durchsuchen...", command=self.browse_analysis_file).grid(row=0, column=2)

        # Parameter-Grid
        frame_params = ttk.LabelFrame(parent, text="Analyse-Parameter", padding=8)
        frame_params.pack(fill=tk.X, pady=5)

        ttk.Label(frame_params, text="Trendmodell:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=3)
        self.cb_trend = ttk.Combobox(frame_params, values=["poly2", "linear"], state="readonly", width=12)
        self.cb_trend.set("poly2")
        self.cb_trend.grid(row=0, column=1, sticky=tk.W, padx=5, pady=3)

        ttk.Label(frame_params, text="Auflösung (m):").grid(row=0, column=2, sticky=tk.W, padx=5, pady=3)
        self.entry_res = ttk.Entry(frame_params, width=10)
        self.entry_res.insert(0, "0.5")
        self.entry_res.grid(row=0, column=3, sticky=tk.W, padx=5, pady=3)

        ttk.Label(frame_params, text="Glättung (Sigma):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=3)
        self.entry_sigma = ttk.Entry(frame_params, width=10)
        self.entry_sigma.insert(0, "1.0")
        self.entry_sigma.grid(row=1, column=1, sticky=tk.W, padx=5, pady=3)

        ttk.Label(frame_params, text="Farbskala:").grid(row=1, column=2, sticky=tk.W, padx=5, pady=3)
        self.cb_cmap = ttk.Combobox(frame_params, values=["RdBu_r", "coolwarm", "bwr", "viridis"], state="readonly", width=12)
        self.cb_cmap.set("RdBu_r")
        self.cb_cmap.grid(row=1, column=3, sticky=tk.W, padx=5, pady=3)

        # Start Button
        self.btn_run_analysis = ttk.Button(parent, text="▶ Relief-Heatmap generieren", command=self.start_analysis)
        self.btn_run_analysis.pack(pady=8)

        # Bildvorschau-Container
        self.preview_frame = ttk.LabelFrame(parent, text=" Heatmap Vorschau ", padding=5)
        self.preview_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.lbl_preview = ttk.Label(self.preview_frame, text="Noch keine Analyse ausgeführt.")
        self.lbl_preview.pack(expand=True)

    def browse_analysis_file(self):
        path = filedialog.askopenfilename(filetypes=[("CSV-Dateien", "*.csv"), ("Text-Dateien", "*.txt"), ("Alle", "*.*")])
        if path:
            self.entry_analysis_input.delete(0, tk.END)
            self.entry_analysis_input.insert(0, path)

    def start_analysis(self):
        if not self.current_project_dir:
            messagebox.showerror("Fehler", "Bitte erst ein Projekt auswählen!")
            return
        
        in_file = self.entry_analysis_input.get().strip()
        if not in_file or not os.path.exists(in_file):
            messagebox.showerror("Fehler", "Bitte eine gültige Eingabedatei angeben!")
            return

        out_img = os.path.join(self.current_project_dir, "heatmap_anomalies.png")
        trend = self.cb_trend.get()
        res = self.entry_res.get().strip()
        sigma = self.entry_sigma.get().strip()
        cmap = self.cb_cmap.get()

        self.btn_run_analysis.config(state=tk.DISABLED)
        threading.Thread(
            target=self._run_analysis_worker,
            args=(in_file, out_img, trend, res, sigma, cmap),
            daemon=True
        ).start()

    def _run_analysis_worker(self, in_file, out_img, trend, res, sigma, cmap):
        try:
            self.log(f"[ANALYSE] Starte microtopography.py...")
            cmd = [
                sys.executable,
                os.path.join(BASE_DIR, "microtopography.py"),
                "-i", in_file,
                "-t", trend,
                "-r", res,
                "-s", sigma,
                "-c", cmap,
                "-u", "cm",
                "-o", out_img
            ]

            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in iter(process.stdout.readline, ''):
                if line:
                    self.log(line.strip())
            process.communicate()

            if process.returncode == 0 and os.path.exists(out_img):
                self.log(f"[OK] Heatmap erfolgreich erzeugt: {out_img}")
                self._update_preview(out_img)
            else:
                self.log(f"[FEHLER] Analyse fehlgeschlagen (Exit-Code {process.returncode})")

        except Exception as e:
            self.log(f"[FEHLER] Beim Ausführen: {str(e)}")
        finally:
            self.btn_run_analysis.config(state=tk.NORMAL)

    def _update_preview(self, img_path):
        try:
            img = Image.open(img_path)
            # Auf Vorschaugröße skalieren (proportional)
            img.thumbnail((450, 320))
            self.preview_image_ref = ImageTk.PhotoImage(img)
            self.lbl_preview.config(image=self.preview_image_ref, text="")
        except Exception as e:
            self.log(f"[WARNUNG] Vorschau konnte nicht geladen werden: {e}")


if __name__ == "__main__":
    app = BodenanalyseGUI()
    app.mainloop()