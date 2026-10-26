"""Natural Earth land for the basemap, clipped to Alaska and its neighbors.

Source: the public-domain Natural Earth vectors, mirrored on GitHub
(nvkelso/natural-earth-vector). Longitudes east of the antimeridian are
shifted by -360 so the Aleutians and Chukotka draw next to mainland Alaska.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

from shapely.geometry import shape, mapping, box
from shapely.ops import unary_union, transform

RAW = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
FILES = {"land": "ne_10m_land.geojson", "lakes": "ne_50m_lakes.geojson",
         "admin1": "ne_50m_admin_1_states_provinces.geojson"}
BBOX = (-196.0, 48.0, -126.0, 73.0)   # lon_min, lat_min, lon_max, lat_max (shifted frame)


def fetch(name: str, cache: Path) -> dict:
    p = cache / FILES[name]
    if not p.exists():
        cache.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(RAW + FILES[name], p)
    return json.loads(p.read_text(encoding="utf-8"))


def shifted(geom):
    """Both frames of a geometry: as-is and shifted west by 360 degrees."""
    west = transform(lambda x, y, z=None: (x - 360.0, y), geom)
    return geom, west


def clip_collection(fc: dict, keep=lambda f: True, tol: float = 0.0):
    rect = box(*BBOX)
    pieces = []
    for f in fc["features"]:
        if not keep(f):
            continue
        g = shape(f["geometry"])
        for frame in shifted(g):
            c = frame.intersection(rect)
            if not c.is_empty:
                pieces.append(c)
    merged = unary_union(pieces) if pieces else None
    if merged is not None and tol:
        merged = merged.simplify(tol, preserve_topology=True)
    return merged


def round_geom(obj, nd=3):
    if isinstance(obj, list):
        return [round_geom(v, nd) for v in obj]
    if isinstance(obj, float):
        return round(obj, nd)
    return obj


def build_land(out_path: Path, cache: Path) -> dict:
    land = clip_collection(fetch("land", cache), tol=0.004)
    lakes = clip_collection(fetch("lakes", cache), tol=0.01)
    admin = fetch("admin1", cache)
    alaska = clip_collection(admin, keep=lambda f: f["properties"].get("name") == "Alaska", tol=0.004)
    feats = []
    if land is not None:
        feats.append({"type": "Feature", "properties": {"kind": "land"},
                      "geometry": round_geom(mapping(land))})
    if lakes is not None:
        feats.append({"type": "Feature", "properties": {"kind": "lake"},
                      "geometry": round_geom(mapping(lakes))})
    if alaska is not None:
        feats.append({"type": "Feature", "properties": {"kind": "alaska"},
                      "geometry": round_geom(mapping(alaska.boundary))})
    fc = {"type": "FeatureCollection",
          "attribution": "Natural Earth (public domain), via nvkelso/natural-earth-vector",
          "features": feats}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(fc, separators=(",", ":")), encoding="utf-8")
    return {"bytes": out_path.stat().st_size, "features": len(feats)}


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("site/data/land.geojson")
    cache = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".cache/natural_earth")
    print(build_land(out, cache))
