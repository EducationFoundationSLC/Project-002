import test from 'node:test';
import assert from 'node:assert/strict';
import { importParcels } from '../import-data.js';
import { indexParcels, parseBounds, queryParcels } from '../parcels.js';
import { createApp } from '../server.js';

const geometry = {
  type: 'FeatureCollection',
  features: [{
    type: 'Feature',
    properties: { PARCEL: '001' },
    geometry: {
      type: 'Polygon',
      coordinates: [[[-80.38, 27.32], [-80.379, 27.32], [-80.379, 27.321], [-80.38, 27.32]]],
    },
  }],
};
const fields = {
  geometryId: 'PARCEL', recordId: 'ID', address: 'ADDRESS',
  owner: 'OWNER', saleDate: 'DATE', salePrice: 'PRICE',
};
const csv = 'ID,ADDRESS,OWNER,DATE,PRICE\n001,Example home,"Example, Owner",2024-01-02,"$123,456.00"\n';

test('imports county-style CSV with quoted fields, BOM, and leading-zero IDs', () => {
  const result = importParcels(geometry, '\ufeff' + csv, fields);
  assert.equal(result.matched, 1);
  assert.equal(result.unmatched, 0);
  assert.deepEqual(result.collection.features[0].properties, {
    id: '001', address: 'Example home', owner: 'Example, Owner',
    saleDate: '2024-01-02', salePrice: 123456,
  });
});

test('preserves zero sale prices and leaves missing details unavailable', () => {
  const extended = structuredClone(geometry);
  extended.features.push({ ...structuredClone(geometry.features[0]), properties: { PARCEL: '002' } });
  const result = importParcels(extended, 'ID,ADDRESS,OWNER,DATE,PRICE\n001,,,,0\n', fields);
  assert.equal(result.collection.features[0].properties.salePrice, 0);
  assert.equal(result.collection.features[0].properties.owner, null);
  assert.equal(result.collection.features[1].properties.salePrice, null);
  assert.equal(result.unmatched, 1);
});

test('rejects mismatched IDs, duplicate records, missing columns, and invalid prices', () => {
  assert.throws(() => importParcels(geometry, csv.replace('001,', '999,'), fields), /No parcel IDs matched/);
  assert.throws(() => importParcels(geometry, csv + '001,,,,0\n', fields), /Duplicate CSV parcel ID/);
  assert.throws(() => importParcels(geometry, csv.replace('OWNER', 'NAME'), fields), /CSV column not found/);
  for (const price of ['unknown', '-1', 'Infinity', '1e3']) {
    assert.throws(() => importParcels(geometry, `ID,ADDRESS,OWNER,DATE,PRICE\n001,,,,${price}\n`, fields), /Invalid sale price/);
  }
  assert.throws(() => importParcels(geometry, csv, {}), /Field mapping/);
});

test('validates parcel geometry and IDs before serving', () => {
  const { collection } = importParcels(geometry, csv, fields);
  const invalid = structuredClone(collection);
  invalid.features[0].geometry.coordinates[0][0][0] = 800000;
  assert.throws(() => indexParcels(invalid), /WGS84/);
  const openRing = structuredClone(collection);
  openRing.features[0].geometry.coordinates[0][3] = [-80.381, 27.32];
  assert.throws(() => indexParcels(openRing), /closed/);
  assert.throws(() => indexParcels({ ...collection, features: [...collection.features, ...collection.features] }), /Duplicate parcel ID/);
  const multi = structuredClone(collection);
  multi.features[0].geometry = { type: 'MultiPolygon', coordinates: [multi.features[0].geometry.coordinates] };
  assert.equal(indexParcels(multi).length, 1);
});

test('accepts bounded map queries and rejects malformed or excessive areas', () => {
  assert.deepEqual(parseBounds('-80.39,27.31,-80.37,27.33'), [-80.39, 27.31, -80.37, 27.33]);
  for (const input of [null, '', '1,2,3', ',2,3,4', 'NaN,2,3,4', '2,2,1,3',
    '-181,2,-180.9,2.1', '-80,91,-79.9,91.1', '-81,27,-80,28']) {
    assert.throws(() => parseBounds(input));
  }
});

test('queries visible parcels only, caps results, and excludes extra source fields', () => {
  const { collection } = importParcels(geometry, csv, fields);
  collection.features[0].properties.privateExtra = 'not served';
  const index = indexParcels(collection);
  const bounds = parseBounds('-80.39,27.31,-80.37,27.33');
  const result = queryParcels(index, bounds);
  assert.equal(result.features.length, 1);
  assert.equal(result.features[0].properties.privateExtra, undefined);
  assert.equal(queryParcels(index, parseBounds('-80.5,27.4,-80.49,27.41')).features.length, 0);
  assert.equal(queryParcels([...index, ...index], bounds, 1).truncated, true);
  assert.equal(queryParcels(index, bounds, 1).truncated, false);
});

async function withServer(index, callback) {
  const server = createApp(index);
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    await callback(`http://127.0.0.1:${server.address().port}`);
  } finally {
    await new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
  }
}

test('HTTP app serves map assets and property data, rejects invalid queries and private paths', async () => {
  const { collection } = importParcels(geometry, csv, fields);
  await withServer(indexParcels(collection), async base => {
    const response = await fetch(`${base}/api/parcels?bbox=-80.39,27.31,-80.37,27.33`);
    assert.equal(response.status, 200);
    assert.equal((await response.json()).features[0].properties.owner, 'Example, Owner');
    assert.match(response.headers.get('content-security-policy'), /script-src 'self'/);
    for (const path of ['/', '/app.js', '/styles.css', '/vendor/leaflet.js', '/vendor/leaflet.css']) {
      assert.equal((await fetch(base + path)).status, 200);
    }
    assert.equal((await fetch(`${base}/api/parcels?bbox=bad`)).status, 400);
    for (const path of ['/data/parcels.geojson', '/package.json', '/%2e%2e/server.js']) {
      assert.equal((await fetch(base + path)).status, 404);
    }
    assert.equal((await fetch(base, { method: 'POST' })).status, 405);
    assert.equal(await (await fetch(base, { method: 'HEAD' })).text(), '');
  });
});

test('HTTP app explains that county data must be imported when absent', async () => {
  await withServer(null, async base => {
    const response = await fetch(`${base}/api/parcels?bbox=-80.39,27.31,-80.37,27.33`);
    assert.equal(response.status, 503);
    assert.match((await response.json()).error, /County data is not loaded/);
  });
});
