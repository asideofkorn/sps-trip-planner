/* Sierra Peaks Trip Planner — interactive Leaflet front-end.
 *
 * Reads parameters from the sidebar controls, calls /api/plan, and draws the
 * resulting trips (routes + peaks) and trailheads on a topo map. Peaks and
 * trailheads expose elevation, coordinates, and an on-demand NWS forecast.
 */

const PALETTE = [
  "#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#1ab0c4",
  "#f032e6", "#86b300", "#d4a017", "#008080", "#9a6324", "#aa0000",
  "#808000", "#3b3bcf", "#b06be6", "#2fae72", "#e07b39", "#787878",
];
const tripColor = (id) => PALETTE[id % PALETTE.length];

let map;
let routeLayer, peakLayer, thLayer;
let lastPlan = null;
let activeTrip = null;

function initMap() {
  map = L.map("map", { zoomControl: true }).setView([37.4, -118.7], 8);

  const topo = L.tileLayer(
    "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
    {
      maxZoom: 17,
      attribution:
        'Map data: &copy; OpenStreetMap contributors, SRTM | ' +
        'Style: &copy; <a href="https://opentopomap.org">OpenTopoMap</a> (CC-BY-SA)',
    }
  ).addTo(map);

  const osm = L.tileLayer(
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    { maxZoom: 19, attribution: "&copy; OpenStreetMap contributors" }
  );

  const sat = L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    { maxZoom: 18, attribution: "Tiles &copy; Esri" }
  );

  L.control.layers(
    {
      "OpenTopoMap (trails + contours)": topo,
      "OpenStreetMap": osm,
      "Esri World Imagery (satellite)": sat,
    },
    {},
    { collapsed: true }
  ).addTo(map);

  routeLayer = L.layerGroup().addTo(map);
  peakLayer = L.layerGroup().addTo(map);
  thLayer = L.layerGroup();
}

/* ---- forecast popup helper ---------------------------------------------- */
async function loadWeather(lat, lon, container) {
  container.innerHTML = "Loading forecast…";
  try {
    const r = await fetch(`/api/weather?lat=${lat}&lon=${lon}`);
    const data = await r.json();
    if (!r.ok || data.error) {
      container.innerHTML =
        `<i>Forecast unavailable${data.detail ? " (offline?)" : ""}.</i>`;
      return;
    }
    container.innerHTML = data.periods
      .slice(0, 4)
      .map(
        (p) =>
          `<div class="period"><span class="pname">${p.name}:</span> ` +
          `${p.temperature}&deg;${p.temperatureUnit}, ${p.shortForecast}` +
          `${p.windSpeed ? " &middot; wind " + p.windSpeed : ""}</div>`
      )
      .join("");
  } catch (e) {
    container.innerHTML = "<i>Forecast unavailable.</i>";
  }
}

function bindWeatherButtons(popupNode) {
  popupNode.querySelectorAll(".wx-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const out = btn.nextElementSibling;
      loadWeather(btn.dataset.lat, btn.dataset.lon, out);
    });
  });
}

function peakPopupHTML(p, tripId) {
  const rows = [
    `<b>${p.name}</b>`,
    `Trip #${tripId + 1}`,
    `${Math.round(p.elevation_ft).toLocaleString()} ft`,
  ];
  if (p.class) rows.push(`Class ${p.class}`);
  if (p.emblem) rows.push("⭐ Emblem peak");
  if (p.nearest_trailhead) rows.push(`Nearest TH: ${p.nearest_trailhead}`);
  rows.push(
    `<span class="coords">${p.latitude.toFixed(5)}, ${p.longitude.toFixed(5)}</span>`
  );
  rows.push(
    `<button class="wx-btn" data-lat="${p.latitude}" data-lon="${p.longitude}">` +
      `Weather forecast</button><div class="wx-out"></div>`
  );
  return `<div class="peak-popup">${rows.join("<br>")}</div>`;
}

function thPopupHTML(t) {
  const rows = [
    `<b>${t.name}</b>`,
    `Trailhead (${t.side} side)`,
    `${Math.round(t.elevation_ft).toLocaleString()} ft`,
  ];
  if (t.notes) rows.push(`<i>${t.notes}</i>`);
  rows.push(
    `<span class="coords">${t.latitude.toFixed(5)}, ${t.longitude.toFixed(5)}</span>`
  );
  rows.push(
    `<button class="wx-btn" data-lat="${t.latitude}" data-lon="${t.longitude}">` +
      `Weather forecast</button><div class="wx-out"></div>`
  );
  return `<div class="peak-popup">${rows.join("<br>")}</div>`;
}

/* ---- drawing ------------------------------------------------------------ */
function drawPlan(plan) {
  routeLayer.clearLayers();
  peakLayer.clearLayers();
  lastPlan = plan;

  const allPts = [];

  plan.clusters.forEach((c) => {
    const color = tripColor(c.cluster_id);
    const pts = c.peaks_ordered.map((p) => [p.latitude, p.longitude]);
    allPts.push(...pts);

    if (pts.length > 1) {
      L.polyline(pts, {
        color,
        weight: 3,
        opacity: 0.85,
      })
        .bindTooltip(
          `Trip #${c.cluster_id + 1}: ${c.num_peaks} peaks, ` +
            `${c.estimated_days}d, ${c.total_distance_mi.toFixed(0)} mi`
        )
        .addTo(routeLayer);
    }

    c.peaks_ordered.forEach((p) => {
      const marker = L.circleMarker([p.latitude, p.longitude], {
        radius: 5,
        color: "#1a1a1a",
        weight: 1,
        fillColor: color,
        fillOpacity: 0.9,
      })
        .bindTooltip(p.name)
        .addTo(peakLayer);
      marker.bindPopup(peakPopupHTML(p, c.cluster_id));
      marker.on("popupopen", (e) => bindWeatherButtons(e.popup.getElement()));
    });
  });

  if (allPts.length) {
    map.fitBounds(L.latLngBounds(allPts).pad(0.08));
  }

  renderSummary(plan);
  renderTripList(plan);
}

function renderSummary(plan) {
  const s = plan.summary;
  document.getElementById("summary").innerHTML = `
    <div class="stat"><span>Trips</span><b>${s.num_clusters}</b></div>
    <div class="stat"><span>Peaks covered</span><b>${s.total_peaks}</b></div>
    <div class="stat"><span>Total trip-days</span><b>${s.total_estimated_days}</b></div>
    <div class="stat"><span>Total distance</span><b>${s.total_distance_mi.toLocaleString()} mi</b></div>
    <div class="stat"><span>Total gain</span><b>${Math.round(s.total_elevation_gain_ft).toLocaleString()} ft</b></div>`;
}

function renderTripList(plan) {
  const el = document.getElementById("triplist");
  el.innerHTML = "<h2>Trips (best first)</h2>";
  plan.clusters.forEach((c) => {
    const row = document.createElement("div");
    row.className = "trip";
    row.innerHTML = `
      <span class="swatch" style="background:${tripColor(c.cluster_id)}"></span>
      <span>#${c.cluster_id + 1} &middot; ${c.num_peaks} pk
        <span class="meta">${c.estimated_days}d &middot;
        ${c.total_distance_mi.toFixed(0)} mi</span></span>`;
    row.addEventListener("click", () => selectTrip(c, row));
    el.appendChild(row);
  });
}

function selectTrip(cluster, rowEl) {
  document
    .querySelectorAll(".triplist .trip")
    .forEach((r) => r.classList.remove("active"));
  if (rowEl) rowEl.classList.add("active");
  activeTrip = cluster;

  const pts = cluster.peaks_ordered.map((p) => [p.latitude, p.longitude]);
  if (pts.length) map.fitBounds(L.latLngBounds(pts).pad(0.25));
  drawProfile(cluster);
}

/* ---- elevation profile -------------------------------------------------- */
function drawProfile(cluster) {
  const panel = document.getElementById("profile-panel");
  const canvas = document.getElementById("profile-canvas");
  panel.classList.remove("hidden");
  document.getElementById("profile-title").textContent =
    `Trip #${cluster.cluster_id + 1} — elevation along route`;

  const peaks = cluster.peaks_ordered;
  const ctx = canvas.getContext("2d");
  const W = canvas.width, H = canvas.height;
  ctx.clearRect(0, 0, W, H);

  if (peaks.length < 2) {
    ctx.fillStyle = "#9aa6c0";
    ctx.font = "13px sans-serif";
    ctx.fillText("Single-peak trip — no route profile.", 12, H / 2);
    return;
  }

  // Cumulative great-circle distance (mi) along the ordered route.
  const dist = [0];
  for (let i = 1; i < peaks.length; i++) {
    dist.push(dist[i - 1] + haversineMi(peaks[i - 1], peaks[i]));
  }
  const elevs = peaks.map((p) => p.elevation_ft);
  const maxD = dist[dist.length - 1] || 1;
  const minE = Math.min(...elevs), maxE = Math.max(...elevs);
  const padL = 46, padR = 10, padT = 12, padB = 24;
  const x = (d) => padL + (d / maxD) * (W - padL - padR);
  const y = (e) =>
    padT + (1 - (e - minE) / Math.max(1, maxE - minE)) * (H - padT - padB);

  // axes
  ctx.strokeStyle = "#566";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(padL, padT); ctx.lineTo(padL, H - padB); ctx.lineTo(W - padR, H - padB);
  ctx.stroke();
  ctx.fillStyle = "#9aa6c0";
  ctx.font = "10px sans-serif";
  ctx.fillText(`${Math.round(maxE).toLocaleString()} ft`, 2, y(maxE) + 4);
  ctx.fillText(`${Math.round(minE).toLocaleString()} ft`, 2, y(minE) + 4);
  ctx.fillText(`${maxD.toFixed(1)} mi`, W - padR - 34, H - 6);

  // line + points
  ctx.strokeStyle = tripColor(cluster.cluster_id);
  ctx.lineWidth = 2;
  ctx.beginPath();
  peaks.forEach((p, i) => {
    const px = x(dist[i]), py = y(elevs[i]);
    if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
  });
  ctx.stroke();
  ctx.fillStyle = tripColor(cluster.cluster_id);
  peaks.forEach((p, i) => {
    ctx.beginPath();
    ctx.arc(x(dist[i]), y(elevs[i]), 3, 0, Math.PI * 2);
    ctx.fill();
  });
}

function haversineMi(a, b) {
  const R = 3958.8;
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(b.latitude - a.latitude);
  const dLon = toRad(b.longitude - a.longitude);
  const s =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(a.latitude)) * Math.cos(toRad(b.latitude)) *
      Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(s), Math.sqrt(1 - s));
}

/* ---- trailheads --------------------------------------------------------- */
function drawTrailheads(trailheads) {
  thLayer.clearLayers();
  trailheads.forEach((t) => {
    const marker = L.circleMarker([t.latitude, t.longitude], {
      radius: 5,
      color: "#000",
      weight: 1,
      fillColor: "#ffd24d",
      fillOpacity: 1,
    })
      .bindTooltip(`${t.name} (${t.side})`)
      .addTo(thLayer);
    marker.bindPopup(thPopupHTML(t));
    marker.on("popupopen", (e) => bindWeatherButtons(e.popup.getElement()));
  });
}

/* ---- params + wiring ---------------------------------------------------- */
function currentParams() {
  const p = new URLSearchParams();
  p.set("max_days", document.getElementById("maxDays").value);
  p.set("miles_per_day", document.getElementById("mpd").value);
  p.set("eps_mi", document.getElementById("eps").value);
  p.set("include_approach", document.getElementById("approach").checked);
  p.set("use_passes", document.getElementById("passes").checked);
  p.set("by_trailhead", document.getElementById("byTrailhead").checked);
  return p;
}

async function replan() {
  document.getElementById("summary").innerHTML =
    '<div class="spinner">Planning…</div>';
  const r = await fetch("/api/plan?" + currentParams().toString());
  const plan = await r.json();
  drawPlan(plan);
}

function wireControls() {
  const link = (id, valId, suffix = "") => {
    const input = document.getElementById(id);
    const out = document.getElementById(valId);
    input.addEventListener("input", () => {
      out.textContent = input.value + suffix;
    });
    input.addEventListener("change", replan);
  };
  link("maxDays", "maxDaysVal");
  link("mpd", "mpdVal");
  link("eps", "epsVal");

  ["approach", "passes", "byTrailhead"].forEach((id) =>
    document.getElementById(id).addEventListener("change", replan)
  );
  document.getElementById("replan").addEventListener("click", replan);

  document.getElementById("layerTh").addEventListener("change", (e) => {
    if (e.target.checked) thLayer.addTo(map);
    else thLayer.remove();
  });

  document.getElementById("profile-close").addEventListener("click", () => {
    document.getElementById("profile-panel").classList.add("hidden");
  });
}

async function boot() {
  initMap();
  wireControls();
  try {
    const meta = await (await fetch("/api/meta")).json();
    if (meta.trailheads) drawTrailheads(meta.trailheads);
  } catch (e) {
    /* trailheads optional */
  }
  await replan();
}

boot();
