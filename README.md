# PEUSAGA: IoT-AI Flood Early Warning & Crop Failure Risk Mitigation System

Public research repository for **PEUSAGA** — Penelitian Magister Teknologi Informasi, Fakultas Teknik, Universitas Malikussaleh.

PEUSAGA integrates **LoRaWAN IoT water-level & environmental telemetry**, **LSTM multi-horizon water-level forecasting**, and **AHP-CROPDAM-X agricultural flood-risk assessment (CFAI)** into a unified Flask + WebGIS decision support platform.

## Repository Structure

```text
.
├── peusaga_app/              # Main Flask web application, REST API, and WebGIS dashboard
├── notebooks/                # Analytical & modeling notebooks (LSTM, AHP-CROPDAM-X, IoT LoRa)
│   ├── 01_LSTM_Muka_Air/
│   ├── 02_AHP_Cropdam-X/
│   └── 03_IoT_LoRa/
├── data/
│   ├── sample/               # Synthetic & anonymized sample datasets for reproducibility
│   ├── aggregated/           # Aggregated model evaluation & simulation metrics
│   └── README.md             # Data dictionary and anonymization documentation
├── scripts/
│   ├── generate_sample_data.py
│   └── sanitize_notebooks.py
├── docs/
│   └── system_testing/       # System test report, response-time benchmarks, and UI screenshots
├── DATA_ACCESS.md            # Data Availability Statement for journal peer review
├── CITATION.cff              # Citation metadata
├── LICENSE                   # MIT License
└── README.md
```

## Quick Start (Demo Mode with Sample Data)

1. **Generate (or regenerate) synthetic sample datasets & WebGIS demo layers**:
   ```bash
   python scripts/generate_sample_data.py
   ```

2. **Set up environment & dependencies for `peusaga_app`**:
   ```bash
   cd peusaga_app
   python -m venv .venv
   # Windows: .venv\Scripts\activate | Linux/macOS: source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env
   ```
   By default, `seed_database.py` uses `sqlite:///storage/peusaga_demo.db` if `DATABASE_URL` is not overridden in `.env`.

3. **Seed demo database & run the application**:
   ```bash
   python seed_database.py
   python app.py
   ```
   Open `http://127.0.0.1:5000` in your browser.
   Demo accounts created by `seed_database.py`:
   - `demo_admin` / `demo_admin_2026`
   - `demo_operator` / `demo_operator_2026`

## Analytical Notebooks

Each module under `notebooks/` includes its own `requirements.txt` and reference evaluation figures under `outputs/`. Notebook cell outputs have been cleared and input paths mapped to `../../data/sample/` for clean execution.

## Data Availability

Raw institutional datasets are excluded from this public repository to comply with agency data-sharing agreements and privacy protections. See [DATA_ACCESS.md](./DATA_ACCESS.md) for the full Data Availability Statement and access request procedure.

## License

This project is released under the [MIT License](./LICENSE).
