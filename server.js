import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { indexParcels, parseBounds, queryParcels } from './parcels.js';

const root = fileURLToPath(new URL('.', import.meta.url));
const files = new Map([
  ['/', ['public/index.html', 'text/html; charset=utf-8']],
  ['/app.js', ['public/app.js', 'text/javascript; charset=utf-8']],
  ['/styles.css', ['public/styles.css', 'text/css; charset=utf-8']],
  ['/vendor/leaflet.js', ['node_modules/leaflet/dist/leaflet.js', 'text/javascript; charset=utf-8']],
  ['/vendor/leaflet.css', ['node_modules/leaflet/dist/leaflet.css', 'text/css; charset=utf-8']],
  ...['marker-icon.png', 'marker-icon-2x.png', 'marker-shadow.png', 'layers.png', 'layers-2x.png']
    .map(name => [`/vendor/images/${name}`, [`node_modules/leaflet/dist/images/${name}`, 'image/png']]),
]);

export function createApp(index = null) {
  return createServer(async (request, response) => {
    response.setHeader('X-Content-Type-Options', 'nosniff');
    response.setHeader('Referrer-Policy', 'strict-origin-when-cross-origin');
    response.setHeader('Content-Security-Policy',
      "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://tile.openstreetmap.org; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'");
    response.setHeader('Permissions-Policy', 'geolocation=(self)');
    const sendJson = (code, data) => {
      response.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' });
      response.end(JSON.stringify(data));
    };
    try {
      if (request.method !== 'GET' && request.method !== 'HEAD') {
        response.setHeader('Allow', 'GET, HEAD');
        sendJson(405, { error: 'Method not allowed.' });
        return;
      }
      const url = new URL(request.url, 'http://localhost');
      if (url.pathname === '/api/parcels') {
        let bounds;
        try {
          bounds = parseBounds(url.searchParams.get('bbox'));
        } catch (error) {
          sendJson(400, { error: error.message });
          return;
        }
        if (index === null) {
          sendJson(503, { error: 'County data is not loaded. Ask the operator to import parcel geometry and property records; see README.' });
          return;
        }
        sendJson(200, queryParcels(index, bounds));
        return;
      }
      const file = files.get(url.pathname);
      if (!file) {
        sendJson(404, { error: 'Not found.' });
        return;
      }
      const content = await readFile(resolve(root, file[0]));
      response.writeHead(200, { 'Content-Type': file[1] });
      response.end(request.method === 'HEAD' ? undefined : content);
    } catch {
      sendJson(500, { error: 'Unable to serve the request.' });
    }
  });
}

async function main() {
  const dataPath = process.env.DATA_FILE || resolve(root, 'data/parcels.geojson');
  let index = null;
  try {
    index = indexParcels(JSON.parse(await readFile(dataPath, 'utf8')));
    console.log(`Loaded ${index.length} parcels.`);
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
    console.warn('No parcel dataset found. Import county data before browsing homes (see README).');
  }
  const port = Number(process.env.PORT || 3000);
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('PORT must be between 1 and 65535.');
  createApp(index).listen(port, process.env.HOST || '127.0.0.1', () => {
    console.log(`Home Explorer listening on port ${port}. Use HTTPS when accessing from a phone.`);
  });
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main().catch(error => {
    console.error(error.message);
    process.exitCode = 1;
  });
}
