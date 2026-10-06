const map = L.map('map').setView([27.32, -80.38], 12);
L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
}).addTo(map);

const status = document.querySelector('#status');
const details = document.querySelector('#details');
const properties = document.querySelector('#properties');
const locate = document.querySelector('#locate');
const currency = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });
let parcels;
let selected;
let locationMarker;
let request;
let refreshTimer;

function selectProperty(feature, layer) {
  if (selected?.setStyle) selected.setStyle({ color: '#216ea0', weight: 2 });
  selected = layer;
  if (layer.setStyle) layer.setStyle({ color: '#d47b00', weight: 4 });
  const record = feature.properties;
  document.querySelector('#details-title').textContent = record.address || 'Property details';
  details.replaceChildren();
  const fields = [
    ['Parcel ID', record.id],
    ['Address', record.address],
    ['Owner', record.owner],
    ['Last sale / purchase date', record.saleDate],
    ['Last sale price', record.salePrice == null ? null : currency.format(record.salePrice)],
  ];
  for (const [label, value] of fields) {
    const term = document.createElement('dt');
    term.textContent = label;
    const description = document.createElement('dd');
    description.textContent = value == null || value === '' ? 'Not available' : String(value);
    details.append(term, description);
  }
  details.hidden = false;
}

async function loadParcels() {
  request?.abort();
  const current = new AbortController();
  request = current;
  if (map.getZoom() < 15) {
    parcels?.remove();
    properties.replaceChildren();
    status.textContent = 'Zoom in to street level to load homes, or use your location.';
    return;
  }
  const bounds = map.getBounds();
  const bbox = [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()].join(',');
  status.textContent = 'Loading county property records…';
  try {
    const response = await fetch(`/api/parcels?bbox=${encodeURIComponent(bbox)}`, { signal: current.signal });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Unable to load properties.');
    if (current.signal.aborted) return;
    parcels?.remove();
    properties.replaceChildren();
    parcels = L.geoJSON(data, {
      style: { color: '#216ea0', weight: 2, fillOpacity: .15 },
      onEachFeature(feature, layer) {
        layer.on('click', () => selectProperty(feature, layer));
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = feature.properties.address || `Parcel ${feature.properties.id}`;
        button.addEventListener('click', () => {
          selectProperty(feature, layer);
          if (layer.getBounds) map.fitBounds(layer.getBounds(), { maxZoom: 18 });
          else if (layer.getLatLng) map.panTo(layer.getLatLng());
        });
        const item = document.createElement('li');
        item.append(button);
        properties.append(item);
      },
    }).addTo(map);
    status.textContent = data.features.length
      ? `${data.features.length} properties loaded. Select a highlighted home.${data.truncated ? ' More properties are available; zoom in further.' : ''}`
      : 'No property records in this view. Move the map to Saint Lucie County.';
  } catch (error) {
    if (current.signal.aborted) return;
    parcels?.remove();
    properties.replaceChildren();
    status.textContent = error.message;
  }
}

locate.addEventListener('click', () => {
  if (!navigator.geolocation) {
    status.textContent = 'Location is unavailable in this browser. You can still move and zoom the map.';
    return;
  }
  if (!window.isSecureContext) {
    status.textContent = 'Location requires HTTPS (or localhost). You can still browse the map manually.';
    return;
  }
  locate.disabled = true;
  status.textContent = 'Requesting your location…';
  navigator.geolocation.getCurrentPosition(position => {
    locate.disabled = false;
    const point = [position.coords.latitude, position.coords.longitude];
    locationMarker?.remove();
    locationMarker = L.circleMarker(point, { color: '#173e58', fillOpacity: 1, radius: 7 })
      .bindTooltip('Your location').addTo(map);
    map.setView(point, 17);
    loadParcels();
  }, () => {
    locate.disabled = false;
    status.textContent = 'Could not get your location. Allow location access or browse the map manually.';
  }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 });
});

map.on('moveend', () => {
  request?.abort();
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(loadParcels, 250);
});
loadParcels();
