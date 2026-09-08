import os
import sys
import threading
import subprocess
import xml.etree.ElementTree as ET
import pandas as pd
import requests
import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image

# Grundeinstellungen: Modernes Dark Theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECTS_ROOT = os.path.join(BASE_DIR, "projekte")
os.makedirs(PROJECTS_ROOT, exist_ok=True)


class ModernBodenanalyseApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Bodenanalyse & Mikro-Topografie Studio")
        self.geometry("1100x820")
        self.minsize(950, 700)

        self.current_project_dir = None
        self.preview_image_ref = None

        # 2-Spalten-Layout: Linke Sidebar (Projekte) + Hauptbereich (Tabs & Konsole)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_main_area()
        self.refresh_project_list()

    # -------------------------------------------------------------
    # 1. SIDEBAR (Projektverwaltung & Optionen)
    # -------------------------------------------------------------
    def _build_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=240, corner_radius=0)
        self.sidebar.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=0, pady=0)
        self.sidebar.grid_rowconfigure(6, weight=1)

        # App-Titel
        lbl_title = ctk.CTkLabel(self.sidebar, text="GEO-ANOMALY", font=ctk.CTkFont(size=20, weight="bold"))
        lbl_title.grid(row=0, column=0, padx=20, pady=(25, 5), sticky="w")
        
        lbl_sub = ctk.CTkLabel(self.sidebar, text="Mikro-Relief Scanner", font=ctk.CTkFont(size=12), text_color="gray70")
        lbl_sub.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="w")

        # Projekt-Sektion
        lbl_proj = ctk.CTkLabel(self.sidebar, text="AKTIVES PROJEKT", font=ctk.CTkFont(size=11, weight="bold"), text_color="gray60")
        lbl_proj.grid(row=2, column=0, padx=20, pady=(10, 5), sticky="w")

        self.opt_projects = ctk.CTkOptionMenu(self.sidebar, values=["Kein Projekt"], command=self.on_project_selected)
        self.opt_projects.grid(row=3, column=0, padx=20, pady=5, sticky="ew")

        btn_new_proj = ctk.CTkButton(self.sidebar, text="+ Neues Projekt", command=self.create_new_project)
        btn_new_proj.grid(row=4, column=0, padx=20, pady=8, sticky="ew")

        btn_open_folder = ctk.CTkButton(self.sidebar, text="Ordner im Explorer", fg_color="transparent", border_width=1, command=self.open_current_folder)
        btn_open_folder.grid(row=5, column=0, padx=20, pady=5, sticky="ew")

        # Theme Switcher ganz unten
        lbl_mode = ctk.CTkLabel(self.sidebar, text="Farbschema:", font=ctk.CTkFont(size=11), text_color="gray60")
        lbl_mode.grid(row=7, column=0, padx=20, pady=(10, 0), sticky="w")
        self.opt_mode = ctk.CTkOptionMenu(self.sidebar, values=["Dark", "Light"], command=ctk.set_appearance_mode)
        self.opt_mode.grid(row=8, column=0, padx=20, pady=(5, 20), sticky="ew")

    # -------------------------------------------------------------
    # 2. HAUPTBEREICH (Tabs & Live-Konsole)
    # -------------------------------------------------------------
    def _build_main_area(self):
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=15)
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(0, weight=1)

        # Tabview
        self.tabs = ctk.CTkTabview(main_frame, corner_radius=10)
        self.tabs.grid(row=0, column=0, sticky="nsew")

        tab_ele = self.tabs.add("1. Höhendaten (API)")
        tab_ana = self.tabs.add("2. Relief-Heatmap")

        self._build_elevation_view(tab_ele)
        self._build_analysis_view(tab_ana)

        # Integrierte Status-Konsole unten
        console_frame = ctk.CTkFrame(self, corner_radius=10)
        console_frame.grid(row=1, column=1, sticky="ew", padx=20, pady=(0, 15))
        console_frame.grid_columnconfigure(0, weight=1)

        lbl_console = ctk.CTkLabel(console_frame, text="System-Status & Protokoll", font=ctk.CTkFont(size=11, weight="bold"), text_color="gray60")
        lbl_console.grid(row=0, column=0, padx=15, pady=(8, 2), sticky="w")

        self.txt_console = ctk.CTkTextbox(console_frame, height=110, font=ctk.CTkFont(family="Consolas", size=11), corner_radius=6)
        self.txt_console.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="ew")

    def log(self, text):
        self.txt_console.insert("end", text + "\n")
        self.txt_console.see("end")

    # -------------------------------------------------------------
    # TAB 1: ELEVATION FETCHER
    # -------------------------------------------------------------
    def _build_elevation_view(self, parent):
        parent.grid_columnconfigure(0, weight=1)

        card = ctk.CTkFrame(parent, corner_radius=10)
        card.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        card.grid_columnconfigure(0, weight=1)

        lbl = ctk.CTkLabel(card, text="Quelldatei aus Google Earth Pro (KML oder CSV)", font=ctk.CTkFont(size=13, weight="bold"))
        lbl.grid(row=0, column=0, columnspan=2, padx=15, pady=(15, 8), sticky="w")

        self.entry_raw = ctk.CTkEntry(card, placeholder_text="Pfad zu exportierter .kml oder Roh-CSV...")
        self.entry_raw.grid(row=1, column=0, padx=(15, 10), pady=10, sticky="ew")

        btn_browse = ctk.CTkButton(card, text="Durchsuchen", width=120, command=self.browse_raw_file)
        btn_browse.grid(row=1, column=1, padx=(0, 15), pady=10)

        # Aktions-Button
        self.btn_fetch = ctk.CTkButton(
            parent,
            text="▶ Höhendaten via Open-Meteo abrufen & abspeichern",
            height=40,
            font=ctk.CTkFont(weight="bold"),
            command=self.start_fetch_elevation
        )
        self.btn_fetch.grid(row=1, column=0, padx=10, pady=15, sticky="ew")

        info_box = ctk.CTkFrame(parent, fg_color=("gray85", "gray17"), corner_radius=8)
        info_box.grid(row=2, column=0, sticky="ew", padx=10, pady=10)
        info_text = (
            "Hinweis: Wenn ein Pfad in Google Earth Pro gezeichnet wird, speichert Google keine Geländehöhen.\n"
            "Dieses Modul extrahiert die Breiten- und Längengrade und holt die exakten Höhendaten\n"
            "vollautomatisch über die Open-Meteo API in Chunks ab."
        )
        ctk.CTkLabel(info_box, text=info_text, justify="left", font=ctk.CTkFont(size=12), text_color="gray70").pack(padx=15, pady=10, anchor="w")

    def browse_raw_file(self):
        file = filedialog.askopenfilename(filetypes=[("Google Earth / Daten", "*.kml;*.csv;*.txt"), ("Alle", "*.*")])
        if file:
            self.entry_raw.delete(0, "end")
            self.entry_raw.insert(0, file)

    def start_fetch_elevation(self):
        if not self.current_project_dir:
            messagebox.showerror("Fehler", "Bitte wähle zuerst ein Projekt aus!")
            return
        input_path = self.entry_raw.get().strip()
        if not input_path or not os.path.exists(input_path):
            messagebox.showerror("Fehler", "Gültige KML- oder CSV-Datei auswählen!")
            return

        self.btn_fetch.configure(state="disabled")
        threading.Thread(target=self._worker_fetch_elevation, args=(input_path,), daemon=True).start()

    def _worker_fetch_elevation(self, input_path):
        try:
            self.log(f"[INFO] Lese Koordinaten aus: {os.path.basename(input_path)}")
            lats, lons = [], []

            if input_path.lower().endswith(".kml"):
                tree = ET.parse(input_path)
                root = tree.getroot()
                coord_text = ""
                for elem in root.iter():
                    if elem.tag.endswith("coordinates"):
                        coord_text += " " + (elem.text or "")
                
                raw = coord_text.strip().split()
                for c in raw:
                    parts = c.split(",")
                    if len(parts) >= 2:
                        lons.append(float(parts[0]))
                        lats.append(float(parts[1]))
            else:
                df = pd.read_csv(input_path, sep=r"\s+|\t|,", engine="python")
                df.columns = [c.strip().lower() for c in df.columns]
                lat_c = [c for c in df.columns if "lat" in c or "y" in c][0]
                lon_c = [c for c in df.columns if "lon" in c or "x" in c][0]
                lats = df[lat_c].astype(float).tolist()
                lons = df[lon_c].astype(float).tolist()

            total = len(lats)
            self.log(f"[API] {total} Stützpunkte gefunden. Starte Abfrage...")

            elevations = []
            chunk_size = 1000
            for i in range(0, total, chunk_size):
                chunk_lats = ",".join(map(str, lats[i:i + chunk_size]))
                chunk_lons = ",".join(map(str, lons[i:i + chunk_size]))
                url = f"https://api.open-meteo.com/v1/elevation?latitude={chunk_lats}&longitude={chunk_lons}"
                res = requests.get(url, timeout=30)
                if res.status_code != 200:
                    raise RuntimeError(f"HTTP {res.status_code}: {res.text}")
                elevations.extend(res.json().get("elevation", []))
                self.log(f"[API] Fortschritt: {min(i + chunk_size, total)}/{total} Punkte")

            out_csv = os.path.join(self.current_project_dir, "messpunkte_mit_hoehen.csv")
            pd.DataFrame({"latitude": lats, "longitude": lons, "ele": elevations}).to_csv(out_csv, index=False)

            self.log(f"[OK] Gespeichert: {out_csv}")
            self.entry_ana_input.delete(0, "end")
            self.entry_ana_input.insert(0, out_csv)
            self.tabs.set("2. Relief-Heatmap")
            messagebox.showinfo("Erfolg", f"{total} Messpunkte mit Höhen versehen!")

        except Exception as e:
            self.log(f"[FEHLER] Elevation API: {e}")
            messagebox.showerror("Fehler", str(e))
        finally:
            self.btn_fetch.configure(state="normal")

    # -------------------------------------------------------------
    # TAB 2: HEATMAP-ANALYSE
    # -------------------------------------------------------------
    def _build_analysis_view(self, parent):
        parent.grid_columnconfigure(0, weight=3)
        parent.grid_columnconfigure(1, weight=4)
        parent.grid_rowconfigure(1, weight=1)

        # Linke Seite: Parameter-Box
        params_card = ctk.CTkFrame(parent, corner_radius=10)
        params_card.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=10, pady=10)
        params_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(params_card, text="Konfiguration", font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, columnspan=2, padx=15, pady=(15, 10), sticky="w")

        ctk.CTkLabel(params_card, text="Eingabedatei:").grid(row=1, column=0, padx=15, pady=5, sticky="w")
        self.entry_ana_input = ctk.CTkEntry(params_card, placeholder_text="Pfad zu messpunkte_mit_hoehen.csv")
        self.entry_ana_input.grid(row=2, column=0, columnspan=2, padx=15, pady=(0, 10), sticky="ew")

        ctk.CTkLabel(params_card, text="Trend-Algorithmus:").grid(row=3, column=0, padx=15, pady=5, sticky="w")
        self.opt_trend = ctk.CTkOptionMenu(params_card, values=["poly2", "linear"])
        self.opt_trend.grid(row=3, column=1, padx=15, pady=5, sticky="ew")

        ctk.CTkLabel(params_card, text="Rasterweite (m):").grid(row=4, column=0, padx=15, pady=5, sticky="w")
        self.entry_res = ctk.CTkEntry(params_card)
        self.entry_res.insert(0, "0.5")
        self.entry_res.grid(row=4, column=1, padx=15, pady=5, sticky="ew")

        ctk.CTkLabel(params_card, text="Glättung (Sigma):").grid(row=5, column=0, padx=15, pady=5, sticky="w")
        self.entry_sigma = ctk.CTkEntry(params_card)
        self.entry_sigma.insert(0, "1.0")
        self.entry_sigma.grid(row=5, column=1, padx=15, pady=5, sticky="ew")

        ctk.CTkLabel(params_card, text="Farbskala:").grid(row=6, column=0, padx=15, pady=5, sticky="w")
        self.opt_cmap = ctk.CTkOptionMenu(params_card, values=["RdBu_r", "coolwarm", "viridis", "bwr"])
        self.opt_cmap.grid(row=6, column=1, padx=15, pady=5, sticky="ew")

        self.btn_run = ctk.CTkButton(params_card, text="▶ Heatmap generieren", height=38, font=ctk.CTkFont(weight="bold"), command=self.start_analysis)
        self.btn_run.grid(row=7, column=0, columnspan=2, padx=15, pady=(20, 15), sticky="ew")

        # Rechte Seite: Bild-Vorschau
        self.preview_card = ctk.CTkFrame(parent, corner_radius=10)
        self.preview_card.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=10, pady=10)
        self.preview_card.grid_rowconfigure(1, weight=1)
        self.preview_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self.preview_card, text="Heatmap-Vorschau", font=ctk.CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=15, pady=(15, 5), sticky="w")
        
        self.lbl_preview = ctk.CTkLabel(self.preview_card, text="Noch keine Heatmap berechnet.", text_color="gray60")
        self.lbl_preview.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

    def start_analysis(self):
        if not self.current_project_dir:
            messagebox.showerror("Fehler", "Bitte zuerst ein Projekt auswählen!")
            return
        in_file = self.entry_ana_input.get().strip()
        if not in_file or not os.path.exists(in_file):
            messagebox.showerror("Fehler", "Bitte gültige CSV-Eingabedatei auswählen!")
            return

        out_img = os.path.join(self.current_project_dir, "heatmap_anomalies.png")
        trend = self.opt_trend.get()
        res = self.entry_res.get().strip()
        sigma = self.entry_sigma.get().strip()
        cmap = self.opt_cmap.get()

        self.btn_run.configure(state="disabled")
        threading.Thread(target=self._worker_analysis, args=(in_file, out_img, trend, res, sigma, cmap), daemon=True).start()

    def _worker_analysis(self, in_file, out_img, trend, res, sigma, cmap):
        try:
            self.log("[ANALYSE] Starte microtopography.py...")
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
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in iter(p.stdout.readline, ''):
                if line:
                    self.log(line.strip())
            p.communicate()

            if p.returncode == 0 and os.path.exists(out_img):
                self.log(f"[OK] Fertig: {out_img}")
                self._update_preview(out_img)
            else:
                self.log(f"[FEHLER] Exit-Code {p.returncode}")
        except Exception as e:
            self.log(f"[FEHLER] {e}")
        finally:
            self.btn_run.configure(state="normal")

    def _update_preview(self, img_path):
        try:
            pil_img = Image.open(img_path)
            # Auf Anzeigebereich skalieren
            target_w, target_h = 440, 360
            pil_img.thumbnail((target_w, target_h), Image.Resampling.LANCZOS)
            
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=pil_img.size)
            self.lbl_preview.configure(image=ctk_img, text="")
        except Exception as e:
            self.log(f"[WARNUNG] Bildanzeige: {e}")

    # -------------------------------------------------------------
    # PROJEKT-LOGIK
    # -------------------------------------------------------------
    def refresh_project_list(self):
        projects = [d for d in os.listdir(PROJECTS_ROOT) if os.path.isdir(os.path.join(PROJECTS_ROOT, d))]
        projects.sort()
        if projects:
            self.opt_projects.configure(values=projects)
            self.opt_projects.set(projects[0])
            self.on_project_selected(projects[0])
        else:
            self.opt_projects.configure(values=["Kein Projekt vorhanden"])
            self.opt_projects.set("Kein Projekt vorhanden")
            self.current_project_dir = None

    def on_project_selected(self, choice):
        if choice and choice != "Kein Projekt vorhanden":
            self.current_project_dir = os.path.join(PROJECTS_ROOT, choice)
            self.log(f"[PROJEKT] Gewechselt zu: {choice}")
            auto_csv = os.path.join(self.current_project_dir, "messpunkte_mit_hoehen.csv")
            if os.path.exists(auto_csv):
                self.entry_ana_input.delete(0, "end")
                self.entry_ana_input.insert(0, auto_csv)

    def create_new_project(self):
        dialog = ctk.CTkInputDialog(text="Name des neuen Projekts (z. B. Scan_Feld_Nord):", title="Neues Projekt")
        name = dialog.get_input()
        if name:
            clean_name = name.strip().replace(" ", "_")
            path = os.path.join(PROJECTS_ROOT, clean_name)
            if os.path.exists(path):
                messagebox.showerror("Fehler", "Projekt existiert bereits!")
                return
            os.makedirs(path, exist_ok=True)
            self.refresh_project_list()
            self.opt_projects.set(clean_name)
            self.on_project_selected(clean_name)

    def open_current_folder(self):
        if self.current_project_dir and os.path.exists(self.current_project_dir):
            os.startfile(self.current_project_dir)
        else:
            messagebox.showwarning("Hinweis", "Kein aktives Projekt ausgewählt!")


if __name__ == "__main__":
    app = ModernBodenanalyseApp()
    app.mainloop()