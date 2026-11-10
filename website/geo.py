"""Parcel geometry helpers: read the county parcel shapefile and convert its
Florida State Plane East (NAD83, US survey feet) coordinates to latitude/longitude.

Standard library only. The projection math is Snyder's inverse Transverse Mercator
("Map Projections - A Working Manual", USGS PP 1395, eq. 8-18 to 8-25), which is
accurate to well under a foot at county scale.
"""
import math
import struct

# GRS 1980 ellipsoid (NAD83). NAD83 and WGS84 differ by about a meter here.
_A = 6378137.0
_F = 1 / 298.257222101
_E2 = _F * (2 - _F)
_EP2 = _E2 / (1 - _E2)
# EPSG:2236 NAD83 / Florida East (ftUS)
_K0 = 0.9999411764705882
_LON0 = math.radians(-81.0)
_LAT0 = math.radians(24.0 + 20.0 / 60.0)
_FE = 200000.0  # meters (656166.667 US ft)
_FN = 0.0
US_FOOT = 1200.0 / 3937.0


def _meridian_arc(phi):
    e2, e4, e6 = _E2, _E2 ** 2, _E2 ** 3
    return _A * ((1 - e2 / 4 - 3 * e4 / 64 - 5 * e6 / 256) * phi
                 - (3 * e2 / 8 + 3 * e4 / 32 + 45 * e6 / 1024) * math.sin(2 * phi)
                 + (15 * e4 / 256 + 45 * e6 / 1024) * math.sin(4 * phi)
                 - (35 * e6 / 3072) * math.sin(6 * phi))


_M0 = _meridian_arc(_LAT0)
_E1 = (1 - math.sqrt(1 - _E2)) / (1 + math.sqrt(1 - _E2))
_MU_DEN = _A * (1 - _E2 / 4 - 3 * _E2 ** 2 / 64 - 5 * _E2 ** 3 / 256)


def stateplane_to_latlon(x_ft, y_ft):
    """Florida East State Plane (US feet) -> (lat, lon) in degrees."""
    x = x_ft * US_FOOT - _FE
    y = y_ft * US_FOOT - _FN
    mu = (_M0 + y / _K0) / _MU_DEN
    e1 = _E1
    phi1 = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu)
            + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
            + (151 * e1 ** 3 / 96) * math.sin(6 * mu)
            + (1097 * e1 ** 4 / 512) * math.sin(8 * mu))
    sin1, cos1, tan1 = math.sin(phi1), math.cos(phi1), math.tan(phi1)
    c1 = _EP2 * cos1 ** 2
    t1 = tan1 ** 2
    n1 = _A / math.sqrt(1 - _E2 * sin1 ** 2)
    r1 = _A * (1 - _E2) / (1 - _E2 * sin1 ** 2) ** 1.5
    d = x / (n1 * _K0)
    lat = phi1 - (n1 * tan1 / r1) * (
        d ** 2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * _EP2) * d ** 4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * _EP2 - 3 * c1 ** 2) * d ** 6 / 720)
    lon = _LON0 + (
        d - (1 + 2 * t1 + c1) * d ** 3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * _EP2 + 24 * t1 ** 2) * d ** 5 / 120) / cos1
    return math.degrees(lat), math.degrees(lon)


def read_dbf(path, wanted):
    """Yield dicts of the wanted fields from a dBASE file, in record order."""
    with open(path, "rb") as f:
        header = f.read(32)
        count, header_len, rec_len = struct.unpack("<IHH", header[4:12])
        fields, offset = [], 1
        while True:
            d = f.read(32)
            if d[0] == 0x0D:
                break
            name = d[:11].split(b"\0")[0].decode("ascii")
            fields.append((name, offset, d[16]))
            offset += d[16]
        layout = [(n, o, ln) for n, o, ln in fields if n in wanted]
        f.seek(header_len)
        for _ in range(count):
            rec = f.read(rec_len)
            yield {n: rec[o:o + ln].decode("latin1").strip() for n, o, ln in layout}


def read_polygons(path):
    """Yield each polygon record as a list of rings of (x, y) in file units."""
    with open(path, "rb") as f:
        f.seek(100)
        while True:
            head = f.read(8)
            if len(head) < 8:
                return
            _, length = struct.unpack(">ii", head)
            content = f.read(length * 2)
            shape_type = struct.unpack("<i", content[:4])[0]
            if shape_type == 0:
                yield []
                continue
            nparts, npoints = struct.unpack("<ii", content[36:44])
            parts = struct.unpack(f"<{nparts}i", content[44:44 + 4 * nparts])
            pts_off = 44 + 4 * nparts
            coords = struct.unpack(f"<{2 * npoints}d", content[pts_off:pts_off + 16 * npoints])
            bounds = list(parts) + [npoints]
            yield [[(coords[2 * i], coords[2 * i + 1]) for i in range(bounds[p], bounds[p + 1])]
                   for p in range(nparts)]


# ---------------------------------------------------------------------------
# Minimal Esri File Geodatabase (.gdbtable) reader - enough for simple feature
# classes with polygon geometry. Format: https://github.com/rouault/dump_gdbtable/wiki/FGDB-Spec

def _varuint(buf, pos):
    shift = result = 0
    while True:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, pos
        shift += 7


def _varint(buf, pos):
    b = buf[pos]
    pos += 1
    result = b & 0x3F
    sign = -1 if b & 0x40 else 1
    shift = 6
    while b & 0x80:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        shift += 7
    return sign * result, pos


def read_gdbtable(path, wanted):
    """Yield (attributes, rings) for each row of a File Geodatabase polygon table.

    attributes holds the wanted fields; rings is a list of [(x, y), ...] in the
    layer's coordinate units, or [] if the row has no geometry.
    """
    with open(path, "rb") as f:
        data = f.read()
    with open(path[:-len("gdbtable")] + "gdbtablx", "rb") as f:
        tablx = f.read()

    # --- field descriptors ---
    fd_off = struct.unpack("<q", data[32:40])[0]
    pos = fd_off + 4 + 4 + 4  # size, version, flags
    nfields = struct.unpack("<h", data[pos:pos + 2])[0]
    pos += 2
    fields = []
    geom = None
    for _ in range(nfields):
        n = data[pos]
        name = data[pos + 1:pos + 1 + 2 * n].decode("utf-16-le")
        pos += 1 + 2 * n
        n = data[pos]
        pos += 1 + 2 * n  # alias
        ftype = data[pos]
        pos += 1
        nullable = False
        if ftype == 6:  # ObjectID
            pos += 2
        elif ftype == 4:  # string
            pos += 4
            flag = data[pos]
            nullable = bool(flag & 1)
            pos += 1
            dlen, pos = _varuint(data, pos)
            pos += dlen
        elif ftype == 7:  # geometry
            pos += 1
            flag = data[pos]
            nullable = bool(flag & 1)
            pos += 1
            wkt_len = struct.unpack("<h", data[pos:pos + 2])[0]
            pos += 2 + wkt_len
            gflags = data[pos]
            pos += 1
            has_m, has_z = bool(gflags & 2), bool(gflags & 4)
            xo, yo, xys = struct.unpack("<3d", data[pos:pos + 24])
            pos += 24
            if has_m:
                pos += 16
            if has_z:
                pos += 16
            pos += 8 + (8 if has_m else 0) + (8 if has_z else 0)  # tolerances
            pos += 32  # xy extent
            pos += 1
            ngrid = struct.unpack("<i", data[pos:pos + 4])[0]
            pos += 4 + 8 * ngrid
            geom = (xo, yo, xys, has_z, has_m)
        elif ftype in (0, 1, 2, 3, 5):  # int16, int32, float32, float64, date
            pos += 1
            flag = data[pos]
            nullable = bool(flag & 1)
            pos += 1
            dlen = data[pos]
            pos += 1 + dlen
        elif ftype in (10, 11):  # GUID, GlobalID
            pos += 1
            flag = data[pos]
            nullable = bool(flag & 1)
            pos += 1
        elif ftype in (8, 9, 12):  # blob, raster, xml
            pos += 1
            flag = data[pos]
            nullable = bool(flag & 1)
            pos += 1
        else:
            raise ValueError(f"unsupported field type {ftype} for {name}")
        fields.append((name, ftype, nullable))
    nullable_count = sum(1 for f in fields if f[2])
    null_bytes = (nullable_count + 7) // 8

    # --- rows, located through the .gdbtablx offset index ---
    nblocks, nrows_x, offset_size = struct.unpack("<3i", tablx[4:16])
    for i in range(nrows_x):
        p = 16 + i * offset_size
        off = int.from_bytes(tablx[p:p + offset_size], "little")
        if off == 0:
            continue  # deleted row
        pos = off + 4
        nulls = data[pos:pos + null_bytes]
        pos += null_bytes
        attrs, rings, ni = {}, [], 0
        for name, ftype, nullable in fields:
            if nullable:
                is_null = nulls[ni // 8] & (1 << (ni % 8))
                ni += 1
                if is_null:
                    if name in wanted:
                        attrs[name] = None
                    continue
            if ftype == 6:
                continue
            if ftype == 4:
                n, pos = _varuint(data, pos)
                if name in wanted:
                    attrs[name] = data[pos:pos + n].decode("utf-8", "replace").strip()
                pos += n
            elif ftype == 7:
                n, pos = _varuint(data, pos)
                rings = _decode_polygon(data[pos:pos + n], geom)
                pos += n
            elif ftype == 0:
                attrs[name] = struct.unpack("<h", data[pos:pos + 2])[0]; pos += 2
            elif ftype == 1:
                attrs[name] = struct.unpack("<i", data[pos:pos + 4])[0]; pos += 4
            elif ftype == 2:
                attrs[name] = struct.unpack("<f", data[pos:pos + 4])[0]; pos += 4
            elif ftype in (3, 5):
                attrs[name] = struct.unpack("<d", data[pos:pos + 8])[0]; pos += 8
            elif ftype in (10, 11):
                pos += 16
            else:  # blob / xml: varuint length prefix
                n, pos = _varuint(data, pos)
                pos += n
        yield {k: v for k, v in attrs.items() if k in wanted}, rings


def _decode_polygon(blob, geom):
    xo, yo, xys, has_z, has_m = geom
    gtype, pos = _varuint(blob, 0)
    base = gtype & 0xFF
    if base not in (5, 15, 19, 25, 51):  # polygon variants
        return []
    npoints, pos = _varuint(blob, pos)
    if npoints == 0:
        return []
    nparts, pos = _varuint(blob, pos)
    if gtype & 0x20000000:  # has curves
        _, pos = _varuint(blob, pos)
    for _ in range(4):  # bbox
        _, pos = _varuint(blob, pos)
    counts = []
    for _ in range(nparts - 1):
        c, pos = _varuint(blob, pos)
        counts.append(c)
    counts.append(npoints - sum(counts))
    rings, dx, dy = [], 0, 0
    for c in counts:
        ring = []
        for _ in range(c):
            vx, pos = _varint(blob, pos)
            vy, pos = _varint(blob, pos)
            dx += vx
            dy += vy
            ring.append((dx / xys + xo, dy / xys + yo))
        rings.append(ring)
    return rings
