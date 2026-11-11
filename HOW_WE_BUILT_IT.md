# Project 002: How We Built the Property Tax Website

This guide walks through how the Project 002 website was built, one step at a time.
The goal of the project is a phone app that shows property taxes for homes near you in
St. Lucie County, Florida. Before building the app, we built a **website** that does the
same job, so we could work out the data and the math first.

Each step explains what we did and why, then shows some real code from the project with
comments. You don't need to understand every line. Read the comments, look at the code
next to them, and try to follow the idea.

---

## Contents

1. [The big picture](#1-the-big-picture)
2. [Step 1: Get the data and organize the folder](#step-1-get-the-data-and-organize-the-folder)
3. [Step 2: Turn spreadsheets into a database](#step-2-turn-spreadsheets-into-a-database)
4. [Step 3: Sort properties into categories](#step-3-sort-properties-into-categories)
5. [Step 4: Figure out the property taxes](#step-4-figure-out-the-property-taxes)
6. [Step 5: Build a web server](#step-5-build-a-web-server)
7. [Step 6: Build the web page](#step-6-build-the-web-page)
8. [Step 7: Put the properties on a map](#step-7-put-the-properties-on-a-map)
9. [Step 8: Draw the lot](#step-8-draw-the-lot)
10. [Bugs we found and fixed](#bugs-we-found-and-fixed)
11. [How to run it yourself](#how-to-run-it-yourself)
12. [Ideas for what to build next](#ideas-for-what-to-build-next)
13. [Glossary](#glossary)

---

## 1. The big picture

The website has three main parts. Data flows through them from left to right:

```
 County data files            Database               Web server              Web page
 (CSV spreadsheets,   ──►   property.db     ──►     server.py      ──►    index.html
  map shape files)          (SQLite)                (Python)               app.js, map.js
                                                                           (JavaScript)
   build_db.py reads the files      the server answers questions     the page asks questions
   and builds the database once     like "show homes with a pool"    and shows the answers
```

| File | Language | What it does |
|---|---|---|
| `website/build_db.py` | Python | Reads the county files and builds one database |
| `website/geo.py` | Python | Reads map shape files and converts their coordinates to latitude and longitude |
| `website/tax_rates.csv` | CSV | The tax rates (millage) for each part of the county |
| `website/server.py` | Python | A small web server that answers searches from the page |
| `website/static/index.html` | HTML | The layout of the page: search box, filters, table, tabs |
| `website/static/app.js` | JavaScript | Makes the page work: loads results, opens property details |
| `website/static/map.js` | JavaScript | Draws the maps and the lot drawings |
| `website/static/style.css` | CSS | Colors, fonts and layout, including the phone layout |

**Why these tools?** The computer we built on had Python installed but not Node.js, so we
used only what comes with Python. That means anyone with Python can run it with nothing
extra to install.

---

## Step 1: Get the data and organize the folder

The St. Lucie County Property Appraiser publishes its property records as **CSV files**.
A CSV file is a spreadsheet saved as plain text: one row per line, with commas between
the columns. Here's what the start of one looks like:

```
"PropertyID","ParcelID","SiteAddress","LandUse","LandUseDescription",...
"1","1101-111-0001-000-1","TBD","6600","ORCHRD GRV",...
```

(That first property is an orange grove, land use code `6600`, with no street address yet.)

We put the CSV files in a folder named `PASLC` (Property Appraiser, St. Lucie County).
There are 11 files, and they all share one column: **`PropertyID`**. That ID is how
we connect the owner file to the value file to the building file, and so on.

### Keeping big files out of GitHub

The data files are huge (hundreds of megabytes), so we don't store them in GitHub. The
`.gitignore` file tells Git which files to skip:

```gitignore
# Skip everything in the PASLC folder...
PASLC/*
# ...except Read.me, which explains where to download the data.
# The "!" means "but DO keep this one".
!PASLC/Read.me

# The database we build from the data. Anyone can rebuild it, so don't upload it.
website/data/

# The county map files. Also big, also downloadable.
StLucieParcelShapefile/*
StLucieGIS_Summary.gdb/*

# Python makes these cache files automatically. They aren't our code.
__pycache__/
```

**Lesson:** Put your *code* in Git, not your *data*. Write down where the data came from
so other people can download it too.

---

## Step 2: Turn spreadsheets into a database

Searching 11 separate spreadsheets every time someone clicks a filter would be very
slow. There are almost **195,000 properties** in the county! So we load everything into
a **database** once. A database is built for fast searching.

We used **SQLite**, a database that lives in a single file (`property.db`). It comes
with Python.

### Reading a CSV file into a table

Here's a simplified version of the `load_raw` function from `build_db.py`:

```python
import csv
import sqlite3

def load_raw(con, table, filename, cols):
    """Copy the columns we care about from one CSV file into a database table."""

    # Start fresh: delete the table if it's left over from last time.
    con.execute(f"DROP TABLE IF EXISTS {table}")

    # Make a table with one TEXT column for each CSV column we want.
    # For cols = ["PropertyID", "Owner"] this builds:
    #   CREATE TABLE raw_owner (PropertyID TEXT, Owner TEXT)
    con.execute(f"CREATE TABLE {table} ({', '.join(c + ' TEXT' for c in cols)})")

    # "?" marks are placeholders. The database fills them in safely later.
    # For 2 columns this makes the text "?,?"
    placeholders = ",".join("?" * len(cols))

    with open(filename, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)   # reads each row as a dictionary: {"PropertyID": "329", ...}
        batch = []
        for row in reader:
            # Keep only the columns we want, with extra spaces trimmed off.
            batch.append(tuple((row.get(c) or "").strip() for c in cols))

            # Saving 50,000 rows at a time is much faster than saving them one by one.
            if len(batch) >= 50000:
                con.executemany(f"INSERT INTO {table} VALUES ({placeholders})", batch)
                batch.clear()
        # Save whatever rows are left over at the end.
        con.executemany(f"INSERT INTO {table} VALUES ({placeholders})", batch)

    # An index works like the index in the back of a textbook: it lets the database
    # jump straight to a PropertyID instead of reading every row to find it.
    con.execute(f"CREATE INDEX ix_{table}_pid ON {table}(PropertyID)")
```

### Joining the tables together

After loading, we combine all the tables into one big `property` table with one row per
property. The database language is **SQL**. A `JOIN` lines up rows from two tables that
have the same `PropertyID`. Here's a shortened version:

```sql
-- Make a new table called "property" from the results of this question.
CREATE TABLE property AS
SELECT
  i.PropertyID                          AS property_id,  -- "AS" renames a column
  i.SiteAddress                         AS address,
  trim(o.OwnerFirstName || ' ' || o.OwnerLastName) AS owner,  -- || glues text together
  CAST(a.TotalAppraisedValue AS INTEGER) AS just_value,  -- turn the text "250000" into the number 250000
  CAST(a.TotalTaxableValue  AS INTEGER) AS taxable_value
FROM raw_ident i                                       -- "i" is a short nickname for raw_ident
LEFT JOIN raw_owner  o ON o.PropertyID = i.PropertyID  -- match owners by PropertyID
LEFT JOIN raw_assess a ON a.PropertyID = i.PropertyID; -- match values by PropertyID
```

A `LEFT JOIN` keeps every property, even if it has no matching row in the other table
(for example, an empty lot has no building). Those missing values come out as `NULL`,
which means "no value".

**Lesson:** Do the slow work once, ahead of time, so the website can be fast for every visitor.

---

## Step 3: Sort properties into categories

The first thing we wanted was a filter for **Residential**, **Commercial** and the
other kinds of property. Every property has a 4-digit **land use code** set by the
Florida Department of Revenue. The first two digits tell you the category:

| First two digits | Category | Examples |
|---|---|---|
| 00–09 | Residential | single-family homes, condos, mobile homes |
| 10–39 | Commercial | stores, offices, restaurants, hotels |
| 40–49 | Industrial | factories, warehouses |
| 50–69 | Agricultural | groves, pasture, timber |
| 70–79 | Institutional | churches, private schools, hospitals |
| 80–89 | Government | public schools, parks, county buildings |
| 90–99 | Miscellaneous | rights-of-way, water, other |

Here's how we wrote that rule in SQL:

```sql
CASE
  -- substr(land_use, 1, 2) takes 2 characters starting at character 1: "0100" -> "01"
  -- CAST(... AS INTEGER) turns the text "01" into the number 1, so we can compare numbers.
  WHEN CAST(substr(land_use,1,2) AS INTEGER) BETWEEN 0  AND 9  THEN 'Residential'
  WHEN CAST(substr(land_use,1,2) AS INTEGER) BETWEEN 10 AND 39 THEN 'Commercial'
  WHEN CAST(substr(land_use,1,2) AS INTEGER) BETWEEN 40 AND 49 THEN 'Industrial'
  WHEN CAST(substr(land_use,1,2) AS INTEGER) BETWEEN 50 AND 69 THEN 'Agricultural'
  WHEN CAST(substr(land_use,1,2) AS INTEGER) BETWEEN 70 AND 79 THEN 'Institutional'
  WHEN CAST(substr(land_use,1,2) AS INTEGER) BETWEEN 80 AND 89 THEN 'Government'
  ELSE 'Miscellaneous'   -- anything else lands here
END
```

The same rule in Python would look like this, which may be easier to read:

```python
def category(land_use):
    """Turn a land use code like "0100" into a category name."""
    first_two = int(land_use[:2])   # "0100"[:2] is "01", and int("01") is 1
    if first_two <= 9:
        return "Residential"
    elif first_two <= 39:
        return "Commercial"
    elif first_two <= 49:
        return "Industrial"
    elif first_two <= 69:
        return "Agricultural"
    elif first_two <= 79:
        return "Institutional"
    elif first_two <= 89:
        return "Government"
    else:
        return "Miscellaneous"

print(category("0100"))  # Residential
print(category("1100"))  # Commercial
```

We also looked through the data for other useful filters: city, ZIP code, value, year
built, square feet, bedrooms, bathrooms, pool, homestead, last sale price and date, and
whether the owner lives outside Florida.

---

## Step 4: Figure out the property taxes

This was the trickiest part. The county data has each property's **values**, but not its
**tax bill**, so we had to calculate the bill ourselves.

### The words you need

- **Just value**: what the county thinks the property would sell for.
- **Assessed value**: the value used for taxes. For homes with a homestead, Florida
  law limits how much this can go up each year, so it's often lower than just value.
- **Exemptions**: amounts taken off before taxes are figured. The biggest one is the
  **homestead exemption** for people who live in their own home.
- **Taxable value** = assessed value − exemptions.
- **Millage rate**: the tax rate. **1 mill = $1 of tax for every $1,000 of taxable value.**

So the basic formula is:

```
tax = taxable value × millage ÷ 1,000
```

### Many taxing authorities

Your tax bill isn't from just one place. The school board, the county, your city, the
hospital district and others each charge their own millage. Which ones you pay depends
on where the property is. The county calls each area a **tax district**. We put all
the rates in `website/tax_rates.csv`. Here's a small piece of it:

```
levy_code,authority,school,rate,district_groups
GF01,County General Fund,0,4.1985,0001 0002 0050 0009 0011 0022 0041
SR08,School (RLE),1,3.0480,0001 0002 0050 0009 0011 0022 0041
PS25,City of Port Saint Lucie,0,4.6607,0011 0041
```

Each line is one tax. `school` is `1` for school taxes and `0` for everything else. The
last column lists the tax districts that pay it. The County General Fund is charged
everywhere, but the City of Port St. Lucie tax is only charged in districts 0011 and
0041, which are inside the city.

### The school tax twist

School taxes follow slightly different rules. Only the **first $25,000** of the
homestead exemption counts for schools, so a home's **school taxable value** is a bit
higher than its regular taxable value. That's why we calculate two parts and add them.

### A worked example

Here's a real home from the data, in tax district 0002:

| | Taxable value | Millage | Tax |
|---|---|---|---|
| School levies | $127,575 | 6.2960 | $803.21 |
| County, city and other levies | $101,164 | 12.8521 | $1,300.17 |
| **Ad valorem tax** (based on value) | | | **$2,103.38** |
| Flat fees (trash pickup, water drainage and so on) | | | $559.92 |
| **Estimated total** | | | **$2,663.30** |

Here's the same math as a small Python program you can run and change:

```python
def estimate_tax(school_taxable, other_taxable, school_mills, other_mills, flat_fees):
    """Estimate a property tax bill.

    Taxes based on value ("ad valorem") use: value x mills / 1000.
    Flat fees (like trash pickup) are added on at the end.
    """
    school_tax = school_taxable * school_mills / 1000
    other_tax = other_taxable * other_mills / 1000
    ad_valorem = school_tax + other_tax
    total = ad_valorem + flat_fees
    return round(total, 2)   # round to the nearest cent


# The worked example from the table above:
print(estimate_tax(
    school_taxable=127_575,   # Python lets you write 127_575 to mean 127575; easier to read
    other_taxable=101_164,
    school_mills=6.296,
    other_mills=12.8521,
    flat_fees=559.92,
))   # prints 2663.3
```

**Try it:** What happens to the tax if the home's taxable value goes up by $10,000?
What if the county raises its millage by 1 mill?

> **Note:** This example uses the 2025 rates. The website now uses the official
> 2026 final rates. These are still *estimates*: the real bill comes from the Tax Collector.

---

## Step 5: Build a web server

A **web server** is a program that waits for a browser to ask for something, then sends
back an answer. Our server does two jobs:

1. Sends the page files (`index.html`, `app.js`, `style.css`) to the browser.
2. Answers data questions at addresses that start with `/api/`, like this one:

```
/api/properties?category=Residential&pool=1&sort=est_tax
```

That address asks: *"Give me Residential properties that have a pool, sorted by
estimated tax."* The server answers in **JSON**, a text format that JavaScript can read
easily:

```json
{
  "total": 1234,
  "rows": [
    { "property_id": 329, "address": "...", "est_tax": 2663.30 }
  ]
}
```

### Turning filters into a database question

Here's a simplified version of `build_where` from `server.py`. It turns the filters
from the address into the `WHERE` part of a SQL question:

```python
# Each filter name from the web address, matched to a piece of SQL.
# The "?" is a placeholder for the number the user typed in.
RANGE_FILTERS = {
    "just_min": "just_value >= ?",     # value at least ...
    "just_max": "just_value <= ?",     # value at most ...
    "year_min": "year_built >= ?",     # built in or after ...
    "beds_min": "bedrooms >= ?",       # at least this many bedrooms
}

def build_where(q):
    """q is a dictionary of filters from the web address, e.g. {"beds_min": "3"}."""
    clauses = []   # pieces of SQL, like "bedrooms >= ?"
    args = []      # the values that go into the "?" spots, like 3.0

    for param, sql_piece in RANGE_FILTERS.items():
        value = q.get(param, "").strip()
        if value:                           # only use filters the user actually filled in
            clauses.append(sql_piece)
            args.append(float(value))       # float() raises an error if it isn't a number

    if not clauses:
        return "", []                       # no filters: return every property
    # Join the pieces with AND, so ALL the conditions have to be true.
    return " WHERE " + " AND ".join(clauses), args


# Example:
where, args = build_where({"beds_min": "3", "year_min": "2010"})
print(where)   #  WHERE year_built >= ? AND bedrooms >= ?
print(args)    # [2010.0, 3.0]
```

### Why we use `?` instead of pasting in what the user typed

We **never** paste what the user typed straight into SQL. Suppose someone typed this into
the search box:

```
'; DROP TABLE property; --
```

If we pasted that into the SQL, the database might run it as a command and delete the
table! This trick is called **SQL injection**, and it's one of the most common ways
websites get hacked. With `?` placeholders, the database always treats what the user
typed as plain *data*, never as a *command*.

### Finding "homes near me"

To find properties near a spot, we need the distance in miles between two
latitude/longitude points. Over a few miles the Earth is almost flat, so a
shortcut works well:

```python
import math

MILES_PER_DEG_LAT = 69.0   # one degree of latitude is about 69 miles anywhere on Earth

def miles_between(lat1, lon1, lat2, lon2):
    """Approximate distance in miles. Good enough for a few miles."""
    # Lines of longitude get closer together as you go toward the poles,
    # so one degree of longitude is shorter. cos() handles that.
    miles_per_deg_lon = MILES_PER_DEG_LAT * math.cos(math.radians(lat1))

    dy = (lat2 - lat1) * MILES_PER_DEG_LAT   # north-south distance in miles
    dx = (lon2 - lon1) * miles_per_deg_lon   # east-west distance in miles
    return math.sqrt(dx * dx + dy * dy)      # the Pythagorean theorem: a² + b² = c²

# Fort Pierce to Port St. Lucie, roughly:
print(round(miles_between(27.4467, -80.3256, 27.2730, -80.3582), 1))  # about 12.1 miles
```

You probably learned the Pythagorean theorem in math class. Here it's being used to
find homes on a map!

---

## Step 6: Build the web page

The page is built from three languages that work together:

- **HTML**: what's on the page (boxes, buttons, the table).
- **CSS**: how it looks (colors, sizes, the phone layout).
- **JavaScript**: what it does (loads data and reacts to clicks).

### Asking the server for data

When you change a filter, `app.js` asks the server for new results and redraws the table.
Here's a simplified version of the `load` function:

```javascript
// "async" means this function can wait for slow things (like the network)
// without freezing the page.
async function load() {
  // Turn the current filters into the ?a=1&b=2 part of a web address.
  const params = new URLSearchParams({ ...state.filters, page: state.page, sort: state.sort });

  try {
    // fetch() asks the server for data. "await" pauses here until the answer arrives.
    const res = await fetch("/api/properties?" + params);
    if (!res.ok) throw new Error(res.statusText);   // the server reported a problem
    const data = await res.json();                  // turn the JSON text into a JavaScript object

    renderSummary(data);     // update the totals at the top
    renderRows(data.rows);   // redraw the table
  } catch (e) {
    // If anything went wrong, show a message instead of a broken page.
    document.querySelector("#table tbody").innerHTML =
      `<tr><td class="empty">Could not load results (${e.message}).</td></tr>`;
  }
}
```

### Drawing the table rows

`renderRows` turns each property into one row of an HTML table:

```javascript
function renderRows(rows) {
  const tbody = document.querySelector("#table tbody");

  if (!rows.length) {   // no results: say so
    tbody.innerHTML = `<tr><td class="empty">No properties match these filters.</td></tr>`;
    return;
  }

  // rows.map(...) makes one string of HTML for each property.
  // .join("") glues all those strings into one big string.
  tbody.innerHTML = rows.map((r) => `
    <tr data-id="${r.property_id}">
      <td>${r.address || "(no address)"}</td>
      <td class="num">${money(r.assessed_value)}</td>
      <td class="num">${money(r.est_tax)}</td>
    </tr>`).join("");
}
```

The `${...}` inside the backtick quotes is a **template literal**: JavaScript replaces
it with the value inside. For example, `` `Hi ${name}` `` with `name = "Sam"` becomes
`Hi Sam`.

### Making it work on a phone

Since this is going to become a phone app, the page has to fit on a small screen. CSS
**media queries** change the layout when the screen is narrow:

```css
/* On wide screens: the filters are on the left (290px wide), and the results fill the rest. */
.layout {
  display: grid;
  grid-template-columns: 290px minmax(0, 1fr);
}

/* When the screen is 860px wide or less (phones and small tablets)... */
@media (max-width: 860px) {
  .layout { grid-template-columns: minmax(0, 1fr); }   /* ...stack everything in one column */
  .hide-sm { display: none; }               /* ...and hide the less important columns */
}
```

---

## Step 7: Put the properties on a map

Next we added two map folders from the county's **GIS** (Geographic Information System)
department:

- `StLucieParcelShapefile`: the outline of every piece of land (a **parcel**).
- `StLucieGIS_Summary.gdb`: more map layers, including outlines for condo buildings.

The GIS account number is the same as the `PropertyID` in the CSV files, so we can
match every outline to its property.

### Problem: the map uses feet, not latitude and longitude

The county's map files don't use latitude and longitude. They use a system called
**Florida State Plane East**, which measures position in **feet** from a starting point
southwest of Florida. A point might be at `x = 862,000 ft, y = 1,090,000 ft`.

Web maps need latitude and longitude, so `geo.py` converts between them. The full
formula is long because the Earth is round, not flat, but the idea is simple:

```python
# Feet east and north on a flat grid  ──►  degrees on a round Earth
lat, lon = stateplane_to_latlon(862000, 1090000)
print(lat, lon)   # about 27.331, -80.366  (in St. Lucie County, between Fort Pierce and Port St. Lucie)
```

We checked the conversion by drawing the outlines over satellite photos. If the math were
wrong, the outlines would be shifted off the houses. They lined up.

### Reading a file format by hand

There's no free Python library for reading the `.gdb` (Esri File Geodatabase) format
without installing extra software. So we wrote our own reader in `geo.py`, using
the published description of the format. Computers store numbers as **bytes**, and to
save space, this format stores each corner of a shape as the *difference* from the
previous corner instead of the full position:

```python
# Each point is saved as "how far from the last point" (dx, dy),
# because small numbers take fewer bytes than big ones.
x, y = 0, 0
ring = []
for step_x, step_y in [(1000, 2000), (50, 0), (0, 30), (-50, 0)]:
    x += step_x          # add the step to get the real position
    y += step_y
    ring.append((x, y))
print(ring)   # [(1000, 2000), (1050, 2000), (1050, 2030), (1000, 2030)]
```

### Drawing on the map with Leaflet

For the map itself we used **Leaflet**, a free JavaScript map library. Drawing a
parcel outline takes just a few lines:

```javascript
// Make a map inside the <div id="map"> element.
const map = L.map("map");

// Add the background: map pictures ("tiles") from OpenStreetMap.
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: "© OpenStreetMap contributors",   // give credit to the map makers
}).addTo(map);

// Draw the parcel outline in yellow. Leaflet wants [latitude, longitude] pairs.
const outline = L.polygon(
  [[27.3001, -80.3502], [27.3001, -80.3495], [27.2997, -80.3495], [27.2997, -80.3502]],
  { color: "#facc15", weight: 3 }
).addTo(map);

// Zoom the map so the outline fills the view.
map.fitBounds(outline.getBounds());
```

Each category gets its own color on the results map. Residential is blue, Commercial is
orange, Agricultural is green, and so on. When you zoom out too far, the map shows dots
instead of outlines so it doesn't have to draw 195,000 shapes at once.

---

## Step 8: Draw the lot

The last feature is a **lot drawing**: a simple diagram of the property's outline,
labeled with how long each side is in feet, plus a north arrow and a scale bar. You can
download it as a picture.

### How long is each side?

Each side runs between two corners. The length comes from the Pythagorean theorem
again, after turning degrees into feet:

```javascript
const FEET_PER_DEG_LAT = 364320;   // 69 miles × 5,280 feet per mile

function sideLengthFeet(lat1, lon1, lat2, lon2) {
  const feetPerDegLon = FEET_PER_DEG_LAT * Math.cos(lat1 * Math.PI / 180);
  const dx = (lon2 - lon1) * feetPerDegLon;   // east-west, in feet
  const dy = (lat2 - lat1) * FEET_PER_DEG_LAT; // north-south, in feet
  return Math.sqrt(dx * dx + dy * dy);
}
```

### How big is the lot? The shoelace formula

To find the area of any shape made of straight sides (a **polygon**), you can use the
**shoelace formula**. It gets its name from the way the multiplications criss-cross
like shoelaces. This is the actual `ringArea` function from `map.js`, with comments added:

```javascript
// pts is a list of corners: [[x0, y0], [x1, y1], ...] going around the shape.
function ringArea(pts) {
  let a = 0;
  for (let i = 0; i < pts.length; i++) {
    const [x0, y0] = pts[i];                     // this corner
    const [x1, y1] = pts[(i + 1) % pts.length];  // the next corner. "%" wraps the last corner back to the first
    a += x0 * y1 - x1 * y0;                      // the criss-cross multiplication
  }
  return a / 2;   // half the total is the area (it comes out negative if the corners go clockwise)
}

// Try it on a 225 ft by 125 ft rectangle:
console.log(ringArea([[0, 0], [225, 0], [225, 125], [0, 125]]));   // 28125 square feet
// 28,125 ÷ 43,560 square feet per acre = 0.646 acres
```

We checked that answer against the property's deed, which says **0.646 acres**. They match.

**Try it:** Check the shoelace formula on a triangle with corners `(0,0)`, `(4,0)` and
`(0,3)`. Does it match ½ × base × height?

---

## Bugs we found and fixed

Every real project has bugs. Here are some we ran into and what they taught us.

### 1. The Costco in the ocean

**What happened:** On the map, a Costco store showed up in the Gulf of Mexico, more
than 100 miles from St. Lucie County.

**Why:** In the map file, the store's center point was saved as `x = 0, y = 0`.
Converted to latitude and longitude, "zero feet" is the starting point of the grid,
which is far off to the southwest.

**Fix:** We only trust a center point if it falls *inside* the property's own outline.
If it doesn't, we calculate the center from the outline ourselves.

```python
# Only trust the saved center point if it's inside the shape's bounding box.
if not (min_x <= point_x <= max_x and min_y <= point_y <= max_y):
    point = None   # throw it away and calculate our own center instead
```

**Lesson:** Data can be wrong. Check that values make sense before you use them.

### 2. Checking our math against an official notice

**What happened:** We compared our estimate for one home with its official **TRIM
notice**, the "proposed taxes" letter the Property Appraiser mails every August. The
county taxes matched, but the city and school taxes were too low.

**Why:** The notice showed that taxes aren't all charged on the same value. That home
has a **senior exemption**, and the senior exemption only lowers *county* taxes. We
had been taking it off *every* tax.

**Fix:** Each tax in `tax_rates.csv` now has a `basis` column: `county`, `school` or
`other`. Each basis uses its own taxable value. After the fix, and after updating to the
2026 rates, every line on the notice matched ours **to the penny**.

**Lesson:** Find an official answer to compare with. Our math looked right until we
checked it against a real notice.

### 3. Duplicate IDs

**What happened:** Building the database crashed with `UNIQUE constraint failed`.

**Why:** We told the database that each `property_id` appears only once, but a few
properties had **two** rows in one of the CSV files, so they appeared twice.

**Fix:** Combine the duplicate rows into one before joining.

**Lesson:** Don't assume the data follows the rules. Let the database check them
for you.

### 4. 10,370 houses on "0 TBD" street

**What happened:** Over ten thousand properties had the address `0  TBD` ("to be
determined"). These are mostly empty lots with no street number yet.

**Fix:** We show them as "(no address)" instead of a fake-looking address.

### 5. Too wide for a phone

**What happened:** On a phone screen, the page was wider than the screen and you had to
scroll sideways.

**Fix:** One CSS change, from `1fr` to `minmax(0, 1fr)`, which lets the results column
shrink to fit.

**Lesson:** Test on the screen size people will actually use.

---

## How to run it yourself

You need **Python 3** and the county data files (see `PASLC/Read.me` for where to
download them).

```bash
# 1. Build the database (this takes a few minutes and only needs to run once)
python website/build_db.py

# 2. Start the web server
python website/server.py

# 3. Open this address in your web browser:
#    http://localhost:8000
```

To stop the server, click in the terminal window and press **Ctrl + C**.

---

## Ideas for what to build next

Here are some things the class could work on, roughly from easiest to hardest:

1. **Change the colors.** Pick new category colors in `CATEGORY_COLORS` in `map.js`.
2. **Add a filter.** For example, "built before 1980" or "lots bigger than 1 acre".
   Look at `RANGE_FILTERS` in `server.py` and the sidebar in `index.html`.
3. **Make a fun stat.** What is the oldest house in the county? Which street has the
   most pools? Write a SQL query to find out.
4. **Update the tax rates.** When the 2026 rates come out, update `tax_rates.csv`
   and rebuild.
5. **Check our math.** Compare our estimate with a real tax bill from the Tax Collector's
   website. How close are we?
6. **Design the phone app.** Sketch the screens on paper first. What should someone
   see when they open the app? Then read the [phone app plan](docs/phone-app/README.md).

---

## Glossary

| Word | Meaning |
|---|---|
| **API** | A set of web addresses a program can call to get data (here, the ones starting with `/api/`). |
| **Assessed value** | The value used for taxes, which can be capped below the just value. |
| **CSV** | "Comma-separated values": a spreadsheet saved as plain text. |
| **Database** | A program that stores data so it can be searched quickly. |
| **Exemption** | An amount subtracted from a property's value before taxes are calculated. |
| **GIS** | Geographic Information System: software and data for maps. |
| **Homestead** | A home the owner lives in full-time; in Florida it gets tax breaks. |
| **Index** | A lookup list that helps a database find rows fast, like the index in a book. |
| **JSON** | A text format for sending data between programs. |
| **Just value** | The county's estimate of what a property would sell for. |
| **Latitude / longitude** | Position on Earth in degrees north/south and east/west. |
| **Mill / millage** | Tax rate: 1 mill = $1 per $1,000 of taxable value. |
| **Parcel** | One piece of land with its own ID. |
| **Polygon** | A shape made of straight sides, like a lot outline. |
| **Query** | A question asked of a database, written in SQL. |
| **Server** | A program that answers requests from web browsers. |
| **SQL** | "Structured Query Language": the language for asking databases questions. |
| **SQL injection** | An attack that sneaks commands into a database through a form; stopped by `?` placeholders. |
| **Taxable value** | Assessed value minus exemptions. This is the value that gets taxed. |
