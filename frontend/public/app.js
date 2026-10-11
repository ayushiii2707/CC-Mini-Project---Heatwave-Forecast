// HeatGuard frontend. Talks to the backend only through the /api/ reverse proxy (nginx).
const API = "/api";
const COLORS = { Normal: "#2fb67c", Heatwave: "#ff8a1f", "Severe heatwave": "#ff3b4e" };
const LEVEL_CLASS = { Normal: "normal", Heatwave: "heatwave", "Severe heatwave": "severe" };
const $ = (id) => document.getElementById(id);
const state = { city: "Delhi", date: "2024-05-27", observed: null, forecast: null, outlook: null, whatif: false };
let trendChart, maeChart, map, markers = {};

const fmtDay = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-IN", { weekday: "short" });
const fmtDate = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short" });
const fmtLong = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" });
const badgeClass = (level) => "badge-" + level.split(" ")[0];

async function api(path, options) {
  const res = await fetch(API + path, options);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof body.detail === "string" ? body.detail
      : Array.isArray(body.detail) ? body.detail.map((d) => d.msg).join("; ") : res.statusText;
    throw new Error(`HTTP ${res.status}: ${detail}`);
  }
  return body;
}

function showError(msg) { $("error").textContent = msg; $("error").hidden = !msg; }

// ---------- data loading ----------
async function refresh() {
  showError("");
  state.whatif = false;
  try {
    const [observed, outlook] = await Promise.all([
      api(`/observed?city=${encodeURIComponent(state.city)}&date=${state.date}&days=30`),
      api(`/outlook?date=${state.date}`),
    ]);
    state.observed = observed;
    state.outlook = outlook;
    state.forecast = await api("/predict", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ city: state.city, date: state.date, recent_tmax: observed.recent_tmax }),
    });
    fillWhatIf(observed.recent_tmax);
    render();
  } catch (e) { showError(e.message); }
}

async function runWhatIf() {
  showError("");
  const values = [...$("whatif").querySelectorAll("input")].map((i) => parseFloat(i.value));
  try {
    state.forecast = await api("/predict", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ city: state.city, date: state.date, recent_tmax: values }),
    });
    state.whatif = true;
    render();
    $("whatif-note").textContent = "What-if mode: forecast uses your values, so actual IMD values are hidden.";
    $("whatif-note").classList.add("mode");
  } catch (e) { showError("What-if rejected by the backend. " + e.message); }
}

// ---------- rendering ----------
function render() {
  renderBanner(); renderKpis(); renderDays(); renderTrend(); renderMap(); renderRanking();
  $("served-by").textContent = `Forecast served by ${state.forecast.pod} in ${state.forecast.inference_ms} ms`;
}

function renderBanner() {
  const f = state.forecast;
  const level = f.highest_alert;
  $("banner").className = "banner level-" + LEVEL_CLASS[level];
  $("banner-kicker").textContent = `${state.city} · 7-day outlook from ${fmtLong(state.date)}${state.whatif ? " · what-if values" : ""}`;
  const firstDay = f.first_alert_day ? f.days[f.first_alert_day - 1] : null;
  $("banner-title").textContent = level === "Normal" ? "No heatwave expected in the next 7 days"
    : `${level} conditions expected from ${fmtDay(firstDay.date)} ${fmtDate(firstDay.date)}`;
  $("banner-text").textContent = f.advisory;
  $("banner-badge").textContent = level;
  $("banner-badge").className = "banner-badge " + badgeClass(level);
  const validated = f.highest_validated_alert;
  $("banner-meta").innerHTML = `Peak ${f.peak.forecast_tmax.toFixed(1)} °C on ${fmtDate(f.peak.date)}<br>`
    + (validated === level ? "Alert within the validated range (days 1–4)" : `Days 1–4: ${validated} · later days low-confidence`);
}

function renderKpis() {
  const f = state.forecast, o = state.observed;
  const today = o.history[o.history.length - 1];
  $("k-today").textContent = state.whatif ? "what-if" : `${today.tmax.toFixed(1)} °C`;
  $("k-today-sub").textContent = state.whatif ? "using your values" : `IMD observed, ${fmtDate(state.date)}`;
  $("k-peak").textContent = `${f.peak.forecast_tmax.toFixed(1)} °C`;
  $("k-peak-sub").textContent = `${fmtDay(f.peak.date)} ${fmtDate(f.peak.date)}`;
  $("k-normal").textContent = `${today.normal.toFixed(1)} °C`;
  const dep = today.tmax - today.normal;
  $("k-normal-sub").textContent = state.whatif ? "climatological normal" : `today is ${dep >= 0 ? "+" : ""}${dep.toFixed(1)} °C vs normal`;
  const alertDays = f.days.filter((d) => d.alert !== "Normal");
  $("k-alerts").textContent = `${alertDays.length} / 7`;
  $("k-alerts-sub").textContent = `${alertDays.filter((d) => d.alert_confidence === "validated").length} in validated range`;
}

function renderDays() {
  const actual = state.whatif ? [] : state.observed.actual_next_7;
  $("days").innerHTML = state.forecast.days.map((d, i) => {
    const a = actual[i] && actual[i].tmax;
    const actualRow = a == null ? "" : `<div class="row"><span>IMD actual</span><b class="${Math.abs(a - d.forecast_tmax) <= d.typical_error_c * 1.5 ? "actual-hit" : "actual-miss"}">${a.toFixed(1)} °C</b></div>`;
    return `<div class="day alert-${d.alert.split(" ")[0]} ${d.alert_confidence === "low" ? "low" : ""}" title="IMD rule applied to ${d.upper_forecast_tmax.toFixed(1)} °C (forecast + ${d.alert_margin_c} °C margin): ${d.rule}">
      <div class="dname">Day ${d.day} · ${fmtDay(d.date)}</div><div class="ddate">${fmtDate(d.date)}</div>
      <div class="temp">${d.forecast_tmax.toFixed(1)}°</div><div class="err">± ${d.typical_error_c.toFixed(1)} °C typical error</div>
      <span class="badge ${badgeClass(d.alert)}">${d.alert}</span>
      <div class="row"><span>Normal</span><b>${d.normal_tmax.toFixed(1)} °C</b></div>
      <div class="row"><span>Alert basis</span><b>${d.upper_forecast_tmax.toFixed(1)} °C</b></div>
      <div class="row"><span>Departure</span><b>${d.departure_from_normal >= 0 ? "+" : ""}${d.departure_from_normal.toFixed(1)} °C</b></div>
      ${actualRow}
      <div class="conf ${d.alert_confidence}">${d.alert_confidence === "validated" ? "✓ validated alert" : "low-confidence alert"}</div>
    </div>`;
  }).join("");
}

function renderTrend() {
  const o = state.observed, f = state.forecast;
  const hist = state.whatif ? o.history.slice(0, -7) : o.history;
  const labels = [...hist.map((h) => h.date), ...f.days.map((d) => d.date)];
  const nH = hist.length, pad = (arr, before) => [...Array(before).fill(null), ...arr];
  const fc = f.days.map((d) => d.forecast_tmax);
  const lastObs = state.whatif ? null : hist[nH - 1].tmax;
  const forecastLine = [...Array(nH - 1).fill(null), lastObs, ...fc];
  const datasets = [
    { label: "Observed (IMD)", data: [...hist.map((h) => h.tmax), ...Array(7).fill(null)], borderColor: "#e8edf6", backgroundColor: "#e8edf6", pointRadius: 2, tension: .25 },
    { label: "Normal", data: [...hist.map((h) => h.normal), ...f.days.map((d) => d.normal_tmax)], borderColor: "#8d9ab3", borderDash: [5, 5], pointRadius: 0 },
    { label: "Forecast", data: forecastLine, borderColor: "#ff6a2b", backgroundColor: "#ff6a2b", borderWidth: 3, pointRadius: 3, tension: .25 },
    { label: "Uncertainty (±typical error)", data: pad(f.days.map((d) => d.forecast_tmax + d.typical_error_c), nH), borderColor: "transparent", backgroundColor: "#ff6a2b2e", pointRadius: 0, fill: "+1" },
    { label: "_low", data: pad(f.days.map((d) => d.forecast_tmax - d.typical_error_c), nH), borderColor: "transparent", pointRadius: 0, fill: false },
    { label: "40 °C plains threshold", data: labels.map(() => 40), borderColor: "#ff3b4e88", borderDash: [2, 4], pointRadius: 0, borderWidth: 1 },
  ];
  if (!state.whatif) {
    datasets.push({ label: "Actual IMD (next 7 days)", data: pad(o.actual_next_7.map((a) => a.tmax), nH), borderColor: "#2fb67c", backgroundColor: "#2fb67c", showLine: false, pointRadius: 5, pointStyle: "rectRot" });
  }
  const cfg = {
    type: "line", data: { labels: labels.map(fmtDate), datasets },
    options: { responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false }, animation: { duration: 300 },
      scales: { x: { ticks: { color: "#8d9ab3", maxTicksLimit: 12 }, grid: { color: "#1c263a" } },
                y: { ticks: { color: "#8d9ab3", callback: (v) => v + "°" }, grid: { color: "#1c263a" } } },
      plugins: { legend: { labels: { color: "#c4cde0", boxWidth: 12, filter: (i) => !i.text.startsWith("_") } },
                 tooltip: { filter: (i) => !i.dataset.label.startsWith("_") && i.raw != null } } },
  };
  if (trendChart) trendChart.destroy();
  trendChart = new Chart($("trend"), cfg);
  $("chart-hint").textContent = state.whatif ? "What-if: forecast from your 7 values (actual IMD values hidden)"
    : "Last 30 days observed vs normal, 7-day forecast with uncertainty band, and what actually happened";
}

function renderMap() {
  if (!map) {
    // Offline base map: bundled Natural Earth outlines (India point-of-view edition), no tile server needed.
    map = L.map("map", { zoomControl: false, attributionControl: true, zoomSnap: 0.1 }).setView([22.5, 80], 4.2);
    map.attributionControl.setPrefix(false).addAttribution("Boundaries: Natural Earth (India view)");
    fetch("vendor/india-region.geojson").then((r) => r.json()).then((geo) => {
      const layer = L.geoJSON(geo, {
        interactive: false,
        style: (f) => f.properties.india
          ? { color: "#5d6b87", weight: 1.2, fillColor: "#1d2840", fillOpacity: 1 }
          : { color: "#2a344a", weight: 0.8, fillColor: "#131a28", fillOpacity: 1 },
      }).addTo(map);
      layer.bringToBack();
      const india = layer.getLayers().find((l) => l.feature.properties.india);
      if (india) map.fitBounds(india.getBounds(), { padding: [8, 8] });
    }).catch(() => {});
  }
  Object.values(markers).forEach((m) => m.remove());
  markers = {};
  state.outlook.cities.forEach((c) => {
    const selected = c.city === state.city;
    const m = L.circleMarker([c.lat, c.lon], {
      radius: selected ? 13 : 9, color: selected ? "#ffffff" : COLORS[c.highest_alert], weight: selected ? 3 : 1.5,
      fillColor: COLORS[c.highest_alert], fillOpacity: .85,
    }).addTo(map);
    m.bindTooltip(`<b>${c.city}</b><br>${c.highest_alert}<br>Peak ${c.peak.forecast_tmax.toFixed(1)} °C`, { direction: "top" });
    m.on("click", () => selectCity(c.city));
    markers[c.city] = m;
  });
}

function renderRanking() {
  $("ranking").innerHTML = state.outlook.cities.map((c) => `
    <tr data-city="${c.city}" class="${c.city === state.city ? "active" : ""}">
      <td><b>${c.city}</b>${c.coastal ? ' <span class="hint">coastal</span>' : ""}</td>
      <td>${c.today_tmax.toFixed(1)} °C</td>
      <td>${c.peak.forecast_tmax.toFixed(1)} °C</td>
      <td><div class="squares">${c.alerts.map((a, i) => `<span class="sq ${a.split(" ")[0]}" title="Day ${i + 1}: ${a}"></span>`).join("")}</div></td>
    </tr>`).join("");
  $("ranking").querySelectorAll("tr").forEach((tr) => tr.addEventListener("click", () => selectCity(tr.dataset.city)));
}

function fillWhatIf(values) {
  $("whatif").innerHTML = values.map((v, i) =>
    `<label>${i === 6 ? "Today" : `−${6 - i}d`}<input type="number" step="0.1" value="${v.toFixed(1)}"></label>`).join("");
  $("whatif-note").textContent = "Values outside −10…55 °C are rejected by the backend (HTTP 422).";
  $("whatif-note").classList.remove("mode");
}

async function renderModelInfo() {
  try {
    const m = await api("/model-info");
    const h = m.horizons;
    $("perf").innerHTML = h.map((x) => `<tr><td>Day ${x.day}</td><td>${x.test_mae.ridge_regression.toFixed(2)} °C</td>
      <td>${Math.round(x.alert_recall * 100)}%</td><td>${Math.round(x.alert_precision * 100)}%</td>
      <td>${x.alert_confidence === "validated" ? "✓ validated" : "low"}</td></tr>`).join("");
    if (maeChart) maeChart.destroy();
    maeChart = new Chart($("mae"), {
      type: "line",
      data: { labels: h.map((x) => "Day " + x.day), datasets: [
        { label: "HeatGuard ML (ridge)", data: h.map((x) => x.test_mae.ridge_regression), borderColor: "#ff6a2b", backgroundColor: "#ff6a2b", borderWidth: 3 },
        { label: "Persistence (same as today)", data: h.map((x) => x.test_mae.persistence_baseline), borderColor: "#5aa9ff", backgroundColor: "#5aa9ff", borderDash: [4, 4] },
        { label: "Climatology (normal)", data: h.map((x) => x.test_mae.climatology_baseline), borderColor: "#8d9ab3", backgroundColor: "#8d9ab3", borderDash: [2, 3] },
      ] },
      options: { responsive: true, maintainAspectRatio: false,
        scales: { x: { ticks: { color: "#8d9ab3" }, grid: { color: "#1c263a" } },
                  y: { title: { display: true, text: "Mean absolute error (°C), 2024", color: "#8d9ab3" }, ticks: { color: "#8d9ab3" }, grid: { color: "#1c263a" }, beginAtZero: true } },
        plugins: { legend: { labels: { color: "#c4cde0", boxWidth: 12 } } } },
    });
  } catch (e) { $("perf").innerHTML = `<tr><td colspan="5">${e.message}</td></tr>`; }
}

async function checkHealth() {
  try {
    const h = await api("/health");
    $("api-status").textContent = `API v${h.version} · ${h.pod}`;
    $("api-status").className = "status-pill ok";
  } catch (e) {
    $("api-status").textContent = "API unreachable";
    $("api-status").className = "status-pill down";
  }
}

function selectCity(city) { state.city = city; $("city").value = city; syncUrl(); refresh(); }
function syncUrl() { history.replaceState(null, "", `?city=${encodeURIComponent(state.city)}&date=${state.date}`); }

async function init() {
  const q = new URLSearchParams(location.search);
  state.city = q.get("city") || state.city;
  state.date = q.get("date") || state.date;
  try {
    const cities = await api("/cities");
    $("city").innerHTML = cities.map((c) => `<option>${c.city}</option>`).join("");
  } catch (e) { showError("Cannot reach the HeatGuard API: " + e.message); }
  $("city").value = state.city;
  $("date").value = state.date;
  $("city").addEventListener("change", () => selectCity($("city").value));
  $("date").addEventListener("change", () => { state.date = $("date").value; syncUrl(); refresh(); });
  document.querySelectorAll(".presets button").forEach((b) => b.addEventListener("click", () => {
    state.city = b.dataset.city; state.date = b.dataset.date; $("city").value = state.city; $("date").value = state.date; syncUrl(); refresh();
  }));
  $("whatif-run").addEventListener("click", runWhatIf);
  $("whatif-reset").addEventListener("click", refresh);
  checkHealth();
  setInterval(checkHealth, 10000);
  renderModelInfo();
  await refresh();
}

init();
