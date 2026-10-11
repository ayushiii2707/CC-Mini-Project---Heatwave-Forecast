// HeatGuard dashboard. Talks to the backend only through the /api/ reverse proxy (nginx).
const API = "/api";
const COLORS = { Normal: "#3d7a68", Heatwave: "#e0952f", "Severe heatwave": "#c23b22" };
const INK = "#1c1814", MUTED = "#857b6b", RULE = "#e3dacb", EMBER = "#c23b22";
const $ = (id) => document.getElementById(id);
const state = { city: "Delhi", date: "2024-05-27", observed: null, forecast: null, outlook: null, whatif: false };
let trendChart, maeChart, map, markers = {};

Chart.defaults.font.family = '"Plex Sans", -apple-system, sans-serif';
Chart.defaults.color = MUTED;

const fmtDay = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-IN", { weekday: "long" });
const fmtDow = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-IN", { weekday: "short" });
const fmtDate = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short" });
const fmtLong = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" });
const lvl = (level) => level.split(" ")[0];
const sign = (v) => (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(1);

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
    $("whatif-note").textContent = "What-if mode: the forecast uses your values, so actual IMD values are hidden.";
    $("whatif-note").classList.add("mode");
    $("banner").scrollIntoView({ behavior: "smooth" });
  } catch (e) { showError("The backend rejected these values. " + e.message); }
}

// ---------- rendering ----------
function render() {
  renderBanner(); renderKpis(); renderDays(); renderTrend(); renderMap(); renderRanking();
  $("served-by").textContent = `Forecast served by ${state.forecast.pod} in ${state.forecast.inference_ms} ms`;
}

function renderBanner() {
  const f = state.forecast, level = f.highest_alert;
  $("banner").className = "bulletin level-" + lvl(level).toLowerCase();
  $("banner-kicker").textContent = `7-day heat bulletin · ${state.city} · issued ${fmtLong(state.date)}${state.whatif ? " · what-if values" : ""}`;
  const first = f.first_alert_day ? f.days[f.first_alert_day - 1] : null;
  $("banner-title").innerHTML = level === "Normal" ? "No heatwave expected this week"
    : `${level} from <em>${fmtDay(first.date)} ${fmtDate(first.date)}</em>`;
  $("banner-text").textContent = f.advisory;
  $("banner-badge").textContent = level;
  $("banner-badge").className = "stamp big " + lvl(level);
  const v = f.highest_validated_alert;
  $("banner-meta").innerHTML = `Peak <span class="num">${f.peak.forecast_tmax.toFixed(1)} °C</span> on ${fmtDate(f.peak.date)}<br>`
    + (v === level ? "Within the validated range (days 1–4)" : `Days 1–4: ${v} · days 5–7 low-confidence`);
}

function renderKpis() {
  const f = state.forecast, o = state.observed;
  const today = o.history[o.history.length - 1];
  $("k-today").textContent = state.whatif ? "what-if" : `${today.tmax.toFixed(1)}°`;
  $("k-today-sub").textContent = state.whatif ? "using your values" : `IMD observed, ${fmtDate(state.date)}`;
  $("k-peak").textContent = `${f.peak.forecast_tmax.toFixed(1)}°`;
  $("k-peak-sub").textContent = `${fmtDow(f.peak.date)} ${fmtDate(f.peak.date)}`;
  $("k-normal").textContent = `${today.normal.toFixed(1)}°`;
  $("k-normal-sub").textContent = state.whatif ? "climatological normal" : `today is ${sign(today.tmax - today.normal)} °C vs normal`;
  const alertDays = f.days.filter((d) => d.alert !== "Normal");
  $("k-alerts").textContent = `${alertDays.length}/7`;
  $("k-alerts-sub").textContent = `${alertDays.filter((d) => d.alert_confidence === "validated").length} in the validated range`;
}

function renderDays() {
  const actual = state.whatif ? [] : state.observed.actual_next_7;
  $("days").innerHTML = state.forecast.days.map((d, i) => {
    const a = actual[i] && actual[i].tmax;
    const ok = a != null && Math.abs(a - d.forecast_tmax) <= d.typical_error_c * 1.5;
    const actualRow = a == null ? "" : `<div><dt>IMD actual</dt><dd class="${ok ? "hit" : "miss"}" title="${ok ? "Green: actual within 1.5× the typical error of the forecast" : "Red: actual differs from the forecast by more than 1.5× its typical error"}">${a.toFixed(1)}°</dd></div>`;
    return `<article class="day ${lvl(d.alert)} ${d.alert_confidence === "low" ? "low" : ""}" style="animation-delay:${i * 70}ms"
        title="IMD rule applied to ${d.upper_forecast_tmax.toFixed(1)} °C (forecast + ${d.alert_margin_c} °C margin): ${d.rule}">
      <div class="dname">${fmtDow(d.date)}</div><div class="ddate">${fmtDate(d.date)} · day ${d.day}</div>
      <div class="temp">${d.forecast_tmax.toFixed(1)}<sup>°C</sup></div><div class="err">± ${d.typical_error_c.toFixed(1)} typical error</div>
      <span class="stamp ${lvl(d.alert)}">${d.alert}</span>
      <dl>
        <div><dt>Normal</dt><dd>${d.normal_tmax.toFixed(1)}°</dd></div>
        <div><dt>Alert basis</dt><dd>${d.upper_forecast_tmax.toFixed(1)}°</dd></div>
        <div><dt>Departure</dt><dd>${sign(d.departure_from_normal)}°</dd></div>
        ${actualRow}
      </dl>
      <div class="conf ${d.alert_confidence}">${d.alert_confidence === "validated" ? "Validated" : "Low confidence"}</div>
    </article>`;
  }).join("");
}

function renderTrend() {
  const o = state.observed, f = state.forecast;
  const hist = state.whatif ? o.history.slice(0, -7) : o.history;
  const labels = [...hist.map((h) => h.date), ...f.days.map((d) => d.date)];
  const nH = hist.length, pad = (arr, before) => [...Array(before).fill(null), ...arr];
  const forecastLine = [...Array(nH - 1).fill(null), state.whatif ? null : hist[nH - 1].tmax, ...f.days.map((d) => d.forecast_tmax)];
  const datasets = [
    { label: "Observed (IMD)", data: [...hist.map((h) => h.tmax), ...Array(7).fill(null)], borderColor: INK, backgroundColor: INK, pointRadius: 0, borderWidth: 2, tension: .3 },
    { label: "Normal", data: [...hist.map((h) => h.normal), ...f.days.map((d) => d.normal_tmax)], borderColor: MUTED, borderDash: [5, 4], pointRadius: 0, borderWidth: 1.5 },
    { label: "Forecast", data: forecastLine, borderColor: EMBER, backgroundColor: EMBER, borderWidth: 2.5, pointRadius: 3, tension: .3 },
    { label: "Uncertainty", data: pad(f.days.map((d) => d.forecast_tmax + d.typical_error_c), nH), borderColor: "transparent", backgroundColor: "rgba(194,59,34,.13)", pointRadius: 0, fill: "+1" },
    { label: "_low", data: pad(f.days.map((d) => d.forecast_tmax - d.typical_error_c), nH), borderColor: "transparent", pointRadius: 0, fill: false },
    { label: "40 °C plains threshold", data: labels.map(() => 40), borderColor: "rgba(194,59,34,.45)", borderDash: [2, 4], pointRadius: 0, borderWidth: 1 },
  ];
  if (!state.whatif) {
    datasets.push({ label: "What actually happened", data: pad(o.actual_next_7.map((a) => a.tmax), nH), borderColor: COLORS.Normal,
      backgroundColor: COLORS.Normal, showLine: false, pointRadius: 5, pointStyle: "rectRot" });
  }
  if (trendChart) trendChart.destroy();
  trendChart = new Chart($("trend"), {
    type: "line", data: { labels: labels.map(fmtDate), datasets },
    options: { responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false }, animation: { duration: 700 },
      scales: { x: { ticks: { maxTicksLimit: 12 }, grid: { color: RULE } },
                y: { ticks: { callback: (v) => v + "°" }, grid: { color: RULE } } },
      plugins: { legend: { labels: { color: INK, boxWidth: 12, filter: (i) => !i.text.startsWith("_") } },
                 tooltip: { backgroundColor: INK, filter: (i) => !i.dataset.label.startsWith("_") && i.raw != null } } },
  });
  $("chart-hint").textContent = state.whatif ? "What-if: forecast from your 7 values (actual IMD values hidden)"
    : "Last 30 days against the normal, the forecast with its uncertainty band, and what actually happened";
}

function renderMap() {
  if (!map) {
    // Offline base map: bundled Natural Earth outlines (India point-of-view edition), no tile server needed.
    map = L.map("map", { zoomControl: false, scrollWheelZoom: false, attributionControl: true, zoomSnap: 0.1 }).setView([22.5, 80], 4.2);
    map.attributionControl.setPrefix(false).addAttribution("Boundaries: Natural Earth (India view)");
    fetch("vendor/india-region.geojson").then((r) => r.json()).then((geo) => {
      const layer = L.geoJSON(geo, {
        interactive: false,
        style: (f) => f.properties.india ? { color: "#8d826f", weight: 1, fillColor: "#e9e1d2", fillOpacity: 1 }
                                         : { color: "#d6cbb7", weight: .7, fillColor: "#f3eee4", fillOpacity: 1 },
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
      radius: selected ? 12 : 8, color: selected ? INK : "#fbf8f1", weight: selected ? 3 : 1.5,
      fillColor: COLORS[c.highest_alert], fillOpacity: 1,
    }).addTo(map);
    m.bindTooltip(`<b>${c.city}</b> · ${c.highest_alert} · peak ${c.peak.forecast_tmax.toFixed(1)} °C`, { direction: "top" });
    m.on("click", () => selectCity(c.city));
    markers[c.city] = m;
  });
}

function renderRanking() {
  $("ranking").innerHTML = state.outlook.cities.map((c) => `
    <tr data-city="${c.city}" class="${c.city === state.city ? "active" : ""}">
      <td><span class="city">${c.city}</span>${c.coastal ? '<span class="coastal">coastal</span>' : ""}</td>
      <td class="num">${c.today_tmax.toFixed(1)}°</td>
      <td class="num">${c.peak.forecast_tmax.toFixed(1)}°</td>
      <td><div class="squares">${c.alerts.map((a, i) => `<span class="sq ${lvl(a)}" title="Day ${i + 1}: ${a}"></span>`).join("")}</div></td>
    </tr>`).join("");
  $("ranking").querySelectorAll("tr").forEach((tr) => tr.addEventListener("click", () => selectCity(tr.dataset.city)));
}

function fillWhatIf(values) {
  $("whatif").innerHTML = values.map((v, i) =>
    `<label>${i === 6 ? "today" : `−${6 - i}d`}<input type="number" step="0.1" value="${v.toFixed(1)}"></label>`).join("");
  $("whatif-note").textContent = "Values outside −10…55 °C are rejected by the backend (HTTP 422).";
  $("whatif-note").classList.remove("mode");
}

async function renderModelInfo() {
  try {
    const h = (await api("/model-info")).horizons;
    $("perf").innerHTML = h.map((x) => `<tr><td>Day ${x.day}</td><td class="num">${x.test_mae.ridge_regression.toFixed(2)} °C</td>
      <td class="num">${Math.round(x.alert_recall * 100)}%</td><td class="num">${Math.round(x.alert_precision * 100)}%</td>
      <td>${x.alert_confidence === "validated" ? "Validated" : "Low"}</td></tr>`).join("");
    if (maeChart) maeChart.destroy();
    maeChart = new Chart($("mae"), {
      type: "bar",
      data: { labels: h.map((x) => "Day " + x.day), datasets: [
        { type: "bar", label: "HeatGuard (ridge)", data: h.map((x) => x.test_mae.ridge_regression), backgroundColor: h.map((x) => x.alert_confidence === "low" ? "#8d826f" : INK), barPercentage: .6 },
        { type: "line", label: "Same as today", data: h.map((x) => x.test_mae.persistence_baseline), borderColor: EMBER, backgroundColor: EMBER, borderDash: [4, 3], pointRadius: 3 },
        { type: "line", label: "Usual for the date", data: h.map((x) => x.test_mae.climatology_baseline), borderColor: "#3b6b8f", backgroundColor: "#3b6b8f", borderDash: [2, 3], pointRadius: 0 },
      ] },
      options: { responsive: true, maintainAspectRatio: false,
        scales: { x: { grid: { display: false } }, y: { title: { display: true, text: "Mean absolute error (°C), 2024" }, grid: { color: RULE }, beginAtZero: true } },
        plugins: { legend: { labels: { color: INK, boxWidth: 12 } }, tooltip: { backgroundColor: INK } } },
    });
  } catch (e) { $("perf").innerHTML = `<tr><td colspan="5">${e.message}</td></tr>`; }
}

async function checkHealth() {
  try {
    const h = await api("/health");
    $("api-status").textContent = `API ${h.version} · ${h.pod}`;
    $("api-status").className = "api-status num ok";
  } catch (e) {
    $("api-status").textContent = "API unreachable";
    $("api-status").className = "api-status num down";
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
