"""Synthetic sample dataset generator for PEUSAGA public repository reproducibility.

Generates anonymized, synthetic datasets with schemas matching the production
research pipeline so reviewers can execute the PEUSAGA web application and
analytical notebooks without exposing raw agency data or PII.
"""
import csv
import json
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SAMPLE_DIR = BASE_DIR / "data" / "sample"
STORAGE_DIR = BASE_DIR / "peusaga_app" / "storage"


def generate_tma_hidrologi(seed: int = 42, hours: int = 720) -> Path:
    """Generate synthetic hourly water level (TMA) and rainfall series (30 days)."""
    rng = random.Random(seed)
    out_path = SAMPLE_DIR / "sample_tma_hidrologi.csv"
    start = datetime(2025, 11, 1, 0, 0, 0)

    tma_hulu = 68.0
    tma_hilir = 54.0
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp_wib",
            "station_id",
            "rainfall_mm_h",
            "tma_hulu_cm",
            "tma_hilir_cm",
            "discharge_m3_s",
        ])
        for h in range(hours):
            ts = start + timedelta(hours=h)
            # Simulate two storm pulses during the 30-day window
            storm_a = 18.0 * math.exp(-((h - 180) ** 2) / (2 * 8.0 ** 2))
            storm_b = 26.0 * math.exp(-((h - 520) ** 2) / (2 * 10.0 ** 2))
            rain = max(0.0, storm_a + storm_b + (rng.gauss(0.8, 1.2) if rng.random() < 0.15 else 0.0))

            tma_hulu = max(42.0, 0.92 * tma_hulu + 0.08 * 65.0 + 1.45 * rain + rng.gauss(0.0, 1.1))
            tma_hilir = max(35.0, 0.90 * tma_hilir + 0.10 * 52.0 + 0.85 * (tma_hulu - 65.0) * 0.15 + rng.gauss(0.0, 0.9))
            discharge = round(0.042 * (tma_hulu ** 1.35), 2)

            writer.writerow([
                ts.strftime("%Y-%m-%d %H:%M:%S"),
                "STATION_SAMPLE_01",
                round(rain, 2),
                round(tma_hulu, 2),
                round(tma_hilir, 2),
                discharge,
            ])
    return out_path


def generate_iot_telemetry(seed: int = 42, records_per_node: int = 120) -> Path:
    """Generate synthetic 3-node LoRaWAN IoT telemetry records."""
    rng = random.Random(seed + 1)
    out_path = SAMPLE_DIR / "sample_telemetri_iot.csv"
    start = datetime(2025, 11, 20, 0, 0, 0)
    nodes = [
        ("node_hulu", "ZONE_1_UPSTREAM", 118.0),
        ("node_hilir", "ZONE_2_MIDSTREAM", 96.0),
        ("node_gateway", "ZONE_3_DOWNSTREAM", 84.0),
    ]

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "recorded_at",
            "node_id",
            "zone_code",
            "water_level_cm",
            "rainfall_mm",
            "soil_moisture_pct",
            "water_temp_c",
            "air_temp_c",
            "air_humidity_pct",
            "battery_v",
            "battery_soc_pct",
            "rssi_dbm",
            "snr_db",
        ])
        for i in range(records_per_node):
            ts = start + timedelta(minutes=15 * i)
            pulse = 22.0 * math.exp(-((i - 60) ** 2) / (2 * 12.0 ** 2))
            for node_id, zone_code, base_wl in nodes:
                wl = base_wl + pulse + rng.gauss(0.0, 1.5)
                rain = max(0.0, pulse * 0.45 + rng.gauss(0.0, 0.5))
                soil = min(98.0, max(35.0, 58.0 + pulse * 1.1 + rng.gauss(0.0, 1.0)))
                w_temp = 26.2 + rng.gauss(0.0, 0.3)
                a_temp = 28.5 + 2.0 * math.sin(i / 12.0) + rng.gauss(0.0, 0.4)
                a_hum = min(98.0, max(60.0, 82.0 - 4.0 * math.sin(i / 12.0) + rng.gauss(0.0, 1.5)))
                batt_v = round(12.2 + 0.3 * math.sin(i / 20.0) + rng.gauss(0.0, 0.04), 2)
                soc = min(100, max(45, int(84 + 8 * math.sin(i / 20.0))))
                rssi = int(-88 + rng.gauss(0.0, 4.0))
                snr = round(6.5 + rng.gauss(0.0, 1.2), 2)
                writer.writerow([
                    ts.strftime("%Y-%m-%d %H:%M:%S"),
                    node_id,
                    zone_code,
                    round(wl, 2),
                    round(rain, 2),
                    round(soil, 2),
                    round(w_temp, 2),
                    round(a_temp, 2),
                    round(a_hum, 2),
                    batt_v,
                    soc,
                    rssi,
                    snr,
                ])
    return out_path


def generate_petak_tersier(seed: int = 42, count: int = 20) -> Path:
    """Generate anonymized synthetic tertiary irrigation plot records."""
    rng = random.Random(seed + 2)
    out_path = SAMPLE_DIR / "sample_petak_tersier.csv"
    stages = ["Vegetatif", "Reproduktif", "Pemasakan"]
    varieties = ["Inpari", "Ciherang", "Mekongga"]

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "plot_id",
            "canal_group",
            "area_ha",
            "elevation_m",
            "growth_stage",
            "rice_variety",
            "sample_cfai_score",
            "risk_category",
        ])
        for idx in range(1, count + 1):
            area = round(rng.uniform(12.0, 85.0), 2)
            elev = round(rng.uniform(8.0, 46.0), 2)
            stage = stages[idx % len(stages)]
            variety = varieties[idx % len(varieties)]
            cfai = round(min(0.95, max(0.12, 0.85 - (elev / 65.0) + rng.gauss(0.0, 0.08))), 4)
            if cfai < 0.30:
                cat = "Rendah"
            elif cfai < 0.55:
                cat = "Sedang"
            elif cfai < 0.75:
                cat = "Tinggi"
            else:
                cat = "Sangat Tinggi"
            writer.writerow([
                f"PLOT_{idx:03d}",
                f"CANAL_GROUP_{(idx - 1) % 4 + 1}",
                area,
                elev,
                stage,
                variety,
                cfai,
                cat,
            ])
    return out_path


def generate_responden_ahp() -> Path:
    """Generate anonymized AHP expert weights summary (no PII)."""
    out_path = SAMPLE_DIR / "sample_responden_ahp.json"
    payload = {
        "note": "Anonymized synthetic expert weighting structure matching the 9-criteria AHP hierarchy.",
        "consistency_ratio": 0.0082,
        "experts": ["EXPERT_01", "EXPERT_02", "EXPERT_03", "EXPERT_04", "EXPERT_05"],
        "criteria_weights": {
            "C1.1": 0.2170,
            "C1.2": 0.1205,
            "C1.3": 0.0644,
            "C2.1": 0.0680,
            "C2.2": 0.2202,
            "C2.3": 0.0897,
            "C3.1": 0.0977,
            "C3.2": 0.0596,
            "C3.3": 0.0629,
        },
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path


def generate_sample_gis_layers() -> list[Path]:
    """Generate lightweight synthetic WebGIS layers for demo mode."""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    layers_path = STORAGE_DIR / "pante_lhong_layers.json"
    sawah_path = STORAGE_DIR / "pante_lhong_sawah.json"
    extras_path = STORAGE_DIR / "pante_lhong_cad_extras.json"

    layers_payload = {
        "CANALS": [
            {
                "name": "Sample Main Canal",
                "type": "primary",
                "latlngs": [[5.115264, 96.702764], [5.1520, 96.7120], [5.187152, 96.720373]],
            },
            {
                "name": "Sample Secondary Canal",
                "type": "secondary",
                "latlngs": [[5.187152, 96.720373], [5.1980, 96.7240], [5.208928, 96.727275]],
            },
        ],
        "BENCHMARKS": [{"name": "BM_SAMPLE_01", "lat": 5.1153, "lon": 96.7028, "elev_m": 44.0}],
        "STRUCTURES": [{"name": "Intake Sample", "lat": 5.1153, "lon": 96.7028}],
        "RAWA_SUPLESI": [],
        "EMBUNG": [],
        "BOUNDARIES": [],
        "LAND_USE_ZONES": [],
        "ADMIN_PLACES": [],
    }
    sawah_payload = [
        {
            "plot_id": f"PLOT_{i:03d}",
            "latlngs": [
                [5.145 + i * 0.004, 96.715],
                [5.147 + i * 0.004, 96.715],
                [5.147 + i * 0.004, 96.717],
                [5.145 + i * 0.004, 96.717],
            ],
        }
        for i in range(1, 6)
    ]
    extras_payload = {
        "roads": [],
        "contours": [],
        "labels": [{"text": "Sample Irrigation Zone", "lat": 5.175, "lon": 96.718}],
    }

    layers_path.write_text(json.dumps(layers_payload, indent=2), encoding="utf-8")
    sawah_path.write_text(json.dumps(sawah_payload, indent=2), encoding="utf-8")
    extras_path.write_text(json.dumps(extras_payload, indent=2), encoding="utf-8")
    return [layers_path, sawah_path, extras_path]


def main() -> None:
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    files = [
        generate_tma_hidrologi(),
        generate_iot_telemetry(),
        generate_petak_tersier(),
        generate_responden_ahp(),
        *generate_sample_gis_layers(),
    ]
    for fp in files:
        print(f"Generated: {fp.relative_to(BASE_DIR)}")


if __name__ == "__main__":
    main()
