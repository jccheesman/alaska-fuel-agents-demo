"""Edge lists -> polylines.

The database stores edges as (from_node, to_node) pairs with arbitrary
orientation and no geometry of their own, so a route or corridor is drawn by
chaining its ordered edges into a node sequence and joining the nodes' lat/lon
with straight segments. Douglas-Peucker runs on the EPSG:3338 metre
coordinates (so a tolerance is a real distance), and the survivors are
emitted as rounded WGS84 [lon, lat] pairs.
"""
from __future__ import annotations

import hashlib
import math


def chain(edge_ids: list[int], endpoints: dict[int, tuple[int, int]]) -> list[list[int]]:
    """Return one or more node sequences. A break (two consecutive edges that
    share no node) starts a new sequence; the caller logs it."""
    parts: list[list[int]] = []
    cur: list[int] = []
    prev_last: int | None = None
    for i, e in enumerate(edge_ids):
        a, b = endpoints[e]
        if prev_last is None:
            # orient the first edge so that its far end is not shared with the next edge
            if i + 1 < len(edge_ids):
                na, nb = endpoints[edge_ids[i + 1]]
                if a in (na, nb) and b not in (na, nb):
                    a, b = b, a
            cur = [a, b]
        elif a == prev_last:
            cur.append(b)
        elif b == prev_last:
            cur.append(a)
        else:
            parts.append(cur)
            cur = [a, b]
        prev_last = cur[-1]
    if cur:
        parts.append(cur)
    return parts


def _perp_dist(p, a, b) -> float:
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def douglas_peucker_keep(xy: list[tuple[float, float]], tol: float) -> list[int]:
    """Indices of the points kept by Douglas-Peucker (iterative)."""
    n = len(xy)
    if n <= 2:
        return list(range(n))
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        s, e = stack.pop()
        if e <= s + 1:
            continue
        best, bi = -1.0, -1
        for i in range(s + 1, e):
            d = _perp_dist(xy[i], xy[s], xy[e])
            if d > best:
                best, bi = d, i
        if best > tol:
            keep[bi] = True
            stack.append((s, bi))
            stack.append((bi, e))
    return [i for i, k in enumerate(keep) if k]


def nodes_to_coords(nodes: list[int], xy: dict[int, tuple[float, float]],
                    ll: dict[int, tuple[float, float]], tol_m: float,
                    decimals: int = 4) -> list[list[float]]:
    pts = [xy[n] for n in nodes]
    kept = douglas_peucker_keep(pts, tol_m)
    out: list[list[float]] = []
    for i in kept:
        lat, lon = ll[nodes[i]]
        if lon > 0:          # Aleutians west of the antimeridian: keep the map continuous
            lon -= 360.0
        pt = [round(lon, decimals), round(lat, decimals)]
        if not out or out[-1] != pt:
            out.append(pt)
    if len(out) == 1:
        out.append(out[0])
    return out


def flat(coords: list[list[float]]) -> list[float]:
    return [v for pt in coords for v in pt]


def geom_id(edge_pids: list[str]) -> str:
    return "g" + hashlib.sha1(" ".join(edge_pids).encode()).hexdigest()[:12]
