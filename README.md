# Project-002
Project 002 - using publicly available data to view homes in Port Saint Lucie Florida on your phone

## Run

Requires Node.js 22 or newer.

```sh
npm ci
npm start
```

Open `http://localhost:3000`. The mobile-friendly web app provides a map, a **Use
my location** button, selectable parcel outlines, and address, owner, last
sale/purchase date, and sale price. Zoom to street level to load properties.
The list beside/below the map is an alternative to tapping a parcel.

For a phone deployment, serve this application through an **HTTPS** reverse proxy.
Browsers allow location only on HTTPS or localhost; visiting a development
computer's plain HTTP address from a phone will not enable location. Set
`HOST=0.0.0.0` only when network access is needed, and `PORT` to change port 3000.
Location denial does not prevent manual map browsing. Coordinates are not stored;
the server receives the visible map bounds, and OpenStreetMap receives tile requests.

## Load county property data

Request/download public parcel geometry and current property records from the
[Saint Lucie County Property Appraiser's data requests page](https://www.paslc.gov/231/Data-Requests).
Request parcel ID, site address, current owner, most recent sale date and sale price.
**No county records are bundled, and no unverified live API is used.** The county
site could not be reached from the implementation environment, so its current
download URLs, schemas, and usage terms have not been verified. Confirm reuse
terms and available fields with the county before publishing records.

1. Export county parcel geometry as a GeoJSON `FeatureCollection` in **WGS84
   (EPSG:4326), longitude then latitude**, using a GIS tool such as QGIS if the
   supplied data is a shapefile. Preserve parcel IDs as strings (including leading
   zeros and punctuation). Geometry must be Polygon or MultiPolygon.
2. Export the property records as UTF-8 CSV with a header and **one current row per
   parcel**. Join separate owner/address/sales tables by parcel ID beforehand if
   necessary, selecting the most recent sale. Include the five requested fields;
   blank values are supported. Dates are displayed as supplied. Prices must be
   non-negative numbers; dollar signs and thousands commas are accepted.
3. Create a field mapping JSON file specifying the actual headers. For example
   (these are illustrative names, **not verified county column names**):

   ```json
   {
     "geometryId": "PARCEL_ID",
     "recordId": "Parcel ID",
     "address": "Site Address",
     "owner": "Owner",
     "saleDate": "Last Sale Date",
     "salePrice": "Last Sale Price"
   }
   ```

4. Import and restart the server:

   ```sh
   npm run import-data -- /path/to/parcels.geojson /path/to/properties.csv /path/to/fields.json data/parcels.geojson
   npm start
   ```

The importer joins exact, trimmed IDs, validates data, rejects duplicate IDs,
and reports geometry records without matching details. Unmatched parcels remain
selectable with unavailable details; an import with no matches fails rather than
silently publishing empty records. Only parcel ID, address, owner, date and price
are retained from the property CSV. Treat the data files as public-record
datasets, not as a place for confidential information.

Alternatively, set `DATA_FILE` to an already normalized GeoJSON file whose feature
properties are `id` (required string), `address`, `owner`, `saleDate` (text or null),
and `salePrice` (number or null). The default file is `data/parcels.geojson`.
Missing data produces a visible setup message when the map is zoomed in; invalid
data stops server startup. Replace/reimport the dataset and restart to refresh
records. Imported datasets and dependencies are excluded from Git.

## Checks and limits

```sh
npm test
```

Tests use Node's built-in runner and synthetic records, not actual homeowner data.
They cover import/join behavior, missing values, validation, map bounds, result
limits, static assets, and API errors.

The server loads a local dataset in memory and returns at most 500 parcels per
view. Zoom in further when results are truncated. This is an initial web app,
not a native app or an offline map: internet access is required for OpenStreetMap
tiles. Respect the [OpenStreetMap tile usage policy](https://operations.osmfoundation.org/policies/tiles/);
use an appropriate tile provider for higher-traffic deployment. Public records
can be incomplete or delayed and are not a substitute for title research.
