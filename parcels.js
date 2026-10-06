export function parseBounds(value) {
  const parts = typeof value === 'string' ? value.split(',') : [];
  if (parts.length !== 4 || parts.some(part => part.trim() === '')) {
    throw new Error('bbox must contain west,south,east,north coordinates.');
  }
  const bounds = parts.map(Number);
  const [west, south, east, north] = bounds;
  if (!bounds.every(Number.isFinite) || west < -180 || east > 180 ||
      south < -90 || north > 90 || west >= east || south >= north) {
    throw new Error('bbox must be a valid longitude/latitude rectangle.');
  }
  if (east - west > 0.2 || north - south > 0.2) {
    throw new Error('Zoom in further to load properties.');
  }
  return bounds;
}

function geometryBounds(geometry) {
  if (!geometry || !['Polygon', 'MultiPolygon'].includes(geometry.type)) {
    throw new Error('Each parcel must have Polygon or MultiPolygon geometry.');
  }
  const polygons = geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.coordinates;
  const bounds = [Infinity, Infinity, -Infinity, -Infinity];
  if (!Array.isArray(polygons) || !polygons.length) throw new Error('Empty parcel geometry.');
  for (const polygon of polygons) {
    if (!Array.isArray(polygon) || !polygon.length) throw new Error('Empty parcel polygon.');
    for (const ring of polygon) {
      if (!Array.isArray(ring) || ring.length < 4) throw new Error('Invalid parcel ring.');
      for (const point of ring) {
        if (!Array.isArray(point) || point.length < 2 ||
            !point.every(Number.isFinite) || Math.abs(point[0]) > 180 || Math.abs(point[1]) > 90) {
          throw new Error('Parcel coordinates must use WGS84 longitude/latitude.');
        }
        bounds[0] = Math.min(bounds[0], point[0]);
        bounds[1] = Math.min(bounds[1], point[1]);
        bounds[2] = Math.max(bounds[2], point[0]);
        bounds[3] = Math.max(bounds[3], point[1]);
      }
      if (ring[0][0] !== ring.at(-1)[0] || ring[0][1] !== ring.at(-1)[1]) {
        throw new Error('Parcel rings must be closed.');
      }
    }
  }
  return bounds;
}

export function indexParcels(collection) {
  if (collection?.type !== 'FeatureCollection' || !Array.isArray(collection.features)) {
    throw new Error('Data must be a GeoJSON FeatureCollection.');
  }
  const ids = new Set();
  return collection.features.map(feature => {
    const record = feature.properties;
    if (feature.type !== 'Feature' || typeof record?.id !== 'string' || !record.id.trim()) {
      throw new Error('Every parcel must have a non-empty string properties.id.');
    }
    if (ids.has(record.id)) throw new Error(`Duplicate parcel ID: ${record.id}`);
    ids.add(record.id);
    for (const field of ['address', 'owner', 'saleDate']) {
      if (record[field] != null && typeof record[field] !== 'string') {
        throw new Error(`${field} must be text or null.`);
      }
    }
    if (record.salePrice != null && (!Number.isFinite(record.salePrice) || record.salePrice < 0)) {
      throw new Error('salePrice must be a non-negative number or null.');
    }
    return {
      feature: {
        type: 'Feature',
        geometry: feature.geometry,
        properties: {
          id: record.id,
          address: record.address ?? null,
          owner: record.owner ?? null,
          saleDate: record.saleDate ?? null,
          salePrice: record.salePrice ?? null,
        },
      },
      bounds: geometryBounds(feature.geometry),
    };
  });
}

export function queryParcels(index, bounds, limit = 500) {
  const features = [];
  let truncated = false;
  for (const parcel of index) {
    const box = parcel.bounds;
    if (box[0] > bounds[2] || box[2] < bounds[0] || box[1] > bounds[3] || box[3] < bounds[1]) continue;
    if (features.length === limit) {
      truncated = true;
      break;
    }
    features.push(parcel.feature);
  }
  return { type: 'FeatureCollection', features, truncated };
}
