import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parse } from 'csv-parse/sync';
import { indexParcels } from './parcels.js';

const requiredFields = ['geometryId', 'recordId', 'address', 'owner', 'saleDate', 'salePrice'];

export function importParcels(geometry, csv, fields) {
  for (const key of requiredFields) {
    if (typeof fields?.[key] !== 'string' || !fields[key].trim()) {
      throw new Error(`Field mapping must specify ${key}.`);
    }
  }
  const records = parse(csv, { columns: true, bom: true, skip_empty_lines: true });
  if (!records.length) throw new Error('Property CSV contains no records.');
  for (const key of requiredFields.filter(key => key !== 'geometryId')) {
    if (!Object.hasOwn(records[0], fields[key])) throw new Error(`CSV column not found: ${fields[key]}`);
  }
  const byId = new Map();
  for (const row of records) {
    const id = row[fields.recordId].trim();
    if (!id) throw new Error('Property CSV contains an empty parcel ID.');
    if (byId.has(id)) throw new Error(`Duplicate CSV parcel ID: ${id}. Use one current record per parcel.`);
    byId.set(id, row);
  }
  if (geometry?.type !== 'FeatureCollection' || !Array.isArray(geometry.features)) {
    throw new Error('Parcel geometry must be a GeoJSON FeatureCollection.');
  }
  let matched = 0;
  const features = geometry.features.map(feature => {
    const rawId = feature.properties?.[fields.geometryId];
    if (typeof rawId !== 'string' || !rawId.trim()) {
      throw new Error('Geometry parcel IDs must be non-empty strings, preserving leading zeros.');
    }
    const id = rawId.trim();
    const row = byId.get(id);
    const record = { id, address: null, owner: null, saleDate: null, salePrice: null };
    if (row) {
      matched++;
      for (const key of ['address', 'owner', 'saleDate']) record[key] = row[fields[key]].trim() || null;
      const rawPrice = row[fields.salePrice].trim();
      if (rawPrice) {
        const price = rawPrice.replace(/[$,]/g, '');
        if (!/^\d+(?:\.\d+)?$/.test(price) || !Number.isFinite(Number(price))) {
          throw new Error(`Invalid sale price for parcel ${id}: ${rawPrice}`);
        }
        record.salePrice = Number(price);
      }
    }
    return { type: 'Feature', geometry: feature.geometry, properties: record };
  });
  if (!matched) throw new Error('No parcel IDs matched the CSV. Check the field mapping and ID formatting.');
  const collection = { type: 'FeatureCollection', features };
  indexParcels(collection);
  return { collection, matched, unmatched: features.length - matched };
}

async function main() {
  const [geometryPath, csvPath, fieldsPath, outputPath, ...extra] = process.argv.slice(2);
  if (!geometryPath || !csvPath || !fieldsPath || !outputPath || extra.length) {
    throw new Error('Usage: npm run import-data -- <parcels.geojson> <properties.csv> <fields.json> <output.geojson>');
  }
  const [geometry, csv, fields] = await Promise.all([
    readFile(geometryPath, 'utf8'), readFile(csvPath, 'utf8'), readFile(fieldsPath, 'utf8'),
  ]);
  const result = importParcels(JSON.parse(geometry), csv, JSON.parse(fields));
  await mkdir(dirname(resolve(outputPath)), { recursive: true });
  await writeFile(outputPath, JSON.stringify(result.collection));
  console.log(`Imported ${result.collection.features.length} parcels; ${result.matched} matched, ${result.unmatched} without property details.`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main().catch(error => {
    console.error(error.message);
    process.exitCode = 1;
  });
}
