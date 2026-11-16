"""Layanan integrasi baca-saja untuk 13 gugus data penelitian, 3 olah data, dan WebGIS."""
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from services.ai_risk_engine import (
    DATA_DIR,
    OLAH_DATA_DIR,
    RESEARCH_ROOT,
    STORAGE_DIR,
    sanitize_research_text,
)

DATASET_METADATA: Dict[str, Dict[str, str]] = {
    "01_Klimatologi_CHIRPS": {"label": "01. Klimatologi CHIRPS", "domain": "Curah Hujan Satelit"},
    "02_Hidrologi_TMA_BWS": {"label": "02. Hidrologi TMA BWS Sumatera I", "domain": "Hidrometri Sungai"},
    "03_Meteorologi_ARR_Curah_Hujan": {"label": "03. Meteorologi ARR Pos Hujan", "domain": "Penakar Hujan Otomatis"},
    "04_Spasial_Curah_Hujan_BMKG": {"label": "04. Spasial Curah Hujan BMKG", "domain": "Klimatologi Regional"},
    "05_Klimatologi_Reanalysis_ERA5": {"label": "05. Reanalysis ERA5-Land", "domain": "Atmosfer & Lengas Tanah"},
    "06_Spasial_dan_Peta_DAS": {"label": "06. Spasial & Peta DAS Peusangan", "domain": "Topografi & Batas DAS"},
    "07_Peta_Rupa_Bumi_BIG": {"label": "07. Peta Rupa Bumi Indonesia (BIG)", "domain": "Basemap Vektor RBI"},
    "08_Jaringan_DI_Pante_Lhong": {"label": "08. Jaringan Irigasi D.I. Pante Lhong", "domain": "Saluran & Petak Tersier"},
    "09_Pertanian_Peusangan": {"label": "09. Data Pertanian & Kelompok Tani", "domain": "Agrosistem 69 Desa"},
    "10_BPBD_Banjir_Bireuen": {"label": "10. Kejadian Banjir BPBD Bireuen", "domain": "Riwayat Bencana Empiris"},
    "11_Tanaman_Bireuen": {"label": "11. Tanaman Padi & Data Puso", "domain": "Validasi Kerentanan Tanaman"},
    "12_Data_Pendukung_Dokumentasi_Pante_Lhong": {"label": "12. Dokumentasi Geotagged Survei", "domain": "Bukti Lapangan 26 Titik"},
    "13_Pengujian_IoT": {"label": "13. Pengujian Lapangan IoT & LSTM", "domain": "Telemetri Empiris & SQLite"},
    "14_Studi_Literatur": {"label": "14. Studi Literatur & State-of-the-Art", "domain": "Korpus Ilmiah & Sintesis Pustaka"},
}

PLOT_DESCRIPTIONS: Dict[str, str] = {
    "01_eda_seri_waktu_tma.png": "Seri waktu harian TMA Keureuto (2015-2024) & sub-harian Krueng Simpo.",
    "02_perbandingan_prediksi_harian.png": "Komparasi performa model LSTM skala harian (A1-A4).",
    "03_perbandingan_interpolasi_1h.png": "Evaluasi metode interpolasi temporal PCHIP vs Linear & Spline.",
    "04_best_hourly_lstm_result.png": "Hasil evaluasi model LSTM terbaik per jam (C2_Ablation_Units_256_128_Adam_1e-3, t+3 jam).",
    "05_uji_lapangan_iot_zeroshot.png": "Validasi zero-shot pada data uji lapangan IoT DAS Peusangan.",
    "01_ahp_bobot_kriteria.png": "Struktur hirarki bobot global AHP konsolidasi 5 pakar (CR = 0.00000).",
    "02_cropdamx_kurva_kerentanan.png": "Kurva kerentanan logistik CROPDAM-X & validasi Random Forest / Bayesian Ridge.",
    "03_cfai_simulasi_petak_tersier.png": "Distribusi CFAI & luasan terdampak pada 103 petak tersier D.I. Pante Lhong.",
    "04_validasi_historis_puso.png": "Korelasi historis skor CFAI terhadap luas puso Kabupaten Bireuen.",
    "01_optimasi_jumlah_node_pareto.png": "Analisis Pareto efisiensi cakupan hidrologi vs biaya instalasi node IoT.",
    "02_peta_spasial_penempatan_node_dan_era5.png": "Peta penempatan node optimal Tahap II sepanjang koridor 10,439 km.",
    "03_analisis_link_budget_dan_fresnel_lora.png": "Simulasi Link Budget LoRa 915 MHz & clearance Zona Fresnel pada intensitas badai.",
    "04_kalibrasi_dan_simulasi_telemetri_6sensor.png": "Kalibrasi 6 sensor lapangan & verifikasi paket telemetri multi-node.",
    "05_profil_daya_baterai_dan_otonomi_surya.png": "Simulasi otonomi baterai 3S Li-ion + panel surya melewati jendela badai.",
}


def list_all_datasets() -> List[Dict[str, Any]]:
    """Memindai 13 direktori Data/ dan 3 modul Olah Data/ secara baca-saja."""
    catalog: List[Dict[str, Any]] = []
    if DATA_DIR.exists():
        for folder in sorted(DATA_DIR.iterdir()):
            if not folder.is_dir():
                continue
            meta = DATASET_METADATA.get(folder.name, {"label": folder.name, "domain": "Dataset Penelitian"})
            files: List[Dict[str, Any]] = []
            total_size = 0
            for fp in sorted(folder.rglob("*")):
                if fp.is_file():
                    sz = fp.stat().st_size
                    total_size += sz
                    if fp.suffix.lower() in {".csv", ".json", ".geojson", ".md", ".txt", ".kml", ".sqlite"}:
                        rel = str(fp.relative_to(RESEARCH_ROOT)).replace("\\", "/")
                        files.append({
                            "name": fp.name,
                            "rel_path": rel,
                            "ext": fp.suffix.lower().lstrip("."),
                            "size_kb": round(sz / 1024.0, 2),
                            "previewable": fp.suffix.lower() in {".csv", ".json", ".geojson", ".md"},
                        })
            catalog.append({
                "key": folder.name,
                "label": meta["label"],
                "domain": meta["domain"],
                "file_count": len(files),
                "total_mb": round(total_size / (1024.0 * 1024.0), 2),
                "files": files[:40],
            })
    return catalog


def list_chart_artifacts() -> List[Dict[str, Any]]:
    """Mendaftar seluruh grafik PNG hasil eksperimen ilmiah pada 3 modul Olah Data."""
    charts: List[Dict[str, Any]] = []
    if not OLAH_DATA_DIR.exists():
        return charts
    for mod in sorted(OLAH_DATA_DIR.iterdir()):
        out_dir = mod / "outputs"
        if not mod.is_dir() or not out_dir.exists():
            continue
        for png in sorted(out_dir.glob("*.png")):
            rel = str(png.relative_to(RESEARCH_ROOT)).replace("\\", "/")
            charts.append({
                "module": mod.name,
                "filename": png.name,
                "rel_path": rel,
                "description": PLOT_DESCRIPTIONS.get(png.name, f"Visualisasi ilmiah {mod.name}"),
                "size_kb": round(png.stat().st_size / 1024.0, 1),
            })
    return charts


def resolve_safe_research_file(rel_path: str) -> Optional[Path]:
    """Memvalidasi jalur berkas hanya di dalam Data/ atau Olah Data/ secara ketat."""
    if not rel_path or ".." in rel_path or rel_path.startswith("/") or ":" in rel_path:
        return None
    candidate = (RESEARCH_ROOT / rel_path).resolve()
    allowed_roots = (DATA_DIR.resolve(), OLAH_DATA_DIR.resolve())
    for root in allowed_roots:
        try:
            candidate.relative_to(root)
            if candidate.exists() and candidate.is_file():
                return candidate
        except ValueError:
            continue
    return None


def preview_dataset_file(rel_path: str, limit: int = 50) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Membaca pratinjau aman CSV, JSON, GeoJSON, atau Markdown (maksimal 50 baris)."""
    target = resolve_safe_research_file(rel_path)
    if target is None:
        return None, "Berkas tidak ditemukan atau berada di luar direktori dataset yang diizinkan."

    ext = target.suffix.lower()
    if ext == ".csv":
        with open(target, encoding="utf-8-sig", errors="replace") as f:
            reader = csv.reader(f)
            headers = next(reader, [])
            rows = []
            for idx, r in enumerate(reader):
                if idx >= limit:
                    break
                rows.append([sanitize_research_text(c) for c in r])
        return {"type": "csv", "filename": target.name, "headers": headers, "rows": rows}, None

    if ext in {".json", ".geojson"}:
        raw_txt = target.read_text(encoding="utf-8", errors="replace")[:150000]
        return {
            "type": "json",
            "filename": target.name,
            "content": sanitize_research_text(raw_txt[:12000]),
        }, None

    if ext in {".md", ".txt"}:
        raw_txt = target.read_text(encoding="utf-8", errors="replace")[:20000]
        return {
            "type": "markdown",
            "filename": target.name,
            "content": sanitize_research_text(raw_txt),
        }, None

    return None, "Format berkas ini tidak mendukung pratinjau teks."


def load_pante_lhong_layers() -> Dict[str, Any]:
    """Memuat lapisan geospasial D.I. Pante Lhong yang telah dikonversi dari UTM 47N ke WGS84."""
    p = STORAGE_DIR / "pante_lhong_layers.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def load_pante_lhong_sawah() -> List[Dict[str, Any]]:
    """Memuat poligon Petak Sawah CAD asli yang telah dipetakan ke 103 blok CFAI."""
    p = STORAGE_DIR / "pante_lhong_sawah.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return []


def load_pante_lhong_cad_extras() -> Dict[str, Any]:
    """Memuat layer CAD tambahan (pemukiman, kebun, tegalan, jalan, kontur, label)."""
    p = STORAGE_DIR / "pante_lhong_cad_extras.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def load_stage2_topology() -> Dict[str, Any]:
    """Memuat koordinat node optimal Tahap II tersnap ke bangunan irigasi CAD & jalur transmisi GeoJSON."""
    nodes_csv = OLAH_DATA_DIR / "03_IoT_LoRa" / "outputs" / "titik_penempatan_node_optimal.csv"
    geojson_path = OLAH_DATA_DIR / "03_IoT_LoRa" / "outputs" / "penempatan_node_iot_pante_lhong.geojson"

    cad_node_snap: Dict[str, Dict[str, Any]] = {
        "node_hulu": {"lat": 5.115264, "lon": 96.702764, "next_hop_km": 8.228, "cum_km": 0.0},
        "node_hilir": {"lat": 5.187152, "lon": 96.720373, "next_hop_km": 2.539, "cum_km": 8.228},
        "node_gateway": {"lat": 5.208928, "lon": 96.727275, "next_hop_km": 0.0, "cum_km": 10.767},
    }

    nodes: List[Dict[str, Any]] = []
    if nodes_csv.exists():
        with open(nodes_csv, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                nid = row.get("node_id") or ""
                snap = cad_node_snap.get(nid, {})
                nodes.append({
                    "node_id": nid,
                    "name": row.get("nama_resmi"),
                    "kecamatan": row.get("kecamatan"),
                    "lat": float(snap.get("lat", row.get("lat") or 0)),
                    "lon": float(snap.get("lon", row.get("lon") or 0)),
                    "elevation_m": float(row.get("elevasi_mdpl") or 0),
                    "role": row.get("peran_jaringan"),
                    "zona": row.get("zona_irigasi"),
                    "next_hop_km": float(snap.get("next_hop_km", row.get("jarak_hop_berikutnya_km") or 0)),
                    "cum_km": float(snap.get("cum_km", row.get("jarak_kumulatif_koridor_km") or 0)),
                    "pole_m": float(row.get("tiang_sensor_m") or 3.0),
                })

    geojson: Dict[str, Any] = {}
    if geojson_path.exists():
        geojson = json.loads(geojson_path.read_text(encoding="utf-8"))
        for feat in geojson.get("features", []):
            geom = feat.get("geometry") or {}
            props = feat.get("properties") or {}
            gtype = geom.get("type")
            if gtype == "Point":
                nid = str(props.get("node_id") or "")
                if nid in cad_node_snap:
                    geom["coordinates"] = [cad_node_snap[nid]["lon"], cad_node_snap[nid]["lat"]]
            elif gtype == "LineString":
                geom["coordinates"] = [
                    [cad_node_snap["node_hulu"]["lon"], cad_node_snap["node_hulu"]["lat"]],
                    [cad_node_snap["node_hilir"]["lon"], cad_node_snap["node_hilir"]["lat"]],
                    [cad_node_snap["node_gateway"]["lon"], cad_node_snap["node_gateway"]["lat"]],
                ]
    return {"nodes": nodes, "geojson": geojson}


def load_climatology_points() -> List[Dict[str, Any]]:
    """Memuat data klimatologi 6 titik grid BMKG vs ERA5-Land DAS Peusangan."""
    p = DATA_DIR / "04_Spasial_Curah_Hujan_BMKG" / "02_data_penelitian" / "curah_hujan_klimatologi_6_titik_peusangan.csv"
    pts: List[Dict[str, Any]] = []
    if p.exists():
        with open(p, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                pts.append({
                    "point_id": row.get("point_id"),
                    "point_code": row.get("point_code"),
                    "point_name": row.get("point_name"),
                    "lat": float(row.get("lat") or 0),
                    "lon": float(row.get("lon") or 0),
                    "annual_mm": float(row.get("tahunan_peta_mm") or 0),
                    "monthly_avg_mm": float(row.get("rerata_bulanan_mm") or 0),
                    "wettest_mm": float(row.get("bulan_terbasah_mm") or 0),
                    "driest_mm": float(row.get("bulan_terkering_mm") or 0),
                    "months": {
                        m: float(row.get(f"{m}_mm") or 0)
                        for m in [
                            "januari", "februari", "maret", "april", "mei", "juni",
                            "juli", "agustus", "september", "oktober", "nopember", "desember",
                        ]
                    },
                })
    return pts


def load_climatology_comparison() -> List[Dict[str, Any]]:
    """Memuat tabel perbandingan klimatologi bulanan BMKG vs ERA5-Land pada 6 titik."""
    p = DATA_DIR / "04_Spasial_Curah_Hujan_BMKG" / "02_data_penelitian" / "perbandingan_klimatologi_bmkg_vs_era5_6_titik.csv"
    rows: List[Dict[str, Any]] = []
    if p.exists():
        with open(p, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                rows.append(dict(row))
    return rows


def load_survey_points() -> List[Dict[str, Any]]:
    """Memuat 26 titik dokumentasi survei geospasial lapangan D.I. Pante Lhong."""
    p = DATA_DIR / "12_Data_Pendukung_Dokumentasi_Pante_Lhong" / "research_geotagged_survey_points.geojson"
    items: List[Dict[str, Any]] = []
    if p.exists():
        gj = json.loads(p.read_text(encoding="utf-8"))
        for feat in gj.get("features", []):
            geom = feat.get("geometry") or {}
            coords = geom.get("coordinates") or [0, 0]
            props = feat.get("properties") or {}
            items.append({
                "file_id": props.get("file_id"),
                "filename": props.get("filename"),
                "media_type": props.get("media_type"),
                "captured_at": props.get("capture_datetime_wib"),
                "altitude_m": props.get("altitude_m"),
                "lat": float(coords[1]),
                "lon": float(coords[0]),
            })
    return items


def load_station_metadata() -> Dict[str, List[Dict[str, Any]]]:
    """Memuat metadata resmi stasiun AWLR dan ARR referensi."""
    awlr_csv = DATA_DIR / "02_Hidrologi_TMA_BWS" / "01_data_terstruktur" / "metadata_stasiun_awlr_ws_pase_peusangan.csv"
    arr_csv = DATA_DIR / "03_Meteorologi_ARR_Curah_Hujan" / "01_data_terstruktur" / "metadata_stasiun_arr_keureuto.csv"
    awlr: List[Dict[str, Any]] = []
    arr: List[Dict[str, Any]] = []
    if awlr_csv.exists():
        with open(awlr_csv, encoding="utf-8-sig") as f:
            awlr = [dict(r) for r in csv.DictReader(f)]
    if arr_csv.exists():
        with open(arr_csv, encoding="utf-8-sig") as f:
            arr = [dict(r) for r in csv.DictReader(f)]
    return {"awlr": awlr, "arr": arr}


def load_canal_network_graph() -> Dict[str, Any]:
    """Memuat graf topologi jaringan irigasi D.I. Pante Lhong."""
    p = DATA_DIR / "08_Jaringan_DI_Pante_Lhong" / "outputs" / "data_graf_jaringan.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def load_rice_variety_matrix() -> Dict[str, List[Dict[str, Any]]]:
    """Memuat matriks varietas padi dominan & validasi kejadian puso historis."""
    v_csv = DATA_DIR / "11_Tanaman_Bireuen" / "02_data_penelitian" / "matriks_varietas_padi_dan_kerentanan_penelitian.csv"
    p_csv = DATA_DIR / "11_Tanaman_Bireuen" / "02_data_penelitian" / "data_puso_validasi_risiko_penelitian.csv"
    varieties: List[Dict[str, Any]] = []
    puso: List[Dict[str, Any]] = []
    if v_csv.exists():
        with open(v_csv, encoding="utf-8-sig") as f:
            varieties = [dict(r) for r in csv.DictReader(f)]
    if p_csv.exists():
        with open(p_csv, encoding="utf-8-sig") as f:
            puso = [dict(r) for r in csv.DictReader(f)]
    return {"varieties": varieties, "puso": puso}
