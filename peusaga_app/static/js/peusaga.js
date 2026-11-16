/* Modul JavaScript Utama PEUSAGA (ES6 Vanilla JS, Leaflet WebGIS, Chart.js, SSE & Delta AJAX) */
(function () {
  "use strict";

  const state = {
    streamPaused: false,
    eventSource: null,
    pollTimer: null,
    lastTelemetryId: 0,
    map: null,
    mapLayers: {},
    cadRenderer: null,
    gisCache: null,
    cadExtrasCache: null,
    dashChart: null,
    lstmChart: null,
  };

  function byId(id) {
    return document.getElementById(id);
  }

  async function apiJson(url, options = {}) {
    const res = await fetch(url, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.message || "Permintaan gagal diproses (" + res.status + ")");
    }
    return data;
  }

  /* ========================================================================
     1. TEMA LIGHT & DARK
     ======================================================================== */
  function initThemeToggle() {
    const btn = byId("btn-theme-toggle");
    if (!btn) return;
    function syncLabel() {
      const cur = document.documentElement.getAttribute("data-theme") || "light";
      btn.textContent = cur === "dark" ? "Tema Terang" : "Tema Gelap";
    }
    syncLabel();
    btn.addEventListener("click", () => {
      const cur = document.documentElement.getAttribute("data-theme") || "light";
      const next = cur === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      localStorage.setItem("peusaga_theme", next);
      syncLabel();
    });
  }

  /* ========================================================================
     2. REAL-TIME SSE & DELTA AJAX POLLING + PAUSE/RESUME
     ======================================================================== */
  function updateStreamBadge(label) {
    const pill = byId("sse-status-pill");
    if (pill) pill.textContent = label;
  }

  function alertBadgeClass(level) {
    const up = String(level || "").toUpperCase();
    if (up === "AMAN") return "badge-safe";
    if (up === "WASPADA") return "badge-warn";
    if (up === "SIAGA") return "badge-alert";
    return "badge-danger";
  }

  function meterClass(level) {
    const up = String(level || "").toUpperCase();
    if (up === "AMAN") return "meter-safe";
    if (up === "WASPADA") return "meter-warn";
    if (up === "SIAGA") return "meter-alert";
    return "meter-danger";
  }

  function updateVisitorSummaryDOM(summary) {
    if (!summary) return;
    const banner = byId("visitor-hero-banner");
    if (banner && summary.banner_class) {
      banner.className = `visitor-hero ${summary.banner_class}`;
    }
    const badge = byId("visitor-alert-badge");
    if (badge) {
      badge.className = `badge ${summary.badge_class || alertBadgeClass(summary.overall_alert)}`;
      badge.textContent = `STATUS: ${summary.overall_alert || "AMAN"}`;
    }
    const titleEl = byId("visitor-alert-title");
    if (titleEl && summary.headline) titleEl.textContent = summary.headline;
    const descEl = byId("visitor-alert-desc");
    if (descEl && summary.advice) descEl.textContent = summary.advice;
    const mw = byId("visitor-max-water");
    if (mw && summary.max_water_cm !== undefined) mw.textContent = `${summary.max_water_cm} cm`;
    const mp = byId("visitor-max-pred");
    if (mp && summary.max_pred_3h_cm !== undefined) mp.textContent = `${summary.max_pred_3h_cm} cm`;
    const rd = byId("visitor-rain-desc");
    if (rd && summary.rain_desc) rd.textContent = summary.rain_desc;
    const mr = byId("visitor-max-rain");
    if (mr && summary.max_rainfall_mm !== undefined) mr.textContent = String(summary.max_rainfall_mm);
    const hm = byId("visitor-humidity");
    if (hm && summary.avg_humidity_pct !== undefined) hm.textContent = String(summary.avg_humidity_pct);
    const lu = byId("visitor-last-updated");
    if (lu && summary.latest_seen) lu.textContent = summary.latest_seen;
  }

  function updateVisitorNodeCardView(nodeId, rowOrNode, predObj) {
    const vCard = byId(`visitor-node-card-${nodeId}`);
    if (!vCard) return;
    const wl = Number(rowOrNode?.water_level ?? rowOrNode?.last_water_level ?? 0);
    const bankfull = Number(vCard.getAttribute("data-bankfull") || rowOrNode?.bankfull_level_cm || 150);
    const fillPct = Math.min(100, Number(((wl / Math.max(1, bankfull)) * 100).toFixed(1)));
    const seen = rowOrNode?.created_at ?? rowOrNode?.last_seen;

    const wlEl = byId(`visitor-wl-${nodeId}`);
    if (wlEl) wlEl.textContent = `${wl} cm`;
    const pctEl = byId(`visitor-pct-${nodeId}`);
    if (pctEl) pctEl.textContent = `${fillPct}%`;
    const barEl = byId(`visitor-bar-${nodeId}`);

    const pred3h = predObj && predObj.pred_plus_3h !== undefined ? Number(predObj.pred_plus_3h) : null;
    const alertLvl = (predObj && predObj.alert_level) || (wl / Math.max(1, bankfull) >= 1 ? "AWAS" : wl / Math.max(1, bankfull) >= 0.85 ? "SIAGA" : wl / Math.max(1, bankfull) >= 0.7 ? "WASPADA" : "AMAN");
    if (barEl) {
      barEl.style.width = `${fillPct}%`;
      barEl.className = `water-meter-fill ${meterClass(alertLvl)}`;
    }
    const badgeEl = byId(`visitor-node-badge-${nodeId}`);
    if (badgeEl) {
      badgeEl.textContent = alertLvl;
      badgeEl.className = `badge ${alertBadgeClass(alertLvl)}`;
    }
    if (pred3h !== null) {
      const predEl = byId(`visitor-pred-${nodeId}`);
      if (predEl) predEl.textContent = `${pred3h} cm`;
      const trendEl = byId(`visitor-trend-${nodeId}`);
      if (trendEl) {
        const diff = pred3h - wl;
        const lbl = diff >= 3 ? "Naik" : diff <= -3 ? "Turun" : "Stabil";
        trendEl.textContent = `Tren: ${lbl}`;
        trendEl.className = `badge ${diff >= 3 ? "badge-warn" : "badge-safe"}`;
      }
    }
    const seenEl = byId(`visitor-seen-${nodeId}`);
    if (seenEl && seen) seenEl.textContent = seen;
  }

  function updateNodeCardView(nodeId, rowOrNode, predObj) {
    updateVisitorNodeCardView(nodeId, rowOrNode, predObj);
    const card = document.querySelector(`[data-node-card="${nodeId}"]`);
    if (card && rowOrNode) {
      const setF = (name, val) => {
        const el = card.querySelector(`[data-field="${name}"]`);
        if (el) el.textContent = val;
      };
      const wl = rowOrNode.water_level ?? rowOrNode.last_water_level ?? 0;
      const rf = rowOrNode.rainfall ?? rowOrNode.last_rainfall ?? 0;
      const sm = rowOrNode.soil_moisture ?? rowOrNode.last_soil_moisture ?? 0;
      const bv = rowOrNode.battery_voltage ?? rowOrNode.last_battery ?? 0;
      const bsoc = rowOrNode.battery_soc_pct ?? rowOrNode.last_battery_soc ?? 0;
      const at = rowOrNode.air_temp ?? rowOrNode.last_air_temp ?? 0;
      const wt = rowOrNode.water_temp ?? rowOrNode.last_water_temp ?? 0;
      const rssi = rowOrNode.rssi ?? rowOrNode.last_rssi ?? 0;
      const sq = rowOrNode.signal_quality_pct ?? rowOrNode.last_signal_quality ?? 0;
      const seen = rowOrNode.created_at ?? rowOrNode.last_seen ?? "-";

      setF("water_level", `${wl} cm`);
      setF("rainfall", `${rf} mm`);
      setF("soil_moisture", `${sm} %`);
      setF("battery", `${bv} V (${bsoc}%)`);
      setF("temp", `${at} / ${wt} C`);
      setF("rssi", `${rssi} dBm (${sq}%)`);
      setF("last_seen", seen);
      if (rowOrNode.packets_received !== undefined) {
        setF("packets", String(rowOrNode.packets_received));
      }
      const stBadge = card.querySelector("[data-node-status]");
      if (stBadge) {
        stBadge.textContent = "ONLINE";
        stBadge.className = "badge badge-safe";
      }
    }

    if (predObj) {
      const kpiVal = document.querySelector(`[data-kpi-pred="${nodeId}"]`);
      const kpiAlt = document.querySelector(`[data-kpi-alert="${nodeId}"]`);
      if (kpiVal && predObj.pred_plus_3h !== undefined) kpiVal.textContent = String(predObj.pred_plus_3h);
      if (kpiAlt && predObj.alert_level) kpiAlt.textContent = predObj.alert_level;

      if (card) {
        const setP = (name, val) => {
          const el = card.querySelector(`[data-field="${name}"]`);
          if (el && val !== undefined && val !== null) el.textContent = String(val);
        };
        setP("pred_1h", predObj.pred_plus_1h);
        setP("pred_2h", predObj.pred_plus_2h);
        setP("pred_3h", predObj.pred_plus_3h);
        setP("pred_6h", predObj.pred_plus_6h);
        setP("pred_7h", predObj.pred_plus_7h);
        setP("pred_source", predObj.model_source);
        const pBadge = card.querySelector('[data-field="pred_alert"]');
        if (pBadge && predObj.alert_level) {
          pBadge.textContent = predObj.alert_level;
          pBadge.className = `badge ${alertBadgeClass(predObj.alert_level)}`;
        }
      }
    }
  }

  function appendTelemetryRow(row) {
    const tbody = byId("telemetry-tbody");
    if (!tbody || !row) return;
    const tr = document.createElement("tr");
    tr.innerHTML =
      `<td class="mono">#${row.id}</td>` +
      `<td class="mono">${row.node_id}</td>` +
      `<td class="mono">${row.water_level}</td>` +
      `<td class="mono">${row.rainfall}</td>` +
      `<td class="mono">${row.rssi} dBm</td>` +
      `<td class="mono">${row.created_at}</td>`;
    tbody.prepend(tr);
    while (tbody.children.length > 20) {
      tbody.removeChild(tbody.lastChild);
    }

    const telCountEl = byId("kpi-tel-count");
    if (telCountEl) {
      const n = parseInt(telCountEl.textContent, 10);
      if (!Number.isNaN(n)) telCountEl.textContent = String(n + 1);
    }

    if (row.cfai) {
      const cv = byId("kpi-cfai-val");
      const cc = byId("kpi-cfai-cat");
      if (cv) cv.textContent = String(row.cfai.cfai_score);
      if (cc) cc.textContent = `Kategori: ${row.cfai.risk_category}`;
    }

    updateNodeCardView(row.node_id, row, row.prediction || null);
  }

  function startSseStream() {
    if (state.streamPaused) return;
    if (state.eventSource) state.eventSource.close();
    try {
      const es = new EventSource("/api/stream");
      state.eventSource = es;
      es.addEventListener("connected", () => updateStreamBadge("Stream: Live SSE"));
      es.addEventListener("heartbeat", () => {
        if (!state.streamPaused) updateStreamBadge("Stream: Live SSE");
      });
      es.addEventListener("telemetry", (ev) => {
        if (state.streamPaused) return;
        const row = JSON.parse(ev.data);
        if (row.id && row.id > state.lastTelemetryId) {
          state.lastTelemetryId = row.id;
          appendTelemetryRow(row);
          if (byId("visitor-nodes-grid")) {
            updateVisitorNodeCardView(row.node_id, row, row.prediction || null);
            refreshAllNodeCards();
          }
        }
        refreshDashboardChart();
      });
      es.addEventListener("dump", () => {
        if (!state.streamPaused) updateStreamBadge("Stream: Paket SOS/Dump");
      });
      es.onerror = () => {
        if (!state.streamPaused) updateStreamBadge("Stream: Polling Aktif");
      };
    } catch {
      updateStreamBadge("Stream: Polling Aktif");
    }
  }

  async function pollTelemetryDelta() {
    if (state.streamPaused || (!byId("telemetry-tbody") && !byId("visitor-nodes-grid"))) return;
    try {
      const data = await apiJson(`/api/telemetry/history?since_id=${state.lastTelemetryId}&limit=10`);
      if (data.records && data.records.length > 0) {
        if (state.lastTelemetryId === 0) {
          state.lastTelemetryId = data.max_id || 0;
        } else {
          data.records.forEach((r) => appendTelemetryRow(r));
          state.lastTelemetryId = Math.max(state.lastTelemetryId, data.max_id || 0);
          refreshDashboardChart();
          if (byId("visitor-nodes-grid")) {
            await refreshAllNodeCards();
          }
        }
      }
    } catch {
      // Abaikan gangguan sementara
    }
  }

  function initStreamControls() {
    const btn = byId("btn-stream-toggle");
    startSseStream();
    pollTelemetryDelta();
    state.pollTimer = setInterval(pollTelemetryDelta, 6000);

    if (btn) {
      btn.addEventListener("click", () => {
        state.streamPaused = !state.streamPaused;
        btn.setAttribute("aria-pressed", String(state.streamPaused));
        btn.textContent = state.streamPaused ? "Lanjutkan Stream" : "Jeda Stream";
        if (state.streamPaused) {
          if (state.eventSource) state.eventSource.close();
          updateStreamBadge("Stream: Dijeda");
        } else {
          updateStreamBadge("Stream: Menghubungkan...");
          startSseStream();
        }
      });
    }
  }

  /* ========================================================================
     3. WEBGIS MULTI-LAYER LEAFLET
     ======================================================================== */
  function latLngToUtm47N(lat, lon) {
    const a = 6378137.0;
    const f = 1.0 / 298.257223563;
    const k0 = 0.9996;
    const e2 = f * (2.0 - f);
    const ep2 = e2 / (1.0 - e2);
    const phi = (Number(lat) * Math.PI) / 180.0;
    const lam = (Number(lon) * Math.PI) / 180.0;
    const lam0 = (99.0 * Math.PI) / 180.0;

    const sinP = Math.sin(phi);
    const cosP = Math.cos(phi);
    const tanP = Math.tan(phi);
    const nVal = a / Math.sqrt(1.0 - e2 * sinP * sinP);
    const tVal = tanP * tanP;
    const cVal = ep2 * cosP * cosP;
    const aVal = cosP * (lam - lam0);

    const e4 = e2 * e2;
    const e6 = e4 * e2;
    const mVal = a * (
      (1.0 - e2 / 4.0 - (3.0 * e4) / 64.0 - (5.0 * e6) / 256.0) * phi -
      ((3.0 * e2) / 8.0 + (3.0 * e4) / 32.0 + (45.0 * e6) / 1024.0) * Math.sin(2.0 * phi) +
      ((15.0 * e4) / 256.0 + (45.0 * e6) / 1024.0) * Math.sin(4.0 * phi) -
      ((35.0 * e6) / 3072.0) * Math.sin(6.0 * phi)
    );

    const x = 500000.0 + k0 * nVal * (
      aVal +
      ((1.0 - tVal + cVal) * Math.pow(aVal, 3)) / 6.0 +
      ((5.0 - 18.0 * tVal + tVal * tVal + 72.0 * cVal - 58.0 * ep2) * Math.pow(aVal, 5)) / 120.0
    );
    const y = k0 * (
      mVal +
      nVal * tanP * (
        (aVal * aVal) / 2.0 +
        ((5.0 - tVal + 9.0 * cVal + 4.0 * cVal * cVal) * Math.pow(aVal, 4)) / 24.0 +
        ((61.0 - 58.0 * tVal + tVal * tVal + 600.0 * cVal - 330.0 * ep2) * Math.pow(aVal, 6)) / 720.0
      )
    );
    return { x: Number(x.toFixed(2)), y: Number(y.toFixed(2)) };
  }

  function resolveXYPair(lat, lon, utmX, utmY) {
    const latNum = Number(lat);
    const lonNum = Number(lon);
    const hasUtm = utmX !== undefined && utmX !== null && utmY !== undefined && utmY !== null && Number.isFinite(Number(utmX)) && Number.isFinite(Number(utmY));
    const utm = hasUtm ? { x: Number(Number(utmX).toFixed(2)), y: Number(Number(utmY).toFixed(2)) } : latLngToUtm47N(latNum, lonNum);
    return {
      xGeo: lonNum.toFixed(6),
      yGeo: latNum.toFixed(6),
      xUtm: utm.x.toFixed(2),
      yUtm: utm.y.toFixed(2),
    };
  }

  function formatCoordHtml(lat, lon, utmX, utmY) {
    const c = resolveXYPair(lat, lon, utmX, utmY);
    return (
      `<br><span class="mono">Koordinat (X, Y) Geografis: X = ${c.xGeo}, Y = ${c.yGeo}</span>` +
      `<br><span class="mono">Koordinat (X, Y) UTM 47N: X = ${c.xUtm} mE, Y = ${c.yUtm} mN</span>`
    );
  }

  function formatCoordTooltip(title, lat, lon, utmX, utmY) {
    const c = resolveXYPair(lat, lon, utmX, utmY);
    return `${title}<br>X = ${c.xGeo}, Y = ${c.yGeo} (UTM: ${c.xUtm}, ${c.yUtm})`;
  }

  function riskColorHex(score) {
    if (score < 0.30) return "#10B981";
    if (score < 0.60) return "#F59E0B";
    if (score <= 0.80) return "#EA580C";
    return "#DC2626";
  }

  function renderParcelPolygons(scenarioKey) {
    const grp = state.mapLayers.parcels;
    const data = state.gisCache;
    if (!grp || !data) return;
    grp.clearLayers();

    const cadSawah = data.cad_sawah || [];
    const rendererOpt = state.cadRenderer ? { renderer: state.cadRenderer } : {};

    if (cadSawah.length > 0) {
      cadSawah.forEach((sw) => {
        const coords = sw.latlngs || [];
        if (!coords.length) return;
        const cLat = Number(sw.c_lat || 0);
        const cLon = Number(sw.c_lon || 0);
        const val = Number(sw[scenarioKey] || sw.cfai_awas || 0.5);
        const poly = L.polygon(coords, {
          ...rendererOpt,
          color: riskColorHex(val),
          weight: 0.7,
          fillColor: riskColorHex(val),
          fillOpacity: 0.52,
        });
        const label = sw.kode_petak ? `${sw.kode_petak} (${sw.id || "Sawah"})` : (sw.id || "Petak Sawah");
        poly.bindPopup(
          `<strong>Petak Sawah CAD: ${label}</strong><br>` +
          `Blok Tersier: ${sw.kode_petak || "-"} | Saluran: ${sw.sistem_saluran || "-"}<br>` +
          `Luas Poligon: ${Number(sw.luas_ha || 0).toFixed(2)} ha<br>` +
          `CFAI (${scenarioKey}): <strong>${val.toFixed(4)}</strong> (${sw.risk_category || "-"})` +
          formatCoordHtml(cLat, cLon)
        );
        poly.bindTooltip(formatCoordTooltip(label, cLat, cLon), { sticky: true });
        poly.addTo(grp);
      });
      return;
    }

    (data.parcels || []).forEach((p) => {
      try {
        const coords = JSON.parse(p.geojson_coords || "[]");
        if (!coords.length) return;
        let sumLat = 0.0;
        let sumLon = 0.0;
        coords.forEach((pt) => {
          sumLat += Number(pt[0] || 0);
          sumLon += Number(pt[1] || 0);
        });
        const cLat = sumLat / coords.length;
        const cLon = sumLon / coords.length;
        const val = Number(p[scenarioKey] || p.cfai_awas || 0.5);
        const poly = L.polygon(coords, {
          ...rendererOpt,
          color: riskColorHex(val),
          weight: 1.5,
          fillOpacity: 0.48,
        });
        poly.bindPopup(
          `<strong>${p.kode_petak}</strong><br>` +
          `Saluran: ${p.sistem_saluran}<br>` +
          `Luas: ${p.area_ha} ha | Modulus: ${p.modulus_l_s_ha} l/dt/ha<br>` +
          `CFAI (${scenarioKey}): <strong>${val.toFixed(4)}</strong> (${p.risk_category})` +
          formatCoordHtml(cLat, cLon)
        );
        poly.bindTooltip(formatCoordTooltip(p.kode_petak, cLat, cLon), { sticky: true });
        poly.addTo(grp);
      } catch {
        // Lewati koordinat tidak valid
      }
    });
  }

  async function initWebGisMap() {
    const mapEl = byId("peusaga-map");
    if (!mapEl || typeof L === "undefined") return;
    const statusEl = byId("map-status");

    const map = L.map("peusaga-map").setView([5.165, 96.715], 12);
    state.map = map;

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors",
      maxZoom: 18,
    }).addTo(map);

    state.cadRenderer = L.canvas({ padding: 0.5 });
    state.mapLayers = {
      stage2: L.layerGroup().addTo(map),
      canals: L.layerGroup().addTo(map),
      parcels: L.layerGroup().addTo(map),
      landuse: L.layerGroup(),
      infra: L.layerGroup(),
      climate: L.layerGroup(),
      stations: L.layerGroup(),
      survey: L.layerGroup(),
    };

    try {
      const data = await apiJson("/api/gis/layers");
      state.gisCache = data;

      // Lapisan 3 Node IoT LoRa & Koridor Optimal D.I. Pante Lhong (10,439 km)
      const s2Nodes = (data.iot_stage2 && data.iot_stage2.nodes) || [];
      const liveMap = {};
      (data.iot_nodes || []).forEach((n) => {
        liveMap[n.node_id] = n;
      });
      const s2Coords = [];
      s2Nodes.forEach((n) => {
        const live = liveMap[n.node_id] || {};
        const lp = live.latest_prediction || {};
        const lat = Number(live.latitude || n.lat);
        const lon = Number(live.longitude || n.lon);
        const title = live.name || n.name;
        s2Coords.push([lat, lon]);
        L.circleMarker([lat, lon], {
          radius: 9,
          color: "#1A1204",
          fillColor: "#F59E0B",
          fillOpacity: 0.95,
          weight: 2,
        })
          .bindPopup(
            `<strong>${title}</strong><br>` +
            `Zona: ${n.zona}<br>Elevasi: ${n.elevation_m} mdpl | Tiang: ${n.pole_m} m<br>` +
            `TMA Aktual: ${live.last_water_level ?? "-"} cm | RSSI: ${live.last_rssi ?? "-"} dBm | Baterai: ${live.last_battery ?? "-"} V<br>` +
            `Prediksi LSTM: t+1j <strong>${lp.pred_plus_1h ?? "-"} cm</strong> | t+3j <strong>${lp.pred_plus_3h ?? "-"} cm</strong> (${lp.alert_level || "-"})` +
            formatCoordHtml(lat, lon)
          )
          .bindTooltip(formatCoordTooltip(title, lat, lon), { direction: "top" })
          .addTo(state.mapLayers.stage2);
      });
      if (s2Coords.length >= 2) {
        L.polyline(s2Coords, { color: "#D97706", weight: 3.5 })
          .bindPopup("Koridor Relay Multi-Hop LoRa 915 MHz D.I. Pante Lhong (10,439 km)")
          .addTo(state.mapLayers.stage2);
      }

      // Lapisan Saluran, Sungai, Bendung, Bangunan Air, Benchmark & Rawa Suplesi Pante Lhong
      (data.channels || []).forEach((ch) => {
        try {
          const pts = JSON.parse(ch.geojson_coords || "[]");
          if (!pts.length) return;
          const isRiver = ch.segment_type === "sungai";
          L.polyline(pts, {
            color: isRiver ? "#0C4A60" : ch.segment_type === "drainase" ? "#7C3AED" : "#0F6E63",
            weight: isRiver ? 3.5 : 2,
            opacity: 0.85,
          })
            .bindPopup(`<strong>${ch.name}</strong><br>${ch.notes || ""}`)
            .addTo(state.mapLayers.canals);
        } catch {
          // Lewati
        }
      });

      (data.structures || []).forEach((st) => {
        if (st.lat && st.lon) {
          L.circleMarker([st.lat, st.lon], {
            radius: st.type === "Bendung" ? 7 : 4,
            color: "#0F6E63",
            fillColor: st.type === "Bendung" ? "#DC2626" : "#14B8A6",
            fillOpacity: 0.85,
            weight: 1.5,
          })
            .bindPopup(
              `<strong>${st.code}</strong> (${st.type})<br>Saluran: ${st.canal || "-"}<br>${st.notes || ""}` +
              formatCoordHtml(st.lat, st.lon, st.x, st.y)
            )
            .bindTooltip(formatCoordTooltip(`${st.code} (${st.type})`, st.lat, st.lon, st.x, st.y), { direction: "top" })
            .addTo(state.mapLayers.canals);
        }
      });

      (data.benchmarks || []).forEach((bm) => {
        if (bm.lat && bm.lon) {
          L.circleMarker([bm.lat, bm.lon], {
            radius: 4.5,
            color: "#1E3A8A",
            fillColor: "#60A5FA",
            fillOpacity: 0.9,
            weight: 1.5,
          })
            .bindPopup(
              `<strong>Benchmark ${bm.code}</strong><br>${bm.loc || "-"} | Elevasi: ${bm.z ?? "-"} m` +
              formatCoordHtml(bm.lat, bm.lon, bm.x, bm.y)
            )
            .bindTooltip(formatCoordTooltip(`BM ${bm.code}`, bm.lat, bm.lon, bm.x, bm.y), { direction: "top" })
            .addTo(state.mapLayers.canals);
        }
      });

      (data.rawa_suplesi || []).forEach((rs) => {
        if (rs.lat && rs.lon) {
          L.circleMarker([rs.lat, rs.lon], {
            radius: 5,
            color: "#065F46",
            fillColor: "#34D399",
            fillOpacity: 0.85,
            weight: 1.5,
          })
            .bindPopup(
              `<strong>${rs.name}</strong> (${rs.code || "Suplesi"})<br>Luas: ${rs.a ?? "-"} ha | Debit: ${rs.q ?? "-"} l/dt` +
              formatCoordHtml(rs.lat, rs.lon, rs.x, rs.y)
            )
            .bindTooltip(formatCoordTooltip(rs.name, rs.lat, rs.lon, rs.x, rs.y), { direction: "top" })
            .addTo(state.mapLayers.canals);
        }
      });

      (data.embung || []).forEach((eb) => {
        if (eb.latlngs && eb.latlngs.length) {
          const cLat = eb.latlngs.reduce((s, p) => s + p[0], 0) / eb.latlngs.length;
          const cLon = eb.latlngs.reduce((s, p) => s + p[1], 0) / eb.latlngs.length;
          L.polygon(eb.latlngs, {
            color: "#0284C7",
            fillColor: "#38BDF8",
            fillOpacity: 0.45,
            weight: 1.8,
          })
            .bindPopup(
              `<strong>${eb.name}</strong><br>Luas: ${eb.luas_ha ?? "-"} ha` +
              formatCoordHtml(cLat, cLon)
            )
            .bindTooltip(formatCoordTooltip(eb.name, cLat, cLon), { sticky: true })
            .addTo(state.mapLayers.canals);
        }
      });

      (data.boundaries || []).forEach((bd) => {
        if (!bd.latlngs || !bd.latlngs.length) return;
        const cLat = bd.latlngs.reduce((s, p) => s + p[0], 0) / bd.latlngs.length;
        const cLon = bd.latlngs.reduce((s, p) => s + p[1], 0) / bd.latlngs.length;
        const label = `${bd.layer_cad || "Batas Irigasi"} (${bd.id || "-"})`;
        if (bd.type === "Polygon") {
          L.polygon(bd.latlngs, {
            color: "#0F766E",
            weight: 1.2,
            dashArray: "4 4",
            fillOpacity: 0.06,
          })
            .bindPopup(`<strong>${label}</strong><br>Luas: ${bd.luas_ha ?? "-"} ha` + formatCoordHtml(cLat, cLon))
            .addTo(state.mapLayers.canals);
        } else {
          L.polyline(bd.latlngs, {
            color: "#64748B",
            weight: 1.2,
            dashArray: "4 4",
            opacity: 0.7,
          })
            .bindPopup(`<strong>${label}</strong>` + formatCoordHtml(cLat, cLon))
            .addTo(state.mapLayers.canals);
        }
      });

      // Lapisan 103 Petak Tersier CFAI
      renderParcelPolygons("cfai_awas");

      // Lapisan Lokasi Lain: Klimatologi 6 Titik, AWLR/ARR, 26 Titik Survei
      (data.locations || []).forEach((loc) => {
        if (loc.category === "climatology_grid") {
          L.circle([loc.latitude, loc.longitude], {
            radius: 1800,
            color: "#2563EB",
            fillOpacity: 0.12,
            weight: 1.5,
          })
            .bindPopup(
              `<strong>${loc.name}</strong><br>${loc.description}` +
              formatCoordHtml(loc.latitude, loc.longitude)
            )
            .bindTooltip(formatCoordTooltip(loc.name, loc.latitude, loc.longitude), { direction: "top" })
            .addTo(state.mapLayers.climate);
        } else if (loc.category === "awlr_station" || loc.category === "arr_station") {
          L.circleMarker([loc.latitude, loc.longitude], {
            radius: 7,
            color: "#7C3AED",
            fillColor: "#A78BFA",
            fillOpacity: 0.9,
            weight: 2,
          })
            .bindPopup(
              `<strong>${loc.name}</strong><br>${loc.description}` +
              formatCoordHtml(loc.latitude, loc.longitude)
            )
            .bindTooltip(formatCoordTooltip(loc.name, loc.latitude, loc.longitude), { direction: "top" })
            .addTo(state.mapLayers.stations);
        } else if (loc.category === "survey_point") {
          L.circleMarker([loc.latitude, loc.longitude], {
            radius: 5,
            color: "#166534",
            fillColor: "#22C55E",
            fillOpacity: 0.85,
            weight: 1.5,
          })
            .bindPopup(
              `<strong>${loc.name}</strong><br>${loc.description} (Elevasi: ${loc.elevation_m ?? "-"} mdpl)` +
              formatCoordHtml(loc.latitude, loc.longitude)
            )
            .bindTooltip(formatCoordTooltip(loc.name, loc.latitude, loc.longitude), { direction: "top" })
            .addTo(state.mapLayers.survey);
        }
      });

      const baseMapSummary =
        `Peta siap: ${(data.parcels || []).length} petak tersier, ` +
        `${(data.channels || []).length} ruas saluran/sungai, ${(data.structures || []).length} bangunan air, ` +
        `${(data.benchmarks || []).length} benchmark, ${(data.rawa_suplesi || []).length} titik suplesi, dan ${(data.locations || []).length} titik referensi termuat.`;
      if (statusEl) {
        statusEl.textContent = baseMapSummary;
      }

      map.on("mousemove click", (ev) => {
        if (!statusEl || !ev || !ev.latlng) return;
        const c = resolveXYPair(ev.latlng.lat, ev.latlng.lng);
        const prefix = ev.type === "click" ? "Titik Dipilih" : "Kursor";
        statusEl.textContent =
          `${prefix}: X = ${c.xGeo}, Y = ${c.yGeo} | UTM 47N: X = ${c.xUtm} mE, Y = ${c.yUtm} mN | ${baseMapSummary}`;
      });

      // Wire layer toggle checkboxes
      async function ensureCadExtrasLoaded() {
        if (state.cadExtrasCache) return;
        try {
          const ex = await apiJson("/api/gis/cad-extras");
          state.cadExtrasCache = ex;
          const rOpt = state.cadRenderer ? { renderer: state.cadRenderer } : {};

          const luStyles = [
            { key: "pemukiman", label: "Pemukiman CAD", color: "#d97706", fill: "#f59e0b", opacity: 0.36 },
            { key: "kebun", label: "Kebun / Perkebunan CAD", color: "#15803d", fill: "#22c55e", opacity: 0.28 },
            { key: "tegalan", label: "Tegalan / Ladang CAD", color: "#a16207", fill: "#eab308", opacity: 0.28 },
            { key: "semak_belukar", label: "Semak Belukar CAD", color: "#65a30d", fill: "#84cc16", opacity: 0.25 },
          ];
          luStyles.forEach((st) => {
            (ex[st.key] || []).forEach((coords) => {
              if (!coords || !coords.length) return;
              const p = L.polygon(coords, {
                ...rOpt,
                color: st.color,
                weight: 0.6,
                fillColor: st.fill,
                fillOpacity: st.opacity,
              });
              const pt = coords[0];
              p.bindPopup(`<strong>${st.label}</strong>` + formatCoordHtml(pt[0], pt[1]));
              p.addTo(state.mapLayers.landuse);
            });
          });

          (ex.roads || []).forEach((pts) => {
            if (!pts || pts.length < 2) return;
            L.polyline(pts, {
              ...rOpt,
              color: "#475569",
              weight: 1.4,
              opacity: 0.72,
            }).addTo(state.mapLayers.infra);
          });

          (ex.contours_mayor || []).forEach((pts) => {
            if (!pts || pts.length < 2) return;
            L.polyline(pts, {
              ...rOpt,
              color: "#92400e",
              weight: 1.1,
              opacity: 0.6,
            }).addTo(state.mapLayers.infra);
          });

          (ex.contours_minor || []).forEach((pts) => {
            if (!pts || pts.length < 2) return;
            L.polyline(pts, {
              ...rOpt,
              color: "#b45309",
              weight: 0.6,
              opacity: 0.35,
            }).addTo(state.mapLayers.infra);
          });

          (ex.contours_5m || []).forEach((pts) => {
            if (!pts || pts.length < 2) return;
            L.polyline(pts, {
              ...rOpt,
              color: "#78350f",
              weight: 1.4,
              dashArray: "4,3",
              opacity: 0.65,
            }).addTo(state.mapLayers.infra);
          });

          (ex.admin_labels || []).forEach((adm) => {
            L.circleMarker([adm.lat, adm.lon], {
              ...rOpt,
              radius: 3.5,
              color: "#1e293b",
              fillColor: "#f8fafc",
              fillOpacity: 0.9,
              weight: 1.2,
            })
              .bindPopup(`<strong>${adm.name}</strong><br>${adm.kind || "Toponimi"}` + formatCoordHtml(adm.lat, adm.lon))
              .bindTooltip(formatCoordTooltip(adm.name, adm.lat, adm.lon), { sticky: true })
              .addTo(state.mapLayers.infra);
          });
        } catch (err) {
          console.error("Gagal memuat cad-extras:", err);
        }
      }

      const mapBind = {
        "layer-stage2": "stage2",
        "layer-canals": "canals",
        "layer-parcels": "parcels",
        "layer-landuse": "landuse",
        "layer-infra": "infra",
        "layer-climate": "climate",
        "layer-stations": "stations",
        "layer-survey": "survey",
      };
      Object.entries(mapBind).forEach(([elId, key]) => {
        const cb = byId(elId);
        if (!cb) return;
        cb.addEventListener("change", async () => {
          if (cb.checked) {
            if (key === "landuse" || key === "infra") {
              await ensureCadExtrasLoaded();
            }
            state.mapLayers[key].addTo(map);
          } else {
            map.removeLayer(state.mapLayers[key]);
          }
        });
      });

      const scSelect = byId("parcel-scenario-select");
      if (scSelect) {
        scSelect.addEventListener("change", () => {
          renderParcelPolygons(scSelect.value);
        });
      }
    } catch (err) {
      if (statusEl) {
        statusEl.className = "state-box state-error";
        statusEl.textContent = `Gagal memuat lapisan WebGIS: ${err.message}`;
      }
    }
  }

  /* ========================================================================
     4. GRAFIK DASHBOARD & TOMBOL SIMULASI CEPAT
     ======================================================================== */
  async function refreshDashboardChart() {
    const canvas = byId("dash-hydro-chart");
    if (!canvas || typeof Chart === "undefined") return;
    try {
      const data = await apiJson("/api/telemetry?limit=24");
      const rows = (data.telemetry || []).slice().reverse();
      const labels = rows.map((r) => (r.created_at || "").slice(11, 19));
      const wlData = rows.map((r) => Number(r.water_level || 0));
      const rfData = rows.map((r) => Number(r.rainfall || 0));

      if (state.dashChart) state.dashChart.destroy();
      state.dashChart = new Chart(canvas, {
        type: "line",
        data: {
          labels,
          datasets: [
            {
              label: "Tinggi Muka Air (cm)",
              data: wlData,
              borderColor: "#0C4A60",
              backgroundColor: "rgba(12, 74, 96, 0.14)",
              fill: true,
              tension: 0.25,
              yAxisID: "y",
            },
            {
              label: "Curah Hujan (mm)",
              data: rfData,
              borderColor: "#D97706",
              backgroundColor: "rgba(217, 119, 6, 0.25)",
              type: "bar",
              yAxisID: "y1",
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: {
            y: { title: { display: true, text: "TMA (cm)" } },
            y1: { position: "right", grid: { drawOnChartArea: false }, title: { display: true, text: "Hujan (mm)" } },
          },
        },
      });
    } catch {
      // Abaikan jika grafik gagal dimuat
    }
  }

  async function refreshAllNodeCards() {
    try {
      const res = await apiJson("/api/nodes");
      (res.nodes || []).forEach((n) => {
        updateNodeCardView(n.node_id, n, n.latest_prediction || null);
      });
      if (res.visitor_summary) {
        updateVisitorSummaryDOM(res.visitor_summary);
      }
    } catch {
      // Abaikan gangguan sinkronisasi sementara
    }
  }

  function initDashboardActions() {
    const btnSim = byId("btn-dash-simulate");
    if (!btnSim) return;
    btnSim.addEventListener("click", async () => {
      btnSim.disabled = true;
      btnSim.textContent = "Mengirim Paket 3 Node...";
      try {
        await apiJson("/api/iot/simulate", {
          method: "POST",
          body: JSON.stringify({
            node_id: "all",
            mode: "normal",
            water_level: Number((150 + Math.random() * 35).toFixed(1)),
            hilir_water_level: Number((125 + Math.random() * 30).toFixed(1)),
            gateway_water_level: Number((105 + Math.random() * 30).toFixed(1)),
            rainfall: Number((10 + Math.random() * 25).toFixed(1)),
          }),
        });
        await pollTelemetryDelta();
        await refreshAllNodeCards();
      } catch (err) {
        alert("Gagal mengirim simulasi: " + err.message);
      } finally {
        btnSim.disabled = false;
        btnSim.textContent = "Simulasi Telemetri & Prediksi 3 Node";
      }
    });
  }

  /* ========================================================================
     5. HALAMAN AI LSTM & KLIMATOLOGI
     ======================================================================== */
  function renderLstmHorizonChart(pred) {
    const canvas = byId("lstm-horizon-chart");
    if (!canvas || typeof Chart === "undefined" || !pred) return;
    const labels = ["Sekarang", "t+1 Jam", "t+2 Jam", "t+3 Jam", "t+6 Jam", "t+7 Jam"];
    const values = [
      pred.current_water_level_cm ?? pred.current_water_level ?? 150,
      pred.pred_plus_1h,
      pred.pred_plus_2h,
      pred.pred_plus_3h,
      pred.pred_plus_6h || pred.pred_plus_3h,
      pred.pred_plus_7h || pred.pred_plus_3h,
    ];
    const bankfull = pred.bankfull_cm || 180;

    if (state.lstmChart) state.lstmChart.destroy();
    state.lstmChart = new Chart(canvas, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Proyeksi TMA (cm)",
            data: values,
            borderColor: "#0F6E63",
            backgroundColor: "rgba(15, 110, 99, 0.16)",
            fill: true,
            tension: 0.25,
          },
          {
            label: "Ambang Bankfull Tanggul (cm)",
            data: labels.map(() => bankfull),
            borderColor: "#DC2626",
            borderDash: [6, 5],
            pointRadius: 0,
            fill: false,
          },
        ],
      },
      options: { responsive: true, maintainAspectRatio: false },
    });
  }

  function initAiLstmPage() {
    const form = byId("lstm-predict-form");
    const nodeSelect = byId("lstm-node-select");

    function applyNodeToLstmForm(nodeId) {
      const nodeList = window.PEUSAGA_NODES || [];
      const predsMap = window.PEUSAGA_NODE_PREDS || {};
      const nodeInfo = nodeList.find((n) => n.node_id === nodeId) || {};
      const nodePred = predsMap[nodeId] || nodeInfo.latest_prediction || (window.PEUSAGA_LATEST_PREDS && window.PEUSAGA_LATEST_PREDS[0]);

      if (nodeSelect) nodeSelect.value = nodeId;
      if (byId("lstm-current-cm") && (nodeInfo.last_water_level !== undefined || (nodePred && nodePred.current_water_level !== undefined))) {
        byId("lstm-current-cm").value = nodeInfo.last_water_level ?? nodePred.current_water_level ?? 155;
      }
      if (byId("lstm-bankfull-cm") && nodeInfo.bankfull_level_cm !== undefined) {
        byId("lstm-bankfull-cm").value = nodeInfo.bankfull_level_cm;
      }
      if (byId("lstm-soil-pct") && nodeInfo.last_soil_moisture !== undefined) {
        byId("lstm-soil-pct").value = nodeInfo.last_soil_moisture;
      }
      if (byId("lstm-hum-pct") && nodeInfo.last_air_humidity !== undefined) {
        byId("lstm-hum-pct").value = nodeInfo.last_air_humidity;
      }
      if (nodePred) {
        const merged = { ...nodePred, bankfull_cm: nodeInfo.bankfull_level_cm || nodePred.bankfull_cm || 180 };
        renderLstmHorizonChart(merged);
      }
    }

    if (nodeSelect) {
      nodeSelect.addEventListener("change", () => applyNodeToLstmForm(nodeSelect.value));
    }
    document.querySelectorAll(".btn-load-node-pred").forEach((btn) => {
      btn.addEventListener("click", () => {
        const nid = btn.getAttribute("data-node-id");
        if (nid) {
          applyNodeToLstmForm(nid);
          const ch = byId("lstm-horizon-chart");
          if (ch) ch.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
      });
    });

    if (window.PEUSAGA_NODE_PREDS && window.PEUSAGA_NODE_PREDS.node_hulu) {
      applyNodeToLstmForm("node_hulu");
    } else if (window.PEUSAGA_LATEST_PREDS && window.PEUSAGA_LATEST_PREDS[0]) {
      renderLstmHorizonChart(window.PEUSAGA_LATEST_PREDS[0]);
    }
    const climCanvas = byId("clim-bar-chart");
    if (climCanvas && window.PEUSAGA_CLIM_POINTS && typeof Chart !== "undefined") {
      new Chart(climCanvas, {
        type: "bar",
        data: {
          labels: window.PEUSAGA_CLIM_POINTS.map((p) => p.point_code),
          datasets: [
            {
              label: "Curah Hujan Tahunan (mm)",
              data: window.PEUSAGA_CLIM_POINTS.map((p) => p.annual_mm),
              backgroundColor: "#0C4A60",
            },
            {
              label: "Bulan Terbasah (mm)",
              data: window.PEUSAGA_CLIM_POINTS.map((p) => p.wettest_mm),
              backgroundColor: "#D97706",
            },
          ],
        },
        options: { responsive: true, maintainAspectRatio: false },
      });
    }

    if (!form) return;
    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const box = byId("lstm-result-box");
      box.className = "state-box";
      box.textContent = "Menjalankan inferensi jaringan saraf Keras LSTM...";
      try {
        const res = await apiJson("/api/predict", {
          method: "POST",
          body: JSON.stringify({
            node_id: byId("lstm-node-select").value,
            override_current_cm: Number(byId("lstm-current-cm").value),
            override_rain_mm: Number(byId("lstm-rain-mm").value),
            soil_moisture_pct: Number(byId("lstm-soil-pct").value),
            air_humidity_pct: Number(byId("lstm-hum-pct").value),
            bankfull_cm: Number(byId("lstm-bankfull-cm").value),
            save: true,
          }),
        });
        const p = res.prediction;
        box.innerHTML =
          `<strong>Status Siaga: ${p.alert_level}</strong> (Sumber: ${p.model_source}, ${p.inference_time_ms} ms)<br>` +
          `TMA Saat Ini: <span class="mono">${p.current_water_level_cm} cm</span> | ` +
          `t+1j: <span class="mono">${p.pred_plus_1h} cm</span> | ` +
          `t+3j: <span class="mono">${p.pred_plus_3h} cm</span> | ` +
          `t+6j: <span class="mono">${p.pred_plus_6h} cm</span> | ` +
          `t+7j: <span class="mono">${p.pred_plus_7h} cm</span>`;
        renderLstmHorizonChart(p);
      } catch (err) {
        box.className = "state-box state-error";
        box.textContent = err.message;
      }
    });
  }

  /* ========================================================================
     6. HALAMAN AHP-CROPDAM-X & 103 PETAK TERSIER
     ======================================================================== */
  function initCropdamxPage() {
    const form = byId("cropdamx-form");
    if (form) {
      form.addEventListener("submit", async (ev) => {
        ev.preventDefault();
        const box = byId("cropdamx-result-box");
        box.className = "state-box";
        box.textContent = "Menghitung skor CFAI & mengevaluasi Surrogate RF / Bayesian...";
        try {
          const res = await apiJson("/api/risk/cropdamx", {
            method: "POST",
            body: JSON.stringify({
              depth_cm: Number(byId("cx-depth").value),
              duration_hours: Number(byId("cx-duration").value),
              velocity_kmh: Number(byId("cx-velocity").value),
              growth_stage: byId("cx-stage").value,
              crop_type: byId("cx-variety").value,
              drainage_modulus: Number(byId("cx-modulus").value),
              save: byId("cx-save-db").checked,
            }),
          });
          const c = res.cfai;
          const s = res.surrogate;
          const sensTxt = (res.sensitivity || [])
            .map((x) => `${x.criteria_code} (${x.perturbation}): ${x.new_cfai}`)
            .join(" | ");
          box.innerHTML =
            `<strong>Skor CFAI: ${c.cfai_score} - Kelas Risiko: ${c.risk_category} (${c.color_indicator})</strong><br>` +
            `RF Surrogate: <span class="mono">${s.rf_surrogate_score ?? "-"}</span> | ` +
            `Bayesian Mean &plusmn; &sigma;: <span class="mono">${s.bayes_mean ?? "-"} &plusmn; ${s.bayes_sigma ?? "-"}</span><br>` +
            `<strong>Rekomendasi Mitigasi:</strong> ${c.recommendation}<br>` +
            `<small class="muted">Sensitivitas &plusmn;20%: ${sensTxt}</small>`;
        } catch (err) {
          box.className = "state-box state-error";
          box.textContent = err.message;
        }
      });
    }

    const searchInput = byId("parcel-search");
    const riskSelect = byId("parcel-risk-filter");
    const tbody = byId("parcels-tbody");
    if (searchInput && riskSelect && tbody) {
      async function filterParcels() {
        const params = new URLSearchParams();
        if (searchInput.value.trim()) params.set("search", searchInput.value.trim());
        if (riskSelect.value) params.set("risk", riskSelect.value);
        try {
          const data = await apiJson(`/api/cropdamx/parcels?${params.toString()}`);
          if (!data.parcels.length) {
            tbody.innerHTML = '<tr><td colspan="9" class="muted">Tidak ada petak tersier yang cocok dengan filter.</td></tr>';
            return;
          }
          tbody.innerHTML = data.parcels
            .map((p) => {
              const cls =
                p.risk_category === "Rendah"
                  ? "badge-safe"
                  : p.risk_category === "Sedang"
                    ? "badge-warn"
                    : p.risk_category === "Tinggi"
                      ? "badge-alert"
                      : "badge-danger";
              return (
                `<tr>` +
                `<td class="mono"><strong>${p.kode_petak}</strong></td>` +
                `<td>${p.sistem_saluran}</td><td>${p.orientasi}</td>` +
                `<td class="mono">${Number(p.area_ha).toFixed(2)}</td>` +
                `<td class="mono">${Number(p.modulus_l_s_ha).toFixed(3)}</td>` +
                `<td class="mono">${Number(p.cfai_siaga).toFixed(4)}</td>` +
                `<td class="mono">${Number(p.cfai_awas).toFixed(4)}</td>` +
                `<td class="mono">${Number(p.cfai_ekstrem).toFixed(4)}</td>` +
                `<td><span class="badge ${cls}">${p.risk_category}</span></td>` +
                `</tr>`
              );
            })
            .join("");
        } catch {
          // Biarkan tabel sebelumnya
        }
      }
      searchInput.addEventListener("input", filterParcels);
      riskSelect.addEventListener("change", filterParcels);
    }
  }

  /* ========================================================================
     7. HALAMAN KONSOL TEKNIK LORA, KALIBRASI & SIMULATOR
     ======================================================================== */
  function initConsolePage() {
    const calNodeSelect = byId("cal-node-id");
    if (calNodeSelect && window.PEUSAGA_CALIBRATIONS) {
      calNodeSelect.addEventListener("change", () => {
        const found = window.PEUSAGA_CALIBRATIONS.find((c) => c.node_id === calNodeSelect.value);
        if (found) {
          byId("cal-pole-cm").value = found.pole_height_cm;
          byId("cal-offset-cm").value = found.water_level_offset_cm;
          byId("cal-bankfull-cm").value = found.bankfull_level_cm;
          byId("cal-rain-mult").value = found.rain_multiplier;
          byId("cal-soil-air").value = found.soil_air_raw;
          byId("cal-soil-water").value = found.soil_water_raw;
        }
      });
    }

    const calForm = byId("calibration-form");
    if (calForm) {
      calForm.addEventListener("submit", async (ev) => {
        ev.preventDefault();
        const fb = byId("cal-feedback");
        fb.className = "state-box";
        try {
          const res = await apiJson("/api/calibration", {
            method: "POST",
            body: JSON.stringify({
              node_id: byId("cal-node-id").value,
              pole_height_cm: Number(byId("cal-pole-cm").value),
              water_level_offset_cm: Number(byId("cal-offset-cm").value),
              bankfull_level_cm: Number(byId("cal-bankfull-cm").value),
              rain_multiplier: Number(byId("cal-rain-mult").value),
              soil_air_raw: Number(byId("cal-soil-air").value),
              soil_water_raw: Number(byId("cal-soil-water").value),
            }),
          });
          fb.textContent = `Kalibrasi ${res.calibration.node_id} diperbarui pada ${res.calibration.updated_at}.`;
        } catch (err) {
          fb.className = "state-box state-error";
          fb.textContent = err.message;
        }
      });
    }

    const simForm = byId("sim-packet-form");
    if (simForm) {
      simForm.addEventListener("submit", async (ev) => {
        ev.preventDefault();
        const fb = byId("sim-feedback");
        fb.className = "state-box";
        fb.textContent = "Mengirim paket...";
        try {
          const res = await fetch("/api/iot/simulate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              node_id: byId("sim-node").value,
              mode: byId("sim-mode").value,
              water_level: Number(byId("sim-wl").value),
              rainfall: Number(byId("sim-rain").value),
              rssi: Number(byId("sim-rssi").value),
              emergency_text: byId("sim-sos-msg").value,
            }),
          });
          const data = await res.json();
          fb.innerHTML = `Respon server (HTTP ${data.http_code}): <span class="mono">${JSON.stringify(data.upstream)}</span>`;
        } catch (err) {
          fb.className = "state-box state-error";
          fb.textContent = err.message;
        }
      });
    }

    const loraForm = byId("lora-calc-form");
    if (loraForm) {
      loraForm.addEventListener("submit", async (ev) => {
        ev.preventDefault();
        const box = byId("lora-result-box");
        try {
          const res = await apiJson("/api/lora/link-budget", {
            method: "POST",
            body: JSON.stringify({
              distance_km: Number(byId("lora-dist").value),
              rain_mm_h: Number(byId("lora-rain").value),
              sf: Number(byId("lora-sf").value),
              tx_power_dbm: Number(byId("lora-tx").value),
            }),
          });
          const r = res.result;
          box.innerHTML =
            `<strong>RSSI: ${r.rssi_dbm} dBm | Link Margin: ${r.link_margin_db} dB | Estimasi PDR: ${r.estimated_pdr_pct}%</strong><br>` +
            `FSPL: <span class="mono">${r.fspl_db} dB</span> | ToA: <span class="mono">${r.toa_ms} ms</span> | ` +
            `Fresnel R1: <span class="mono">${r.fresnel_r1_mid_m} m</span> (Min. clearance 60%: ${r.recommended_clearance_m} m)`;
        } catch (err) {
          box.className = "state-box state-error";
          box.textContent = err.message;
        }
      });
    }

    const pwrForm = byId("power-calc-form");
    if (pwrForm) {
      pwrForm.addEventListener("submit", async (ev) => {
        ev.preventDefault();
        const box = byId("power-result-box");
        try {
          const res = await apiJson("/api/iot/power-autonomy", {
            method: "POST",
            body: JSON.stringify({
              battery_wh: Number(byId("pwr-wh").value),
              avg_load_w: Number(byId("pwr-load").value),
              panel_wp: Number(byId("pwr-wp").value),
              rainy_days_no_sun: Number(byId("pwr-days").value),
            }),
          });
          const p = res.result;
          box.innerHTML =
            `<strong>Otonomi Tanpa Matahari: ${p.autonomy_hours} jam (${p.status_text})</strong><br>` +
            `Konsumsi harian: <span class="mono">${p.daily_consumption_wh} Wh</span> | ` +
            `Panen surya: <span class="mono">${p.daily_solar_yield_wh} Wh/hari</span> | ` +
            `Sisa SoC pasca mendung: <span class="mono">${p.soc_after_rainy_days_pct}%</span>`;
        } catch (err) {
          box.className = "state-box state-error";
          box.textContent = err.message;
        }
      });
    }
  }

  /* ========================================================================
     8. KATALOG DATASET & HALAMAN ADMIN
     ======================================================================== */
  function initDatasetsPage() {
    document.querySelectorAll(".btn-preview-dataset").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const rel = btn.getAttribute("data-relpath");
        const meta = byId("dataset-preview-meta");
        const box = byId("dataset-preview-box");
        meta.textContent = `Memuat: ${rel}...`;
        box.textContent = "Mengambil baris awal berkas secara baca-saja...";
        try {
          const data = await apiJson(`/api/datasets/preview?path=${encodeURIComponent(rel)}&limit=30`);
          const pv = data.preview;
          meta.textContent = `Berkas: ${pv.filename} (Tipe: ${pv.type})`;
          if (pv.type === "csv") {
            const headerLine = pv.headers.join(" | ");
            const bodyLines = pv.rows.map((r) => r.join(" | ")).join("\n");
            box.textContent = `${headerLine}\n${"-".repeat(Math.min(80, headerLine.length))}\n${bodyLines}`;
          } else {
            box.textContent = pv.content || "(Berkas kosong)";
          }
          box.scrollIntoView({ behavior: "smooth", block: "nearest" });
        } catch (err) {
          meta.textContent = "Gagal membaca berkas.";
          box.textContent = err.message;
        }
      });
    });
  }

  function initAdminPage() {
    const loginForm = byId("login-form");
    if (loginForm) {
      loginForm.addEventListener("submit", async (ev) => {
        ev.preventDefault();
        const banner = byId("auth-status-banner");
        banner.className = "state-box";
        try {
          const res = await apiJson("/api/auth/login", {
            method: "POST",
            body: JSON.stringify({
              username: byId("auth-username").value,
              password: byId("auth-password").value,
            }),
          });
          banner.innerHTML = `Masuk sebagai <strong>${res.user.username}</strong> (${res.user.role}).`;
        } catch (err) {
          banner.className = "state-box state-error";
          banner.textContent = err.message;
        }
      });
    }

    const logoutBtn = byId("btn-logout");
    if (logoutBtn) {
      logoutBtn.addEventListener("click", async () => {
        await apiJson("/api/auth/logout", { method: "POST" });
        window.location.href = "/";
      });
    }

    const setForm = byId("settings-form");
    if (setForm) {
      setForm.addEventListener("submit", async (ev) => {
        ev.preventDefault();
        const fb = byId("settings-feedback");
        const payload = {};
        setForm.querySelectorAll("input[name]").forEach((inp) => {
          payload[inp.name] = inp.value;
        });
        try {
          await apiJson("/api/admin/settings", {
            method: "POST",
            body: JSON.stringify({ settings: payload }),
          });
          fb.className = "state-box";
          fb.textContent = "Seluruh pengaturan berhasil diperbarui di MySQL.";
        } catch (err) {
          fb.className = "state-box state-error";
          fb.textContent = err.message;
        }
      });
    }

    const bcForm = byId("broadcast-form");
    if (bcForm) {
      bcForm.addEventListener("submit", async (ev) => {
        ev.preventDefault();
        const fb = byId("bc-feedback");
        try {
          const res = await apiJson("/api/broadcast", {
            method: "POST",
            body: JSON.stringify({
              channel: byId("bc-channel").value,
              alert_level: byId("bc-level").value,
              recipient_group: byId("bc-recipient").value,
              message_text: byId("bc-message").value,
            }),
          });
          const b = res.broadcast;
          fb.className = "state-box";
          fb.textContent = `Diseminasi ${b.channel} (${b.status}): ${b.response_summary}`;
          const tbody = byId("broadcast-tbody");
          if (tbody) {
            const tr = document.createElement("tr");
            tr.innerHTML =
              `<td class="mono">${b.created_at}</td><td class="mono">${b.channel}</td>` +
              `<td><span class="badge badge-alert">${b.alert_level}</span></td>` +
              `<td class="mono">${b.status}</td><td>${b.message_text}</td>`;
            tbody.prepend(tr);
          }
        } catch (err) {
          fb.className = "state-box state-error";
          fb.textContent = err.message;
        }
      });
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    initThemeToggle();
    initStreamControls();
    initWebGisMap();
    refreshDashboardChart();
    initDashboardActions();
    initAiLstmPage();
    initCropdamxPage();
    initConsolePage();
    initDatasetsPage();
    initAdminPage();
  });
})();
