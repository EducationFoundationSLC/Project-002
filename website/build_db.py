"""Build the SQLite database the website reads from.

Reads the Saint Lucie County Property Appraiser CSV exports in ../PASLC and
writes website/data/property.db. Re-run whenever the CSVs are refreshed:

    python website/build_db.py
    python website/build_db.py --geometry-only   # just reload parcel shapes

Parcel shapes come from the county GIS exports in ../StLucieParcelShapefile and
../StLucieGIS_Summary.gdb (condo outlines). Both are optional.
"""
import csv
import glob
import json
import os
import sqlite3
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_DIR = os.path.join(HERE, "..", "PASLC")
RATES_CSV = os.path.join(HERE, "tax_rates.csv")
RATES_YEAR = 2025  # year of the millage in tax_rates.csv (DOR "2025 Final Millage Rates")
FIRST_HOMESTEAD = 25000  # the only homestead exemption that applies to school levies
SENIOR_EXEMPTION = 25000  # St. Lucie County's senior exemption; county levies only

# Community Redevelopment Area district groups levy the same millage as their parent.
DISTRICT_GROUP_ALIAS = {
    "9011": "0011", "9111": "0011", "9211": "0011", "9341": "0011",
    "9022": "0022", "9122": "0022", "9222": "0022", "9322": "0022",
}
DB_PATH = os.path.join(HERE, "data", "property.db")
PARCEL_SHP = os.path.join(HERE, "..", "StLucieParcelShapefile", "StLucie_Parcel_Shapefile",
                          "StLucie_Parcel_Shapefile")
GDB_DIR = os.path.join(HERE, "..", "StLucieGIS_Summary.gdb")

sys.path.insert(0, HERE)
import geo  # noqa: E402

# Florida Department of Revenue land-use code ranges (first two digits).
CATEGORY_SQL = """
CASE
  WHEN CAST(substr(land_use,1,2) AS INTEGER) BETWEEN 0  AND 9  THEN 'Residential'
  WHEN CAST(substr(land_use,1,2) AS INTEGER) BETWEEN 10 AND 39 THEN 'Commercial'
  WHEN CAST(substr(land_use,1,2) AS INTEGER) BETWEEN 40 AND 49 THEN 'Industrial'
  WHEN CAST(substr(land_use,1,2) AS INTEGER) BETWEEN 50 AND 69 THEN 'Agricultural'
  WHEN CAST(substr(land_use,1,2) AS INTEGER) BETWEEN 70 AND 79 THEN 'Institutional'
  WHEN CAST(substr(land_use,1,2) AS INTEGER) BETWEEN 80 AND 89 THEN 'Government'
  ELSE 'Miscellaneous'
END
"""

# raw table name -> (csv file, columns to keep)
RAW = {
    "raw_ident": ("PropertyIdentification.csv", [
        "PropertyID", "ParcelID", "SiteAddress", "LandUse", "LandUseDescription",
        "Neighborhood", "SubdivisionName", "TotalArea"]),
    "raw_site": ("SiteLocation.csv", [
        "PropertyID", "LocationStartNumber", "StreetDirection", "StreetName",
        "StreetWay", "UnitNumber", "Jurisdiction", "LocationPostal"]),
    "raw_legal": ("LegalDescription.csv", ["PropertyID", "Zoning", "LegalDescription"]),
    "raw_owner": ("PropertyOwnership.csv", [
        "PropertyID", "OwnerFirstName", "OwnerLastName", "Owner2FirstName",
        "Owner2LastName", "Street1", "Street2", "City", "StateProvince",
        "PostalCodeFull", "Country"]),
    "raw_assess": ("Assessment.csv", [
        "PropertyID", "TotalAppraisedLandValue", "TotalAppraisedBuildingValue",
        "TotalAppraisedValue", "TotalAssessedValue", "TotalValueExemption",
        "TotalTaxableValue", "DistrictGroup", "TotalAgriculturalCredit"]),
    "raw_bldg": ("BuildingBasics.csv", [
        "PropertyID", "BuildingID", "BuildingSequence", "GrossArea", "FinishedArea",
        "YearBuilt", "BuildingTypeDescription"]),
    "raw_interior": ("BuildingInterior.csv", [
        "PropertyID", "BuildingSequence", "Bedrooms", "FullBath", "AdditionalFullBath",
        "ThreeQuarterBath", "HalfBath", "AdditionalHalfBath"]),
    "raw_exempt": ("Exemptions.csv", [
        "PropertyID", "Exemption", "ExemptionDescription", "GrantYear"]),
    "raw_other": ("OtherAssessments.csv", [
        "PropertyID", "FullDescription", "AssessmentAmount"]),
    "raw_sfyi": ("SFYI.csv", ["PropertyID", "SFYIShortDescription"]),
    "raw_sales": ("Transactions.csv", [
        "PropertyID", "SaleDate", "SalePrice", "NALCodeDescription",
        "DeedDescription", "Grantor"]),
}


def load_raw(con, table, filename, cols):
    path = os.path.join(CSV_DIR, filename)
    con.execute(f"DROP TABLE IF EXISTS {table}")
    con.execute(f"CREATE TABLE {table} ({', '.join(c + ' TEXT' for c in cols)})")
    placeholders = ",".join("?" * len(cols))
    with open(path, newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.DictReader(fh)
        batch = []
        n = 0
        for row in reader:
            batch.append(tuple((row.get(c) or "").strip() for c in cols))
            if len(batch) >= 50000:
                con.executemany(f"INSERT INTO {table} VALUES ({placeholders})", batch)
                n += len(batch)
                batch.clear()
        con.executemany(f"INSERT INTO {table} VALUES ({placeholders})", batch)
        n += len(batch)
    con.execute(f"CREATE INDEX ix_{table}_pid ON {table}(PropertyID)")
    print(f"  {filename:30s} {n:>9,} rows")


BUILD_SQL = f"""
DROP TABLE IF EXISTS property;
CREATE TABLE property AS
WITH bldg AS (
  SELECT PropertyID,
         COUNT(*)                                   AS buildings,
         MIN(NULLIF(CAST(YearBuilt AS INTEGER),0))   AS year_built,
         SUM(CAST(FinishedArea AS INTEGER))          AS living_area,
         MAX(CASE WHEN BuildingSequence='1' THEN BuildingTypeDescription END) AS building_type
  FROM raw_bldg GROUP BY PropertyID
),
interior AS (
  SELECT PropertyID,
         SUM(CAST(Bedrooms AS INTEGER)) AS bedrooms,
         SUM(CAST(FullBath AS INTEGER) + CAST(AdditionalFullBath AS INTEGER)
             + CAST(ThreeQuarterBath AS INTEGER)) AS full_baths,
         SUM(CAST(HalfBath AS INTEGER) + CAST(AdditionalHalfBath AS INTEGER)) AS half_baths
  FROM raw_interior GROUP BY PropertyID
),
other AS (
  SELECT PropertyID, SUM(CAST(AssessmentAmount AS REAL)) AS non_ad_valorem
  FROM raw_other GROUP BY PropertyID
),
exempt AS (
  SELECT PropertyID,
         MAX(ExemptionDescription LIKE 'Homestead%') AS homestead,
         GROUP_CONCAT(ExemptionDescription, '; ')     AS exemptions
  FROM raw_exempt GROUP BY PropertyID
),
pool AS (
  SELECT DISTINCT PropertyID FROM raw_sfyi
  WHERE SFYIShortDescription IN ('RES POOL AVG','RES POOL HI','COM POOL AVG','COM POOL HI')
),
sale AS (
  SELECT PropertyID, SaleDate, SalePrice FROM (
    SELECT PropertyID, substr(SaleDate,1,10) AS SaleDate, CAST(SalePrice AS REAL) AS SalePrice,
           ROW_NUMBER() OVER (PARTITION BY PropertyID ORDER BY SaleDate DESC) AS rn
    FROM raw_sales WHERE CAST(SalePrice AS REAL) > 100
  ) WHERE rn = 1
)
SELECT
  CAST(i.PropertyID AS INTEGER)                                   AS property_id,
  i.ParcelID                                                      AS parcel_id,
  CASE WHEN i.SiteAddress NOT IN ('', 'TBD') THEN i.SiteAddress
       WHEN s.StreetName NOT IN ('', 'TBD') THEN
            trim(s.LocationStartNumber || ' ' || s.StreetDirection || ' ' ||
                 s.StreetName || ' ' || s.StreetWay)
       END                                                        AS address,  -- NULL when unknown
  NULLIF(s.UnitNumber,'')                                         AS unit,
  s.Jurisdiction                                                  AS jurisdiction,
  NULLIF(s.LocationPostal,'')                                     AS zip,
  i.LandUse                                                       AS land_use,
  i.LandUseDescription                                            AS land_use_desc,
  {CATEGORY_SQL.replace('land_use', 'i.LandUse')}                 AS category,
  NULLIF(i.SubdivisionName,'')                                    AS subdivision,
  i.Neighborhood                                                  AS neighborhood,
  NULLIF(l.Zoning,'')                                             AS zoning,
  ROUND(CAST(i.TotalArea AS REAL) / 43560.0, 3)                   AS acres,
  trim(o.OwnerFirstName || ' ' || o.OwnerLastName)                AS owner,
  NULLIF(trim(o.Owner2FirstName || ' ' || o.Owner2LastName),'')   AS owner2,
  trim(o.Street1 || ' ' || o.Street2 || ', ' || o.City || ' ' ||
       o.StateProvince || ' ' || o.PostalCodeFull)                AS mailing_address,
  NULLIF(o.StateProvince,'')                                      AS owner_state,
  CASE WHEN o.StateProvince NOT IN ('', 'FL') THEN 1 ELSE 0 END   AS out_of_state_owner,
  b.buildings, b.year_built, b.living_area, b.building_type,
  n.bedrooms, n.full_baths, n.half_baths,
  CASE WHEN p.PropertyID IS NULL THEN 0 ELSE 1 END                AS pool,
  COALESCE(e.homestead, 0)                                        AS homestead,
  e.exemptions,
  CAST(a.TotalAppraisedLandValue AS INTEGER)                      AS land_value,
  CAST(a.TotalAppraisedBuildingValue AS INTEGER)                  AS building_value,
  CAST(a.TotalAppraisedValue AS INTEGER)                          AS just_value,
  CAST(a.TotalAssessedValue AS INTEGER)                           AS assessed_value,
  CAST(a.TotalValueExemption AS INTEGER)                          AS exemption_value,
  CAST(a.TotalTaxableValue AS INTEGER)                            AS taxable_value,
  NULLIF(a.DistrictGroup,'')                                      AS district_group,
  CAST(a.TotalAgriculturalCredit AS INTEGER)                      AS ag_credit,
  ROUND(COALESCE(ot.non_ad_valorem, 0), 2)                        AS non_ad_valorem,
  sa.SaleDate                                                     AS last_sale_date,
  sa.SalePrice                                                    AS last_sale_price
FROM raw_ident i
LEFT JOIN raw_site   s  ON s.PropertyID  = i.PropertyID
LEFT JOIN (SELECT PropertyID, MAX(Zoning) AS Zoning FROM raw_legal GROUP BY PropertyID)
                     l  ON l.PropertyID  = i.PropertyID
LEFT JOIN raw_owner  o  ON o.PropertyID  = i.PropertyID
LEFT JOIN raw_assess a  ON a.PropertyID  = i.PropertyID
LEFT JOIN bldg       b  ON b.PropertyID  = i.PropertyID
LEFT JOIN interior   n  ON n.PropertyID  = i.PropertyID
LEFT JOIN other      ot ON ot.PropertyID = i.PropertyID
LEFT JOIN exempt     e  ON e.PropertyID  = i.PropertyID
LEFT JOIN pool       p  ON p.PropertyID  = i.PropertyID
LEFT JOIN sale       sa ON sa.PropertyID = i.PropertyID;

CREATE UNIQUE INDEX ix_property_id ON property(property_id);
CREATE INDEX ix_property_cat      ON property(category, land_use_desc);
CREATE INDEX ix_property_juris    ON property(jurisdiction);
CREATE INDEX ix_property_zip      ON property(zip);
CREATE INDEX ix_property_just     ON property(just_value);
CREATE INDEX ix_property_taxable  ON property(taxable_value);
CREATE INDEX ix_property_year     ON property(year_built);
CREATE INDEX ix_property_sale     ON property(last_sale_date);
CREATE INDEX ix_property_parcel   ON property(parcel_id);

-- Detail tables for the property drawer.
DROP TABLE IF EXISTS sales;
CREATE TABLE sales AS
  SELECT CAST(PropertyID AS INTEGER) AS property_id, substr(SaleDate,1,10) AS sale_date,
         CAST(SalePrice AS REAL) AS price, NALCodeDescription AS qualification,
         DeedDescription AS deed, Grantor AS grantor
  FROM raw_sales;
CREATE INDEX ix_sales_pid ON sales(property_id);

DROP TABLE IF EXISTS exemptions;
CREATE TABLE exemptions AS
  SELECT CAST(PropertyID AS INTEGER) AS property_id, ExemptionDescription AS description,
         GrantYear AS grant_year FROM raw_exempt;
CREATE INDEX ix_exemptions_pid ON exemptions(property_id);

DROP TABLE IF EXISTS other_assessments;
CREATE TABLE other_assessments AS
  SELECT CAST(PropertyID AS INTEGER) AS property_id, FullDescription AS description,
         CAST(AssessmentAmount AS REAL) AS amount FROM raw_other;
CREATE INDEX ix_other_pid ON other_assessments(property_id);

DROP TABLE IF EXISTS legal;
CREATE TABLE legal AS
  SELECT DISTINCT CAST(PropertyID AS INTEGER) AS property_id, LegalDescription AS description
  FROM raw_legal;
CREATE INDEX ix_legal_pid ON legal(property_id);
"""


def add_tax_estimates(con):
    """Estimate each parcel's tax bill from tax_rates.csv.

    Each levy is charged on one of three taxable values (the "basis" column):
      county - the roll's taxable value (TotalTaxableValue), after every exemption.
      other  - city, fire, water management and other districts. The senior exemption
               is county-only, so these levies add it back.
      school - only the first $25,000 homestead exemption applies, and the 10%
               non-homestead assessment cap does not (school assessed value = just value).
    Checked against a 2026 TRIM notice: Column 1 (2025 rates) and the per-authority
    taxable values match.
    """
    con.executescript("""
        DROP TABLE IF EXISTS levies;
        CREATE TABLE levies (district_group TEXT, levy_code TEXT, authority TEXT,
                             basis TEXT, school INTEGER, rate REAL);
        DROP TABLE IF EXISTS meta;
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
    """)
    with open(RATES_CSV, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["basis"] not in ("county", "other", "school"):
                raise ValueError(f"{r['levy_code']}: basis must be county, other or school")
            for group in r["district_groups"].split():
                con.execute("INSERT INTO levies VALUES (?,?,?,?,?,?)",
                            (group, r["levy_code"], r["authority"], r["basis"],
                             int(r["basis"] == "school"), float(r["rate"])))
    con.execute("INSERT INTO meta VALUES ('rates_year', ?)", (str(RATES_YEAR),))

    # Size of the second (non-school) homestead exemption on this roll, e.g. 26,411.
    hx_total = con.execute("""
        SELECT exemption_value FROM property
        WHERE exemptions = 'Homestead Exemption; Homestead Exemption over $ 50,000'
        GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT 1""").fetchone()
    second_hx = (hx_total[0] - FIRST_HOMESTEAD) if hx_total else 25000
    con.execute("INSERT INTO meta VALUES ('second_homestead', ?)", (str(second_hx),))

    cases = " ".join(f"WHEN '{k}' THEN '{v}'" for k, v in DISTRICT_GROUP_ALIAS.items())
    # The second homestead exemption ($25,000-$50,000 band) doesn't apply to schools.
    additional_hx = f"MIN({second_hx}, MAX(0, assessed_value - {FIRST_HOMESTEAD * 2}))"
    con.executescript(f"""
        ALTER TABLE property ADD COLUMN tax_district TEXT;
        ALTER TABLE property ADD COLUMN senior_exemption INTEGER;
        ALTER TABLE property ADD COLUMN district_taxable INTEGER;
        ALTER TABLE property ADD COLUMN school_taxable INTEGER;
        ALTER TABLE property ADD COLUMN millage REAL;
        ALTER TABLE property ADD COLUMN est_ad_valorem REAL;
        ALTER TABLE property ADD COLUMN est_tax REAL;
        UPDATE property SET tax_district = CASE district_group {cases} ELSE district_group END;
        -- The senior exemption only reduces county levies. Its amount isn't in the
        -- data, so take it from what's left of the total after the homestead exemptions.
        UPDATE property SET senior_exemption = CASE
            WHEN exemptions LIKE '%Senior Homestead%' AND COALESCE(taxable_value, 0) > 0
            THEN MIN({SENIOR_EXEMPTION}, MAX(0, exemption_value - {FIRST_HOMESTEAD} - {additional_hx}))
            ELSE 0 END;
        UPDATE property SET district_taxable = taxable_value + senior_exemption;
        UPDATE property SET school_taxable = CASE
            WHEN taxable_value IS NULL OR taxable_value = 0 THEN taxable_value
            WHEN homestead = 1 THEN taxable_value + {additional_hx} + senior_exemption
            WHEN COALESCE(ag_credit, 0) = 0 AND just_value > assessed_value
                 THEN taxable_value + (just_value - assessed_value)
            ELSE taxable_value END;
        DROP TABLE IF EXISTS _rates;
        CREATE TEMP TABLE _rates AS
            SELECT district_group,
                   SUM(rate) AS millage,
                   SUM(CASE WHEN basis = 'county' THEN rate ELSE 0 END) AS county_mills,
                   SUM(CASE WHEN basis = 'other'  THEN rate ELSE 0 END) AS other_mills,
                   SUM(CASE WHEN basis = 'school' THEN rate ELSE 0 END) AS school_mills
            FROM levies GROUP BY district_group;
        UPDATE property SET
            millage = (SELECT millage FROM _rates r WHERE r.district_group = property.tax_district),
            est_ad_valorem = ROUND((SELECT (county_mills * property.taxable_value
                                           + other_mills * property.district_taxable
                                           + school_mills * property.school_taxable) / 1000.0
                                    FROM _rates r WHERE r.district_group = property.tax_district), 2);
        UPDATE property SET est_tax = ROUND(COALESCE(est_ad_valorem, 0) + COALESCE(non_ad_valorem, 0), 2);
        CREATE INDEX ix_property_est_tax ON property(est_tax);
        CREATE INDEX ix_property_assessed ON property(assessed_value);
    """)
    for group, mills in con.execute("SELECT district_group, ROUND(SUM(rate),4) FROM levies GROUP BY 1"):
        print(f"  district {group}: {mills} mills")
    print(f"  second homestead exemption on roll: ${second_hx:,}")


def _ring_area_centroid(ring):
    """Signed area and centroid of a ring in planar coordinates."""
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]):
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if a == 0:
        xs, ys = zip(*ring)
        return 0.0, (sum(xs) / len(xs), sum(ys) / len(ys))
    return a / 2, (cx / (3 * a), cy / (3 * a))


def _find_condo_table():
    """The condo-outline layer (vGISCondoAll) is the polygon table keyed by unit ParcelID."""
    for path in sorted(glob.glob(os.path.join(GDB_DIR, "*.gdbtable"))):
        with open(path, "rb") as f:
            head = f.read(20000)
        if ("DisplaySiteAddress".encode("utf-16-le") in head
                and "ParcelID".encode("utf-16-le") in head
                and "SHAPE".encode("utf-16-le") in head):
            return path
    return None


def load_geometry(con):
    """Store each property's parcel outline (lat/lon) and centroid.

    The GIS account number is the CAMA PropertyID, so shapes are matched on that, with
    the parcel ID (CamaPID / ParcelID) as a fallback. Condo units have no parcel of their
    own; the GDB condo layer gives each unit its complex outline.
    """
    by_id, by_parcel = {}, {}  # key -> (source, rings in state plane feet, label point or None)

    def add(key_id, key_parcel, source, rings, pt):
        for index, key in ((by_id, key_id), (by_parcel, key_parcel)):
            if not key:
                continue
            if key in index and index[key][0] == source:  # multi-record parcel: merge rings
                index[key][1].extend(rings)
            elif key not in index:
                index[key] = (source, list(rings), pt)

    if os.path.exists(PARCEL_SHP + ".shp"):
        attrs = geo.read_dbf(PARCEL_SHP + ".dbf", {"AccountNum", "CamaPID", "XCOORD", "YCOORD"})
        n = 0
        for a, rings in zip(attrs, geo.read_polygons(PARCEL_SHP + ".shp")):
            if not rings:
                continue
            pt = (float(a["XCOORD"]), float(a["YCOORD"])) if a["XCOORD"] and a["YCOORD"] else None
            acct = int(float(a["AccountNum"])) if a["AccountNum"] else None
            add(acct, a["CamaPID"], "parcel", rings, pt)
            n += 1
        print(f"  parcel shapefile: {n:,} polygons")
    condo_table = _find_condo_table() if os.path.isdir(GDB_DIR) else None
    if condo_table:
        n = 0
        for a, rings in geo.read_gdbtable(condo_table, {"AccountNumber", "ParcelID"}):
            if rings:
                add(a.get("AccountNumber"), a.get("ParcelID"), "condo", rings, None)
                n += 1
        print(f"  condo outlines ({os.path.basename(condo_table)}): {n:,} polygons")

    con.executescript("""
        DROP TABLE IF EXISTS parcel_geom;
        CREATE TABLE parcel_geom (property_id INTEGER PRIMARY KEY, source TEXT,
            min_lat REAL, min_lon REAL, max_lat REAL, max_lon REAL, rings TEXT);
    """)
    for col in ("lat", "lon"):
        try:
            con.execute(f"ALTER TABLE property ADD COLUMN {col} REAL")
        except sqlite3.OperationalError:
            pass  # already there (geometry-only rebuild)
    con.execute("UPDATE property SET lat = NULL, lon = NULL")

    project = geo.stateplane_to_latlon
    batch_geom, batch_pt = [], []
    matched_by = {"account": 0, "parcel id": 0}
    for pid, prop_id in con.execute("SELECT parcel_id, property_id FROM property").fetchall():
        shape = by_id.get(prop_id)
        if shape:
            matched_by["account"] += 1
        else:
            shape = by_parcel.get(pid)
            if not shape:
                continue
            matched_by["parcel id"] += 1
        source, rings, pt = shape
        if pt is not None:  # some records carry XCOORD/YCOORD = 0; only trust points on the shape
            xs = [x for r in rings for x, _ in r]
            ys = [y for r in rings for _, y in r]
            if not (min(xs) <= pt[0] <= max(xs) and min(ys) <= pt[1] <= max(ys)):
                pt = None
        if pt is None:
            biggest = max(rings, key=lambda r: abs(_ring_area_centroid(r)[0]))
            pt = _ring_area_centroid(biggest)[1]
        lat, lon = project(*pt)
        ll_rings = []
        for ring in rings:
            out = []
            for x, y in ring:
                la, lo = project(x, y)
                p = [round(lo, 6), round(la, 6)]  # GeoJSON order
                if not out or out[-1] != p:
                    out.append(p)
            if len(out) >= 3:
                ll_rings.append(out)
        if not ll_rings:
            continue
        lons = [p[0] for r in ll_rings for p in r]
        lats = [p[1] for r in ll_rings for p in r]
        batch_geom.append((prop_id, source, min(lats), min(lons), max(lats), max(lons),
                           json.dumps(ll_rings, separators=(",", ":"))))
        batch_pt.append((round(lat, 6), round(lon, 6), prop_id))
    con.executemany("INSERT INTO parcel_geom VALUES (?,?,?,?,?,?,?)", batch_geom)
    con.executemany("UPDATE property SET lat = ?, lon = ? WHERE property_id = ?", batch_pt)
    con.executescript("""
        CREATE INDEX IF NOT EXISTS ix_property_latlon ON property(lat, lon);
        CREATE INDEX ix_geom_bbox ON parcel_geom(min_lat, max_lat, min_lon, max_lon);
    """)
    total = con.execute("SELECT COUNT(*) FROM property").fetchone()[0]
    print(f"  {len(batch_geom):,} of {total:,} properties have a shape "
          f"(matched by account number: {matched_by['account']:,}, by parcel ID: {matched_by['parcel id']:,})")


def main():
    if "--geometry-only" in sys.argv:
        t0 = time.time()
        con = sqlite3.connect(DB_PATH)
        print("Loading parcel geometry...")
        load_geometry(con)
        con.commit()
        con.close()
        print(f"Done in {time.time() - t0:.0f}s")
        return
    if not os.path.isdir(CSV_DIR):
        sys.exit(f"CSV folder not found: {CSV_DIR}")
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    tmp = DB_PATH + ".tmp"
    if os.path.exists(tmp):
        os.remove(tmp)
    t0 = time.time()
    con = sqlite3.connect(tmp)
    con.execute("PRAGMA journal_mode=OFF")
    con.execute("PRAGMA synchronous=OFF")
    print("Loading CSVs...")
    for table, (filename, cols) in RAW.items():
        load_raw(con, table, filename, cols)
    con.commit()
    print("Building property table...")
    con.executescript(BUILD_SQL)
    print("Estimating taxes...")
    add_tax_estimates(con)
    print("Loading parcel geometry...")
    load_geometry(con)
    for table in RAW:
        con.execute(f"DROP TABLE {table}")
    con.commit()
    con.execute("VACUUM")
    con.close()
    os.replace(tmp, DB_PATH)
    print(f"Done in {time.time() - t0:.0f}s -> {DB_PATH}")


if __name__ == "__main__":
    main()
