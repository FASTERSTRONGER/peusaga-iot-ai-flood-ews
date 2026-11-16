"""Definisi model SQLAlchemy untuk basis data MySQL 8.0 PEUSAGA."""
from datetime import datetime, timezone, timedelta
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.mysql import LONGTEXT

db = SQLAlchemy()
WIB = timezone(timedelta(hours=7))


def now_wib_str() -> str:
    """Mengembalikan stempel waktu WIB format ISO standar basis data."""
    return datetime.now(WIB).strftime("%Y-%m-%d %H:%M:%S")


class NodeStatus(db.Model):
    """Status terkini masing-masing node IoT LoRa di DAS Peusangan dan D.I. Pante Lhong."""
    __tablename__ = "node_status"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    node_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    name = db.Column(db.String(128), nullable=False)
    location = db.Column(db.String(192))
    stage = db.Column(db.String(64), default="Optimal Pante Lhong (10,439 km)")
    status = db.Column(db.String(32), default="offline")
    last_seen = db.Column(db.String(32))
    last_rssi = db.Column(db.Integer)
    last_snr = db.Column(db.Float)
    last_water_level = db.Column(db.Float)
    last_rainfall = db.Column(db.Float)
    last_soil_moisture = db.Column(db.Float)
    last_water_temp = db.Column(db.Float)
    last_air_temp = db.Column(db.Float)
    last_air_humidity = db.Column(db.Float)
    last_battery = db.Column(db.Float)
    last_battery_soc = db.Column(db.Integer)
    last_signal_quality = db.Column(db.Integer)
    packets_received = db.Column(db.Integer, default=0)
    auth_key = db.Column(db.String(128))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    elevation_m = db.Column(db.Float)
    notes = db.Column(db.Text)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "node_id": self.node_id,
            "name": self.name,
            "location": self.location,
            "stage": self.stage,
            "status": self.status,
            "last_seen": self.last_seen,
            "last_rssi": self.last_rssi,
            "last_snr": self.last_snr,
            "last_water_level": self.last_water_level,
            "last_rainfall": self.last_rainfall,
            "last_soil_moisture": self.last_soil_moisture,
            "last_water_temp": self.last_water_temp,
            "last_air_temp": self.last_air_temp,
            "last_air_humidity": self.last_air_humidity,
            "last_battery": self.last_battery,
            "last_battery_soc": self.last_battery_soc,
            "last_signal_quality": self.last_signal_quality,
            "packets_received": self.packets_received or 0,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "elevation_m": self.elevation_m,
            "notes": self.notes,
        }


class SensorTelemetry(db.Model):
    """Rekaman deret waktu telemetri sensor multi-parameter node IoT."""
    __tablename__ = "sensor_telemetry"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    node_id = db.Column(db.String(64), index=True)
    water_level = db.Column(db.Float)
    rainfall = db.Column(db.Float)
    soil_moisture = db.Column(db.Float)
    water_temp = db.Column(db.Float)
    air_temp = db.Column(db.Float)
    air_humidity = db.Column(db.Float)
    battery_voltage = db.Column(db.Float)
    rssi = db.Column(db.Integer)
    snr = db.Column(db.Float)
    raw_payload = db.Column(db.Text)
    log_id = db.Column(db.Integer)
    created_at = db.Column(db.String(32), index=True, default=now_wib_str)
    relay_hops = db.Column(db.Integer, default=0)
    auth_key = db.Column(db.String(128))
    battery_soc_pct = db.Column(db.Integer)
    signal_quality_pct = db.Column(db.Integer)
    distance = db.Column(db.Float)
    soil_adc = db.Column(db.Integer)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "node_id": self.node_id,
            "water_level": self.water_level,
            "rainfall": self.rainfall,
            "soil_moisture": self.soil_moisture,
            "water_temp": self.water_temp,
            "air_temp": self.air_temp,
            "air_humidity": self.air_humidity,
            "battery_voltage": self.battery_voltage,
            "rssi": self.rssi,
            "snr": self.snr,
            "relay_hops": self.relay_hops,
            "battery_soc_pct": self.battery_soc_pct,
            "signal_quality_pct": self.signal_quality_pct,
            "distance": self.distance,
            "soil_adc": self.soil_adc,
            "created_at": self.created_at,
        }


class AiPrediction(db.Model):
    """Hasil prediksi tinggi muka air (TMA) multi-horizon berbasis LSTM."""
    __tablename__ = "ai_predictions"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    node_id = db.Column(db.String(64), index=True)
    input_window_size = db.Column(db.Integer, default=24)
    current_water_level = db.Column(db.Float)
    pred_plus_1h = db.Column(db.Float)
    pred_plus_2h = db.Column(db.Float)
    pred_plus_3h = db.Column(db.Float)
    pred_plus_6h = db.Column(db.Float)
    pred_plus_7h = db.Column(db.Float)
    model_source = db.Column(db.String(64), default="keras_lstm_t3h")
    alert_level = db.Column(db.String(128))
    inference_time_ms = db.Column(db.Float)
    created_at = db.Column(db.String(32), index=True, default=now_wib_str)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "node_id": self.node_id,
            "input_window_size": self.input_window_size,
            "current_water_level": self.current_water_level,
            "pred_plus_1h": self.pred_plus_1h,
            "pred_plus_2h": self.pred_plus_2h,
            "pred_plus_3h": self.pred_plus_3h,
            "pred_plus_6h": self.pred_plus_6h,
            "pred_plus_7h": self.pred_plus_7h,
            "model_source": self.model_source,
            "alert_level": self.alert_level,
            "inference_time_ms": self.inference_time_ms,
            "created_at": self.created_at,
        }


class CropdamxAssessment(db.Model):
    """Riwayat evaluasi indeks kerentanan banjir tanaman padi (CFAI)."""
    __tablename__ = "cropdamx_assessments"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    petak_code = db.Column(db.String(32), default="UMUM")
    crop_type = db.Column(db.String(128))
    growth_stage = db.Column(db.String(64))
    predicted_water_level = db.Column(db.Float)
    flood_duration_hours = db.Column(db.Float)
    cfai_score = db.Column(db.Float)
    rf_surrogate_score = db.Column(db.Float)
    bayes_sigma = db.Column(db.Float)
    risk_category = db.Column(db.String(64), index=True)
    recommendation = db.Column(db.Text)
    created_at = db.Column(db.String(32), index=True, default=now_wib_str)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "petak_code": self.petak_code,
            "crop_type": self.crop_type,
            "growth_stage": self.growth_stage,
            "predicted_water_level": self.predicted_water_level,
            "flood_duration_hours": self.flood_duration_hours,
            "cfai_score": self.cfai_score,
            "rf_surrogate_score": self.rf_surrogate_score,
            "bayes_sigma": self.bayes_sigma,
            "risk_category": self.risk_category,
            "recommendation": self.recommendation,
            "created_at": self.created_at,
        }


class DumpMessage(db.Model):
    """Karantina paket LoRa non-standar dan siaran darurat SOS."""
    __tablename__ = "dump_messages"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    source_identifier = db.Column(db.String(255))
    provided_key = db.Column(db.String(255))
    message_type = db.Column(db.String(128))
    is_emergency = db.Column(db.Integer, default=0, index=True)
    emergency_text = db.Column(db.Text)
    rssi = db.Column(db.Integer)
    snr = db.Column(db.Float)
    raw_payload = db.Column(db.Text)
    log_id = db.Column(db.Integer)
    created_at = db.Column(db.String(32), index=True, default=now_wib_str)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_identifier": self.source_identifier,
            "provided_key": self.provided_key,
            "message_type": self.message_type,
            "is_emergency": self.is_emergency,
            "emergency_text": self.emergency_text,
            "rssi": self.rssi,
            "snr": self.snr,
            "raw_payload": self.raw_payload,
            "created_at": self.created_at,
        }


class SensorCalibration(db.Model):
    """Parameter kalibrasi jarak sensor JSN-SR04T dan sensor agronomi per node."""
    __tablename__ = "sensor_calibrations"

    node_id = db.Column(db.String(64), primary_key=True)
    pole_height_cm = db.Column(db.Float, default=250.0)
    water_level_offset_cm = db.Column(db.Float, default=0.0)
    rain_multiplier = db.Column(db.Float, default=0.2794)
    soil_air_raw = db.Column(db.Integer, default=4095)
    soil_water_raw = db.Column(db.Integer, default=1200)
    soil_offset_pct = db.Column(db.Float, default=0.0)
    water_temp_offset_c = db.Column(db.Float, default=0.0)
    air_temp_offset_c = db.Column(db.Float, default=0.0)
    air_hum_offset_pct = db.Column(db.Float, default=0.0)
    battery_multiplier = db.Column(db.Float, default=1.0)
    battery_offset_v = db.Column(db.Float, default=0.0)
    bankfull_level_cm = db.Column(db.Float, default=180.0)
    updated_at = db.Column(db.String(32), default=now_wib_str)

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "pole_height_cm": self.pole_height_cm,
            "water_level_offset_cm": self.water_level_offset_cm,
            "rain_multiplier": self.rain_multiplier,
            "soil_air_raw": self.soil_air_raw,
            "soil_water_raw": self.soil_water_raw,
            "soil_offset_pct": self.soil_offset_pct,
            "water_temp_offset_c": self.water_temp_offset_c,
            "air_temp_offset_c": self.air_temp_offset_c,
            "air_hum_offset_pct": self.air_hum_offset_pct,
            "battery_multiplier": self.battery_multiplier,
            "battery_offset_v": self.battery_offset_v,
            "bankfull_level_cm": self.bankfull_level_cm,
            "updated_at": self.updated_at,
        }


class ApiLog(db.Model):
    """Audit log transaksi HTTP ingesti dan pemanggilan endpoint API."""
    __tablename__ = "api_logs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    method = db.Column(db.String(32), index=True)
    uri = db.Column(db.Text)
    path = db.Column(db.String(255), index=True)
    query_string = db.Column(db.Text)
    query_params = db.Column(db.Text)
    headers = db.Column(db.Text)
    payload_raw = db.Column(db.Text)
    payload_parsed = db.Column(db.Text)
    payload_type = db.Column(db.String(128))
    content_type = db.Column(db.String(255))
    ip_address = db.Column(db.String(128))
    user_agent = db.Column(db.Text)
    response_status = db.Column(db.Integer)
    response_body = db.Column(db.Text)
    created_at = db.Column(db.String(32), index=True, default=now_wib_str)
    duration_ms = db.Column(db.Float)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "method": self.method,
            "uri": self.uri,
            "path": self.path,
            "payload_type": self.payload_type,
            "payload_raw": self.payload_raw,
            "payload_parsed": self.payload_parsed,
            "ip_address": self.ip_address,
            "response_status": self.response_status,
            "duration_ms": self.duration_ms,
            "created_at": self.created_at,
        }


class GisLocation(db.Model):
    """Titik geospasial stasiun AWLR, ARR, node IoT, titik ERA5/BMKG, dan survei."""
    __tablename__ = "gis_locations"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(160), nullable=False)
    category = db.Column(db.String(64), nullable=False, index=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    elevation_m = db.Column(db.Float, default=0.0)
    description = db.Column(db.Text)
    layer_group = db.Column(db.String(64), default="monitoring")
    metadata_json = db.Column(db.Text)
    updated_at = db.Column(db.String(32), default=now_wib_str)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "elevation_m": self.elevation_m,
            "description": self.description,
            "layer_group": self.layer_group,
            "metadata_json": self.metadata_json,
            "updated_at": self.updated_at,
        }


class GisFarmParcel(db.Model):
    """103 petak tersier D.I. Pante Lhong lengkap dengan hasil simulasi CFAI."""
    __tablename__ = "gis_farm_parcels"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    kode_petak = db.Column(db.String(48), unique=False, nullable=False, index=True)
    name = db.Column(db.String(160), nullable=False)
    crop_type = db.Column(db.String(128), default="Padi Varietas Ciherang")
    growth_stage = db.Column(db.String(64), default="Reproduktif")
    area_ha = db.Column(db.Float, default=0.0)
    sistem_saluran = db.Column(db.String(128))
    orientasi = db.Column(db.String(64))
    modulus_l_s_ha = db.Column(db.Float, default=0.526)
    geojson_coords = db.Column(db.Text().with_variant(LONGTEXT(), "mysql"))
    cfai_siaga = db.Column(db.Float, default=0.0)
    cfai_awas = db.Column(db.Float, default=0.0)
    cfai_ekstrem = db.Column(db.Float, default=0.0)
    risk_category = db.Column(db.String(32), default="Sedang")
    updated_at = db.Column(db.String(32), default=now_wib_str)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kode_petak": self.kode_petak,
            "name": self.name,
            "crop_type": self.crop_type,
            "growth_stage": self.growth_stage,
            "area_ha": self.area_ha,
            "sistem_saluran": self.sistem_saluran,
            "orientasi": self.orientasi,
            "modulus_l_s_ha": self.modulus_l_s_ha,
            "geojson_coords": self.geojson_coords,
            "cfai_siaga": self.cfai_siaga,
            "cfai_awas": self.cfai_awas,
            "cfai_ekstrem": self.cfai_ekstrem,
            "risk_category": self.risk_category,
            "updated_at": self.updated_at,
        }


class GisRiverChannel(db.Model):
    """Geometri alur sungai utama Krueng Peusangan dan segmen saluran."""
    __tablename__ = "gis_river_channels"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(160), nullable=False)
    segment_type = db.Column(db.String(64), default="sungai")
    geojson_coords = db.Column(db.Text().with_variant(LONGTEXT(), "mysql"))
    bankfull_level_cm = db.Column(db.Float, default=180.0)
    width_m = db.Column(db.Float, default=45.0)
    notes = db.Column(db.Text)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "segment_type": self.segment_type,
            "geojson_coords": self.geojson_coords,
            "bankfull_level_cm": self.bankfull_level_cm,
            "width_m": self.width_m,
            "notes": self.notes,
        }


class LstmEvaluationScenario(db.Model):
    """Benchmark 20 skenario eksperimen LSTM (harian, per jam, ablasi, lintas DAS)."""
    __tablename__ = "lstm_evaluation_scenarios"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    experiment_code = db.Column(db.String(128), unique=True, nullable=False)
    scale_type = db.Column(db.String(32), default="Per Jam")
    feature_count = db.Column(db.Integer)
    window_size = db.Column(db.Integer)
    horizon = db.Column(db.Integer)
    lstm_units = db.Column(db.String(32))
    learning_rate = db.Column(db.Float)
    rmse_m = db.Column(db.Float)
    mae_m = db.Column(db.Float)
    r2_score = db.Column(db.Float)
    nse_score = db.Column(db.Float)
    acc_siaga_pct = db.Column(db.Float)
    epochs_run = db.Column(db.Integer)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "experiment_code": self.experiment_code,
            "scale_type": self.scale_type,
            "feature_count": self.feature_count,
            "window_size": self.window_size,
            "horizon": self.horizon,
            "lstm_units": self.lstm_units,
            "learning_rate": self.learning_rate,
            "rmse_m": self.rmse_m,
            "mae_m": self.mae_m,
            "r2_score": self.r2_score,
            "nse_score": self.nse_score,
            "acc_siaga_pct": self.acc_siaga_pct,
            "epochs_run": self.epochs_run,
        }


class AhpWeight(db.Model):
    """Matriks bobot konsolidasi AHP 5 pakar (3 kriteria utama, 9 sub-kriteria)."""
    __tablename__ = "ahp_weights"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    criteria_code = db.Column(db.String(16), nullable=False)
    criteria_name = db.Column(db.String(128), nullable=False)
    subcriteria_code = db.Column(db.String(16), unique=True, nullable=False)
    subcriteria_name = db.Column(db.String(160), nullable=False)
    criteria_weight = db.Column(db.Float, nullable=False)
    local_weight = db.Column(db.Float, nullable=False)
    global_weight = db.Column(db.Float, nullable=False)
    consistency_ratio = db.Column(db.Float, default=0.0)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "criteria_code": self.criteria_code,
            "criteria_name": self.criteria_name,
            "subcriteria_code": self.subcriteria_code,
            "subcriteria_name": self.subcriteria_name,
            "criteria_weight": self.criteria_weight,
            "local_weight": self.local_weight,
            "global_weight": self.global_weight,
            "consistency_ratio": self.consistency_ratio,
        }


class FarmerGroup(db.Model):
    """Direktori kelompok tani pada 69 desa wilayah D.I. Pante Lhong untuk diseminasi."""
    __tablename__ = "farmer_groups"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    kecamatan = db.Column(db.String(96), index=True)
    desa = db.Column(db.String(128), index=True)
    poktan_name = db.Column(db.String(160))
    member_count = db.Column(db.Integer, default=25)
    area_ha = db.Column(db.Float, default=0.0)
    channel_type = db.Column(db.String(64), default="WhatsApp")
    contact_channel = db.Column(db.String(160))
    active_alert_opt_in = db.Column(db.Boolean, default=True)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kecamatan": self.kecamatan,
            "desa": self.desa,
            "poktan_name": self.poktan_name,
            "member_count": self.member_count,
            "area_ha": self.area_ha,
            "channel_type": self.channel_type,
            "contact_channel": self.contact_channel,
            "active_alert_opt_in": bool(self.active_alert_opt_in),
            "latitude": self.latitude,
            "longitude": self.longitude,
        }


class FloodEvent(db.Model):
    """Rekam historis kejadian banjir Kabupaten Bireuen untuk kalibrasi risiko."""
    __tablename__ = "flood_events"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    event_date = db.Column(db.String(64), index=True)
    year = db.Column(db.Integer, index=True)
    kecamatan = db.Column(db.Text)
    desa = db.Column(db.Text)
    cause = db.Column(db.Text)
    inundation_depth_cm = db.Column(db.Float, default=0.0)
    duration_hours = db.Column(db.Float, default=0.0)
    affected_area_ha = db.Column(db.Float, default=0.0)
    affected_families = db.Column(db.Integer, default=0)
    source = db.Column(db.String(128), default="BPBD Bireuen")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "event_date": self.event_date,
            "year": self.year,
            "kecamatan": self.kecamatan,
            "desa": self.desa,
            "cause": self.cause,
            "inundation_depth_cm": self.inundation_depth_cm,
            "duration_hours": self.duration_hours,
            "affected_area_ha": self.affected_area_ha,
            "affected_families": self.affected_families,
            "source": self.source,
        }


class BroadcastLog(db.Model):
    """Catatan pengiriman notifikasi peringatan dini ke kelompok tani dan BPBD."""
    __tablename__ = "broadcast_logs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    channel = db.Column(db.String(32), nullable=False)
    recipient_group = db.Column(db.String(160), nullable=False)
    alert_level = db.Column(db.String(32), nullable=False)
    message_text = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(32), default="SIMULATED")
    http_code = db.Column(db.Integer, default=200)
    response_summary = db.Column(db.Text)
    triggered_by = db.Column(db.String(64), default="operator")
    created_at = db.Column(db.String(32), index=True, default=now_wib_str)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "channel": self.channel,
            "recipient_group": self.recipient_group,
            "alert_level": self.alert_level,
            "message_text": self.message_text,
            "status": self.status,
            "http_code": self.http_code,
            "response_summary": self.response_summary,
            "triggered_by": self.triggered_by,
            "created_at": self.created_at,
        }


class SystemUser(db.Model):
    """Pengguna resmi sistem PEUSAGA (Admin, Operator Irigasi, Peneliti)."""
    __tablename__ = "system_users"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(128))
    role = db.Column(db.String(32), default="operator")
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.String(32), default=now_wib_str)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "full_name": self.full_name,
            "role": self.role,
            "is_active": bool(self.is_active),
            "created_at": self.created_at,
        }


class SystemSetting(db.Model):
    """Konfigurasi operasional ambang siaga dan parameter webhook PEUSAGA."""
    __tablename__ = "system_settings"

    setting_key = db.Column(db.String(96), primary_key=True)
    setting_value = db.Column(db.Text)
    category = db.Column(db.String(48), default="general")
    description = db.Column(db.String(255))
    updated_at = db.Column(db.String(32), default=now_wib_str)

    def to_dict(self) -> dict:
        return {
            "setting_key": self.setting_key,
            "setting_value": self.setting_value,
            "category": self.category,
            "description": self.description,
            "updated_at": self.updated_at,
        }
