"""Aplikasi Web Fullstack Monolitik PEUSAGA (Flask + MySQL 8.0 + AI LSTM + CROPDAM-X)."""
import json
import os
import queue
import time
from functools import wraps
from typing import Any, Dict, List, Optional, Tuple

import requests as http_requests
from dotenv import load_dotenv
from flask import (
    Flask,
    Response,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    stream_with_context,
    url_for,
)
from sqlalchemy import desc, func
from werkzeug.security import check_password_hash, generate_password_hash

from models import (
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
    SystemSetting,
    SystemUser,
    db,
    now_wib_str,
)
from services.ai_risk_engine import (
    ai_risk_engine,
    sanitize_research_text,
)
from services.data_catalog_service import (
    list_all_datasets,
    list_chart_artifacts,
    load_canal_network_graph,
    load_climatology_comparison,
    load_climatology_points,
    load_pante_lhong_cad_extras,
    load_pante_lhong_layers,
    load_pante_lhong_sawah,
    load_rice_variety_matrix,
    load_stage2_topology,
    preview_dataset_file,
    resolve_safe_research_file,
)

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "peusaga-demo-session-key")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://root:@127.0.0.1:3306/peusaga_db?charset=utf8mb4",
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True, "pool_recycle": 1800}

db.init_app(app)

OFFICIAL_NODE_KEYS: Dict[str, str] = {
    os.getenv("HULU_NODE_KEY", "KEY_PEUSANGAN_HULU_915"): "node_hulu",
    os.getenv("HILIR_NODE_KEY", "KEY_PEUSANGAN_HILIR_915"): "node_hilir",
    os.getenv("GATEWAY_DEFAULT_KEY", "KEY_PEUSANGAN_GATEWAY_915"): "node_gateway",
    "KEY_PEUSANGAN_HULU_923": "node_hulu",
    "KEY_PEUSANGAN_HILIR_923": "node_hilir",
    "KEY_PEUSANGAN_GATEWAY_923": "node_gateway",
}

_SSE_CLIENTS: List[queue.Queue] = []


def _broadcast_sse(event_name: str, payload: Dict[str, Any]) -> None:
    """Mengirimkan event JSON secara real-time ke seluruh klien SSE aktif."""
    data_str = json.dumps(payload, ensure_ascii=False)
    dead: List[queue.Queue] = []
    for q in list(_SSE_CLIENTS):
        try:
            q.put_nowait(f"event: {event_name}\ndata: {data_str}\n\n")
        except Exception:
            dead.append(q)
    for d in dead:
        if d in _SSE_CLIENTS:
            _SSE_CLIENTS.remove(d)


def _calc_liion_soc(voltage: Optional[float]) -> Optional[int]:
    """Menghitung State-of-Charge baterai Li-ion 3S (9,6 V - 12,6 V)."""
    if voltage is None:
        return None
    pct = ((float(voltage) - 9.6) / (12.6 - 9.6)) * 100.0
    return int(max(0, min(100, round(pct))))


def _calc_rssi_quality(rssi: Optional[int]) -> Optional[int]:
    """Mengonversi RSSI LoRa dBm menjadi indeks kualitas sinyal persentase."""
    if rssi is None:
        return None
    pct = ((float(rssi) + 120.0) / 60.0) * 100.0
    return int(max(0, min(100, round(pct))))


def _init_weights_once() -> None:
    """Memuat bobot AHP dari MySQL ke mesin komputasi AI-Risiko."""
    try:
        rows = [w.to_dict() for w in AhpWeight.query.all()]
        if rows:
            ai_risk_engine.update_weights_from_db(rows)
    except Exception:
        pass


with app.app_context():
    _init_weights_once()


def _parse_ingestion_payload() -> Tuple[Dict[str, Any], str, str]:
    """Mengekstrak payload masuk dari JSON, form, query string, atau CSV mentah Arduino."""
    raw_bytes = request.get_data(as_text=True) or ""
    if request.is_json:
        parsed = request.get_json(silent=True) or {}
        return parsed, raw_bytes or json.dumps(parsed), "json"

    if request.form:
        parsed = dict(request.form)
        return parsed, raw_bytes or json.dumps(parsed), "form"

    if request.args:
        parsed = dict(request.args)
        return parsed, request.query_string.decode("utf-8", errors="ignore"), "query"

    if "," in raw_bytes:
        parts = [p.strip() for p in raw_bytes.split(",")]
        if len(parts) >= 7:
            parsed = {
                "battery_voltage": parts[0],
                "soil_adc": parts[1],
                "rainfall": parts[2],
                "air_temp": parts[3],
                "air_humidity": parts[4],
                "water_temp": parts[5],
                "distance": parts[6],
                "rssi": parts[7] if len(parts) > 7 else -75,
                "snr": parts[8] if len(parts) > 8 else 9.5,
            }
            return parsed, raw_bytes, "arduino_csv"

    return {}, raw_bytes, "raw"


def _log_http_tx(
    payload_raw: str,
    payload_parsed: Dict[str, Any],
    payload_type: str,
    status_code: int,
    resp_body: Dict[str, Any],
    start_ts: float,
) -> int:
    """Mencatat setiap transaksi API ke tabel api_logs."""
    duration = round((time.perf_counter() - start_ts) * 1000.0, 2)
    log_row = ApiLog(
        method=request.method,
        uri=request.full_path.rstrip("?"),
        path=request.path,
        query_string=request.query_string.decode("utf-8", errors="ignore"),
        query_params=json.dumps(dict(request.args), ensure_ascii=False),
        headers=json.dumps(
            {k: v for k, v in request.headers.items() if k.lower() not in {"authorization", "cookie"}},
            ensure_ascii=False,
        ),
        payload_raw=sanitize_research_text(payload_raw[:4000]),
        payload_parsed=sanitize_research_text(json.dumps(payload_parsed, ensure_ascii=False)[:4000]),
        payload_type=payload_type,
        content_type=request.content_type or "text/plain",
        ip_address=request.remote_addr or "127.0.0.1",
        user_agent=(request.user_agent.string or "")[:300],
        response_status=status_code,
        response_body=sanitize_research_text(json.dumps(resp_body, ensure_ascii=False)[:4000]),
        duration_ms=duration,
        created_at=now_wib_str(),
    )
    db.session.add(log_row)
    db.session.flush()
    return log_row.id


def _apply_node_calibration(node_id: str, parsed: Dict[str, Any]) -> Dict[str, Any]:
    """Menerapkan rumus kalibrasi sensor per node sesuai basis data sensor_calibrations."""
    cal = db.session.get(SensorCalibration, node_id)
    if not cal:
        cal = SensorCalibration(node_id=node_id)

    def _flt(keys: Tuple[str, ...], default: Optional[float] = None) -> Optional[float]:
        for k in keys:
            if k in parsed and str(parsed[k]).strip() != "":
                try:
                    return float(parsed[k])
                except (ValueError, TypeError):
                    pass
        return default

    raw_dist = _flt(("distance", "jarak", "dist_cm"))
    raw_wl = _flt(("water_level", "tma", "wl"))
    if raw_dist is not None:
        water_level = max(0.0, round(cal.pole_height_cm - raw_dist + cal.water_level_offset_cm, 2))
    elif raw_wl is not None:
        water_level = max(0.0, round(raw_wl + cal.water_level_offset_cm, 2))
    else:
        water_level = 120.0

    raw_rain = _flt(("rainfall", "rain", "curah_hujan"), 0.0) or 0.0
    rainfall = max(0.0, round(raw_rain * cal.rain_multiplier, 2))

    raw_soil_adc = _flt(("soil_adc", "soil"))
    raw_soil_pct = _flt(("soil_moisture",))
    if raw_soil_pct is not None and (raw_soil_adc is None or raw_soil_pct <= 100.0):
        soil_moisture = max(0.0, min(100.0, round(raw_soil_pct + cal.soil_offset_pct, 1)))
        soil_adc = int(raw_soil_adc) if raw_soil_adc is not None else None
    elif raw_soil_adc is not None:
        span = max(1, cal.soil_air_raw - cal.soil_water_raw)
        pct = ((cal.soil_air_raw - raw_soil_adc) / span) * 100.0 + cal.soil_offset_pct
        soil_moisture = max(0.0, min(100.0, round(pct, 1)))
        soil_adc = int(raw_soil_adc)
    else:
        soil_moisture = 55.0
        soil_adc = None

    bat_raw = _flt(("battery_voltage", "vol", "voltage", "bat"), 12.1) or 12.1
    bat_v = round(bat_raw * cal.battery_multiplier + cal.battery_offset_v, 2)
    air_t = round((_flt(("air_temp", "dht_t", "temp"), 28.5) or 28.5) + cal.air_temp_offset_c, 1)
    air_h = round(max(0.0, min(100.0, (_flt(("air_humidity", "dht_h", "hum"), 80.0) or 80.0) + cal.air_hum_offset_pct)), 1)
    wat_t = round((_flt(("water_temp", "ds_t"), 25.5) or 25.5) + cal.water_temp_offset_c, 1)

    rssi_raw = _flt(("rssi",), -78.0)
    rssi = int(round(rssi_raw)) if rssi_raw is not None else -78
    snr = round(_flt(("snr",), 9.5) or 9.5, 1)
    hops = int(round(_flt(("relay_hops", "hops"), 0) or 0))

    return {
        "water_level": water_level,
        "distance": round(raw_dist, 1) if raw_dist is not None else round(max(0.0, cal.pole_height_cm - water_level), 1),
        "rainfall": rainfall,
        "soil_moisture": soil_moisture,
        "soil_adc": soil_adc,
        "water_temp": wat_t,
        "air_temp": air_t,
        "air_humidity": air_h,
        "battery_voltage": bat_v,
        "battery_soc_pct": _calc_liion_soc(bat_v),
        "rssi": rssi,
        "signal_quality_pct": _calc_rssi_quality(rssi),
        "snr": snr,
        "relay_hops": hops,
        "bankfull_level_cm": cal.bankfull_level_cm,
    }


def _handle_iot_ingestion() -> Tuple[Response, int]:
    """Pipeline terpusat ingesti node Arduino/LoRa: validasi kunci, kalibrasi, LSTM, CROPDAM-X, SSE."""
    start_ts = time.perf_counter()
    parsed, raw_body, payload_type = _parse_ingestion_payload()

    provided_key = str(
        parsed.get("api_key")
        or parsed.get("auth_key")
        or parsed.get("key")
        or request.headers.get("X-API-Key")
        or ""
    ).strip()
    requested_node = str(parsed.get("node_id") or parsed.get("device_id") or "").strip()

    is_sos = bool(
        str(parsed.get("is_emergency", "")).lower() in {"1", "true", "yes"}
        or "sos" in str(parsed.get("message_type", "")).lower()
        or "sos" in raw_body.lower()
        or "emergency" in raw_body.lower()
    )

    resolved_node = OFFICIAL_NODE_KEYS.get(provided_key)
    if not resolved_node and requested_node in {"node_hulu", "node_hilir", "node_gateway"} and not provided_key:
        # Terima hanya jika merupakan paket simulasi lokal bertanda simulasi tanpa kunci
        if str(parsed.get("simulated", "")).lower() in {"1", "true"}:
            resolved_node = requested_node

    # Jika kunci tidak sah atau berstatus SOS darurat -> catat di dump_messages
    if is_sos or not resolved_node:
        m_type = "EMERGENCY_SOS" if is_sos else "QUARANTINED_UNAUTHORIZED"
        status_code = 202 if is_sos else 401
        resp = {
            "status": "quarantined",
            "message": "Pesan SOS darurat dicatat." if is_sos else "Kunci API node tidak valid; paket masuk karantina.",
            "message_type": m_type,
        }
        log_id = _log_http_tx(raw_body, parsed, payload_type, status_code, resp, start_ts)
        dump = DumpMessage(
            source_identifier=sanitize_research_text(requested_node or request.remote_addr or "unknown_node"),
            provided_key=provided_key or "-",
            message_type=m_type,
            is_emergency=1 if is_sos else 0,
            emergency_text=sanitize_research_text(str(parsed.get("emergency_text") or parsed.get("message") or raw_body)[:500]),
            rssi=int(float(parsed["rssi"])) if parsed.get("rssi") not in (None, "") else None,
            snr=float(parsed["snr"]) if parsed.get("snr") not in (None, "") else None,
            raw_payload=sanitize_research_text(raw_body[:2000]),
            log_id=log_id,
            created_at=now_wib_str(),
        )
        db.session.add(dump)
        db.session.commit()
        _broadcast_sse("dump", dump.to_dict())
        return jsonify(resp), status_code

    node_id = requested_node if requested_node in {"node_hulu", "node_hilir", "node_gateway"} else resolved_node
    vals = _apply_node_calibration(node_id, parsed)
    now_ts = now_wib_str()

    # Logika prediksi LSTM dari 23 rekaman historis + bacaan baru
    recent_rows = (
        SensorTelemetry.query.filter_by(node_id=node_id)
        .order_by(desc(SensorTelemetry.id))
        .limit(23)
        .all()
    )
    wl_seq = [r.water_level or vals["water_level"] for r in reversed(recent_rows)] + [vals["water_level"]]
    rf_seq = [r.rainfall or 0.0 for r in reversed(recent_rows)] + [vals["rainfall"]]
    pred = ai_risk_engine.predict_water_level(
        water_levels_cm=wl_seq,
        rainfall_mm=rf_seq,
        soil_moisture_pct=vals["soil_moisture"],
        air_humidity_pct=vals["air_humidity"],
        air_temp_c=vals["air_temp"],
        bankfull_cm=vals["bankfull_level_cm"],
    )

    excess_cm = max(0.0, pred["pred_plus_3h"] - vals["bankfull_level_cm"])
    cfai_res = ai_risk_engine.compute_cfai(
        depth_cm=excess_cm,
        duration_h=12.0 if excess_cm > 0 else 2.0,
        velocity_kmh=4.2,
        stage="Reproduktif",
        variety="Ciherang",
    )

    resp = {
        "status": "ok",
        "node_id": node_id,
        "water_level_cm": vals["water_level"],
        "pred_plus_3h_cm": pred["pred_plus_3h"],
        "alert_level": pred["alert_level"],
        "cfai_score": cfai_res["cfai_score"],
        "risk_category": cfai_res["risk_category"],
        "timestamp": now_ts,
    }
    log_id = _log_http_tx(raw_body, parsed, payload_type, 200, resp, start_ts)

    tel = SensorTelemetry(
        node_id=node_id,
        water_level=vals["water_level"],
        rainfall=vals["rainfall"],
        soil_moisture=vals["soil_moisture"],
        water_temp=vals["water_temp"],
        air_temp=vals["air_temp"],
        air_humidity=vals["air_humidity"],
        battery_voltage=vals["battery_voltage"],
        rssi=vals["rssi"],
        snr=vals["snr"],
        raw_payload=sanitize_research_text(raw_body[:2000]),
        log_id=log_id,
        created_at=now_ts,
        relay_hops=vals["relay_hops"],
        auth_key=provided_key or "SIMULATED",
        battery_soc_pct=vals["battery_soc_pct"],
        signal_quality_pct=vals["signal_quality_pct"],
        distance=vals["distance"],
        soil_adc=vals["soil_adc"],
    )
    db.session.add(tel)

    node_row = NodeStatus.query.filter_by(node_id=node_id).first()
    if node_row:
        node_row.status = "online"
        node_row.last_seen = now_ts
        node_row.last_rssi = vals["rssi"]
        node_row.last_snr = vals["snr"]
        node_row.last_water_level = vals["water_level"]
        node_row.last_rainfall = vals["rainfall"]
        node_row.last_soil_moisture = vals["soil_moisture"]
        node_row.last_water_temp = vals["water_temp"]
        node_row.last_air_temp = vals["air_temp"]
        node_row.last_air_humidity = vals["air_humidity"]
        node_row.last_battery = vals["battery_voltage"]
        node_row.last_battery_soc = vals["battery_soc_pct"]
        node_row.last_signal_quality = vals["signal_quality_pct"]
        node_row.packets_received = (node_row.packets_received or 0) + 1

    ai_row = AiPrediction(
        node_id=node_id,
        input_window_size=len(wl_seq),
        current_water_level=vals["water_level"],
        pred_plus_1h=pred["pred_plus_1h"],
        pred_plus_2h=pred["pred_plus_2h"],
        pred_plus_3h=pred["pred_plus_3h"],
        pred_plus_6h=pred["pred_plus_6h"],
        pred_plus_7h=pred["pred_plus_7h"],
        model_source=pred["model_source"],
        alert_level=pred["alert_level"],
        inference_time_ms=pred["inference_time_ms"],
        created_at=now_ts,
    )
    db.session.add(ai_row)

    crop_row = CropdamxAssessment(
        petak_code="KORIDOR_IOT",
        crop_type="Padi Ciherang",
        growth_stage="Reproduktif",
        predicted_water_level=excess_cm,
        flood_duration_hours=12.0 if excess_cm > 0 else 2.0,
        cfai_score=cfai_res["cfai_score"],
        rf_surrogate_score=cfai_res["cfai_score"],
        bayes_sigma=0.015,
        risk_category=cfai_res["risk_category"],
        recommendation=cfai_res["recommendation"],
        created_at=now_ts,
    )
    db.session.add(crop_row)
    db.session.commit()

    tel_dict = tel.to_dict()
    tel_dict["prediction"] = pred
    tel_dict["cfai"] = cfai_res
    _broadcast_sse("telemetry", tel_dict)
    return jsonify(resp), 200


def _is_safe_next_url(target: Optional[str]) -> bool:
    """Memastikan URL redirect lokal aman dan tidak mengarah ke domain eksternal."""
    return bool(target and target.startswith("/") and not target.startswith("//"))


@app.context_processor
def inject_auth_context() -> Dict[str, Any]:
    """Menyuntikkan status sesi login pengguna ke seluruh template Jinja2."""
    user = session.get("user")
    return {
        "current_user": user,
        "is_authenticated": bool(user),
    }


def login_required(view_func):
    """Mewajibkan sesi login Admin/Operator sebelum mengakses halaman teknis."""
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("page_login", next=request.path))
        return view_func(*args, **kwargs)
    return wrapper


def api_login_required(view_func):
    """Mewajibkan sesi login Admin/Operator untuk endpoint kontrol dan mutasi API."""
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            return jsonify({
                "status": "error",
                "message": "Akses ditolak. Silakan masuk sebagai Admin/Operator terlebih dahulu.",
            }), 401
        return view_func(*args, **kwargs)
    return wrapper


# ==============================================================================
# RUTE HALAMAN WEB (LANDING PUBLIK + 6 MODUL OPERASIONAL TERPROTEKSI LOGIN)
# ==============================================================================

_VISITOR_NODE_META: Dict[str, Dict[str, str]] = {
    "node_hulu": {
        "visitor_name": "Titik Pantau 1: Hulu (Bendung Pante Lhong)",
        "visitor_area": "Kecamatan Juli - Kawasan Intake & Saluran Induk Atas",
        "visitor_role": "Memantau debit air dari hulu sungai sebelum masuk ke saluran irigasi sawah.",
    },
    "node_hilir": {
        "visitor_name": "Titik Pantau 2: Tengah & Sawah Aktif (Peusangan)",
        "visitor_area": "Kecamatan Peusangan - Kawasan Saluran Sekunder & Hamparan Padi",
        "visitor_role": "Memantau ketinggian air langsung di dekat area tanam padi produktif petani.",
    },
    "node_gateway": {
        "visitor_name": "Titik Pantau 3: Hilir & Pembuang (Kota Juang)",
        "visitor_area": "Kota Juang - Peusangan Hilir (Dataran Rendah)",
        "visitor_role": "Memantau kenaikan muka air di kawasan rendah hilir dan jalur drainase.",
    },
}

_ALERT_RANK: Dict[str, int] = {"AMAN": 0, "WASPADA": 1, "SIAGA": 2, "AWAS": 3}

_VISITOR_ALERT_COPY: Dict[str, Dict[str, str]] = {
    "AMAN": {
        "headline": "Kondisi Air Saat Ini: AMAN - Aliran Sungai & Irigasi Terkendali",
        "advice": "Ketinggian air di tiga titik pantau berada jauh di bawah batas tanggul aman. Petani dapat beraktivitas, mengolah lahan, memupuk, dan mengatur air sawah seperti biasa.",
        "badge_class": "badge-safe",
        "banner_class": "visitor-banner-safe",
    },
    "WASPADA": {
        "headline": "Kondisi Air Saat Ini: WASPADA - Tinggi Air Mulai Meningkat",
        "advice": "Debit air mulai naik atau diperkirakan meningkat dalam 3 jam ke depan. Petani dianjurkan memeriksa pematang sawah, membersihkan saluran pembuang dari sumbatan, dan memantau perkembangan berikutnya.",
        "badge_class": "badge-warn",
        "banner_class": "visitor-banner-warn",
    },
    "SIAGA": {
        "headline": "Kondisi Air Saat Ini: SIAGA - Siapkan Saluran Pembuang Petak Sawah",
        "advice": "Ketinggian air mendekati batas tanggul. Keujruen Blang dan petani di petak dataran rendah diminta membuka saluran pembuang tersier, menunda pemupukan, dan mengamankan peralatan sawah.",
        "badge_class": "badge-alert",
        "banner_class": "visitor-banner-alert",
    },
    "AWAS": {
        "headline": "Kondisi Air Saat Ini: AWAS - Risiko Luapan Air Tinggi di Sawah & Hilir",
        "advice": "Ketinggian air mencapai atau melampaui batas tanggul aman. Segera amankan peralatan pertanian dan ternak dari bantaran sungai, tutup pintu masuk air petak sawah, serta ikuti arahan petugas P3A dan BPBD.",
        "badge_class": "badge-danger",
        "banner_class": "visitor-banner-danger",
    },
}


def _classify_level_ratio(water_cm: float, bankfull_cm: float) -> str:
    ratio = water_cm / max(1.0, bankfull_cm)
    if ratio >= 1.0:
        return "AWAS"
    if ratio >= 0.85:
        return "SIAGA"
    if ratio >= 0.70:
        return "WASPADA"
    return "AMAN"


def _get_nodes_with_predictions() -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """Mengambil seluruh status node beserta kalibrasi dan prediksi LSTM terbaru tiap node."""
    cals = {c.node_id: c.to_dict() for c in SensorCalibration.query.all()}
    nodes: List[Dict[str, Any]] = []
    node_preds: Dict[str, Dict[str, Any]] = {}
    for n in NodeStatus.query.order_by(NodeStatus.id).all():
        d = n.to_dict()
        cal = cals.get(n.node_id, {})
        d["pole_height_cm"] = cal.get("pole_height_cm", 300.0)
        d["bankfull_level_cm"] = cal.get("bankfull_level_cm", 150.0)
        lp = (
            AiPrediction.query.filter_by(node_id=n.node_id)
            .order_by(desc(AiPrediction.id))
            .first()
        )
        lp_dict = lp.to_dict() if lp else {}
        if lp_dict:
            lp_dict["bankfull_cm"] = d["bankfull_level_cm"]
        d["latest_prediction"] = lp_dict

        last_wl = float(d.get("last_water_level") or 0.0)
        bankfull = float(d["bankfull_level_cm"] or 150.0)
        pred_3h = float(lp_dict.get("pred_plus_3h") or last_wl)
        delta_3h = round(pred_3h - last_wl, 1)
        if delta_3h >= 3.0:
            trend_label = "Naik"
            trend_badge = "badge-warn"
        elif delta_3h <= -3.0:
            trend_label = "Turun"
            trend_badge = "badge-safe"
        else:
            trend_label = "Stabil"
            trend_badge = "badge-safe"

        cur_alert = str(lp_dict.get("alert_level") or _classify_level_ratio(max(last_wl, pred_3h), bankfull)).upper()
        meta = _VISITOR_NODE_META.get(n.node_id, {})
        d["visitor"] = {
            "name": meta.get("visitor_name", d.get("name", n.node_id)),
            "area": meta.get("visitor_area", d.get("location", "")),
            "role": meta.get("visitor_role", ""),
            "fill_pct": min(100.0, round((last_wl / max(1.0, bankfull)) * 100.0, 1)),
            "pred_3h": round(pred_3h, 1),
            "delta_3h": delta_3h,
            "trend_label": trend_label,
            "trend_badge": trend_badge,
            "alert_level": cur_alert,
            "alert_badge": (
                "badge-safe" if cur_alert == "AMAN"
                else ("badge-warn" if cur_alert == "WASPADA"
                else ("badge-alert" if cur_alert == "SIAGA" else "badge-danger"))
            ),
        }
        node_preds[n.node_id] = lp_dict
        nodes.append(d)
    return nodes, node_preds


def _build_visitor_summary(nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Menyusun ringkasan kondisi air dalam bahasa sehari-hari untuk landing page pengunjung."""
    overall_alert = "AMAN"
    highest_rank = 0
    max_wl = 0.0
    max_pred_3h = 0.0
    max_rain = 0.0
    hum_vals: List[float] = []
    latest_seen = "-"

    for n in nodes:
        vis = n.get("visitor") or {}
        al = str(vis.get("alert_level") or "AMAN").upper()
        rank = _ALERT_RANK.get(al, 0)
        if rank >= highest_rank:
            highest_rank = rank
            overall_alert = al
        max_wl = max(max_wl, float(n.get("last_water_level") or 0.0))
        max_pred_3h = max(max_pred_3h, float(vis.get("pred_3h") or 0.0))
        max_rain = max(max_rain, float(n.get("last_rainfall") or 0.0))
        if n.get("last_air_humidity") is not None:
            hum_vals.append(float(n["last_air_humidity"]))
        seen = str(n.get("last_seen") or "")
        if seen and (latest_seen == "-" or seen > latest_seen):
            latest_seen = seen

    copy = _VISITOR_ALERT_COPY.get(overall_alert, _VISITOR_ALERT_COPY["AMAN"])
    avg_hum = round(sum(hum_vals) / len(hum_vals), 1) if hum_vals else 82.0
    if max_rain >= 20.0:
        rain_desc = "Hujan Lebat"
    elif max_rain >= 5.0:
        rain_desc = "Hujan Sedang"
    elif max_rain > 0.0:
        rain_desc = "Hujan Ringan"
    else:
        rain_desc = "Cerah / Tidak Hujan"

    return {
        "overall_alert": overall_alert,
        "headline": copy["headline"],
        "advice": copy["advice"],
        "badge_class": copy["badge_class"],
        "banner_class": copy["banner_class"],
        "max_water_cm": round(max_wl, 1),
        "max_pred_3h_cm": round(max_pred_3h, 1),
        "max_rainfall_mm": round(max_rain, 1),
        "rain_desc": rain_desc,
        "avg_humidity_pct": avg_hum,
        "latest_seen": latest_seen,
    }


def _build_dashboard_context() -> Dict[str, Any]:
    """Menyusun konteks data terpadu untuk halaman pengunjung maupun dashboard operasional."""
    nodes, node_preds = _get_nodes_with_predictions()
    latest_pred = AiPrediction.query.order_by(desc(AiPrediction.id)).first()
    latest_crop = CropdamxAssessment.query.order_by(desc(CropdamxAssessment.id)).first()
    recent_tel = [
        t.to_dict()
        for t in SensorTelemetry.query.order_by(desc(SensorTelemetry.id)).limit(15).all()
    ]
    total_area_ha = db.session.query(func.sum(GisFarmParcel.area_ha)).scalar() or 5853.74
    stats = {
        "total_telemetry": SensorTelemetry.query.count(),
        "total_predictions": AiPrediction.query.count(),
        "total_parcels": GisFarmParcel.query.count(),
        "total_area_ha": round(float(total_area_ha), 2),
        "total_farmer_groups": FarmerGroup.query.count(),
        "total_flood_events": FloodEvent.query.count(),
    }
    return {
        "nodes": nodes,
        "node_preds": node_preds,
        "latest_pred": latest_pred.to_dict() if latest_pred else {},
        "latest_crop": latest_crop.to_dict() if latest_crop else {},
        "recent_tel": recent_tel,
        "stats": stats,
        "visitor_summary": _build_visitor_summary(nodes),
    }


@app.route("/")
def page_landing():
    """Halaman depan publik (Landing Page humanize untuk pengunjung umum dan petani)."""
    ctx = _build_dashboard_context()
    return render_template("landing.html", active_page="landing", **ctx)


@app.route("/login", methods=["GET", "POST"])
def page_login():
    """Halaman masuk khusus Administrator dan Operator PEUSAGA."""
    raw_next = request.args.get("next") or request.form.get("next") or ""
    next_url = raw_next if _is_safe_next_url(raw_next) else url_for("page_dashboard")

    if session.get("user") and request.method == "GET":
        return redirect(next_url)

    error_msg: Optional[str] = None
    prefill_username = ""

    if request.method == "POST":
        if request.is_json:
            data = request.get_json(silent=True) or {}
            username = str(data.get("username", "")).strip()
            password = str(data.get("password", ""))
        else:
            username = str(request.form.get("username", "")).strip()
            password = str(request.form.get("password", ""))
        prefill_username = username
        user = SystemUser.query.filter_by(username=username).first()
        if not user or not user.is_active or not check_password_hash(user.password_hash, password):
            error_msg = "Nama pengguna atau kata sandi tidak valid."
            if request.is_json:
                return jsonify({"status": "error", "message": error_msg}), 401
            return (
                render_template(
                    "login.html",
                    active_page="login",
                    error_msg=error_msg,
                    next_url=next_url,
                    prefill_username=prefill_username,
                ),
                401,
            )

        session["user"] = user.to_dict()
        if request.is_json:
            return jsonify({"status": "ok", "user": session["user"], "redirect": next_url})
        return redirect(next_url)

    return render_template(
        "login.html",
        active_page="login",
        error_msg=error_msg,
        next_url=next_url,
        prefill_username=prefill_username,
    )


@app.route("/logout", methods=["GET", "POST"])
def page_logout():
    """Mengakhiri sesi Admin/Operator dan kembali ke Landing Page publik."""
    session.pop("user", None)
    return redirect(url_for("page_landing"))


@app.route("/dashboard")
@login_required
def page_dashboard():
    """Halaman operasional: Dashboard Pemantauan Real-time & WebGIS Multi-Layer."""
    ctx = _build_dashboard_context()
    return render_template("dashboard.html", active_page="dashboard", **ctx)


@app.route("/ai-lstm")
@login_required
def page_ai_lstm():
    """Halaman analitik model AI LSTM, proyeksi multi-horizon, dan klimatologi."""
    nodes, node_preds = _get_nodes_with_predictions()
    scenarios = [
        s.to_dict()
        for s in LstmEvaluationScenario.query.order_by(LstmEvaluationScenario.rmse_m).all()
    ]
    latest_preds = [
        p.to_dict()
        for p in AiPrediction.query.order_by(desc(AiPrediction.id)).limit(24).all()
    ]
    clim_points = load_climatology_points()
    clim_comp = load_climatology_comparison()
    model_status = ai_risk_engine.get_model_status(preload=False)
    charts = [c for c in list_chart_artifacts() if c["module"] == "01_LSTM_Muka_Air"]
    return render_template(
        "ai_lstm.html",
        active_page="ai_lstm",
        nodes=nodes,
        node_preds=node_preds,
        scenarios=scenarios,
        latest_preds=latest_preds,
        clim_points=clim_points,
        clim_comp=clim_comp[:24],
        model_status=model_status,
        charts=charts,
    )


@app.route("/cropdamx")
@login_required
def page_cropdamx():
    """Halaman DSS AHP-CROPDAM-X, 103 Petak Tersier, dan Validasi Historis Puso."""
    weights = [w.to_dict() for w in AhpWeight.query.order_by(AhpWeight.id).all()]
    parcels = [p.to_dict() for p in GisFarmParcel.query.order_by(GisFarmParcel.id).all()]
    flood_events = [
        f.to_dict() for f in FloodEvent.query.order_by(desc(FloodEvent.year), desc(FloodEvent.id)).limit(40).all()
    ]
    rice_meta = load_rice_variety_matrix()
    charts = [c for c in list_chart_artifacts() if c["module"] == "02_AHP_Cropdam-X"]
    return render_template(
        "cropdamx.html",
        active_page="cropdamx",
        weights=weights,
        parcels=parcels,
        flood_events=flood_events,
        varieties=rice_meta["varieties"],
        puso_records=rice_meta["puso"],
        charts=charts,
    )


@app.route("/console")
@login_required
def page_console():
    """Halaman konsol teknik IoT LoRa, kalibrasi node, link budget, otonomi daya, dan dump."""
    nodes, _ = _get_nodes_with_predictions()
    calibrations = [c.to_dict() for c in SensorCalibration.query.all()]
    dumps = [d.to_dict() for d in DumpMessage.query.order_by(desc(DumpMessage.id)).limit(40).all()]
    logs = [l.to_dict() for l in ApiLog.query.order_by(desc(ApiLog.id)).limit(40).all()]
    charts = [c for c in list_chart_artifacts() if c["module"] == "03_IoT_LoRa"]
    return render_template(
        "console.html",
        active_page="console",
        nodes=nodes,
        calibrations=calibrations,
        dumps=dumps,
        logs=logs,
        charts=charts,
    )


@app.route("/datasets")
@login_required
def page_datasets():
    """Halaman katalog baca-saja 13 dataset penelitian dan galeri bukti ilmiah."""
    catalog = list_all_datasets()
    charts = list_chart_artifacts()
    graph = load_canal_network_graph()
    return render_template(
        "datasets.html",
        active_page="datasets",
        catalog=catalog,
        charts=charts,
        graph_summary={
            "nodes": len(graph.get("nodes", [])) if isinstance(graph, dict) else 0,
            "edges": len(graph.get("edges", [])) if isinstance(graph, dict) else 0,
        },
    )


@app.route("/admin")
@login_required
def page_admin():
    """Halaman administrasi autentikasi, ambang siaga, webhook diseminasi, dan 69 desa poktan."""
    users = [u.to_dict() for u in SystemUser.query.all()]
    settings = [s.to_dict() for s in SystemSetting.query.all()]
    groups = [g.to_dict() for g in FarmerGroup.query.order_by(FarmerGroup.id).limit(100).all()]
    broadcasts = [b.to_dict() for b in BroadcastLog.query.order_by(desc(BroadcastLog.id)).limit(30).all()]
    return render_template(
        "admin.html",
        active_page="admin",
        users=users,
        settings=settings,
        groups=groups,
        total_groups=FarmerGroup.query.count(),
        broadcasts=broadcasts,
        current_user=session.get("user"),
    )


# ==============================================================================
# RUTE INGESTI HARDWARE ARDUINO / ESP32 (KOMPATIBEL MUNDUR)
# ==============================================================================

@app.route("/api", methods=["GET", "POST"])
@app.route("/api_ews.php", methods=["GET", "POST"])
def api_ingest_ews():
    return _handle_iot_ingestion()


# ==============================================================================
# RUTE REAL-TIME SSE STREAM & TELEMETRI DELTA
# ==============================================================================

@app.route("/api/stream")
def api_sse_stream():
    """Mengalirkan pembaruan telemetri real-time via Server-Sent Events (SSE)."""
    q: queue.Queue = queue.Queue(maxsize=50)
    _SSE_CLIENTS.append(q)

    def event_gen():
        try:
            init_nodes, _ = _get_nodes_with_predictions()
            init_payload = {
                "connected_at": now_wib_str(),
                "nodes": init_nodes,
            }
            yield f"event: connected\ndata: {json.dumps(init_payload, ensure_ascii=False)}\n\n"
            while True:
                try:
                    msg = q.get(timeout=8)
                    yield msg
                except queue.Empty:
                    hb = json.dumps({"ts": now_wib_str()})
                    yield f"event: heartbeat\ndata: {hb}\n\n"
        finally:
            if q in _SSE_CLIENTS:
                _SSE_CLIENTS.remove(q)

    return Response(
        stream_with_context(event_gen()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/api/nodes")
@app.route("/api/status")
def api_nodes():
    nodes, node_preds = _get_nodes_with_predictions()
    return jsonify({
        "status": "ok",
        "nodes": nodes,
        "predictions_by_node": node_preds,
        "visitor_summary": _build_visitor_summary(nodes),
    })


@app.route("/api/telemetry")
def api_telemetry_latest():
    limit = min(200, int(request.args.get("limit", 40)))
    node_id = request.args.get("node_id")
    q = SensorTelemetry.query
    if node_id:
        q = q.filter_by(node_id=node_id)
    rows = [r.to_dict() for r in q.order_by(desc(SensorTelemetry.id)).limit(limit).all()]
    return jsonify({"status": "ok", "count": len(rows), "telemetry": rows})


@app.route("/api/telemetry/history")
def api_telemetry_history():
    since_id = int(request.args.get("since_id", 0))
    limit = min(200, int(request.args.get("limit", 60)))
    node_id = request.args.get("node_id")
    q = SensorTelemetry.query
    if node_id:
        q = q.filter_by(node_id=node_id)
    if since_id > 0:
        q = q.filter(SensorTelemetry.id > since_id).order_by(SensorTelemetry.id.asc())
    else:
        q = q.order_by(desc(SensorTelemetry.id))
    rows = [r.to_dict() for r in q.limit(limit).all()]
    if since_id == 0:
        rows.reverse()
    max_id = max([r["id"] for r in rows], default=since_id)
    return jsonify({"status": "ok", "since_id": since_id, "max_id": max_id, "records": rows})


@app.route("/api/calibration", methods=["GET", "POST"])
@api_login_required
def api_calibration():
    if request.method == "GET":
        node_id = request.args.get("node_id")
        if node_id:
            cal = db.session.get(SensorCalibration, node_id)
            if not cal:
                return jsonify({"status": "error", "message": "Node tidak ditemukan"}), 404
            return jsonify({"status": "ok", "calibration": cal.to_dict()})
        return jsonify({"status": "ok", "calibrations": [c.to_dict() for c in SensorCalibration.query.all()]})

    data = request.get_json(silent=True) or {}
    node_id = data.get("node_id", "node_hulu")
    cal = db.session.get(SensorCalibration, node_id)
    if not cal:
        cal = SensorCalibration(node_id=node_id)
        db.session.add(cal)

    numeric_fields = [
        "pole_height_cm", "water_level_offset_cm", "rain_multiplier",
        "soil_offset_pct", "water_temp_offset_c", "air_temp_offset_c",
        "air_hum_offset_pct", "battery_multiplier", "battery_offset_v",
        "bankfull_level_cm",
    ]
    for fld in numeric_fields:
        if fld in data and data[fld] != "":
            setattr(cal, fld, float(data[fld]))
    for int_fld in ("soil_air_raw", "soil_water_raw"):
        if int_fld in data and data[int_fld] != "":
            setattr(cal, int_fld, int(float(data[int_fld])))
    cal.updated_at = now_wib_str()
    db.session.commit()
    return jsonify({"status": "ok", "calibration": cal.to_dict()})


# ==============================================================================
# RUTE PREDIKSI AI LSTM & ANALISIS RISIKO AHP-CROPDAM-X
# ==============================================================================

@app.route("/api/predict", methods=["POST"])
@api_login_required
def api_predict_lstm():
    data = request.get_json(silent=True) or {}
    node_id = data.get("node_id", "node_hulu")
    cal = db.session.get(SensorCalibration, node_id)
    bankfull = float(data.get("bankfull_cm") or (cal.bankfull_level_cm if cal else 180.0))

    seq_wl = data.get("water_levels_cm")
    seq_rf = data.get("rainfall_mm")
    if not seq_wl:
        rows = (
            SensorTelemetry.query.filter_by(node_id=node_id)
            .order_by(desc(SensorTelemetry.id))
            .limit(24)
            .all()
        )
        rows = list(reversed(rows))
        seq_wl = [float(r.water_level or 120.0) for r in rows]
        seq_rf = [float(r.rainfall or 0.0) for r in rows]
        if data.get("override_current_cm") is not None and seq_wl:
            seq_wl[-1] = float(data["override_current_cm"])
        if data.get("override_rain_mm") is not None and seq_rf:
            seq_rf[-1] = float(data["override_rain_mm"])

    res = ai_risk_engine.predict_water_level(
        water_levels_cm=[float(x) for x in seq_wl],
        rainfall_mm=[float(x) for x in (seq_rf or [])],
        soil_moisture_pct=float(data.get("soil_moisture_pct", 65.0)),
        air_humidity_pct=float(data.get("air_humidity_pct", 82.0)),
        air_temp_c=float(data.get("air_temp_c", 28.5)),
        bankfull_cm=bankfull,
    )

    if data.get("save", True):
        pred_row = AiPrediction(
            node_id=node_id,
            input_window_size=len(seq_wl),
            current_water_level=res["current_water_level_cm"],
            pred_plus_1h=res["pred_plus_1h"],
            pred_plus_2h=res["pred_plus_2h"],
            pred_plus_3h=res["pred_plus_3h"],
            pred_plus_6h=res["pred_plus_6h"],
            pred_plus_7h=res["pred_plus_7h"],
            model_source=res["model_source"],
            alert_level=res["alert_level"],
            inference_time_ms=res["inference_time_ms"],
            created_at=now_wib_str(),
        )
        db.session.add(pred_row)
        db.session.commit()
        res["saved_id"] = pred_row.id

    return jsonify({"status": "ok", "node_id": node_id, "prediction": res})


@app.route("/api/lstm/scenarios")
def api_lstm_scenarios():
    rows = [s.to_dict() for s in LstmEvaluationScenario.query.order_by(LstmEvaluationScenario.rmse_m).all()]
    return jsonify({"status": "ok", "scenarios": rows})


@app.route("/api/risk/cropdamx", methods=["POST"])
@api_login_required
def api_cropdamx_evaluate():
    data = request.get_json(silent=True) or {}
    depth_cm = float(data.get("depth_cm", 65.0))
    duration_h = float(data.get("duration_hours", 36.0))
    velocity_kmh = float(data.get("velocity_kmh", 4.5))
    stage = str(data.get("growth_stage", "Reproduktif"))
    variety = str(data.get("crop_type", "Ciherang"))
    topo_risk = float(data.get("topo_risk", 0.5))
    drainage_modulus = float(data.get("drainage_modulus", 0.526))
    dist_river_m = float(data.get("dist_river_m", 500.0))

    cfai = ai_risk_engine.compute_cfai(
        depth_cm=depth_cm,
        duration_h=duration_h,
        velocity_kmh=velocity_kmh,
        stage=stage,
        variety=variety,
        topo_risk=topo_risk,
        drainage_modulus=drainage_modulus,
        dist_river_m=dist_river_m,
    )
    surrogate = ai_risk_engine.predict_surrogate(depth_cm, duration_h, stage, variety)
    sensitivity = ai_risk_engine.sensitivity_analysis(depth_cm, duration_h, velocity_kmh, stage, variety)

    if data.get("save", False):
        rec = CropdamxAssessment(
            petak_code=str(data.get("petak_code", "SIMULASI")),
            crop_type=variety,
            growth_stage=stage,
            predicted_water_level=depth_cm,
            flood_duration_hours=duration_h,
            cfai_score=cfai["cfai_score"],
            rf_surrogate_score=surrogate.get("rf_surrogate_score"),
            bayes_sigma=surrogate.get("bayes_sigma"),
            risk_category=cfai["risk_category"],
            recommendation=cfai["recommendation"],
            created_at=now_wib_str(),
        )
        db.session.add(rec)
        db.session.commit()

    return jsonify({
        "status": "ok",
        "cfai": cfai,
        "surrogate": surrogate,
        "sensitivity": sensitivity,
    })


@app.route("/api/cropdamx/parcels")
def api_cropdamx_parcels():
    risk_filter = request.args.get("risk")
    search = (request.args.get("search") or "").strip().lower()
    q = GisFarmParcel.query
    if risk_filter:
        q = q.filter_by(risk_category=risk_filter)
    rows = [p.to_dict() for p in q.order_by(desc(GisFarmParcel.cfai_awas)).all()]
    if search:
        rows = [
            r for r in rows
            if search in (r["kode_petak"] or "").lower()
            or search in (r["sistem_saluran"] or "").lower()
        ]
    return jsonify({"status": "ok", "count": len(rows), "parcels": rows})


@app.route("/api/cropdamx/weights")
def api_cropdamx_weights():
    return jsonify({"status": "ok", "weights": [w.to_dict() for w in AhpWeight.query.all()]})


@app.route("/api/cropdamx/flood-events")
def api_flood_events():
    year = request.args.get("year")
    q = FloodEvent.query
    if year:
        q = q.filter_by(year=int(year))
    rows = [r.to_dict() for r in q.order_by(desc(FloodEvent.event_date)).limit(150).all()]
    return jsonify({"status": "ok", "count": len(rows), "events": rows})


# ==============================================================================
# RUTE WEBGIS MULTI-LAYER
# ==============================================================================

@app.route("/api/gis/layers")
def api_gis_layers():
    """Mengembalikan seluruh lapisan WebGIS (3 Node IoT Pante Lhong, 103 Petak, Grid & Survei)."""
    nodes, _ = _get_nodes_with_predictions()
    locations = [l.to_dict() for l in GisLocation.query.all()]
    parcels = [p.to_dict() for p in GisFarmParcel.query.all()]
    channels = [c.to_dict() for c in GisRiverChannel.query.all()]
    pante_layers = load_pante_lhong_layers()
    cad_sawah = load_pante_lhong_sawah()
    stage2 = load_stage2_topology()

    return jsonify({
        "status": "ok",
        "iot_nodes": nodes,
        "iot_stage2": stage2,
        "locations": locations,
        "parcels": parcels,
        "cad_sawah": cad_sawah,
        "channels": channels,
        "benchmarks": pante_layers.get("BENCHMARKS", []),
        "structures": pante_layers.get("STRUCTURES", []),
        "rawa_suplesi": pante_layers.get("RAWA_SUPLESI", []),
        "embung": pante_layers.get("EMBUNG", []),
        "boundaries": pante_layers.get("BOUNDARIES", []),
        "land_use_zones": pante_layers.get("LAND_USE_ZONES", []),
        "admin_places": pante_layers.get("ADMIN_PLACES", []),
    })


@app.route("/api/gis/cad-extras")
def api_gis_cad_extras():
    """Mengembalikan lapisan CAD sekunder (tata guna lahan, jalan, kontur) secara lazy-load."""
    extras = load_pante_lhong_cad_extras()
    return jsonify({
        "status": "ok",
        **extras,
    })


@app.route("/api/gis/location", methods=["POST"])
@api_login_required
def api_gis_add_location():
    data = request.get_json(silent=True) or {}
    loc = GisLocation(
        name=sanitize_research_text(data.get("name", "Titik Baru")),
        category=str(data.get("category", "custom_point")),
        latitude=float(data.get("latitude", 5.18)),
        longitude=float(data.get("longitude", 96.76)),
        elevation_m=float(data.get("elevation_m", 10.0)),
        description=sanitize_research_text(data.get("description", "")),
        layer_group=str(data.get("layer_group", "custom")),
        updated_at=now_wib_str(),
    )
    db.session.add(loc)
    db.session.commit()
    return jsonify({"status": "ok", "location": loc.to_dict()}), 201


@app.route("/api/gis/parcel", methods=["POST"])
@api_login_required
def api_gis_add_parcel():
    data = request.get_json(silent=True) or {}
    coords = data.get("coordinates") or [[5.18, 96.76], [5.183, 96.76], [5.183, 96.764], [5.18, 96.764]]
    parcel = GisFarmParcel(
        kode_petak=str(data.get("kode_petak", f"CUSTOM.{int(time.time()) % 1000}")),
        name=str(data.get("name", "Petak Sawah Tambahan")),
        crop_type=str(data.get("crop_type", "Padi Varietas Ciherang")),
        growth_stage=str(data.get("growth_stage", "Reproduktif")),
        area_ha=float(data.get("area_ha", 25.0)),
        sistem_saluran=str(data.get("sistem_saluran", "Input Manual Operator")),
        orientasi=str(data.get("orientasi", "Kanan")),
        modulus_l_s_ha=float(data.get("modulus_l_s_ha", 0.526)),
        geojson_coords=json.dumps(coords),
        cfai_siaga=0.35,
        cfai_awas=0.60,
        cfai_ekstrem=0.80,
        risk_category="Tinggi",
    )
    db.session.add(parcel)
    db.session.commit()
    return jsonify({"status": "ok", "parcel": parcel.to_dict()}), 201


# ==============================================================================
# RUTE KALKULATOR TEKNIK LORA, DAYA SURYA, SIMULATOR, & DUMP
# ==============================================================================

@app.route("/api/lora/link-budget", methods=["POST"])
@api_login_required
def api_lora_link_budget():
    data = request.get_json(silent=True) or {}
    res = ai_risk_engine.calculate_lora_link_budget(
        distance_km=float(data.get("distance_km", 7.387)),
        rain_mm_h=float(data.get("rain_mm_h", 20.0)),
        sf=int(data.get("sf", 9)),
        tx_power_dbm=float(data.get("tx_power_dbm", 20.0)),
        payload_bytes=int(data.get("payload_bytes", 42)),
        freq_mhz=float(data.get("freq_mhz", 915.0)),
    )
    return jsonify({"status": "ok", "result": res})


@app.route("/api/iot/power-autonomy", methods=["POST"])
@api_login_required
def api_power_autonomy():
    data = request.get_json(silent=True) or {}
    res = ai_risk_engine.calculate_power_autonomy(
        battery_wh=float(data.get("battery_wh", 57.72)),
        avg_load_w=float(data.get("avg_load_w", 0.6804)),
        panel_wp=float(data.get("panel_wp", 10.0)),
        sun_hours_per_day=float(data.get("sun_hours_per_day", 3.8)),
        rainy_days_no_sun=int(data.get("rainy_days_no_sun", 3)),
    )
    return jsonify({"status": "ok", "result": res})


@app.route("/api/iot/simulate", methods=["POST"])
@app.route("/api/simulate", methods=["POST"])
@api_login_required
def api_iot_simulate():
    """Menjalankan simulasi kirim paket telemetri atau SOS lewat pipeline ingesti resmi."""
    data = request.get_json(silent=True) or {}
    node_id = str(data.get("node_id", "node_hulu"))
    mode = str(data.get("mode", "normal"))

    key_lookup = {
        "node_hulu": os.getenv("HULU_NODE_KEY", "KEY_PEUSANGAN_HULU_915"),
        "node_hilir": os.getenv("HILIR_NODE_KEY", "KEY_PEUSANGAN_HILIR_915"),
        "node_gateway": os.getenv("GATEWAY_DEFAULT_KEY", "KEY_PEUSANGAN_GATEWAY_915"),
    }

    if node_id == "all":
        node_profiles = {
            "node_hulu": {"wl": float(data.get("water_level", 162.0)), "rf": float(data.get("rainfall", 22.0)), "rssi": -72},
            "node_hilir": {"wl": float(data.get("hilir_water_level", 134.0)), "rf": float(data.get("rainfall", 18.5)), "rssi": -79},
            "node_gateway": {"wl": float(data.get("gateway_water_level", 112.0)), "rf": float(data.get("rainfall", 15.0)), "rssi": -84},
        }
        results = []
        with app.test_client() as tc:
            for nid, prof in node_profiles.items():
                resp = tc.post(
                    "/api",
                    json={
                        "node_id": nid,
                        "api_key": key_lookup.get(nid, ""),
                        "water_level": prof["wl"],
                        "rainfall": prof["rf"],
                        "soil_moisture": data.get("soil_moisture", 74.0),
                        "air_temp": data.get("air_temp", 27.4),
                        "air_humidity": data.get("air_humidity", 86.0),
                        "water_temp": data.get("water_temp", 25.2),
                        "battery_voltage": data.get("battery_voltage", 12.15),
                        "rssi": prof["rssi"],
                        "snr": data.get("snr", 9.8),
                    },
                )
                results.append(resp.get_json())
        return jsonify({"status": "ok", "http_code": 200, "mode": "all", "results": results}), 200

    with app.test_client() as tc:
        if mode == "sos":
            resp = tc.post(
                "/api",
                json={
                    "node_id": node_id,
                    "api_key": key_lookup.get(node_id, ""),
                    "is_emergency": 1,
                    "message_type": "EMERGENCY_SOS",
                    "emergency_text": data.get("emergency_text", "Peringatan darurat banjir luapan tanggul"),
                    "rssi": data.get("rssi", -88),
                    "snr": data.get("snr", 6.5),
                },
            )
        else:
            resp = tc.post(
                "/api",
                json={
                    "node_id": node_id,
                    "api_key": key_lookup.get(node_id, ""),
                    "water_level": data.get("water_level", 148.5),
                    "rainfall": data.get("rainfall", 18.2),
                    "soil_moisture": data.get("soil_moisture", 74.0),
                    "air_temp": data.get("air_temp", 27.4),
                    "air_humidity": data.get("air_humidity", 86.0),
                    "water_temp": data.get("water_temp", 25.2),
                    "battery_voltage": data.get("battery_voltage", 12.15),
                    "rssi": data.get("rssi", -74),
                    "snr": data.get("snr", 10.2),
                },
            )
    return jsonify({"status": "ok", "http_code": resp.status_code, "upstream": resp.get_json()}), resp.status_code


@app.route("/api/dumps")
@api_login_required
def api_dumps():
    rows = [d.to_dict() for d in DumpMessage.query.order_by(desc(DumpMessage.id)).limit(100).all()]
    return jsonify({"status": "ok", "dumps": rows})


@app.route("/api/logs")
@api_login_required
def api_logs():
    rows = [l.to_dict() for l in ApiLog.query.order_by(desc(ApiLog.id)).limit(100).all()]
    return jsonify({"status": "ok", "logs": rows})


# ==============================================================================
# RUTE DISEMINASI PERINGATAN & WEBHOOK TELEGRAM/WHATSAPP
# ==============================================================================

@app.route("/api/broadcast", methods=["POST"])
@api_login_required
def api_broadcast_alert():
    """Mengirim atau mensimulasikan siaran peringatan dini ke kelompok tani dan BPBD."""
    data = request.get_json(silent=True) or {}
    channel = str(data.get("channel", "Telegram")).strip()
    recipient = str(data.get("recipient_group", "69 Desa Kelompok Tani D.I. Pante Lhong & BPBD Bireuen")).strip()
    alert_level = str(data.get("alert_level", "SIAGA")).strip()
    message_text = sanitize_research_text(
        str(data.get("message_text", "Peringatan Dini PEUSAGA: Elevasi TMA meningkat, siapkan drainase petak."))
    )
    dry_run_setting = SystemSetting.query.get("webhook_dry_run")
    dry_run = (os.getenv("WEBHOOK_DRY_RUN", "true").lower() == "true") or (
        dry_run_setting and dry_run_setting.setting_value.lower() == "true"
    )

    status = "SIMULATED"
    http_code = 200
    summary = "Diseminasi tercatat dalam mode simulasi aman (WEBHOOK_DRY_RUN=true)."

    if not dry_run:
        if channel.lower() == "telegram":
            token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
            chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
            if token and chat_id:
                try:
                    r = http_requests.post(
                        f"https://api.telegram.org/bot{token}/sendMessage",
                        json={"chat_id": chat_id, "text": f"[{alert_level}] {message_text}"},
                        timeout=6,
                    )
                    http_code = r.status_code
                    status = "SENT" if r.ok else "FAILED"
                    summary = r.text[:250]
                except Exception as exc:
                    status = "FAILED"
                    http_code = 502
                    summary = str(exc)[:250]
            else:
                summary = "Token/Chat ID Telegram belum diisi di .env; dialihkan ke log lokal."
        elif channel.lower() == "whatsapp":
            wh_url = os.getenv("WHATSAPP_WEBHOOK_URL", "").strip()
            wh_token = os.getenv("WHATSAPP_API_TOKEN", "").strip()
            if wh_url:
                try:
                    headers = {"Authorization": f"Bearer {wh_token}"} if wh_token else {}
                    r = http_requests.post(
                        wh_url,
                        json={"recipient": recipient, "alert_level": alert_level, "message": message_text},
                        headers=headers,
                        timeout=6,
                    )
                    http_code = r.status_code
                    status = "SENT" if r.ok else "FAILED"
                    summary = r.text[:250]
                except Exception as exc:
                    status = "FAILED"
                    http_code = 502
                    summary = str(exc)[:250]
            else:
                summary = "WHATSAPP_WEBHOOK_URL belum dikonfigurasi di .env; dialihkan ke log lokal."

    entry = BroadcastLog(
        channel=channel,
        recipient_group=recipient,
        alert_level=alert_level,
        message_text=message_text,
        status=status,
        http_code=http_code,
        response_summary=summary,
        triggered_by=(session.get("user") or {}).get("username", "operator"),
        created_at=now_wib_str(),
    )
    db.session.add(entry)
    db.session.commit()
    _broadcast_sse("alert", entry.to_dict())
    return jsonify({"status": "ok", "broadcast": entry.to_dict()})


@app.route("/api/broadcast/logs")
@api_login_required
def api_broadcast_logs():
    rows = [b.to_dict() for b in BroadcastLog.query.order_by(desc(BroadcastLog.id)).limit(50).all()]
    return jsonify({"status": "ok", "logs": rows})


# ==============================================================================
# RUTE KATALOG 13 DATASET PENELITIAN & GRAFIK BUKTI ILMIAH
# ==============================================================================

@app.route("/api/datasets/catalog")
@api_login_required
def api_datasets_catalog():
    return jsonify({"status": "ok", "datasets": list_all_datasets(), "charts": list_chart_artifacts()})


@app.route("/api/datasets/preview")
@api_login_required
def api_datasets_preview():
    rel_path = request.args.get("path", "")
    limit = min(100, int(request.args.get("limit", 40)))
    data, err = preview_dataset_file(rel_path, limit=limit)
    if err:
        return jsonify({"status": "error", "message": err}), 400
    return jsonify({"status": "ok", "preview": data})


@app.route("/api/datasets/chart/<path:rel_path>")
@api_login_required
def api_datasets_chart(rel_path: str):
    fp = resolve_safe_research_file(rel_path)
    if fp is None or fp.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        abort(404)
    return send_file(str(fp))


@app.route("/api/datasets/climatology")
@api_login_required
def api_datasets_climatology():
    return jsonify({
        "status": "ok",
        "points": load_climatology_points(),
        "comparison": load_climatology_comparison(),
    })


@app.route("/api/datasets/graph")
@api_login_required
def api_datasets_graph():
    return jsonify({"status": "ok", "graph": load_canal_network_graph()})


@app.route("/api/datasets/varieties")
@api_login_required
def api_datasets_varieties():
    return jsonify({"status": "ok", "data": load_rice_variety_matrix()})


# ==============================================================================
# RUTE AUTENTIKASI & PENGATURAN SISTEM
# ==============================================================================

@app.route("/api/auth/login", methods=["POST"])
def api_auth_login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    user = SystemUser.query.filter_by(username=username).first()
    if not user or not user.is_active or not check_password_hash(user.password_hash, password):
        return jsonify({"status": "error", "message": "Nama pengguna atau kata sandi tidak cocok."}), 401
    session["user"] = user.to_dict()
    return jsonify({"status": "ok", "user": session["user"]})


@app.route("/api/auth/logout", methods=["POST"])
def api_auth_logout():
    session.pop("user", None)
    return jsonify({"status": "ok"})


@app.route("/api/auth/status")
def api_auth_status():
    return jsonify({"status": "ok", "user": session.get("user")})


@app.route("/api/admin/settings", methods=["GET", "POST"])
@api_login_required
def api_admin_settings():
    if request.method == "GET":
        return jsonify({"status": "ok", "settings": [s.to_dict() for s in SystemSetting.query.all()]})

    data = request.get_json(silent=True) or {}
    updates = data.get("settings") or data
    for k, v in updates.items():
        row = db.session.get(SystemSetting, k)
        if row:
            row.setting_value = str(v)
            row.updated_at = now_wib_str()
        else:
            db.session.add(
                SystemSetting(
                    setting_key=str(k),
                    setting_value=str(v),
                    category="custom",
                    updated_at=now_wib_str(),
                )
            )
    db.session.commit()
    return jsonify({"status": "ok", "settings": [s.to_dict() for s in SystemSetting.query.all()]})


@app.route("/api/system/status")
def api_system_status():
    """Ringkasan kesehatan sistem backend, MySQL, dan model AI."""
    return jsonify({
        "status": "ok",
        "database": "MySQL 8.0 Connected",
        "ai_engine": ai_risk_engine.get_model_status(preload=False),
        "counts": {
            "nodes": NodeStatus.query.count(),
            "telemetry": SensorTelemetry.query.count(),
            "predictions": AiPrediction.query.count(),
            "cropdamx": CropdamxAssessment.query.count(),
            "parcels": GisFarmParcel.query.count(),
            "farmer_groups": FarmerGroup.query.count(),
            "flood_events": FloodEvent.query.count(),
        },
        "server_time_wib": now_wib_str(),
    })


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
