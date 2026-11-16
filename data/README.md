# Data Dictionary & Anonymization Notes

## 1. `data/sample/` (Synthetic Sample Datasets)
Generated deterministically by `scripts/generate_sample_data.py` (`seed=42`):

| File | Description | Key Columns |
| :--- | :--- | :--- |
| `sample_tma_hidrologi.csv` | Synthetic 30-day hourly water level (TMA) and rainfall series (720 rows). | `timestamp_wib`, `station_id`, `rainfall_mm_h`, `tma_hulu_cm`, `tma_hilir_cm`, `discharge_m3_s` |
| `sample_telemetri_iot.csv` | Synthetic 3-node LoRaWAN IoT telemetry at 15-minute intervals (360 rows). | `recorded_at`, `node_id`, `zone_code`, `water_level_cm`, `rainfall_mm`, `soil_moisture_pct`, `battery_v`, `rssi_dbm`, `snr_db` |
| `sample_petak_tersier.csv` | Anonymized synthetic tertiary irrigation plots (20 plots). | `plot_id`, `canal_group`, `area_ha`, `elevation_m`, `growth_stage`, `rice_variety`, `sample_cfai_score`, `risk_category` |
| `sample_responden_ahp.json` | Anonymized AHP 9-criteria global weights (`EXPERT_01`–`EXPERT_05`). | `consistency_ratio`, `experts`, `criteria_weights` |

## 2. `data/aggregated/` (Model & Simulation Summaries)
Non-sensitive aggregated outputs from the analytical notebooks:
- `ringkasan_evaluasi_lstm.csv`: Comparative RMSE, MAE, R², and NSE across LSTM scenarios.
- `ahp_bobot_global.csv`: Consolidated global AHP criterion weights.
- `matriks_rekomendasi_mitigasi.csv`: Rule-based crop-damage mitigation matrix.
- `evaluasi_pareto_jumlah_node.csv`: Pareto trade-off between IoT node count, hydrological coverage, and cost.
- `simulasi_link_budget_lora_915mhz.csv`: LoRa 915 MHz link-budget and Fresnel clearance summary.
- `evaluasi_otonomi_daya_node.csv`: Solar + 3S Li-ion battery autonomy evaluation.
