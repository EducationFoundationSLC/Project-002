// St. Lucie property browser front end. Filter state lives in the URL hash so
// any filtered view can be bookmarked or shared.
const state = { page: 1, size: 50, sort: "est_tax", dir: "desc", view: "tax", filters: {} };
const DEFAULTS = { sort: "est_tax", dir: "desc", view: "tax" };
const MULTI = ["category", "land_use", "jurisdiction", "zip", "exemption"];
// Labels shown to people but not sent to the server.
const LABEL_KEYS = ["near_label", "selection_label"];
const apiParams = (filters) => Object.fromEntries(Object.entries(filters).filter(([k]) => !LABEL_KEYS.includes(k)));
const $ = (s, el = document) => el.querySelector(s);
const money = (n) => (n == null ? "—" : (n < 0 ? "−$" : "$") + Math.abs(Math.round(n)).toLocaleString());
const cents = (n) => (n == null ? "—" : "$" + n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
const num = (n) => (n == null || n === 0 ? "—" : n.toLocaleString());
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

let filterMeta = null;

// Short names for the exemption list shown in the table.
function shortExemptions(list) {
  if (!list) return "";
  const names = list.split("; ").map((e) => e
    .replace(/^Homestead Exemption over.*$/, "")
    .replace(/^Homestead Exemption$/, "Homestead")
    .replace(/^Senior Homestead.*$/, "Senior")
    .replace(/^Widow'?s Exemption$/, "Widow")
    .replace(/^Widower'?s Exemption$/, "Widower")
    .replace(/^Veteran'?s Disability$/, "Veteran")
    .replace(/^Total & Permanent Service Connected Disability$/, "Vet 100%")
    .replace(/^Total & Permanent Disability$/, "Disability"));
  return [...new Set(names.filter(Boolean))].join(", ");
}

// How the owner's mailing address compares with the property address (see build_db.py).
const MAIL_TEXT = { same: "Same as property", different: "Different address", po_box: "PO box", elsewhere: "Different or PO box" };
const MAIL_BADGE = {
  different: '<span class="badge warn" title="Mailing address is different from the property address">Mail elsewhere</span>',
  po_box: '<span class="badge warn" title="Mail goes to a PO box">PO box</span>',
};

// ---------- table columns ----------
const C = {
  address: { label: "Address", sort: "address", cell: (r) => `<div class="addr">${esc(r.address || "(no address)")}${r.unit ? " #" + esc(r.unit) : ""}</div>
      <div class="meta">${r.distance != null ? `<b>${r.distance} mi</b> · ` : ""}${esc(r.jurisdiction)} ${esc(r.zip || "")}${r.pool ? '<span class="badge">Pool</span>' : ""}${r.homestead ? '<span class="badge">HX</span>' : ""}${MAIL_BADGE[r.mail_status] || ""}</div>` },
  type: { label: "Type", sort: "land_use_desc", cls: "hide-sm", cell: (r) => `<div>${esc(r.land_use_desc)}</div><div class="meta">${esc(r.category)}</div>` },
  owner: { label: "Owners", sort: "owner", cls: "owner hide-sm",
    cell: (r) => `<div>${esc(r.owner)}</div>${r.owner2 ? `<div>${esc(r.owner2)}</div>` : ""}`,
    title: (r) => [r.owner, r.owner2].filter(Boolean).join("\n") },
  just: { label: "Just value", sort: "just_value", cls: "num hide-sm", cell: (r) => money(r.just_value) },
  assessed: { label: "Assessed", sort: "assessed_value", cls: "num", cell: (r) => money(r.assessed_value) },
  exempt: { label: "Exemptions", sort: "exemption_value", cls: "num exempt", cell: (r) => r.exemption_value
      ? `${money(-r.exemption_value)}<div class="meta">${esc(shortExemptions(r.exemptions))}</div>` : "—" },
  taxable: { label: "Taxable", sort: "taxable_value", cls: "num", cell: (r) => money(r.taxable_value) },
  tax: { label: "Est. tax / yr", sort: "est_tax", cls: "num tax", cell: (r) => r.est_tax == null ? "—"
      : `${money(r.est_tax)}${r.non_ad_valorem ? `<div class="meta">incl. ${money(r.non_ad_valorem)} fees</div>` : ""}` },
  built: { label: "Built", sort: "year_built", cls: "num", cell: (r) => r.year_built ?? "—" },
  area: { label: "Sq ft", sort: "living_area", cls: "num hide-sm", cell: (r) => num(r.living_area) },
  bdba: { label: "Bd/Ba", sort: "bedrooms", cls: "num", cell: (r) => r.bedrooms
      ? `${r.bedrooms}/${r.full_baths ? r.full_baths + (r.half_baths ? ".5" : "") : 0}` : "—" },
  sale: { label: "Last sale", sort: "last_sale_date", cls: "num", cell: (r) => r.last_sale_date
      ? `${money(r.last_sale_price)}<div class="meta">${r.last_sale_date}</div>` : "—" },
};
const VIEWS = {
  tax: ["address", "type", "owner", "just", "assessed", "exempt", "taxable", "tax"],
  property: ["address", "type", "owner", "built", "area", "bdba", "just", "sale"],
  map: ["address", "type", "owner", "just", "assessed", "exempt", "taxable", "tax"],
};
const cols = () => VIEWS[state.view].map((k) => C[k]);

// ---------- state <-> URL ----------
function readHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  state.filters = {};
  Object.assign(state, DEFAULTS, { page: 1, detail: null });
  for (const [k, v] of p) {
    if (k === "page") state.page = +v || 1;
    else if (k === "sort" || k === "dir") state[k] = v;
    else if (k === "view") state.view = VIEWS[v] ? v : "tax";
    else if (k === "p") state.detail = v;
    else state.filters[k] = v;
  }
}
function writeHash() {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(state.filters)) if (v !== "" && v != null) p.set(k, v);
  for (const k of ["sort", "dir", "view"]) if (state[k] !== DEFAULTS[k]) p.set(k, state[k]);
  if (state.page > 1) p.set("page", state.page);
  if (state.detail) p.set("p", state.detail);
  history.replaceState(null, "", "#" + p.toString());
}
const listOf = (k) => (state.filters[k] ? state.filters[k].split(",") : []);
function setList(k, arr) {
  if (arr.length) state.filters[k] = arr.join(",");
  else delete state.filters[k];
}

// ---------- near me ----------
function nearState() {
  if (!state.filters.near) return null;
  const [lat, lon] = state.filters.near.split(",").map(Number);
  return { lat, lon, radius: +(state.filters.radius || 0.5), label: state.filters.near_label || "you" };
}
function setNear(lat, lon, label) {
  state.filters.near = `${lat.toFixed(5)},${lon.toFixed(5)}`;
  if (label) state.filters.near_label = label; else delete state.filters.near_label;
  state.sort = "distance";
  state.dir = "asc";
  syncInputs();
  refilter();
}
function clearNear() {
  delete state.filters.near;
  delete state.filters.radius;
  delete state.filters.near_label;
  if (state.sort === "distance") { state.sort = DEFAULTS.sort; state.dir = DEFAULTS.dir; }
}
$("#near-me").addEventListener("click", () => {
  if (state.filters.near && !state.filters.near_label) { clearNear(); syncInputs(); return refilter(); }
  if (!navigator.geolocation) return alert("Location isn't available in this browser.");
  $("#near-me").textContent = "📍 Locating…";
  navigator.geolocation.getCurrentPosition(
    (pos) => { $("#near-me").textContent = "📍 Near me"; setNear(pos.coords.latitude, pos.coords.longitude); },
    (err) => { $("#near-me").textContent = "📍 Near me"; alert("Couldn't get your location: " + err.message); },
    { enableHighAccuracy: true, timeout: 15000 });
});

// ---------- filter sidebar ----------
function checkbox(name, value, label, count, checked) {
  return `<label class="check"><input type="checkbox" data-multi="${name}" value="${esc(value)}" ${checked ? "checked" : ""}>
    <span>${esc(label)}</span><span class="count">${count.toLocaleString()}</span></label>`;
}

function renderFilters() {
  const cats = listOf("category"), uses = listOf("land_use");
  $("#f-category").innerHTML = filterMeta.categories.map((c, i) => `
    <div class="cat-row">${checkbox("category", c.name, c.name, c.count, cats.includes(c.name))}
      <button class="expand" data-target="sub-${i}" aria-expanded="false" title="Show subtypes">▸</button></div>
    <div class="subtypes" id="sub-${i}" hidden>
      ${c.land_uses.map((u) => checkbox("land_use", u.name, u.name, u.count, uses.includes(u.name))).join("")}
    </div>`).join("");
  const j = listOf("jurisdiction"), z = listOf("zip");
  $("#f-jurisdiction").innerHTML = filterMeta.jurisdictions.map((r) => checkbox("jurisdiction", r.name, r.name, r.count, j.includes(r.name))).join("");
  $("#f-zip").innerHTML = filterMeta.zips.map((r) => checkbox("zip", r.name, r.name, r.count, z.includes(r.name))).join("");
  const ex = listOf("exemption");
  $("#f-exemption").innerHTML = filterMeta.exemptions.map((r) => checkbox("exemption", r.name, r.name, r.count, ex.includes(r.name))).join("");
  document.querySelectorAll(".subtypes").forEach((el) => {
    if (el.querySelector("input:checked")) toggleSub(el.previousElementSibling.querySelector(".expand"), true);
  });
  $("#rates-note").textContent = `Taxes estimated from ${filterMeta.rates_year} final millage rates`;
}

function syncInputs() {
  document.querySelectorAll("[data-f]").forEach((el) => (el.value = state.filters[el.dataset.f] ?? ""));
  $("#search").value = state.filters.q ?? "";
  document.querySelectorAll("[data-multi]").forEach((el) => (el.checked = listOf(el.dataset.multi).includes(el.value)));
  document.querySelectorAll("[data-view]").forEach((b) => b.setAttribute("aria-selected", b.dataset.view === state.view));
  const near = nearState();
  $("#near-box").hidden = !near;
  if (near) $("#near-label").textContent = near.label;
  $("#near-me").classList.toggle("active", !!near && !state.filters.near_label);
  const isMap = state.view === "map";
  $("#map-view").hidden = !isMap;
  $("#table-view").hidden = isMap;
  $("#pager").hidden = isMap;
}

function toggleSub(btn, force) {
  const el = document.getElementById(btn.dataset.target);
  const open = force ?? el.hidden;
  el.hidden = !open;
  btn.textContent = open ? "▾" : "▸";
  btn.setAttribute("aria-expanded", open);
}

// ---------- results ----------
function renderHead() {
  $("#table thead tr").innerHTML = cols().map((c) => {
    const sorted = c.sort === state.sort;
    return `<th data-sort="${c.sort}" class="${c.cls || ""}${sorted ? " sorted" : ""}${sorted && state.dir === "asc" ? " asc" : ""}">${c.label}</th>`;
  }).join("");
}

let inflight;
async function load() {
  writeHash();
  renderHead();
  const params = new URLSearchParams({ ...apiParams(state.filters), page: state.page, size: state.size, sort: state.sort, dir: state.dir });
  inflight?.abort();
  inflight = new AbortController();
  const tb = $("#table tbody");
  tb.style.opacity = 0.5;
  let data;
  try {
    const res = await fetch("/api/properties?" + params, { signal: inflight.signal });
    if (!res.ok) throw new Error(res.statusText);
    data = await res.json();
  } catch (e) {
    if (e.name === "AbortError") return;
    tb.innerHTML = `<tr><td colspan="${cols().length}" class="empty">Could not load results (${esc(e.message)}). Check the filter values.</td></tr>`;
    tb.style.opacity = 1;
    return;
  }
  renderSummary(data);
  renderRows(data.rows);
  if (state.view === "map") {
    if (!ResultsMap.map) ResultsMap.init($("#results-map"), openDetail);
    ResultsMap.show(apiParams(state.filters), nearState());
  }
  const pages = Math.max(1, Math.ceil(data.total / data.size));
  $("#page-info").textContent = `Page ${data.page.toLocaleString()} of ${pages.toLocaleString()}`;
  $("#prev").disabled = data.page <= 1;
  $("#next").disabled = data.page >= pages;
}

const LABELS = {
  q: "Search", just_min: "Value ≥", just_max: "Value ≤", taxable_min: "Taxable ≥", taxable_max: "Taxable ≤",
  assessed_min: "Assessed ≥", assessed_max: "Assessed ≤", tax_min: "Tax ≥", tax_max: "Tax ≤",
  year_min: "Built ≥", year_max: "Built ≤", area_min: "Sq ft ≥", area_max: "Sq ft ≤", acres_min: "Acres ≥",
  acres_max: "Acres ≤", beds_min: "Beds ≥", baths_min: "Baths ≥", sale_price_min: "Sale ≥", sale_price_max: "Sale ≤",
  sold_after: "Sold after", sold_before: "Sold before", homestead: "Homestead", pool: "Pool",
  out_of_state: "Out-of-state owner", improved: "Improved", exempt: "Exemptions",
};
const FLAGS = ["homestead", "pool", "out_of_state", "improved", "exempt"];
const MONEY_PARAMS = /^(just|taxable|assessed|tax|sale_price)_(min|max)$/;
function chipLabel(k, v) {
  if (k === "near") { const n = nearState(); return `Within ${n.radius} mi of ${n.label}`; }
  if (k === "mail") return `Mailing: ${MAIL_TEXT[v] || v}`;
  if (k === "selection") return `AI: ${state.filters.selection_label || "selected properties"}`;
  if (MULTI.includes(k)) return v.split(",").join(", ");
  if (FLAGS.includes(k)) return `${LABELS[k]}: ${v === "1" ? "yes" : "no"}`;
  return `${LABELS[k] || k} ${MONEY_PARAMS.test(k) ? money(+v) : v}`;
}

function renderSummary(d) {
  const s = d.summary;
  const chips = Object.entries(state.filters)
    .filter(([k]) => k !== "radius" && !LABEL_KEYS.includes(k))
    .map(([k, v]) => `<button class="chip" data-clear="${k}" title="Remove filter">${esc(chipLabel(k, v))} ×</button>`).join("");
  $("#summary").innerHTML = `
    <div class="stat"><b>${d.total.toLocaleString()}</b><span>properties</span></div>
    <div class="stat"><b>${money(s.assessed)}</b><span>assessed value</span></div>
    <div class="stat"><b>${money(s.exempt)}</b><span>exemptions</span></div>
    <div class="stat"><b>${money(s.taxable)}</b><span>taxable value</span></div>
    <div class="stat hl"><b>${money(s.tax)}</b><span>estimated taxes / yr</span></div>
    ${chips ? `<div class="chips">${chips}</div>` : ""}`;
}

function renderRows(rows) {
  const tb = $("#table tbody");
  tb.style.opacity = 1;
  if (!rows.length) {
    tb.innerHTML = `<tr><td colspan="${cols().length}" class="empty">No properties match these filters.</td></tr>`;
    return;
  }
  tb.innerHTML = rows.map((r) => `<tr data-id="${r.property_id}">${cols().map((c) =>
    `<td class="${c.cls || ""}"${c.title ? ` title="${esc(c.title(r))}"` : ""}>${c.cell(r)}</td>`).join("")}</tr>`).join("");
}

// ---------- detail drawer ----------
function taxBill(d) {
  if (d.est_tax == null) return `<p class="meta">No assessment on the roll for this parcel, so no tax estimate.</p>`;
  const row = (l) => `<tr><td>${esc(l.authority)}</td><td class="num">${l.rate.toFixed(4)}</td>
      <td class="num">${money(l.taxable)}</td><td class="num">${cents(l.tax)}</td></tr>`;
  const group = (basis, title) => {
    const ls = d.levies.filter((l) => l.basis === basis);
    return ls.length ? `<tr class="group"><td colspan="4">${title}</td></tr>${ls.map(row).join("")}` : "";
  };
  const mills = d.levies.reduce((a, l) => a + l.rate, 0);
  return `<table class="bill">
    <tr><th>Taxing authority</th><th class="num">Mills</th><th class="num">Taxable</th><th class="num">Tax</th></tr>
    ${group("school", "School")}
    ${group("county", "County")}
    ${group("other", "City &amp; districts")}
    <tr><th>Ad valorem subtotal</th><th class="num">${mills.toFixed(4)}</th><th></th><th class="num">${cents(d.est_ad_valorem)}</th></tr>
    ${d.other_assessments.length ? `<tr class="group"><td colspan="4">Non-ad valorem assessments</td></tr>
      ${d.other_assessments.map((o) => `<tr><td colspan="3">${esc(o.description)}</td><td class="num">${cents(o.amount)}</td></tr>`).join("")}` : ""}
    <tr class="total"><th colspan="3">Estimated total tax</th><th class="num">${cents(d.est_tax)}</th></tr>
  </table>
  <p class="meta">Estimate using ${esc(d.rates_year)} final millage rates for tax district ${esc(d.tax_district)}.
  Each kind of tax uses its own taxable value: the second homestead exemption and the 10% non-homestead
  assessment cap don't apply to school taxes, and the senior exemption only applies to county taxes. Your actual bill from the Tax Collector may differ, and paying
  in November gets a 4% discount.</p>`;
}

// The Property Appraiser's TRIM (Truth in Millage) notice PDF, keyed by PropertyID.
// We link to it rather than download it: the county's server only serves it to browsers.
const TRIM_URL = "https://api.paslc.gov/TrimPrint/api/pdf/INLINE/";

async function openDetail(id) {
  const res = await fetch("/api/property/" + encodeURIComponent(id));
  if (!res.ok) { state.detail = null; writeHash(); return; }
  const d = await res.json();
  state.detail = id;
  writeHash();
  const kv = (label, val) => `<div><span>${label}</span>${val ?? "—"}</div>`;
  const sales = d.sales.filter((s) => s.price > 0);
  $("#drawer-body").innerHTML = `
    <h2 id="d-title">${esc(d.address || "(no address)")}${d.unit ? " #" + esc(d.unit) : ""}</h2>
    <p class="lead">${esc(d.jurisdiction)} ${esc(d.zip || "")} · Parcel ${esc(d.parcel_id)}</p>
    ${d.geometry ? `<div class="parcel-map" id="parcel-map"></div>
    <div class="map-actions">
      <button class="ghost" data-act="near-here">Properties near here</button>
      <a class="ghost" target="_blank" rel="noopener" href="https://www.google.com/maps/search/?api=1&query=${d.lat},${d.lon}">Google Maps ↗</a>
      <a class="ghost" target="_blank" rel="noopener" href="https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${d.lat},${d.lon}">Street View ↗</a>
    </div>` : `<p class="meta">No GIS parcel outline for this property.</p>`}
    <div class="kv">
      ${kv("Type", `${esc(d.land_use_desc)} (${esc(d.category)})`)}
      ${kv("Zoning", esc(d.zoning))}
      ${kv("Subdivision", esc(d.subdivision))}
      ${kv("Lot size", d.acres ? d.acres + " acres" : null)}
    </div>
    <h3>Values</h3>
    <div class="kv">
      ${kv("Land value", money(d.land_value))}
      ${kv("Building value", money(d.building_value))}
      ${kv("Just (market) value", money(d.just_value))}
      ${kv("Assessed value", `<b>${money(d.assessed_value)}</b>`)}
      ${kv("Exemptions", d.exemption_value ? money(-d.exemption_value) : "$0")}
      ${kv("Taxable value", `<b>${money(d.taxable_value)}</b>`)}
      ${d.district_taxable !== d.taxable_value ? kv("City &amp; district taxable value", money(d.district_taxable)) : ""}
      ${d.school_taxable !== d.taxable_value ? kv("School taxable value", money(d.school_taxable)) : ""}
      ${d.just_value > d.assessed_value ? kv("Assessment cap savings", money(d.just_value - d.assessed_value)) : ""}
    </div>
    <h3>Exemptions</h3>
    ${d.exemption_list.length ? `<table>
      ${d.exemption_list.map((e) => `<tr><td>${esc(e.description)}</td><td class="num">since ${esc(e.grant_year)}</td></tr>`).join("")}
      <tr><th>Total exempt</th><th class="num">${money(d.exemption_value)}</th></tr></table>`
      : `<p class="meta">None</p>`}
    <h3>Estimated taxes</h3>
    ${taxBill(d)}
    <div class="map-actions">
      <a class="ghost" target="_blank" rel="noopener" href="${TRIM_URL}${encodeURIComponent(d.property_id)}">Official TRIM notice (PDF) ↗</a>
    </div>
    <p class="meta">The Property Appraiser's Truth in Millage notice: official values and proposed taxes for this property.</p>
    ${d.geometry ? `<h3>Lot drawing</h3>
    <div class="plat">${platSvg(d)}</div>
    <div class="map-actions">
      <button class="ghost" data-act="svg">Download SVG</button>
      <button class="ghost" data-act="png">Download PNG</button>
    </div>` : ""}
    ${d.buildings ? `<h3>Building</h3><div class="kv">
      ${kv("Building type", esc(d.building_type))}
      ${kv("Year built", d.year_built)}
      ${kv("Living area", d.living_area ? d.living_area.toLocaleString() + " sq ft" : null)}
      ${kv("Bedrooms / baths", d.bedrooms ? `${d.bedrooms} bd / ${d.full_baths} full, ${d.half_baths} half` : null)}
      ${kv("Buildings on parcel", d.buildings)}
      ${kv("Pool", d.pool ? "Yes" : "No")}</div>` : ""}
    <h3>Owner &amp; mailing address</h3>
    <div>${[d.owner, d.owner2, d.owner3].filter(Boolean).map(esc).join("<br>")}</div>
    <div class="kv addresses">
      ${kv("Property address", `${esc(d.address || "(no address)")}${d.unit && !(d.address || "").includes(d.unit) ? " #" + esc(d.unit) : ""}<br>${esc(d.jurisdiction)} ${esc(d.zip || "")}`)}
      ${kv("Mailing address", d.mail_line1 || d.mailing_address
        ? [d.mail_line1, d.mail_line2].filter(Boolean).map(esc).join("<br>") +
          (d.mail_line1 ? `<br>${esc([d.mail_city, d.mail_state, d.mail_zip].filter(Boolean).join(" "))}${d.mail_country ? "<br>" + esc(d.mail_country) : ""}` : esc(d.mailing_address))
        : null)}
    </div>
    ${d.mail_status && d.mail_status !== "unknown" ? `<p class="meta">${d.mail_status === "same"
      ? "✓ Mail goes to the property address."
      : `⚠ Mail goes ${d.mail_status === "po_box" ? "to a PO box" : "to a different address"}.
         ${d.homestead ? "This property has a homestead exemption, which requires the owner to live here as their permanent home. A different mailing address doesn't prove they don't (some people use a PO box, a relative's or a business address), but it can be worth a closer look." : ""}`}</p>` : ""}
    ${sales.length ? `<h3>Sales history</h3><table>
      <tr><th>Date</th><th class="num">Price</th><th>Type</th></tr>
      ${sales.map((s) => `<tr><td>${esc(s.sale_date)}</td><td class="num">${money(s.price)}</td><td>${esc(s.deed)}<div class="meta">${esc(s.qualification)}</div></td></tr>`).join("")}</table>` : ""}
    ${d.legal ? `<h3>Legal description</h3><p class="legal">${esc(d.legal)}</p>` : ""}`;
  $("#drawer").hidden = false;
  $("#drawer-close").focus();
  current = d;
  if (d.geometry) showParcelMap($("#parcel-map"), d, openDetail);
}
let current = null;

$("#drawer-body").addEventListener("click", (e) => {
  const act = e.target.dataset.act;
  if (!act || !current) return;
  const name = `parcel-${current.parcel_id}`;
  if (act === "svg") downloadSvg(platSvg(current), name);
  if (act === "png") downloadPng(platSvg(current), name);
  if (act === "near-here") {
    const label = current.address || `parcel ${current.parcel_id}`;
    closeDrawer();
    setNear(current.lat, current.lon, label);
  }
});
function closeDrawer() {
  if ($("#drawer").hidden) return;
  $("#drawer").hidden = true;
  state.detail = null;
  writeHash();
}

// ---------- events ----------
function refilter() { state.page = 1; load(); }

document.addEventListener("change", (e) => {
  const el = e.target;
  if (el.dataset.multi) {
    const k = el.dataset.multi, cur = new Set(listOf(k));
    el.checked ? cur.add(el.value) : cur.delete(el.value);
    setList(k, [...cur]);
    refilter();
  } else if (el.dataset.f) {
    if (el.value === "") delete state.filters[el.dataset.f];
    else state.filters[el.dataset.f] = el.value;
    refilter();
  }
});

let searchTimer;
$("#search").addEventListener("input", (e) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    const v = e.target.value.trim();
    if (v) state.filters.q = v; else delete state.filters.q;
    refilter();
  }, 300);
});

document.addEventListener("click", (e) => {
  const t = e.target;
  if (t.matches(".expand")) return toggleSub(t);
  if (t.matches("[data-clear]")) {
    if (t.dataset.clear === "near") clearNear(); else delete state.filters[t.dataset.clear];
    if (t.dataset.clear === "selection") delete state.filters.selection_label;
    syncInputs();
    return refilter();
  }
  if (t.matches("[data-view]")) {
    state.view = t.dataset.view;
    syncInputs();
    return load();
  }
  const th = t.closest("th[data-sort]");
  if (th) {
    if (state.sort === th.dataset.sort) state.dir = state.dir === "desc" ? "asc" : "desc";
    else { state.sort = th.dataset.sort; state.dir = ["address", "owner", "land_use_desc"].includes(state.sort) ? "asc" : "desc"; }
    return refilter();
  }
  const tr = t.closest("tbody tr[data-id]");
  if (tr) return openDetail(tr.dataset.id);
  if (t === $("#drawer")) closeDrawer();
});
$("#drawer-close").addEventListener("click", closeDrawer);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });
$("#prev").addEventListener("click", () => { state.page--; load(); window.scrollTo(0, 0); });
$("#next").addEventListener("click", () => { state.page++; load(); window.scrollTo(0, 0); });
$("#reset").addEventListener("click", () => { clearNear(); state.filters = {}; syncInputs(); refilter(); });
$("#toggle-filters").addEventListener("click", (e) => {
  const open = $("#filters").classList.toggle("open");
  e.target.setAttribute("aria-expanded", open);
});

// ---------- Ask AI ----------
// Questions go to /api/ask. The server asks Claude, which can run read-only
// database queries and choose properties to show in the table and map.
const askHistory = [];  // earlier questions and answers, so follow-up questions work

// A very small Markdown renderer for answers: paragraphs, lists, tables, **bold**, `code`.
function renderMarkdown(text) {
  const inline = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>");
  const out = [];
  const lines = text.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;
    if (line.startsWith("|")) {  // a table: collect its rows, skip the |---| line
      const rows = [];
      for (; i < lines.length && lines[i].trim().startsWith("|"); i++) {
        if (!/^\|[\s:|-]+\|$/.test(lines[i].trim())) rows.push(lines[i].trim().slice(1, -1).split("|").map((c) => c.trim()));
      }
      i--;
      out.push(`<table>${rows.map((r, n) => `<tr>${r.map((c) => n ? `<td>${inline(c)}</td>` : `<th>${inline(c)}</th>`).join("")}</tr>`).join("")}</table>`);
    } else if (/^([-*]|\d+\.)\s/.test(line)) {  // a list
      const items = [];
      for (; i < lines.length && /^([-*]|\d+\.)\s/.test(lines[i].trim()); i++) items.push(lines[i].trim().replace(/^([-*]|\d+\.)\s+/, ""));
      i--;
      out.push(`<ul>${items.map((it) => `<li>${inline(it)}</li>`).join("")}</ul>`);
    } else {
      out.push(`<p>${inline(line.replace(/^#+\s*/, ""))}</p>`);
    }
  }
  return out.join("");
}

function addAskMessage(cls, html) {
  const div = document.createElement("div");
  div.className = cls;
  div.innerHTML = html;
  $("#ask-log").appendChild(div);
  $("#ask-log").scrollTop = $("#ask-log").scrollHeight;
  return div;
}

async function askQuestion(question) {
  addAskMessage("ask-q", esc(question));
  const pending = addAskMessage("ask-a meta", "Thinking… (this can take a little while)");
  $("#ask-input").disabled = true;
  let data;
  try {
    const res = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, history: askHistory, filters: apiParams(state.filters) }),
    });
    data = res.ok ? await res.json() : { error: `The server answered ${res.status}.` };
  } catch (e) {
    data = { error: "Couldn't reach the server." };
  }
  $("#ask-input").disabled = false;
  $("#ask-input").focus();
  if (data.error) {
    pending.className = "ask-a ask-error";
    pending.textContent = data.error;
    return;
  }
  askHistory.push({ role: "user", content: question }, { role: "assistant", content: data.answer });
  pending.className = "ask-a";
  pending.innerHTML = renderMarkdown(data.answer) +
    (data.queries?.length ? `<details><summary>How I found this (${data.queries.length} database ${data.queries.length === 1 ? "query" : "queries"})</summary>
      ${data.queries.map((q) => `<pre>${esc(q)}</pre>`).join("")}</details>` : "");
  if (data.show) {  // show the properties Claude picked in the table and map
    clearNear();
    state.filters = { ...data.show.filters };
    state.sort = data.show.sort;
    state.dir = data.show.dir;
    syncInputs();
    refilter();
  }
}

function toggleAsk(open) {
  $("#ask").hidden = !open;
  $("#ask-open").classList.toggle("active", open);
  $("#ask-open").setAttribute("aria-expanded", open);
  if (open) $("#ask-input").focus();
}
$("#ask-open").addEventListener("click", () => toggleAsk($("#ask").hidden));
$("#ask-close").addEventListener("click", () => toggleAsk(false));
$("#ask-new").addEventListener("click", () => {
  askHistory.length = 0;
  $("#ask-log").querySelectorAll(".ask-q, .ask-a").forEach((el) => el.remove());
});
$("#ask-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const q = $("#ask-input").value.trim();
  if (!q || $("#ask-input").disabled) return;
  $("#ask-input").value = "";
  askQuestion(q);
});
$("#ask-log").addEventListener("click", (e) => {
  if (e.target.matches("[data-example]") && !$("#ask-input").disabled) askQuestion(e.target.textContent);
});

(async function init() {
  readHash();
  filterMeta = await (await fetch("/api/filters")).json();
  renderFilters();
  syncInputs();
  load();
  if (state.detail) openDetail(state.detail);
})();
