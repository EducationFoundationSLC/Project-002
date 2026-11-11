"""Saint Lucie County property browser - local web server (standard library only).

    python website/build_db.py   # once, after downloading the CSVs
    python website/server.py     # then open http://localhost:8000
"""
import json
import math
import mimetypes
import os
import sqlite3
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ask  # noqa: E402  "Ask AI" chat (needs the anthropic package and an API key)

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "data", "property.db")
STATIC = os.path.join(HERE, "static")
PAGE_SIZE_MAX = 200
MAP_FEATURES_MAX = 3000
MILES_PER_DEG_LAT = 69.0

LIST_COLUMNS = [
    "property_id", "parcel_id", "address", "unit", "jurisdiction", "zip", "category",
    "land_use_desc", "owner", "owner2", "year_built", "living_area", "bedrooms", "full_baths",
    "half_baths", "acres", "pool", "homestead", "just_value", "assessed_value",
    "exemption_value", "exemptions", "taxable_value", "non_ad_valorem", "est_ad_valorem",
    "est_tax", "millage", "last_sale_date", "last_sale_price", "lat", "lon", "mail_status",
]
SORTABLE = set(LIST_COLUMNS) | {"distance"}

# query param -> SQL fragment; each takes one bound value.
RANGE_FILTERS = {
    "just_min": "just_value >= ?", "just_max": "just_value <= ?",
    "taxable_min": "taxable_value >= ?", "taxable_max": "taxable_value <= ?",
    "assessed_min": "assessed_value >= ?", "assessed_max": "assessed_value <= ?",
    "tax_min": "est_tax >= ?", "tax_max": "est_tax <= ?",
    "year_min": "year_built >= ?", "year_max": "year_built <= ?",
    "area_min": "living_area >= ?", "area_max": "living_area <= ?",
    "acres_min": "acres >= ?", "acres_max": "acres <= ?",
    "beds_min": "bedrooms >= ?", "baths_min": "full_baths >= ?",
    "sale_price_min": "last_sale_price >= ?", "sale_price_max": "last_sale_price <= ?",
    "sold_after": "last_sale_date >= ?", "sold_before": "last_sale_date <= ?",
}
MULTI_FILTERS = {  # param -> column; comma-separated values, OR'd together
    "category": "category", "land_use": "land_use_desc",
    "jurisdiction": "jurisdiction", "zip": "zip",
}
FLAG_FILTERS = {"pool": "pool", "homestead": "homestead", "out_of_state": "out_of_state_owner"}
# mail=... compares the owner's mailing address with the property address (see build_db.py).
MAIL_FILTERS = {"same": ("same",), "different": ("different",), "po_box": ("po_box",),
                "elsewhere": ("different", "po_box")}


def db():
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA mmap_size = 536870912")
    con.execute("PRAGMA cache_size = -65536")
    return con


def parse_near(q):
    """'near=lat,lon&radius=miles' -> (lat, lon, radius) or None."""
    if not q.get("near"):
        return None
    lat, lon = (float(v) for v in q["near"].split(","))
    radius = min(max(float(q.get("radius", 0.5)), 0.05), 25)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("bad coordinates")
    return lat, lon, radius


def distance_sql(near):
    """Squared distance in miles (flat-earth approximation; fine for a few miles).
    Values are validated floats, so they are inlined rather than bound."""
    lat, lon, _ = near
    k = MILES_PER_DEG_LAT * math.cos(math.radians(lat))
    return (f"(((lat - {lat!r}) * {MILES_PER_DEG_LAT}) * ((lat - {lat!r}) * {MILES_PER_DEG_LAT})"
            f" + ((lon - {lon!r}) * {k!r}) * ((lon - {lon!r}) * {k!r}))")


def build_where(q):
    clauses, args = [], []
    near = parse_near(q)
    if near:
        lat, lon, radius = near
        dlat = radius / MILES_PER_DEG_LAT
        dlon = radius / (MILES_PER_DEG_LAT * math.cos(math.radians(lat)))
        clauses.append("lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?")
        args += [lat - dlat, lat + dlat, lon - dlon, lon + dlon]
        clauses.append(f"{distance_sql(near)} <= ?")
        args.append(radius * radius)
    for param, col in MULTI_FILTERS.items():
        vals = [v for v in q.get(param, "").split(",") if v]
        if vals:
            clauses.append(f"{col} IN ({','.join('?' * len(vals))})")
            args += vals
    groups = [v for v in q.get("exemption", "").split(",") if v]
    if groups:  # properties with at least one exemption in these groups
        clauses.append("property_id IN (SELECT property_id FROM exemptions "
                       f"WHERE exemption_group IN ({','.join('?' * len(groups))}))")
        args += groups
    if q.get("selection"):  # properties picked by an Ask AI query
        clauses.append("property_id IN (SELECT value FROM json_each(?))")
        args.append(json.dumps(ask.selection_ids(q["selection"])))
    for param, frag in RANGE_FILTERS.items():
        v = q.get(param, "").strip()
        if v:
            clauses.append(frag)
            args.append(v if param.startswith("sold_") else float(v))
    for param, col in FLAG_FILTERS.items():
        v = q.get(param)
        if v in ("0", "1"):
            clauses.append(f"{col} = ?")
            args.append(int(v))
    if q.get("mail"):
        statuses = MAIL_FILTERS[q["mail"]]  # unknown values raise KeyError -> 400
        clauses.append(f"mail_status IN ({','.join('?' * len(statuses))})")
        args += statuses
    if q.get("exempt") in ("0", "1"):
        clauses.append("COALESCE(exemption_value,0) > 0" if q["exempt"] == "1"
                       else "COALESCE(exemption_value,0) = 0")
    if q.get("improved") in ("0", "1"):
        clauses.append("COALESCE(building_value,0) > 0" if q["improved"] == "1"
                       else "COALESCE(building_value,0) = 0")
    text = q.get("q", "").strip()
    if text:
        like = f"%{text}%"
        clauses.append("(address LIKE ? OR owner LIKE ? OR owner2 LIKE ? OR parcel_id LIKE ? OR subdivision LIKE ?)")
        args += [like] * 5
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", args


def api_properties(q):
    where, args = build_where(q)
    near = parse_near(q)
    sort = q.get("sort", "just_value")
    if sort not in SORTABLE or (sort == "distance" and not near):
        sort = "just_value"
    direction = "ASC" if q.get("dir") == "asc" else "DESC"
    columns = ",".join(LIST_COLUMNS)
    if near:
        columns += f", {distance_sql(near)} AS distance"
    size = min(max(int(q.get("size", 50)), 1), PAGE_SIZE_MAX)
    page = max(int(q.get("page", 1)), 1)
    with db() as con:
        total = con.execute(f"SELECT COUNT(*) FROM property{where}", args).fetchone()[0]
        summary = con.execute(
            f"SELECT SUM(just_value) AS just, SUM(assessed_value) AS assessed, "
            f"SUM(exemption_value) AS exempt, SUM(taxable_value) AS taxable, "
            f"SUM(non_ad_valorem) AS nav, SUM(est_tax) AS tax FROM property{where}",
            args).fetchone()
        rows = con.execute(
            f"SELECT {columns} FROM property{where} "
            f"ORDER BY {sort} IS NULL, {sort} {direction}, property_id LIMIT ? OFFSET ?",
            args + [size, (page - 1) * size]).fetchall()
    out = [dict(r) for r in rows]
    for r in out:
        if r.get("distance") is not None:
            r["distance"] = round(math.sqrt(r["distance"]), 2)  # miles
    return {
        "total": total, "page": page, "size": size,
        "summary": dict(summary),
        "rows": out,
    }


def count_properties(filters):
    """How many properties match a set of website filters (used by Ask AI)."""
    where, args = build_where(filters)
    with db() as con:
        return con.execute(f"SELECT COUNT(*) FROM property{where}", args).fetchone()[0]


def api_map(q):
    """Properties inside a map view: points always, outlines when shapes=1."""
    min_lon, min_lat, max_lon, max_lat = (float(v) for v in q["bbox"].split(","))
    where, args = build_where(q)
    where = (where + " AND " if where else " WHERE ") + "lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?"
    args += [min_lat, max_lat, min_lon, max_lon]
    want_shapes = q.get("shapes") == "1"
    with db() as con:
        total = con.execute(f"SELECT COUNT(*) FROM property{where}", args).fetchone()[0]
        if total > MAP_FEATURES_MAX:
            return {"total": total, "truncated": True, "features": []}
        if want_shapes:
            sql = (f"SELECT p.property_id, p.category, p.address, p.est_tax, p.lat, p.lon, g.rings "
                   # parcel_geom shares no column names with the filters, so `where` is unambiguous
                   f"FROM property p LEFT JOIN parcel_geom g ON g.property_id = p.property_id{where}")
        else:
            sql = f"SELECT property_id, category, address, est_tax, lat, lon FROM property{where}"
        rows = con.execute(sql, args).fetchall()
    features = []
    for r in rows:
        f = {k: r[k] for k in ("property_id", "category", "address", "est_tax", "lat", "lon")}
        if want_shapes and r["rings"]:
            f["rings"] = json.loads(r["rings"])
        features.append(f)
    return {"total": total, "truncated": False, "features": features}


def api_filters():
    with db() as con:
        cats = con.execute(
            "SELECT category, land_use_desc, COUNT(*) n FROM property "
            "GROUP BY 1, 2 ORDER BY 1, 3 DESC").fetchall()
        juris = con.execute(
            "SELECT jurisdiction, COUNT(*) n FROM property WHERE jurisdiction <> '' "
            "GROUP BY 1 ORDER BY 2 DESC").fetchall()
        rates_year = con.execute("SELECT value FROM meta WHERE key='rates_year'").fetchone()[0]
        exemption_groups = con.execute(
            "SELECT exemption_group, COUNT(DISTINCT property_id) n FROM exemptions "
            "GROUP BY 1 ORDER BY 2 DESC").fetchall()
        zips = con.execute(
            "SELECT zip, COUNT(*) n FROM property WHERE zip IS NOT NULL "
            "GROUP BY 1 ORDER BY 1").fetchall()
    categories = {}
    for c in cats:
        entry = categories.setdefault(c["category"], {"name": c["category"], "count": 0, "land_uses": []})
        entry["count"] += c["n"]
        entry["land_uses"].append({"name": c["land_use_desc"], "count": c["n"]})
    return {
        "categories": sorted(categories.values(), key=lambda e: -e["count"]),
        "jurisdictions": [{"name": r[0], "count": r[1]} for r in juris],
        "zips": [{"name": r[0], "count": r[1]} for r in zips],
        "exemptions": [{"name": r[0], "count": r[1]} for r in exemption_groups],
        "ask_ai": ask.setup_problem() is None,
        "rates_year": rates_year,
    }


def api_property(pid):
    with db() as con:
        row = con.execute("SELECT * FROM property WHERE property_id = ?", (pid,)).fetchone()
        if not row:
            return None
        detail = dict(row)
        detail["sales"] = [dict(r) for r in con.execute(
            "SELECT sale_date, price, qualification, deed, grantor FROM sales "
            "WHERE property_id = ? ORDER BY sale_date DESC", (pid,))]
        detail["exemption_list"] = [dict(r) for r in con.execute(
            "SELECT description, grant_year FROM exemptions WHERE property_id = ?", (pid,))]
        detail["other_assessments"] = [dict(r) for r in con.execute(
            "SELECT description, amount FROM other_assessments WHERE property_id = ?", (pid,))]
        taxable_for = {"school": detail["school_taxable"], "county": detail["taxable_value"],
                       "other": detail["district_taxable"]}
        detail["levies"] = [
            {**dict(r), "taxable": taxable_for[r["basis"]]}
            for r in con.execute(
                "SELECT levy_code, authority, basis, school, rate FROM levies WHERE district_group = ? "
                "ORDER BY CASE basis WHEN 'school' THEN 0 WHEN 'county' THEN 1 ELSE 2 END, rate DESC",
                (detail["tax_district"],))]
        for lv in detail["levies"]:
            lv["tax"] = round((lv["taxable"] or 0) * lv["rate"] / 1000, 2)
        detail["rates_year"] = con.execute("SELECT value FROM meta WHERE key='rates_year'").fetchone()[0]
        geom = con.execute("SELECT source, rings FROM parcel_geom WHERE property_id = ?",
                           (pid,)).fetchone()
        detail["geometry"] = {"source": geom["source"], "rings": json.loads(geom["rings"])} if geom else None
        legal = con.execute("SELECT description FROM legal WHERE property_id = ?", (pid,)).fetchone()
        detail["legal"] = legal[0] if legal else None
    return detail


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[-1] for k, v in parse_qs(url.query).items()}
        try:
            if url.path == "/api/properties":
                return self.send_json(api_properties(q))
            if url.path == "/api/map":
                return self.send_json(api_map(q))
            if url.path == "/api/filters":
                return self.send_json(api_filters())
            if url.path.startswith("/api/property/"):
                data = api_property(int(url.path.rsplit("/", 1)[1]))
                return self.send_json(data) if data else self.send_error(404)
        except (ValueError, KeyError):
            return self.send_error(400, "Bad parameter")
        self.send_static(url.path)

    def do_POST(self):
        if urlparse(self.path).path != "/api/ask":
            return self.send_error(404)
        try:
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= 50000:
                raise ValueError
            body = json.loads(self.rfile.read(length))
            question = str(body.get("question", "")).strip()[:1000]
            if not question:
                raise ValueError
            history = body.get("history") if isinstance(body.get("history"), list) else []
            filters = body.get("filters") if isinstance(body.get("filters"), dict) else {}
        except (ValueError, TypeError):
            return self.send_error(400, "Bad request")
        try:
            result = ask.answer(question, history, {k: str(v) for k, v in filters.items()},
                                visitor=self.client_address[0], db_path=DB_PATH,
                                count_properties=count_properties)
        except Exception as e:  # network or API problems: tell the user instead of crashing
            result = {"error": f"The AI service had a problem ({type(e).__name__}). Please try again."}
        self.send_json(result)

    def send_json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_static(self, path):
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        full = os.path.realpath(os.path.join(STATIC, rel))
        if not full.startswith(os.path.realpath(STATIC) + os.sep) or not os.path.isfile(full):
            return self.send_error(404)
        with open(full, "rb") as fh:
            body = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(full)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


def main():
    if not os.path.exists(DB_PATH):
        sys.exit("Database not found. Run: python website/build_db.py")
    port = int(os.environ.get("PORT", 8000))
    print(f"Serving on http://localhost:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
