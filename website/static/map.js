// Map views: the results map, the satellite map in the property drawer, and the
// lot drawing (an SVG of the parcel outline with edge dimensions).
const CATEGORY_COLORS = {
  Residential: "#3b82f6", Commercial: "#f59e0b", Industrial: "#8b5cf6", Agricultural: "#16a34a",
  Institutional: "#db2777", Government: "#475569", Miscellaneous: "#9ca3af",
};
const COUNTY_BOUNDS = [[27.15, -80.68], [27.56, -80.17]];
const SHAPES_MIN_ZOOM = 16;  // below this the results map draws dots instead of outlines

function baseLayers() {
  return {
    Satellite: L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
      maxZoom: 20, maxNativeZoom: 19,
      attribution: "Imagery © Esri, Maxar, Earthstar Geographics",
    }),
    Streets: L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 20, maxNativeZoom: 19,
      attribution: "© OpenStreetMap contributors",
    }),
  };
}

// GeoJSON-style rings ([lon, lat]) -> Leaflet latlngs ([lat, lon]).
const toLatLngs = (rings) => rings.map((r) => r.map(([lon, lat]) => [lat, lon]));

// ---------------------------------------------------------------- results map
const ResultsMap = {
  map: null, layer: null, nearCircle: null, params: null, onSelect: null, pending: null,

  init(el, onSelect) {
    this.onSelect = onSelect;
    const layers = baseLayers();
    this.map = L.map(el, { preferCanvas: true, layers: [layers.Streets] }).fitBounds(COUNTY_BOUNDS);
    L.control.layers(layers, null, { position: "topright" }).addTo(this.map);
    this.layer = L.layerGroup().addTo(this.map);
    this.map.on("moveend", () => this.refresh());
    document.getElementById("map-legend").innerHTML = Object.entries(CATEGORY_COLORS)
      .map(([k, c]) => `<span><i style="background:${c}"></i>${k}</span>`).join("");
  },

  show(params, near) {
    this.params = params;
    this.map.invalidateSize();
    if (this.nearCircle) { this.nearCircle.remove(); this.nearCircle = null; }
    if (near) {
      this.nearCircle = L.circle([near.lat, near.lon], {
        radius: near.radius * 1609.34, color: "#0b6e69", weight: 2, fill: false, dashArray: "6 6",
      }).addTo(this.map);
      this.map.fitBounds(this.nearCircle.getBounds());  // triggers refresh via moveend
    }
    this.refresh();
  },

  async refresh() {
    if (!this.params || !this.map._container.offsetParent) return;  // hidden
    const b = this.map.getBounds();
    const zoom = this.map.getZoom();
    const p = new URLSearchParams(this.params);
    p.set("bbox", [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].map((v) => v.toFixed(6)).join(","));
    if (zoom >= SHAPES_MIN_ZOOM) p.set("shapes", "1");
    this.pending?.abort();
    this.pending = new AbortController();
    const status = document.getElementById("map-status");
    status.textContent = "Loading…";
    let data;
    try {
      data = await (await fetch("/api/map?" + p, { signal: this.pending.signal })).json();
    } catch (e) {
      if (e.name !== "AbortError") status.textContent = "Could not load map data";
      return;
    }
    this.layer.clearLayers();
    if (data.truncated) {
      status.textContent = `${data.total.toLocaleString()} properties in view. Zoom in or add filters to see them.`;
      return;
    }
    status.textContent = data.total ? `${data.total.toLocaleString()} properties in view` : "No matching properties in view";
    for (const f of data.features) {
      const color = CATEGORY_COLORS[f.category] || "#999";
      const shape = f.rings
        ? L.polygon(toLatLngs(f.rings), { color, weight: 1.5, fillOpacity: 0.25 })
        : L.circleMarker([f.lat, f.lon], { radius: 4, color, weight: 1, fillOpacity: 0.8 });
      shape.bindTooltip(`${f.address || "(no address)"}${f.est_tax != null ? ` · est. tax $${Math.round(f.est_tax).toLocaleString()}` : ""}`);
      shape.on("click", () => this.onSelect(f.property_id));
      shape.addTo(this.layer);
    }
  },
};

// ---------------------------------------------------------- drawer parcel map
let parcelMapInstance = null;

async function showParcelMap(el, d, onSelect) {
  if (parcelMapInstance) { parcelMapInstance.remove(); parcelMapInstance = null; }
  if (!d.geometry) return;
  const layers = baseLayers();
  const map = L.map(el, { layers: [layers.Satellite], zoomControl: true, attributionControl: true });
  parcelMapInstance = map;
  L.control.layers(layers, null, { position: "topright" }).addTo(map);
  const outline = L.polygon(toLatLngs(d.geometry.rings), {
    color: "#facc15", weight: 3, fillOpacity: 0.12,
  }).addTo(map);
  map.fitBounds(outline.getBounds(), { padding: [30, 30], maxZoom: 19 });

  // Neighbouring parcel lines for context.
  const b = outline.getBounds().pad(1.5);
  try {
    const res = await fetch(`/api/map?shapes=1&bbox=${[b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].join(",")}`);
    const data = await res.json();
    if (parcelMapInstance !== map) return;  // drawer moved on
    for (const f of data.features) {
      if (f.property_id === d.property_id || !f.rings) continue;
      L.polygon(toLatLngs(f.rings), { color: "#ffffff", weight: 1, opacity: 0.7, fillOpacity: 0 })
        .bindTooltip(f.address || "(no address)")
        .on("click", () => onSelect(f.property_id))
        .addTo(map);
    }
    outline.bringToFront();
  } catch { /* context lines are optional */ }
}

// --------------------------------------------------------------- lot drawing
const FEET_PER_DEG_LAT = 364320;  // 69.0 miles

function ringArea(pts) {
  let a = 0;
  for (let i = 0; i < pts.length; i++) {
    const [x0, y0] = pts[i], [x1, y1] = pts[(i + 1) % pts.length];
    a += x0 * y1 - x1 * y0;
  }
  return a / 2;
}

// Build an SVG plan of the parcel: outline, edge lengths in feet, north arrow, scale bar.
function platSvg(d) {
  if (!d.geometry) return null;
  const rings = d.geometry.rings;
  const lat0 = rings[0].reduce((a, p) => a + p[1], 0) / rings[0].length;
  const lon0 = rings[0].reduce((a, p) => a + p[0], 0) / rings[0].length;
  const kx = FEET_PER_DEG_LAT * Math.cos(lat0 * Math.PI / 180);
  const ft = rings.map((r) => r.map(([lon, lat]) => [(lon - lon0) * kx, (lat - lat0) * FEET_PER_DEG_LAT]));

  const W = 640, H = 480, PAD = 70;
  const xs = ft.flat().map((p) => p[0]), ys = ft.flat().map((p) => p[1]);
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
  const spanX = Math.max(maxX - minX, 1), spanY = Math.max(maxY - minY, 1);
  const scale = Math.min((W - 2 * PAD) / spanX, (H - 2 * PAD - 30) / spanY);
  const ox = (W - spanX * scale) / 2, oy = 40 + (H - 40 - spanY * scale) / 2;
  const sx = (x) => ox + (x - minX) * scale;
  const sy = (y) => oy + (maxY - y) * scale;  // SVG y grows downward

  const path = ft.map((r) => "M" + r.map(([x, y]) => `${sx(x).toFixed(1)},${sy(y).toFixed(1)}`).join("L") + "Z").join("");

  // Edge labels: only for the outer rings and edges long enough to read.
  const labels = [];
  const isCondo = d.geometry.source === "condo";
  for (const r of ft) {
    if (ringArea(r) === 0) continue;
    const ccw = ringArea(r) > 0;
    const edges = r.map((p, i) => [p, r[(i + 1) % r.length]]);
    const minLen = Math.max(...edges.map(([a, b]) => Math.hypot(b[0] - a[0], b[1] - a[1]))) * (edges.length > 24 ? 0.25 : 0.06);
    for (const [a, b] of edges) {
      const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
      if (len < minLen || len * scale < 28) continue;
      const mx = sx((a[0] + b[0]) / 2), my = sy((a[1] + b[1]) / 2);
      // Outward normal in screen space (rings are drawn with y flipped).
      let nx = (sy(b[1]) - sy(a[1])), ny = -(sx(b[0]) - sx(a[0]));
      const n = Math.hypot(nx, ny) || 1;
      nx /= n; ny /= n;
      if (ccw) { nx = -nx; ny = -ny; }
      let ang = Math.atan2(sy(b[1]) - sy(a[1]), sx(b[0]) - sx(a[0])) * 180 / Math.PI;
      if (ang > 90) ang -= 180;
      if (ang < -90) ang += 180;
      const tx = mx + nx * 12, ty = my + ny * 12;
      labels.push(`<text x="${tx.toFixed(1)}" y="${ty.toFixed(1)}" transform="rotate(${ang.toFixed(1)} ${tx.toFixed(1)} ${ty.toFixed(1)})" text-anchor="middle" dominant-baseline="middle" class="dim">${Math.round(len).toLocaleString()}′</text>`);
    }
  }

  const areaFt = Math.abs(ft.reduce((a, r) => a + ringArea(r), 0));
  // Scale bar with a round length.
  const target = 120 / scale;
  const pow = Math.pow(10, Math.floor(Math.log10(target)));
  const barFt = [1, 2, 5, 10].map((m) => m * pow).filter((v) => v <= target).pop() || pow;
  const barPx = barFt * scale;
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const title = `${d.address || "(no address)"}${d.unit ? " #" + d.unit : ""}`;
  const sub = `Parcel ${d.parcel_id} · ${Math.round(areaFt).toLocaleString()} sq ft (${(areaFt / 43560).toFixed(2)} ac)${isCondo ? " · condo complex outline" : ""}`;

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" font-family="system-ui, Segoe UI, sans-serif">
  <style>.dim{font-size:12px;fill:#334155}</style>
  <rect width="100%" height="100%" fill="#ffffff"/>
  <text x="20" y="26" font-size="16" font-weight="600" fill="#0f172a">${esc(title)}</text>
  <text x="20" y="44" font-size="12" fill="#64748b">${esc(sub)}</text>
  <path d="${path}" fill="#dbeafe" fill-rule="evenodd" stroke="#1d4ed8" stroke-width="2" stroke-linejoin="round"/>
  ${labels.join("\n  ")}
  <g transform="translate(${W - 36} ${H - 70})">
    <path d="M0,-22 L8,6 L0,0 L-8,6 Z" fill="#0f172a"/>
    <text y="22" text-anchor="middle" font-size="12" font-weight="600" fill="#0f172a">N</text>
  </g>
  <g transform="translate(20 ${H - 26})">
    <rect width="${barPx.toFixed(1)}" height="6" fill="#0f172a"/>
    <rect width="${(barPx / 2).toFixed(1)}" height="6" fill="#ffffff" stroke="#0f172a"/>
    <text y="-6" font-size="11" fill="#334155">0</text>
    <text x="${barPx.toFixed(1)}" y="-6" font-size="11" text-anchor="end" fill="#334155">${barFt.toLocaleString()} ft</text>
  </g>
  <text x="${W - 20}" y="${H - 8}" font-size="10" text-anchor="end" fill="#94a3b8">Dimensions measured from county GIS parcel lines; not a survey.</text>
</svg>`;
}

function downloadBlob(blob, filename) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

function downloadSvg(svg, name) {
  downloadBlob(new Blob([svg], { type: "image/svg+xml" }), name + ".svg");
}

function downloadPng(svg, name) {
  const img = new Image();
  const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
  img.onload = () => {
    const c = document.createElement("canvas");
    c.width = img.width * 2;
    c.height = img.height * 2;
    const ctx = c.getContext("2d");
    ctx.scale(2, 2);
    ctx.drawImage(img, 0, 0);
    URL.revokeObjectURL(url);
    c.toBlob((b) => downloadBlob(b, name + ".png"), "image/png");
  };
  img.src = url;
}
