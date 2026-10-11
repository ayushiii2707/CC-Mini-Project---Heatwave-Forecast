// HeatGuard landing page. All figures come from the backend API (/api/...), i.e. real IMD data and model metrics.
const API = "/api";
const FEATURED_DATE = "2024-05-27";
const PIN = { Normal: "#6aa592", Heatwave: "#e0952f", "Severe heatwave": "#e0533a" };
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const $ = (id) => document.getElementById(id);
const fmtLong = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" });
const fmtShort = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short" });
const stampClass = (level) => level.split(" ")[0];

async function api(path) {
  const r = await fetch(API + path);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

// ---------- heat stripes: Delhi, every day of 2024 ----------
const STOPS = [[15, [46, 93, 134]], [22, [143, 179, 201]], [30, [241, 227, 196]], [38, [240, 165, 63]], [43, [212, 84, 43]], [47, [122, 20, 20]]];
function heatColor(t) {
  if (t <= STOPS[0][0]) return `rgb(${STOPS[0][1]})`;
  for (let i = 1; i < STOPS.length; i++) {
    const [t1, c1] = STOPS[i], [t0, c0] = STOPS[i - 1];
    if (t <= t1) {
      const f = (t - t0) / (t1 - t0);
      return `rgb(${c0.map((v, k) => Math.round(v + (c1[k] - v) * f)).join(",")})`;
    }
  }
  return `rgb(${STOPS[STOPS.length - 1][1]})`;
}

async function loadYear(city) {
  // /observed returns up to 90 days of history; five windows cover 1 Jan - 31 Dec 2024.
  const ends = [["2024-03-30", 90], ["2024-06-28", 90], ["2024-09-26", 90], ["2024-12-25", 90], ["2024-12-31", 7]];
  const parts = await Promise.all(ends.map(([d, n]) => api(`/observed?city=${city}&date=${d}&days=${n}`)));
  const byDate = new Map();
  parts.forEach((p) => p.history.forEach((h) => { if (h.tmax != null) byDate.set(h.date, h.tmax); }));
  return [...byDate.entries()].filter(([d]) => d.startsWith("2024")).sort((a, b) => a[0].localeCompare(b[0]));
}

function drawStripes(days) {
  const canvas = $("stripes");
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  canvas.width = w * dpr; canvas.height = h * dpr;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  const sw = w / days.length;
  const start = performance.now(), dur = reduceMotion ? 0 : 2200;
  function frame(now) {
    const p = dur ? Math.min(1, (now - start) / dur) : 1;
    const ease = 1 - Math.pow(1 - p, 3);
    const n = Math.floor(days.length * ease);
    ctx.clearRect(0, 0, w, h);
    for (let i = 0; i < n; i++) {
      ctx.fillStyle = heatColor(days[i][1]);
      ctx.fillRect(i * sw, 0, Math.ceil(sw) + 0.5, h);
    }
    if (p < 1) {
      ctx.fillStyle = "#1c1814";
      ctx.fillRect(n * sw, 0, 2, h); // drawing cursor
      requestAnimationFrame(frame);
    }
  }
  requestAnimationFrame(frame);

  const tip = $("stripe-tip");
  canvas.onmousemove = (e) => {
    const r = canvas.getBoundingClientRect();
    const i = Math.min(days.length - 1, Math.max(0, Math.floor((e.clientX - r.left) / sw)));
    tip.hidden = false;
    tip.style.left = `${e.clientX - r.left}px`;
    tip.textContent = `${fmtShort(days[i][0])} · ${days[i][1].toFixed(1)} °C`;
  };
  canvas.onmouseleave = () => { tip.hidden = true; };
  const hottest = days.reduce((a, b) => (b[1] > a[1] ? b : a));
  $("stripes-note").textContent = `Hottest day: ${fmtShort(hottest[0])}, ${hottest[1].toFixed(1)} °C.`;
}

// ---------- count-up stats ----------
function countUp(el) {
  const target = parseFloat(el.dataset.count), dec = parseInt(el.dataset.dec || "0", 10), suffix = el.dataset.suffix || "";
  const fmt = (v) => (dec ? v.toFixed(dec) : Math.round(v).toLocaleString("en-IN")) + suffix;
  if (reduceMotion) { el.textContent = fmt(target); return; }
  const start = performance.now(), dur = 1400;
  (function step(now) {
    const p = Math.min(1, (now - start) / dur);
    el.textContent = fmt(target * (1 - Math.pow(1 - p, 3)));
    if (p < 1) requestAnimationFrame(step);
  })(start);
}

// ---------- hero card + outlook ----------
function renderHero(outlook, health) {
  const top = outlook.cities[0];
  const f = top.forecast_tmax;
  $("hc-date").textContent = fmtLong(outlook.date);
  $("hc-city").textContent = top.city;
  $("hc-temp").textContent = top.peak.forecast_tmax.toFixed(1);
  $("hc-stamp").textContent = top.highest_alert;
  $("hc-stamp").className = "stamp " + stampClass(top.highest_alert);
  const lo = Math.min(...f) - 2, hi = Math.max(...f) + 0.5;
  $("hc-bars").innerHTML = f.map((t, i) =>
    `<div style="background:${PIN[top.alerts[i]]}" data-h="${((t - lo) / (hi - lo)) * 100}"><span>${t.toFixed(1)}</span></div>`).join("");
  requestAnimationFrame(() => $("hc-bars").querySelectorAll("div").forEach((d, i) =>
    setTimeout(() => { d.style.height = d.dataset.h + "%"; }, 120 * i)));
  $("hc-pod").textContent = `served by ${health.pod}`;
}

function renderOutlook(outlook) {
  $("ol-date").textContent = fmtLong(outlook.date);
  $("ol-list").innerHTML = outlook.cities.map((c, i) => `
    <li><span class="rk">${String(i + 1).padStart(2, "0")}</span><span class="nm">${c.city}</span>
      <span class="ol-sq">${c.alerts.map((a) => `<i class="${stampClass(a)}"></i>`).join("")}</span>
      <span class="pk">${c.peak.forecast_tmax.toFixed(1)}°</span></li>`).join("");

  const map = L.map("lmap", { zoomControl: false, scrollWheelZoom: false, dragging: false, doubleClickZoom: false,
                              attributionControl: true, zoomSnap: 0.1 });
  map.attributionControl.setPrefix(false).addAttribution("Boundaries: Natural Earth (India view)");
  fetch("vendor/india-region.geojson").then((r) => r.json()).then((geo) => {
    const layer = L.geoJSON(geo, {
      interactive: false,
      style: (f) => f.properties.india ? { color: "#8d826f", weight: 1, fillColor: "#2a241d", fillOpacity: 1 }
                                       : { color: "#3a332b", weight: .6, fillColor: "#211c17", fillOpacity: 1 },
    }).addTo(map);
    const india = layer.getLayers().find((l) => l.feature.properties.india);
    map.fitBounds(india.getBounds(), { padding: [6, 6] });
  });
  outlook.cities.forEach((c) => {
    const icon = L.divIcon({ className: "", iconSize: [0, 0],
      html: `<div class="city-pin ${stampClass(c.highest_alert)}"><span class="ring"></span><span class="core"></span><span class="lbl">${c.city}</span></div>` });
    L.marker([c.lat, c.lon], { icon, keyboard: false }).addTo(map)
      .bindTooltip(`${c.city}: ${c.highest_alert}, peak ${c.peak.forecast_tmax.toFixed(1)} °C`)
      .on("click", () => { location.href = `/dashboard?city=${encodeURIComponent(c.city)}&date=${outlook.date}`; });
  });
}

// ---------- reliability bars ----------
function renderReliability(info) {
  const h = info.horizons;
  const max = Math.max(...h.map((x) => x.test_mae.persistence_baseline)) * 1.1;
  $("rel").innerHTML = h.map((x) => `
    <div class="rel-col">
      <div class="bar ${x.alert_confidence === "low" ? "low" : ""}" data-h="${(x.test_mae.ridge_regression / max) * 100}"><span class="v">${x.test_mae.ridge_regression.toFixed(2)}°</span></div>
      <span class="p" style="bottom:${(x.test_mae.persistence_baseline / max) * 100}%" title="Persistence ${x.test_mae.persistence_baseline} °C"></span>
      <span class="d">Day ${x.day}</span>
    </div>`).join("");
  const day1 = h[0];
  $("stat-mae").dataset.count = day1.test_mae.ridge_regression;
  $("stat-recall").dataset.count = Math.round(day1.alert_recall * 100);
}

// ---------- scroll reveal ----------
function observe() {
  const io = new IntersectionObserver((entries) => entries.forEach((e) => {
    if (!e.isIntersecting) return;
    const el = e.target;
    el.classList.add("in");
    if (el.dataset.count !== undefined) countUp(el);
    if (el.id === "rel") el.querySelectorAll(".bar").forEach((b, i) => setTimeout(() => { b.style.height = b.dataset.h + "%"; }, 90 * i));
    if (el.id === "ol-list") el.querySelectorAll("li").forEach((li, i) => setTimeout(() => li.classList.add("in"), 70 * i));
    io.unobserve(el);
  }), { threshold: 0.2 });
  document.querySelectorAll(".reveal, [data-count], #rel, #ol-list").forEach((el) => io.observe(el));
}

async function init() {
  try {
    const [health, outlook, info] = await Promise.all([api("/health"), api(`/outlook?date=${FEATURED_DATE}`), api("/model-info")]);
    renderHero(outlook, health);
    renderOutlook(outlook);
    renderReliability(info);
  } catch (e) {
    $("hc-pod").textContent = "API unreachable: " + e.message;
  }
  observe();
  try { drawStripes(await loadYear("Delhi")); } catch (e) { $("stripes-note").textContent = "Could not load IMD data: " + e.message; }
}

init();
