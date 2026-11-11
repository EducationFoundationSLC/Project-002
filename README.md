# Project-002
Project 002 - using publicly available data to view homes in Port Saint Lucie Florida on your phone and reporting on the web.
PASLC data files are located here: https://www.paslc.gov/231/Data-Requests


## Learning guide

New to the project? [HOW_WE_BUILT_IT.md](HOW_WE_BUILT_IT.md) walks through how the website was built, step by step, with commented code examples.

Planning the phone app? Start with [docs/phone-app/README.md](docs/phone-app/README.md), then see the [Android / Google Play](docs/phone-app/android.md) and [iPhone / App Store](docs/phone-app/iphone.md) guides.

## Property browser website

A local website that lists every parcel in Saint Lucie County with filters.

1. Download the CSV files into the `PASLC` folder (see `PASLC/Read.me`). For maps,
   also add the county GIS exports `StLucieParcelShapefile/` and
   `StLucieGIS_Summary.gdb/` (optional; without them the site works but has no maps).
2. Build the database (about 2 minutes; re-run whenever the CSVs are refreshed):

   ```
   python website/build_db.py
   ```

3. Start the website: double-click **`start-website.cmd`** in the project folder. It
   stops any copy that's already running, swaps in a newly built database if one is
   waiting, finds your Anthropic API key for Ask AI (or asks for it once and can save
   it), starts the server, and opens http://localhost:8000. Press Ctrl+C in its window
   (or close the window) to stop the website.

   Or start it by hand:

   ```
   python website/server.py
   ```

Only the Python 3 standard library is required, plus the `anthropic` package for Ask AI. The generated database
(`website/data/property.db`) is not committed.

### Filters

- **Property type** – Residential, Commercial, Industrial, Agricultural, Institutional,
  Government, Miscellaneous (grouped by Florida DOR land-use code), each expandable
  into its specific land uses (Single Family, Condo, Office Building, ...)
- **Location** – jurisdiction (Port Saint Lucie, Fort Pierce, Saint Lucie Village,
  unincorporated county) and ZIP code
- **Value & tax** – just (market), assessed and taxable value, estimated annual tax,
  any exemption, homestead exemption
- **Exemption type** – Homestead, Senior (65+), Disabled veteran, Widow or widower,
  Disability, Surviving spouse, Religious / charitable / education, Government & public,
  Other. The groups of county exemption codes are set in `EXEMPTION_GROUPS` in
  `build_db.py`.
- **Building** – vacant vs. improved, year built, living area, bedrooms, baths,
  lot size, pool
- **Sales & ownership** – last sale date and price, out-of-state owner, and **mailing
  address**: same as property, different address, PO box, or either of the last two. The
  mailing address comes from `RealPropertyGeneralMailingInformation.csv`. `build_db.py`
  compares it with the property address using the house number, street name, unit and
  ZIP, so spelling differences ("Terr"/"Ter", "St"/"Saint", "N A1A"/"N Highway A1A")
  still count as the same address. Addresses without a house number count as unknown. A
  different mailing address is a reason for a closer look at a homestead property, not
  proof that the owner doesn't live there.
- Free-text search on address, owner, parcel ID, or subdivision

Click a row to see full values, exemptions, non-ad valorem charges, building
details, owner, sales history, and legal description. The filtered view is kept
in the URL, so it can be bookmarked or shared.

### Tax estimates

The CSVs contain values and exemptions but not tax rates. `website/tax_rates.csv`
holds the millage for each levy and the tax district groups it applies to, taken from
the Property Appraiser's "2026 Final Millage Rates" table (paslc.gov, Millage / Tax Rates
page). Each parcel's estimate is its taxable value times its district's millage, plus
non-ad valorem assessments. The `basis` column says which taxable value each levy uses,
matching the TRIM notice:

- `county`: the roll's taxable value, after all exemptions.
- `other` (cities and independent districts): adds back the senior exemption, which
  only applies to county levies.
- `school`: only the first $25,000 homestead exemption applies, and the 10%
  non-homestead assessment cap doesn't.

Each levy is rounded to the cent before the levies are added together, as on the TRIM
notice. A 2026 TRIM notice for a homestead property with a senior exemption in district
0011 matches line for line, down to the cent ($4,322.19 ad valorem). Each property also
links to its official TRIM notice from the Property Appraiser.

When new rates are adopted, edit `tax_rates.csv`, set `RATES_YEAR` in `build_db.py`,
and rebuild. The district totals in the rate table make a quick check that every rate
was entered.

Known gap: the City of Port St. Lucie solid waste fee (about $482 on a 2026 TRIM notice)
isn't in the Property Appraiser's CSV export, so it's missing from estimates for PSL
properties.

### Ask AI (chat about the data)

The **✨ Ask AI** button opens a chat box. Type a question in plain English, for example
"Show me properties with a senior exemption and a disabled veteran exemption." Claude,
Anthropic's AI, answers it from the database. When the question asks to see properties,
they appear in the table and map. Under each answer, "How I found this" shows the database
queries Claude ran.

The code is in `website/ask.py`. Claude can use two tools:

- `run_sql`: runs one read-only `SELECT` query. The connection is read-only, an SQLite
  authorizer blocks everything except reading, and queries stop after 5 seconds.
- `show_on_website`: sets the website's filters. A query can also pick the properties,
  which works for things filters can't express, such as two exemptions that must both
  apply.

**Setup:**

1. Install the SDK: `pip install anthropic`
2. Get an API key at https://console.anthropic.com. An adult or the organization should
   own the account. Set a monthly spending limit there.
3. Set the key before starting the server (PowerShell):

   ```powershell
   $env:ANTHROPIC_API_KEY = "sk-ant-..."
   python website/server.py
   ```

   Never put the key in a file in this repository.

Without a key, the rest of the website works, and the chat box explains how to set one
up. These optional settings are environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `ASK_MODEL` | `claude-opus-5-5` | Claude model to use |
| `ASK_EFFORT` | `medium` | How hard Claude thinks: `low`, `medium` or `high` |
| `ASK_QUESTIONS_PER_HOUR` | `30` | Limit for each visitor |

Each question costs a few cents with the default model. A cheaper model such as
`claude-haiku-5-5` costs much less, so try it on your usual questions to see whether the
answers are still good. Before a public launch, review the hourly limit, the spending limit,
and whether answers should include owner names.

### Maps and lot drawings

`build_db.py` reads the parcel polygons from the shapefile and the condo-complex
outlines from the geodatabase (matched on GIS account number = CAMA PropertyID),
converts them from Florida State Plane East (US feet) to latitude/longitude, and
stores them with each property. `python website/build_db.py --geometry-only`
reloads just the shapes. This gives:

- a **Map** tab showing the filtered properties, colored by type (outlines when
  zoomed in, dots when zoomed out)
- **Near me**: uses your device location to list properties within a chosen
  distance, sorted nearest first. "Properties near here" in a property's panel
  does the same around that property
- in each property's panel, a satellite map with the parcel outlined and a lot
  drawing with edge dimensions in feet, downloadable as SVG or PNG

Base maps load from OpenStreetMap and Esri World Imagery, so maps need an
internet connection.
