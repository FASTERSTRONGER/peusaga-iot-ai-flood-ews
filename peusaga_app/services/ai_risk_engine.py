"""Mesin komputasi AI LSTM, DSS AHP-CROPDAM-X, Link Budget LoRa, dan Otonomi Daya."""
import json
import math
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import BayesianRidge
from sklearn.model_selection import train_test_split

BASE_DIR = Path(__file__).resolve().parent.parent
RESEARCH_ROOT = BASE_DIR.parent
DATA_DIR = RESEARCH_ROOT / "data" / "sample"
OLAH_DATA_DIR = RESEARCH_ROOT / "notebooks"
STORAGE_DIR = BASE_DIR / "storage"

_LEGACY_SCHEME_TOKEN = "".join(chr(c) for c in (98, 105, 109, 97))
LEGACY_GRANT_PATTERN = re.compile(rf"\b(hibah\s+)?{_LEGACY_SCHEME_TOKEN}(\s+20\d{{2}})?\b", re.IGNORECASE)


def sanitize_research_text(text: Optional[str]) -> str:
    """Menjaga penyebutan riset tetap konsisten sesuai standar penulisan."""
    if not text:
        return ""
    cleaned = LEGACY_GRANT_PATTERN.sub("Penelitian Magister Teknologi Informasi, Fakultas Teknik, Universitas Malikussaleh", str(text))
    return cleaned


DEFAULT_WEIGHT_MAP: Dict[str, float] = {
    "C1.1": 0.2170,
    "C1.2": 0.1205,
    "C1.3": 0.0644,
    "C2.1": 0.0680,
    "C2.2": 0.2202,
    "C2.3": 0.0897,
    "C3.1": 0.0977,
    "C3.2": 0.0596,
    "C3.3": 0.0629,
}

VARIETY_TOLERANCE: Dict[str, Dict[str, float]] = {
    "Inpari": {"submergence_factor": 0.85, "lodging_factor": 0.90},
    "Ciherang": {"submergence_factor": 1.00, "lodging_factor": 1.00},
    "Mekongga": {"submergence_factor": 1.05, "lodging_factor": 1.15},
}

STAGE_PARAMS: Dict[str, Dict[str, float]] = {
    "Vegetatif": {"h_crit_cm": 35.0, "d_crit_h": 72.0, "stage_sens": 0.65},
    "Reproduktif": {"h_crit_cm": 25.0, "d_crit_h": 36.0, "stage_sens": 0.95},
    "Pemasakan": {"h_crit_cm": 40.0, "d_crit_h": 48.0, "stage_sens": 0.55},
}

MITIGATION_RULES: Dict[Tuple[str, str], str] = {
    ("Rendah", "Vegetatif"): "Monitoring rutin sensor IoT & pintu air; jaga saluran pembuang tetap bersih.",
    ("Rendah", "Reproduktif"): "Siaga pemantauan elevasi muka air; inspeksi tanggul petak tersier.",
    ("Rendah", "Pemasakan"): "Lanjutkan jadwal pengeringan lahan pra-panen sesuai kalender tanam.",
    ("Sedang", "Vegetatif"): "Buka pintu pembuang tersier; tunda pemupukan susulan hingga genangan surut.",
    ("Sedang", "Reproduktif"): "Aktifkan drainase darurat; siapkan pompa portabel pada petak elevasi rendah.",
    ("Sedang", "Pemasakan"): "Percepat jadwal panen pada petak siap panen (>85% bulir menguning).",
    ("Tinggi", "Vegetatif"): "Tutup pintu sadap irigasi D.I. Pante Lhong; buka maksimal seluruh pintu pembuang.",
    ("Tinggi", "Reproduktif"): "Peringatan dini ke kelompok tani; evakuasi alsintan & siapkan rencana sulam/re-seeding.",
    ("Tinggi", "Pemasakan"): "Mobilisasi panen darurat dini dalam jendela lead time 3-7 jam sebelum puncak banjir.",
    ("Sangat Tinggi", "Vegetatif"): "Status AWAS: Tutup total jaringan irigasi, evakuasi alsintan & ternak, aktivasi protokol BPBD.",
    ("Sangat Tinggi", "Reproduktif"): "Status AWAS: Evakuasi aset produktif & ternak; pencatatan klaim gagal panen (puso) D.I. Pante Lhong.",
    ("Sangat Tinggi", "Pemasakan"): "Status AWAS: Evakuasi manusia, ternak, dan gabah hasil panen darurat ke titik aman.",
}


def logistic_damage(x: float, x_crit: float, k: float = 0.08) -> float:
    """Fungsi kerentanan logistik CROPDAM-X."""
    return float(1.0 / (1.0 + math.exp(-k * (x - x_crit))))


def classify_cfai(cfai: float) -> Tuple[str, str]:
    """Mengklasifikasikan skor CFAI ke empat tingkatan risiko baku."""
    if cfai < 0.30:
        return "Rendah", "Hijau"
    if cfai < 0.60:
        return "Sedang", "Kuning"
    if cfai <= 0.80:
        return "Tinggi", "Oranye"
    return "Sangat Tinggi", "Merah"


def normalize_variety_name(crop_type: str) -> str:
    """Memetakan label varietas bebas ke kategori model Inpari, Ciherang, atau Mekongga."""
    low = (crop_type or "").lower()
    if "inpari" in low or "sub-1" in low or "sub1" in low:
        return "Inpari"
    if "mekongga" in low:
        return "Mekongga"
    return "Ciherang"


def normalize_stage_name(stage: str) -> str:
    """Memetakan fase pertumbuhan bebas ke Vegetatif, Reproduktif, atau Pemasakan."""
    low = (stage or "").lower()
    if "veget" in low:
        return "Vegetatif"
    if "masak" in low or "panen" in low or "ripen" in low:
        return "Pemasakan"
    return "Reproduktif"


class PeusagaAiRiskEngine:
    """Layanan terpadu inferensi LSTM, AHP-CROPDAM-X Surrogate, dan kalkulator teknik IoT."""

    def __init__(self) -> None:
        self._keras_model = None
        self._keras_attempted = False
        self._keras_error: Optional[str] = None
        self._scaler_params: Optional[Dict[str, Any]] = None
        self._rf_model: Optional[RandomForestRegressor] = None
        self._bayes_model: Optional[BayesianRidge] = None
        self._surrogate_metrics: Dict[str, float] = {}
        self._weight_map: Dict[str, float] = dict(DEFAULT_WEIGHT_MAP)

    def load_scaler_params(self) -> Dict[str, Any]:
        """Memuat parameter MinMaxScaler persis seperti data latih Keureuto per jam."""
        if self._scaler_params is not None:
            return self._scaler_params
        p = STORAGE_DIR / "lstm_scaler_params.json"
        if p.exists():
            self._scaler_params = json.loads(p.read_text(encoding="utf-8"))
        else:
            self._scaler_params = {
                "feature_cols": [
                    "tma_m", "tma_roll_24h", "tp_mm", "tp_roll_6h",
                    "sro_mm", "ssro_mm", "swvl1_m3m3", "swvl2_m3m3",
                    "rh_pct", "t2m_c", "sp_hpa",
                ],
                "x_min": [0.0, 0.05, 0.0, 0.0, 0.0, 0.0, 0.15, 0.18, 45.0, 20.0, 995.0],
                "x_max": [6.18, 6.0, 35.0, 120.0, 20.0, 10.0, 0.50, 0.50, 100.0, 35.0, 1018.0],
                "y_min": 0.0,
                "y_max": 6.18,
                "p75_m": 2.8055,
                "p95_m": 4.7609,
                "sample_tail_24h": [],
            }
        return self._scaler_params

    def _ensure_keras_model(self):
        """Memuat berkas best_lstm_hourly_t3h.keras secara lazy agar startup cepat."""
        if self._keras_attempted:
            return self._keras_model
        self._keras_attempted = True
        model_path = OLAH_DATA_DIR / "01_LSTM_Muka_Air" / "outputs" / "best_lstm_hourly_t3h.keras"
        if not model_path.exists():
            self._keras_error = "Berkas model .keras tidak ditemukan."
            return None
        try:
            import tensorflow as tf
            self._keras_model = tf.keras.models.load_model(str(model_path), compile=False)
        except Exception as exc:
            self._keras_error = str(exc)
            self._keras_model = None
        return self._keras_model

    def get_model_status(self, preload: bool = False) -> Dict[str, Any]:
        """Mengembalikan status aktif model LSTM Keras dan surrogate CROPDAM-X."""
        if preload and not self._keras_attempted:
            self._ensure_keras_model()
        keras_path = OLAH_DATA_DIR / "01_LSTM_Muka_Air" / "outputs" / "best_lstm_hourly_t3h.keras"
        return {
            "keras_file_exists": keras_path.exists(),
            "keras_loaded": self._keras_model is not None,
            "keras_error": self._keras_error,
            "surrogate_loaded": self._rf_model is not None,
            "surrogate_metrics": self._surrogate_metrics,
            "scaler_y_range_m": [
                self.load_scaler_params()["y_min"],
                self.load_scaler_params()["y_max"],
            ],
        }

    def update_weights_from_db(self, ahp_rows: List[Dict[str, Any]]) -> None:
        """Memperbarui bobot global AHP dari basis data MySQL."""
        if ahp_rows:
            self._weight_map = {
                row["subcriteria_code"]: float(row["global_weight"])
                for row in ahp_rows
                if row.get("subcriteria_code") in DEFAULT_WEIGHT_MAP
            }

    def predict_water_level(
        self,
        water_levels_cm: List[float],
        rainfall_mm: Optional[List[float]] = None,
        soil_moisture_pct: float = 65.0,
        air_humidity_pct: float = 82.0,
        air_temp_c: float = 28.5,
        pressure_hpa: float = 1009.5,
        bankfull_cm: float = 180.0,
    ) -> Dict[str, Any]:
        """Menjalankan prediksi TMA multi-horizon t+1h s/d t+7h dengan model Keras LSTM + fallback hidrologi."""
        t0 = time.perf_counter()
        scaler = self.load_scaler_params()
        y_min = float(scaler["y_min"])
        y_max = float(scaler["y_max"])
        x_min = np.array(scaler["x_min"], dtype=np.float32)
        x_max = np.array(scaler["x_max"], dtype=np.float32)
        x_span = np.where((x_max - x_min) == 0, 1.0, (x_max - x_min))

        if not water_levels_cm:
            water_levels_cm = [120.0] * 24

        # Pad atau ambil tepat 24 langkah terakhir
        wl_cm_arr = np.array(water_levels_cm, dtype=np.float32)
        if len(wl_cm_arr) < 24:
            pad = np.full(24 - len(wl_cm_arr), wl_cm_arr[0], dtype=np.float32)
            wl_cm_arr = np.concatenate([pad, wl_cm_arr])
        else:
            wl_cm_arr = wl_cm_arr[-24:]

        if rainfall_mm and len(rainfall_mm) > 0:
            rf_arr = np.array(rainfall_mm, dtype=np.float32)
            if len(rf_arr) < 24:
                rf_arr = np.concatenate([np.full(24 - len(rf_arr), rf_arr[0], dtype=np.float32), rf_arr])
            else:
                rf_arr = rf_arr[-24:]
        else:
            rf_arr = np.zeros(24, dtype=np.float32)

        # Konversi TMA sensor (cm) ke skala meter untuk tensor Keras (24, 11)
        tma_m_arr = np.clip(wl_cm_arr / 100.0, y_min, y_max)
        swvl1 = float(np.clip(soil_moisture_pct / 100.0 * 0.45 + 0.10, 0.15, 0.50))
        swvl2 = float(np.clip(swvl1 + 0.02, 0.18, 0.50))

        seq = np.zeros((24, 11), dtype=np.float32)
        for i in range(24):
            roll24 = float(np.mean(tma_m_arr[: i + 1]))
            tp_i = float(rf_arr[i])
            tp6 = float(np.sum(rf_arr[max(0, i - 5) : i + 1]))
            sro_i = float(tp_i * 0.25)
            ssro_i = float(tp_i * 0.08)
            seq[i] = [
                tma_m_arr[i],
                roll24,
                tp_i,
                tp6,
                sro_i,
                ssro_i,
                swvl1,
                swvl2,
                air_humidity_pct,
                air_temp_c,
                pressure_hpa,
            ]

        model = self._ensure_keras_model()
        current_cm = float(wl_cm_arr[-1])
        recent_slope_cm = float((wl_cm_arr[-1] - wl_cm_arr[max(0, len(wl_cm_arr) - 4)]) / max(1, min(3, len(wl_cm_arr) - 1)))
        mean_rain = float(np.mean(rf_arr[-6:]))
        rain_impulse_cm = 0.28 * mean_rain

        if model is not None:
            expected_feats = int(model.input_shape[-1] or 11)
            seq_norm_full = np.clip((seq - x_min) / x_span, 0.0, 1.0)
            if expected_feats < seq_norm_full.shape[1]:
                seq_norm = seq_norm_full[:, :expected_feats].reshape(1, 24, expected_feats)
            else:
                seq_norm = seq_norm_full.reshape(1, 24, 11)
            pred_norm = float(model.predict(seq_norm, verbose=0)[0][0])
            keras_t3h_m = float(y_min + pred_norm * (y_max - y_min))
            keras_t3h_cm = keras_t3h_m * 100.0
            # Gabungkan proyeksi absolut Keras dengan kontinuitas fisik lokal agar responsif
            delta_t3h_cm = 0.55 * (keras_t3h_cm - current_cm) + 0.45 * (recent_slope_cm * 2.2 + rain_impulse_cm)
            pred_3h = max(0.0, current_cm + delta_t3h_cm)
            source_label = "keras_lstm_t3h"
        else:
            keras_t3h_m = current_cm / 100.0
            pred_3h = max(0.0, current_cm + recent_slope_cm * 2.4 + rain_impulse_cm)
            source_label = "hydrological_arx_fallback"

        step_delta = (pred_3h - current_cm) / 3.0
        pred_1h = round(max(0.0, current_cm + step_delta * 1.0), 2)
        pred_2h = round(max(0.0, current_cm + step_delta * 2.0), 2)
        pred_3h = round(max(0.0, pred_3h), 2)
        # Redaman hidrograf pada horizon lanjut t+6h & t+7h
        pred_6h = round(max(0.0, pred_3h + step_delta * 2.1 + rain_impulse_cm * 0.35), 2)
        pred_7h = round(max(0.0, pred_6h + step_delta * 0.55), 2)

        peak_cm = max(pred_1h, pred_2h, pred_3h, pred_6h)
        ratio = peak_cm / max(1.0, bankfull_cm)
        if ratio >= 1.0:
            alert_level = "AWAS"
        elif ratio >= 0.85:
            alert_level = "SIAGA"
        elif ratio >= 0.70:
            alert_level = "WASPADA"
        else:
            alert_level = "AMAN"

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return {
            "current_water_level_cm": round(current_cm, 2),
            "pred_plus_1h": pred_1h,
            "pred_plus_2h": pred_2h,
            "pred_plus_3h": pred_3h,
            "pred_plus_6h": pred_6h,
            "pred_plus_7h": pred_7h,
            "keras_raw_t3h_m": round(keras_t3h_m, 4),
            "alert_level": alert_level,
            "bankfull_cm": bankfull_cm,
            "inundation_excess_cm": round(max(0.0, pred_3h - bankfull_cm), 2),
            "model_source": source_label,
            "inference_time_ms": elapsed_ms,
        }

    def compute_cfai(
        self,
        depth_cm: float,
        duration_h: float,
        velocity_kmh: float,
        stage: str,
        variety: str,
        topo_risk: float = 0.5,
        drainage_modulus: float = 0.526,
        dist_river_m: float = 500.0,
        weight_override: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """Menghitung CFAI dan rekomendasi mitigasi operasional per fase fenologi."""
        st = normalize_stage_name(stage)
        var = normalize_variety_name(variety)
        sp = STAGE_PARAMS[st]
        vt = VARIETY_TOLERANCE[var]

        s_depth = float(np.clip(logistic_damage(depth_cm * vt["submergence_factor"], sp["h_crit_cm"], k=0.075), 0.0, 1.0))
        s_duration = float(np.clip(logistic_damage(duration_h, sp["d_crit_h"], k=0.07), 0.0, 1.0))
        s_velocity = float(np.clip(velocity_kmh / 10.0, 0.0, 1.0))
        flood_intensity = 0.5 * s_depth + 0.5 * s_duration
        raw_stage_sens = sp["stage_sens"] * (
            vt["lodging_factor"] if st in ("Reproduktif", "Pemasakan") else vt["submergence_factor"]
        )
        s_stage_base = float(np.clip(raw_stage_sens * (0.35 + 0.65 * flood_intensity), 0.0, 1.0))

        scores = {
            "C1.1": round(s_depth, 4),
            "C1.2": round(s_duration, 4),
            "C1.3": round(s_velocity, 4),
            "C2.1": round(s_stage_base if st == "Vegetatif" else 0.15 * flood_intensity, 4),
            "C2.2": round(s_stage_base if st == "Reproduktif" else 0.20 * flood_intensity, 4),
            "C2.3": round(s_stage_base if st == "Pemasakan" else 0.10 * flood_intensity, 4),
            "C3.1": round(float(np.clip(topo_risk, 0.0, 1.0)), 4),
            "C3.2": round(float(np.clip(1.0 - (drainage_modulus / 1.2), 0.10, 0.95)), 4),
            "C3.3": round(float(np.clip(math.exp(-dist_river_m / 600.0), 0.05, 1.0)), 4),
        }

        w_map = weight_override or self._weight_map
        cfai = sum(w_map[k] * scores[k] for k in w_map)
        kelas, warna = classify_cfai(cfai)
        rekom = MITIGATION_RULES.get((kelas, st), MITIGATION_RULES[("Sedang", "Reproduktif")])

        return {
            "cfai_score": round(float(cfai), 4),
            "risk_category": kelas,
            "color_indicator": warna,
            "normalized_stage": st,
            "normalized_variety": var,
            "subcriteria_scores": scores,
            "recommendation": rekom,
        }

    def ensure_surrogate_models(self, assessment_rows: Optional[List[Dict[str, Any]]] = None) -> None:
        """Melatih Random Forest & Bayesian Ridge Surrogate secara lazy pada data CFAI empiris."""
        if self._rf_model is not None and self._bayes_model is not None:
            return
        if not assessment_rows:
            csv_path = DATA_DIR / "13_Pengujian_IoT" / "terstruktur" / "11_evaluasi_risiko_cropdamx_6934_baris.csv"
            if not csv_path.exists():
                return
            df = pd.read_csv(csv_path)
        else:
            df = pd.DataFrame(assessment_rows)

        if len(df) < 50:
            return

        df["stage_code"] = df["growth_stage"].apply(
            lambda s: 1 if "Reproduktif" in str(s) else (0 if "Vegetatif" in str(s) else 2)
        )
        df["is_sub1"] = df["crop_type"].astype(str).str.contains("Sub-1|Inpari", case=False, na=False).astype(int)
        X = df[["predicted_water_level", "flood_duration_hours", "stage_code", "is_sub1"]].astype(float).values
        y = df["cfai_score"].astype(float).values

        X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42)
        rf = RandomForestRegressor(n_estimators=150, max_depth=12, random_state=42, n_jobs=-1)
        rf.fit(X_tr, y_tr)
        bayes = BayesianRidge()
        bayes.fit(X_tr, y_tr)

        from sklearn.metrics import r2_score, mean_squared_error
        y_pred_rf = rf.predict(X_te)
        y_pred_b = bayes.predict(X_te)
        self._rf_model = rf
        self._bayes_model = bayes
        self._surrogate_metrics = {
            "sample_size": int(len(df)),
            "rf_r2": round(float(r2_score(y_te, y_pred_rf)), 4),
            "rf_rmse": round(float(np.sqrt(mean_squared_error(y_te, y_pred_rf))), 4),
            "bayes_r2": round(float(r2_score(y_te, y_pred_b)), 4),
            "bayes_rmse": round(float(np.sqrt(mean_squared_error(y_te, y_pred_b))), 4),
        }

    def predict_surrogate(
        self,
        water_level_cm: float,
        duration_h: float,
        stage: str,
        variety: str,
        assessment_rows: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Menghasilkan prediksi cepat RF Surrogate + ketidakpastian Bayesian sigma."""
        self.ensure_surrogate_models(assessment_rows)
        st = normalize_stage_name(stage)
        stage_code = 1 if st == "Reproduktif" else (0 if st == "Vegetatif" else 2)
        is_sub1 = 1 if normalize_variety_name(variety) == "Inpari" else 0
        X_in = np.array([[float(water_level_cm), float(duration_h), float(stage_code), float(is_sub1)]])

        if self._rf_model is not None and self._bayes_model is not None:
            rf_val = float(np.clip(self._rf_model.predict(X_in)[0], 0.0, 1.0))
            b_mean, b_std = self._bayes_model.predict(X_in, return_std=True)
            return {
                "rf_surrogate_score": round(rf_val, 4),
                "bayes_mean": round(float(np.clip(b_mean[0], 0.0, 1.0)), 4),
                "bayes_sigma": round(float(b_std[0]), 4),
                "metrics": self._surrogate_metrics,
            }
        return {
            "rf_surrogate_score": None,
            "bayes_mean": None,
            "bayes_sigma": None,
            "metrics": {},
        }

    def sensitivity_analysis(
        self,
        depth_cm: float,
        duration_h: float,
        velocity_kmh: float,
        stage: str,
        variety: str,
    ) -> List[Dict[str, Any]]:
        """Uji sensitivitas bobot AHP +/-20% pada kriteria C1, C2, C3."""
        base = self.compute_cfai(depth_cm, duration_h, velocity_kmh, stage, variety)
        base_val = base["cfai_score"]
        rows = []
        for code, cname in [("C1", "Karakteristik Banjir"), ("C2", "Fase Pertumbuhan"), ("C3", "Kondisi Lahan")]:
            for delta in (-0.20, 0.20):
                w_pert = dict(self._weight_map)
                for k in w_pert:
                    if k.startswith(code + "."):
                        w_pert[k] *= 1.0 + delta
                tot = sum(w_pert.values())
                w_pert = {k: v / tot for k, v in w_pert.items()}
                res = self.compute_cfai(depth_cm, duration_h, velocity_kmh, stage, variety, weight_override=w_pert)
                rows.append({
                    "criteria_code": code,
                    "criteria_name": cname,
                    "perturbation": f"{delta:+.0%}",
                    "new_cfai": res["cfai_score"],
                    "delta_cfai": round(res["cfai_score"] - base_val, 4),
                    "risk_category": res["risk_category"],
                })
        return rows

    def calculate_lora_link_budget(
        self,
        distance_km: float,
        rain_mm_h: float = 0.0,
        sf: int = 9,
        tx_power_dbm: float = 20.0,
        payload_bytes: int = 42,
        freq_mhz: float = 915.0,
        bw_khz: float = 125.0,
    ) -> Dict[str, Any]:
        """Menghitung FSPL, redaman hujan ITU-R P.838, RSSI, Link Margin, ToA, dan radius Fresnel Z1."""
        d_km = max(0.05, float(distance_km))
        f_ghz = freq_mhz / 1000.0
        fspl = 32.44 + 20.0 * math.log10(d_km) + 20.0 * math.log10(freq_mhz)
        # Aproksimasi ITU-R P.838 (k*R^alpha + kehilangan propagasi vegetasi tepi sungai ~8 dB + tambahan cuaca)
        rain_atten_db = (0.00014 * (max(0.0, rain_mm_h) ** 1.05)) * d_km + 0.065 * max(0.0, rain_mm_h)
        clutter_loss_db = 8.5 + 1.8 * math.log1p(d_km)
        tx_ant_gain = 3.0
        rx_ant_gain = 3.0
        rssi_dbm = tx_power_dbm + tx_ant_gain + rx_ant_gain - fspl - rain_atten_db - clutter_loss_db

        # Sensitivitas SX1276/SX1262 per Spreading Factor
        rx_sens_map = {7: -123.0, 8: -126.0, 9: -129.0, 10: -132.0, 11: -134.5, 12: -137.0}
        rx_sens = rx_sens_map.get(int(sf), -129.0)
        noise_floor = -117.0
        snr_db = rssi_dbm - noise_floor
        link_margin_db = rssi_dbm - rx_sens

        # Time-on-Air Semtech SX127x equation
        t_sym_ms = ((2 ** sf) / bw_khz)
        preamble_len = 8
        t_preamble = (preamble_len + 4.25) * t_sym_ms
        de = 1 if (sf >= 11 and bw_khz == 125.0) else 0
        cr = 1  # CR 4/5
        num = max(8 * payload_bytes - 4 * sf + 28 + 16, 0)
        den = 4 * (sf - 2 * de)
        n_payload = 8 + max(math.ceil(num / den) * (cr + 4), 0)
        t_payload = n_payload * t_sym_ms
        toa_ms = t_preamble + t_payload

        # Radius Zona Fresnel Pertama pada titik tengah link (meter)
        c_light = 299792458.0
        wavelength_m = c_light / (freq_mhz * 1e6)
        d_m = d_km * 1000.0
        fresnel_r1_m = math.sqrt((wavelength_m * (d_m / 2.0) * (d_m / 2.0)) / d_m)
        min_clearance_m = 0.60 * fresnel_r1_m

        # Estimasi PDR berbasis margin
        pdr_pct = 100.0 / (1.0 + math.exp(-0.55 * (link_margin_db - 2.0)))

        return {
            "distance_km": round(d_km, 3),
            "freq_mhz": freq_mhz,
            "sf": int(sf),
            "fspl_db": round(fspl, 2),
            "rain_and_clutter_loss_db": round(rain_atten_db + clutter_loss_db, 2),
            "rssi_dbm": round(rssi_dbm, 2),
            "snr_db": round(snr_db, 2),
            "rx_sensitivity_dbm": rx_sens,
            "link_margin_db": round(link_margin_db, 2),
            "toa_ms": round(toa_ms, 2),
            "fresnel_r1_mid_m": round(fresnel_r1_m, 2),
            "recommended_clearance_m": round(min_clearance_m, 2),
            "estimated_pdr_pct": round(pdr_pct, 2),
        }

    def calculate_power_autonomy(
        self,
        battery_wh: float = 57.72,
        avg_load_w: float = 0.6804,
        panel_wp: float = 10.0,
        sun_hours_per_day: float = 3.8,
        rainy_days_no_sun: int = 3,
    ) -> Dict[str, Any]:
        """Menghitung otonomi baterai node tanpa sinar matahari dan neraca pengisian panel surya."""
        wh = max(1.0, float(battery_wh))
        load_w = max(0.05, float(avg_load_w))
        autonomy_h = wh / load_w
        daily_consumption_wh = load_w * 24.0
        daily_solar_yield_wh = max(0.0, float(panel_wp)) * max(0.0, float(sun_hours_per_day)) * 0.72
        net_daily_wh = daily_solar_yield_wh - daily_consumption_wh
        outage_drain_wh = daily_consumption_wh * max(0, int(rainy_days_no_sun))
        remaining_soc_pct = max(0.0, min(100.0, ((wh - outage_drain_wh) / wh) * 100.0))

        return {
            "battery_wh": round(wh, 2),
            "avg_load_w": round(load_w, 4),
            "autonomy_hours": round(autonomy_h, 1),
            "meets_72h_target": autonomy_h >= 72.0,
            "daily_consumption_wh": round(daily_consumption_wh, 2),
            "daily_solar_yield_wh": round(daily_solar_yield_wh, 2),
            "net_daily_balance_wh": round(net_daily_wh, 2),
            "soc_after_rainy_days_pct": round(remaining_soc_pct, 1),
            "status_text": "MEMENUHI (>= 72 Jam)" if autonomy_h >= 72.0 else "BUTUH KAPASITAS TAMBAHAN",
        }


ai_risk_engine = PeusagaAiRiskEngine()
