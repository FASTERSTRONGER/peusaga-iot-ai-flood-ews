"""Public sample database seeder for PEUSAGA journal reproducibility.

Seeds the application database using anonymized synthetic sample datasets
located in ../data/sample/ and generic demo credentials.
"""
import csv
import json
import os
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv
from flask import Flask
from werkzeug.security import generate_password_hash

from models import (
    AhpWeight,
    GisFarmParcel,
    NodeStatus,
    SensorCalibration,
    SensorTelemetry,
    SystemUser,
    db,
    now_wib_str,
)
from services.ai_risk_engine import DATA_DIR, DEFAULT_WEIGHT_MAP, classify_cfai


def create_minimal_app() -> Flask:
    """Create minimal Flask app context for database seeding."""
    load_dotenv()
    flask_app = Flask(__name__)
    db_url = os.getenv(
        "DATABASE_URL",
        "sqlite:///storage/peusaga_demo.db",
    )
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    flask_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(flask_app)
    return flask_app


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val) if val not in (None, "") else default
    except (ValueError, TypeError):
        return default


def _safe_int(val: Any, default: int = 0) -> int:
    try:
        return int(float(val)) if val not in (None, "") else default
    except (ValueError, TypeError):
        return default


def seed_all(reset: bool = False) -> Dict[str, int]:
    """Seed all core tables from synthetic sample datasets."""
    if reset:
        db.drop_all()
    db.create_all()

    counts: Dict[str, int] = {}

    # 1. Demo System Users (non-production credentials)
    if SystemUser.query.count() == 0:
        demo_users = [
            ("demo_admin", "demo_admin_2026", "Demo Administrator", "admin"),
            ("demo_operator", "demo_operator_2026", "Demo Operator", "operator"),
        ]
        for uname, raw_pw, fname, role in demo_users:
            db.session.add(
                SystemUser(
                    username=uname,
                    password_hash=generate_password_hash(raw_pw),
                    full_name=fname,
                    role=role,
                    is_active=True,
                    created_at=now_wib_str(),
                )
            )
        db.session.commit()
    counts["system_users"] = SystemUser.query.count()

    # 2. Sample IoT Nodes & Calibration
    node_profiles = [
        ("node_hulu", "Node 1: Upstream (Sample)", "Zone I - Upstream", 5.115264, 96.702764, 44.02, 450.0, 180.0, os.getenv("HULU_NODE_KEY", "DEMO_HULU_KEY")),
        ("node_hilir", "Node 2: Midstream Relay (Sample)", "Zone II - Midstream", 5.187152, 96.720373, 48.94, 300.0, 150.0, os.getenv("HILIR_NODE_KEY", "DEMO_HILIR_KEY")),
        ("node_gateway", "Node 3: Downstream Gateway (Sample)", "Zone III - Downstream", 5.208928, 96.727275, 14.17, 250.0, 140.0, os.getenv("GATEWAY_DEFAULT_KEY", "DEMO_GATEWAY_KEY")),
    ]
    if NodeStatus.query.count() == 0:
        for nid, name, loc, lat, lon, elev, pole_h, bankfull, key in node_profiles:
            db.session.add(
                NodeStatus(
                    node_id=nid,
                    name=name,
                    location=loc,
                    stage="Sample Topology",
                    status="online",
                    last_seen=now_wib_str(),
                    last_rssi=-85,
                    last_snr=6.8,
                    last_water_level=95.0,
                    last_rainfall=2.4,
                    last_soil_moisture=64.0,
                    last_water_temp=26.3,
                    last_air_temp=28.8,
                    last_air_humidity=81.0,
                    last_battery=12.3,
                    last_battery_soc=88,
                    last_signal_quality=85,
                    packets_received=120,
                    auth_key=key,
                    latitude=lat,
                    longitude=lon,
                    elevation_m=elev,
                    notes="Sample demo node",
                )
            )
            db.session.add(
                SensorCalibration(
                    node_id=nid,
                    pole_height_cm=pole_h,
                    bankfull_level_cm=bankfull,
                    updated_at=now_wib_str(),
                )
            )
        db.session.commit()
    counts["node_status"] = NodeStatus.query.count()

    # 3. Sample IoT Telemetry from data/sample/sample_telemetri_iot.csv
    telemetry_csv = DATA_DIR / "sample_telemetri_iot.csv"
    if SensorTelemetry.query.count() == 0 and telemetry_csv.exists():
        with telemetry_csv.open("r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                db.session.add(
                    SensorTelemetry(
                        node_id=row["node_id"],
                        water_level_cm=_safe_float(row.get("water_level_cm")),
                        rainfall_mm=_safe_float(row.get("rainfall_mm")),
                        soil_moisture_pct=_safe_float(row.get("soil_moisture_pct")),
                        water_temp_c=_safe_float(row.get("water_temp_c")),
                        air_temp_c=_safe_float(row.get("air_temp_c")),
                        air_humidity_pct=_safe_float(row.get("air_humidity_pct")),
                        battery_voltage=_safe_float(row.get("battery_v")),
                        battery_soc=_safe_int(row.get("battery_soc_pct")),
                        rssi=_safe_int(row.get("rssi_dbm")),
                        snr=_safe_float(row.get("snr_db")),
                        recorded_at=row.get("recorded_at") or now_wib_str(),
                    )
                )
        db.session.commit()
    counts["sensor_telemetry"] = SensorTelemetry.query.count()

    # 4. Sample AHP Weights
    ahp_json = DATA_DIR / "sample_responden_ahp.json"
    if AhpWeight.query.count() == 0:
        weights = DEFAULT_WEIGHT_MAP
        if ahp_json.exists():
            payload = json.loads(ahp_json.read_text(encoding="utf-8"))
            weights = payload.get("criteria_weights", DEFAULT_WEIGHT_MAP)
        for code, w in weights.items():
            db.session.add(
                AhpWeight(
                    criterion_code=code,
                    criterion_name=f"Criterion {code}",
                    weight_value=float(w),
                    updated_at=now_wib_str(),
                )
            )
        db.session.commit()
    counts["ahp_weights"] = AhpWeight.query.count()

    # 5. Sample Farm Parcels from data/sample/sample_petak_tersier.csv
    parcels_csv = DATA_DIR / "sample_petak_tersier.csv"
    if GisFarmParcel.query.count() == 0 and parcels_csv.exists():
        with parcels_csv.open("r", encoding="utf-8") as f:
            for idx, row in enumerate(csv.DictReader(f), start=1):
                cfai = _safe_float(row.get("sample_cfai_score"), 0.35)
                cat, _ = classify_cfai(cfai)
                lat = 5.145 + (idx % 5) * 0.008
                lon = 96.715 + (idx // 5) * 0.008
                db.session.add(
                    GisFarmParcel(
                        parcel_code=row["plot_id"],
                        parcel_name=f"{row['plot_id']} ({row['canal_group']})",
                        area_ha=_safe_float(row.get("area_ha"), 25.0),
                        elevation_m=_safe_float(row.get("elevation_m"), 20.0),
                        growth_stage=row.get("growth_stage", "Vegetatif"),
                        rice_variety=row.get("rice_variety", "Ciherang"),
                        cfai_score=cfai,
                        risk_level=cat,
                        polygon_json=json.dumps([
                            [lat, lon],
                            [lat + 0.002, lon],
                            [lat + 0.002, lon + 0.002],
                            [lat, lon + 0.002],
                        ]),
                    )
                )
        db.session.commit()
    counts["gis_farm_parcels"] = GisFarmParcel.query.count()

    return counts


if __name__ == "__main__":
    app = create_minimal_app()
    with app.app_context():
        result = seed_all(reset=True)
        print("Database seeded with public sample data:", result)
