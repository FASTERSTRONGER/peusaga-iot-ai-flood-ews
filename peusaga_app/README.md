# PEUSAGA Fullstack System

Sistem peringatan dini banjir dan analisis kerentanan tanaman padi (**Peusangan Early-warning & Unified Smart Agro-hydrology Guard Algorithm**) yang dikembangkan dalam **Penelitian Magister Teknologi Informasi, Fakultas Teknik, Universitas Malikussaleh**.

## Arsitektur Utama

- **Backend**: Python 3.12 + Flask (`app.py`, `models.py`, `services/`)
- **Basis Data**: MySQL 8.0 (`peusaga_db`, `utf8mb4`) menggunakan Flask-SQLAlchemy dan PyMySQL
- **Kecerdasan Buatan**: TensorFlow Keras Stacked LSTM (`best_lstm_hourly_t3h.keras`, window 24 jam x 11 fitur) + fallback hidrologi deterministik
- **Sistem Pendukung Keputusan**: AHP 5 Pakar (`CR = 0.00000`), indeks CROPDAM-X (CFAI) untuk 103 petak tersier (`5.853,74 ha`), serta surrogate `RandomForestRegressor` dan `BayesianRidge`
- **Antarmuka Web**: Jinja2 modular, CSS adaptif Light/Dark terverifikasi WCAG, JavaScript ES6, Leaflet WebGIS Multi-Layer, Chart.js, serta aliran real-time Server-Sent Events (SSE) dan delta AJAX polling

## Menjalankan Aplikasi

1. Salin berkas `.env.example` menjadi `.env` dan sesuaikan koneksi `DATABASE_URL` serta kunci autentikasi node IoT.
2. Pastikan layanan MySQL 8.0 berjalan dan basis data `peusaga_db` tersedia.
3. Aktifkan lingkungan virtual Python 3.12 dan muat data awal ke MySQL:
   ```bash
   python seed_database.py
   ```
4. Jalankan server Flask:
   ```bash
   python app.py
   ```
5. Buka peramban web menuju `http://127.0.0.1:5000`.
