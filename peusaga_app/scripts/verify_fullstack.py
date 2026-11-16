"""Skrip verifikasi end-to-end otomatis Sistem Fullstack PEUSAGA."""
import json
import os
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from sqlalchemy import func
from werkzeug.security import generate_password_hash

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app import app, _calc_liion_soc  # noqa: E402
from models import (  # noqa: E402
    AhpWeight,
    AiPrediction,
    ApiLog,
    BroadcastLog,
    CropdamxAssessment,
    DumpMessage,
    FarmerGroup,
    FloodEvent,
    GisFarmParcel,
    GisLocation,
    GisRiverChannel,
    LstmEvaluationScenario,
    NodeStatus,
    SensorCalibration,
    SensorTelemetry,
    SystemUser,
    db,
)


def run_all_checks() -> None:
    """Menjalankan seluruh verifikasi basis data, rute web, AI Keras, IoT, WebGIS, dan higienitas."""
    results = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        status = "PASS" if cond else "FAIL"
        results.append((name, status, detail))
        print(f"[{status}] {name}: {detail}")
        if not cond:
            raise AssertionError(f"{name} gagal: {detail}")

    # 1. Verifikasi Transparansi Logo PNG
    logo_path = BASE_DIR / "static" / "img" / "logo_peusaga.png"
    img = Image.open(logo_path)
    arr = np.array(img)
    check(
        "Logo PNG Transparan",
        img.mode == "RGBA" and int(arr[0, 0, 3]) == 0 and int((arr[:, :, 3] == 0).sum()) > 10000,
        f"size={img.size}, mode={img.mode}, corner_alpha={int(arr[0, 0, 3])}",
    )

    with app.app_context():
        # 2. Verifikasi Isi Tabel MySQL
        tot_ha = float(db.session.query(func.sum(GisFarmParcel.area_ha)).scalar() or 0.0)
        counts = {
            "system_users": SystemUser.query.count(),
            "node_status": NodeStatus.query.count(),
            "sensor_calibrations": SensorCalibration.query.count(),
            "sensor_telemetry": SensorTelemetry.query.count(),
            "ai_predictions": AiPrediction.query.count(),
            "cropdamx_assessments": CropdamxAssessment.query.count(),
            "dump_messages": DumpMessage.query.count(),
            "api_logs": ApiLog.query.count(),
            "gis_locations": GisLocation.query.count(),
            "gis_farm_parcels": GisFarmParcel.query.count(),
            "gis_river_channels": GisRiverChannel.query.count(),
            "lstm_evaluation_scenarios": LstmEvaluationScenario.query.count(),
            "ahp_weights": AhpWeight.query.count(),
            "farmer_groups": FarmerGroup.query.count(),
            "flood_events": FloodEvent.query.count(),
        }
        check(
            "MySQL Baseline Seeding",
            counts["sensor_telemetry"] >= 2618
            and counts["ai_predictions"] >= 2750
            and counts["cropdamx_assessments"] >= 6934
            and counts["gis_farm_parcels"] == 103
            and abs(tot_ha - 5853.74) < 0.05,
            f"parcels=103 ({tot_ha:.2f} ha), telemetry={counts['sensor_telemetry']}, flood_events={counts['flood_events']}",
        )

        max_tel_id = db.session.query(func.max(SensorTelemetry.id)).scalar() or 0
        max_pred_id = db.session.query(func.max(AiPrediction.id)).scalar() or 0
        max_crop_id = db.session.query(func.max(CropdamxAssessment.id)).scalar() or 0
        max_dump_id = db.session.query(func.max(DumpMessage.id)).scalar() or 0
        max_log_id = db.session.query(func.max(ApiLog.id)).scalar() or 0
        max_bc_id = db.session.query(func.max(BroadcastLog.id)).scalar() or 0

        # 2b. Verifikasi Posisi Baru 3 Node D.I. Pante Lhong & Prediksi Ketiga Node
        expected_coords = {
            "node_hulu": (5.115264, 96.702764),
            "node_hilir": (5.187152, 96.720373),
            "node_gateway": (5.208928, 96.727275),
        }
        nodes_db = {n.node_id: n for n in NodeStatus.query.all()}
        coords_ok = all(
            nid in nodes_db
            and abs((nodes_db[nid].latitude or 0.0) - lat) < 1e-4
            and abs((nodes_db[nid].longitude or 0.0) - lon) < 1e-4
            for nid, (lat, lon) in expected_coords.items()
        )
        old_pos_count = GisLocation.query.filter(
            (GisLocation.category == "iot_stage1") | (func.abs(GisLocation.latitude - 5.193171) < 0.001)
        ).count()
        check(
            "Posisi Baru 3 Node Pante Lhong",
            coords_ok and old_pos_count == 0,
            f"coords_ok={coords_ok}, old_pos_count={old_pos_count}",
        )

        pred_per_node = dict(
            db.session.query(AiPrediction.node_id, func.count(AiPrediction.id))
            .group_by(AiPrediction.node_id)
            .all()
        )
        keras_per_node = dict(
            db.session.query(AiPrediction.node_id, func.count(AiPrediction.id))
            .filter(AiPrediction.model_source == "keras_lstm_t3h")
            .group_by(AiPrediction.node_id)
            .all()
        )
        check(
            "Prediksi Historis & Keras 3 Node",
            all(pred_per_node.get(nid, 0) >= 870 and keras_per_node.get(nid, 0) >= 1 for nid in expected_coords),
            f"total_per_node={pred_per_node}, keras_per_node={keras_per_node}",
        )

    forbidden_re = re.compile(r"\bbima\b", re.IGNORECASE)

    with app.app_context():
        verify_username = "_verify_admin"
        verify_pass = "VerifyPass!2026"
        existing_v = SystemUser.query.filter_by(username=verify_username).first()
        if existing_v:
            db.session.delete(existing_v)
            db.session.commit()
        db.session.add(
            SystemUser(
                username=verify_username,
                password_hash=generate_password_hash(verify_pass),
                full_name="Verifier Admin",
                role="admin",
                is_active=True,
                created_at="2026-11-15 00:00:00",
            )
        )
        db.session.commit()

    try:
        with app.test_client() as client:
            # 3. Verifikasi Halaman Publik (/ & /login), Anti-Slop DOM, dan Proteksi Rute Admin
            def assert_html_clean(route_path: str, resp) -> str:
                html = resp.get_data(as_text=True)
                h1_count = len(re.findall(r"<h1\b", html))
                has_emdash = "\u2014" in html
                has_svg = "<svg" in html.lower()
                has_forbidden = bool(forbidden_re.search(html))
                check(
                    f"HTML Route {route_path}",
                    resp.status_code == 200
                    and '<html lang="id"' in html
                    and "<main" in html
                    and "<footer" in html
                    and "logo_peusaga.png" in html
                    and h1_count == 1
                    and not has_emdash
                    and not has_svg
                    and not has_forbidden,
                    f"HTTP {resp.status_code}, h1={h1_count}, emdash={has_emdash}, svg={has_svg}, clean={not has_forbidden}",
                )
                return html

            r_home = client.get("/")
            home_html = assert_html_clean("/", r_home)
            admin_menu_leaked = any(
                tok in home_html
                for tok in ("Dashboard Operasional", "Prediksi LSTM", "Konsol IoT LoRa", "Katalog Dataset", "Admin &amp; Peringatan", "btn-dash-simulate")
            )
            check(
                "Landing Page Humanize & Pemisahan Menu Pengunjung",
                "Masuk Admin" in home_html
                and "Pantauan Tinggi Air" in home_html
                and "Panduan Tindakan Petani" in home_html
                and not admin_menu_leaked,
                f"humanized=True, admin_menu_leaked={admin_menu_leaked}",
            )

            r_login_page = client.get("/login")
            assert_html_clean("/login", r_login_page)

            # 3b. Verifikasi Proteksi Redirect Tanpa Login (302 -> /login) & Guard API (401)
            protected_routes = ["/dashboard", "/ai-lstm", "/cropdamx", "/console", "/datasets", "/admin"]
            redirect_ok = True
            for pr in protected_routes:
                rp = client.get(pr, follow_redirects=False)
                if rp.status_code != 302 or "/login" not in (rp.headers.get("Location") or ""):
                    redirect_ok = False
            r_unauth_sim = client.post("/api/simulate", json={"node_id": "all"})
            r_unauth_pred = client.post("/api/predict", json={"node_id": "node_hulu"})
            r_unauth_cal = client.post("/api/calibration", json={"node_id": "node_hulu"})
            r_unauth_pv = client.get("/api/datasets/preview?path=Olah Data/01_LSTM_Muka_Air/outputs/ringkasan_evaluasi_lstm.csv")
            check(
                "Route Guard & Proteksi API Tanpa Login",
                redirect_ok
                and r_unauth_sim.status_code == 401
                and r_unauth_pred.status_code == 401
                and r_unauth_cal.status_code == 401
                and r_unauth_pv.status_code == 401,
                f"redirects_302={redirect_ok}, unauth_api=[{r_unauth_sim.status_code},{r_unauth_pred.status_code},{r_unauth_cal.status_code},{r_unauth_pv.status_code}]",
            )

            # 3c. Verifikasi Endpoint Baca Publik untuk Landing Page (/api/status, /api/nodes, /api/gis/layers)
            r_pub_status = client.get("/api/status")
            ps_json = r_pub_status.get_json() or {}
            check(
                "API Publik Landing Page (/api/status)",
                r_pub_status.status_code == 200 and len(ps_json.get("nodes", [])) == 3 and "visitor_summary" in ps_json,
                f"HTTP={r_pub_status.status_code}, nodes={len(ps_json.get('nodes', []))}, overall={ps_json.get('visitor_summary', {}).get('overall_alert')}",
            )

            # 4. Ingesti Arduino JSON & CSV pada /api dan /api_ews.php (Tanpa Sesi Browser)
            hulu_key = os.getenv("HULU_NODE_KEY", "KEY_PEUSANGAN_HULU_915")
            r_json = client.post(
                "/api",
                json={
                    "node_id": "node_hulu",
                    "api_key": hulu_key,
                    "water_level": 152.4,
                    "rainfall": 12.0,
                    "soil_moisture": 68.0,
                    "battery_voltage": 12.18,
                    "rssi": -76,
                },
            )
            d_json = r_json.get_json()
            check("Ingesti JSON /api (Tanpa Login Browser)", r_json.status_code == 200 and d_json.get("status") == "ok", str(d_json))

            r_csv = client.post(
                f"/api_ews.php?node_id=node_hilir&api_key={os.getenv('HILIR_NODE_KEY', 'KEY_PEUSANGAN_HILIR_915')}",
                data="12.22,1980,8.5,28.1,82.0,25.4,142.0,-78,9.8",
                content_type="text/plain",
            )
            d_csv = r_csv.get_json()
            check(
                "Ingesti Arduino CSV /api_ews.php",
                r_csv.status_code == 200 and d_csv.get("node_id") == "node_hilir",
                str(d_csv),
            )

            # 5. Karantina SOS & Kunci Tidak Sah
            r_sos = client.post(
                "/api",
                json={"node_id": "node_hulu", "api_key": hulu_key, "is_emergency": 1, "emergency_text": "Uji SOS"},
            )
            r_bad = client.post("/api", json={"node_id": "node_hulu", "api_key": "INVALID_KEY", "water_level": 100})
            check(
                "Karantina SOS & Auth Hardware",
                r_sos.status_code == 202 and r_bad.status_code == 401,
                f"SOS HTTP={r_sos.status_code}, Invalid HTTP={r_bad.status_code}",
            )

            # 5b. Login Admin & Verifikasi Akses Penuh Seluruh Menu Admin
            r_bad_login = client.post("/login", data={"username": verify_username, "password": "wrong"}, follow_redirects=False)
            r_good_login = client.post(
                "/login?next=/dashboard",
                data={"username": verify_username, "password": verify_pass},
                follow_redirects=False,
            )
            check(
                "Autentikasi Login Admin (/login)",
                r_bad_login.status_code == 401 and r_good_login.status_code == 302 and "/dashboard" in (r_good_login.headers.get("Location") or ""),
                f"bad={r_bad_login.status_code}, good_redirect={r_good_login.headers.get('Location')}",
            )

            for rt in protected_routes:
                rp_auth = client.get(rt)
                html_auth = assert_html_clean(rt, rp_auth)
                if rt == "/dashboard":
                    check(
                        "Navbar Admin Setelah Login",
                        "Dashboard Operasional" in html_auth and "Keluar" in html_auth,
                        "Menu operasional dan tombol Keluar tampil saat sesi admin aktif",
                    )

            # 6. Inferensi Keras LSTM Ketiga Node (/api/predict & /api/iot/simulate all)
            node_pred_summary = {}
            for nid in ("node_hulu", "node_hilir", "node_gateway"):
                r_pred = client.post("/api/predict", json={"node_id": nid, "save": True})
                dp = r_pred.get_json()
                pred = dp.get("prediction", {})
                assert r_pred.status_code == 200 and pred.get("model_source") == "keras_lstm_t3h"
                node_pred_summary[nid] = pred.get("pred_plus_3h")
            r_sim_all = client.post("/api/iot/simulate", json={"node_id": "all", "mode": "normal"})
            sim_all_json = r_sim_all.get_json() or {}
            check(
                "Keras LSTM & Simulasi 3 Node",
                r_sim_all.status_code == 200 and len(sim_all_json.get("results", [])) == 3,
                f"t+3h={node_pred_summary}, sim_all={len(sim_all_json.get('results', []))} node",
            )

            # 7. AHP-CROPDAM-X & Surrogate RF/Bayesian + 103 Petak
            r_cx = client.post(
                "/api/risk/cropdamx",
                json={
                    "depth_cm": 65.0,
                    "duration_hours": 36.0,
                    "velocity_kmh": 5.0,
                    "growth_stage": "Reproduktif",
                    "crop_type": "Ciherang",
                    "save": True,
                },
            )
            dc = r_cx.get_json()
            check(
                "AHP-CROPDAM-X & Surrogate",
                r_cx.status_code == 200
                and dc.get("cfai", {}).get("cfai_score", 0) > 0
                and dc.get("surrogate", {}).get("rf_surrogate_score") is not None
                and len(dc.get("sensitivity", [])) == 6,
                f"CFAI={dc.get('cfai', {}).get('cfai_score')}, RF={dc.get('surrogate', {}).get('rf_surrogate_score')}, sigma={dc.get('surrogate', {}).get('bayes_sigma')}",
            )

            r_parcels = client.get("/api/cropdamx/parcels?search=CK")
            check(
                "Filter Petak Tersier",
                r_parcels.status_code == 200 and r_parcels.get_json().get("count", 0) > 0,
                f"matched={r_parcels.get_json().get('count')}",
            )

            # 8. WebGIS Layers, Broadcast, Link Budget, Power, Dataset Preview
            r_gis = client.get("/api/gis/layers")
            dg = r_gis.get_json()
            check(
                "WebGIS Multi-Layer Payload",
                r_gis.status_code == 200
                and len(dg.get("iot_nodes", [])) == 3
                and "iot_stage1_nodes" not in dg
                and len(dg.get("parcels", [])) == 103
                and len(dg.get("cad_sawah", [])) >= 2600
                and len(dg.get("land_use_zones", [])) == 0
                and len(dg.get("structures", [])) >= 137
                and len(dg.get("benchmarks", [])) == 25
                and len(dg.get("boundaries", [])) >= 364,
                f"iot_nodes={len(dg.get('iot_nodes', []))}, parcels={len(dg.get('parcels', []))}, cad_sawah={len(dg.get('cad_sawah', []))}, structures={len(dg.get('structures', []))}, channels={len(dg.get('channels', []))}, boundaries={len(dg.get('boundaries', []))}",
            )

            r_ext = client.get("/api/gis/cad-extras")
            dx = r_ext.get_json() or {}
            check(
                "WebGIS CAD Extras Lazy-Load",
                r_ext.status_code == 200
                and len(dx.get("pemukiman", [])) >= 1400
                and len(dx.get("roads", [])) >= 1300,
                f"status={r_ext.status_code}, pemukiman={len(dx.get('pemukiman', []))}, roads={len(dx.get('roads', []))}",
            )

            r_bc = client.post(
                "/api/broadcast",
                json={"channel": "Telegram", "alert_level": "SIAGA", "message_text": "Uji diseminasi PEUSAGA"},
            )
            check("Webhook Broadcast Dry-Run", r_bc.status_code == 200 and r_bc.get_json()["broadcast"]["status"] == "SIMULATED", "SIMULATED OK")

            r_lora = client.post("/api/lora/link-budget", json={"distance_km": 7.387, "rain_mm_h": 50, "sf": 9})
            r_pwr = client.post("/api/iot/power-autonomy", json={"battery_wh": 57.72, "avg_load_w": 0.6804})
            check(
                "Kalkulator Teknik LoRa & Daya",
                r_lora.status_code == 200 and r_pwr.status_code == 200 and r_pwr.get_json()["result"]["meets_72h_target"],
                f"RSSI={r_lora.get_json()['result']['rssi_dbm']} dBm, autonomy={r_pwr.get_json()['result']['autonomy_hours']}h",
            )

            r_pv_ok = client.get("/api/datasets/preview?path=Olah Data/01_LSTM_Muka_Air/outputs/ringkasan_evaluasi_lstm.csv")
            r_pv_bad = client.get("/api/datasets/preview?path=../../secret.txt")
            r_chart = client.get("/api/datasets/chart/Olah Data/01_LSTM_Muka_Air/outputs/04_best_hourly_lstm_result.png")
            check(
                "Dataset Preview & Path Guard",
                r_pv_ok.status_code == 200 and r_pv_bad.status_code == 400 and r_chart.status_code == 200,
                f"csv=200, traversal_blocked={r_pv_bad.status_code}, chart={r_chart.status_code}",
            )

            r_logout = client.get("/logout", follow_redirects=False)
            r_after_logout = client.get("/dashboard", follow_redirects=False)
            check(
                "Logout Menghapus Sesi",
                r_logout.status_code == 302 and r_after_logout.status_code == 302 and "/login" in (r_after_logout.headers.get("Location") or ""),
                f"logout={r_logout.status_code}, post_logout_dashboard={r_after_logout.status_code}",
            )
    finally:
        # 9. Bersihkan baris uji sintetis & pulihkan counter awal agar basis data bersih
        with app.app_context():
            SensorTelemetry.query.filter(SensorTelemetry.id > max_tel_id).delete()
            AiPrediction.query.filter(AiPrediction.id > max_pred_id).delete()
            CropdamxAssessment.query.filter(CropdamxAssessment.id > max_crop_id).delete()
            DumpMessage.query.filter(DumpMessage.id > max_dump_id).delete()
            ApiLog.query.filter(ApiLog.id > max_log_id).delete()
            BroadcastLog.query.filter(BroadcastLog.id > max_bc_id).delete()
            SystemUser.query.filter_by(username=verify_username).delete()
            db.session.commit()

    # 10. Pemeriksaan Higienitas Berkas Sumber Aplikasi
    leak_hits = []
    for ext in ("*.py", "*.html", "*.css", "*.js", "*.md"):
        for fp in BASE_DIR.rglob(ext):
            if ".venv" in fp.parts or "storage" in fp.parts:
                continue
            txt = fp.read_text(encoding="utf-8", errors="ignore")
            if fp.name != "verify_fullstack.py" and forbidden_re.search(txt):
                leak_hits.append(f"{fp.name}: forbidden token")
            if fp.name != "verify_fullstack.py" and any(p in txt for p in ("C:\\Users\\", "D:\\Project\\")):
                leak_hits.append(f"{fp.name}: local path leak")
            if "\u2014" in txt and fp.suffix in {".html", ".css", ".js"}:
                leak_hits.append(f"{fp.name}: em-dash")

    js_text = (BASE_DIR / "static" / "js" / "peusaga.js").read_text(encoding="utf-8")
    check(
        "Koordinat (X, Y) Peta WebGIS",
        all(fn in js_text for fn in ("latLngToUtm47N", "formatCoordHtml", "formatCoordTooltip", "Koordinat (X, Y) UTM 47N")),
        "Fungsi & label koordinat X/Y geografis + UTM 47N tersedia pada seluruh layer peta",
    )

    check("Higienitas Kode & Keamanan Path", len(leak_hits) == 0, "Bersih" if not leak_hits else str(leak_hits))
    print(f"\nSemua {len(results)} pemeriksaan verifikasi LULUS.")


if __name__ == "__main__":
    run_all_checks()
