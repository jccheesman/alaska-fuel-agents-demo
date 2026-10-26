"""Hubs, facilities and corridors from fuel_network.duckdb (read-only).

Also exposes `Network`, the in-memory lookups (node coordinates, edge
endpoints, public ids, modes) the route and disruption extractors share.
"""
from __future__ import annotations

import json
from pathlib import Path

import duckdb

from common import (BuildError, ORIGIN_HUB, NOME_HUB, SCENARIO, mask_to_list,
                    months_to_mask, pid, read_json, write_json)
from geom import chain, nodes_to_coords

MODE_BY_TYPE: dict[str, str] = {}


class Network:
    """Everything the geometry code needs, loaded once from the database."""

    def __init__(self, harness: Path):
        self.harness = harness
        self.con = duckdb.connect(str(harness / "fuel_network.duckdb"), read_only=True)
        con = self.con
        # modes: edge type -> report mode
        for mode, report_mode, types in con.execute(
                "SELECT mode, report_mode, edge_types FROM modes").fetchall():
            for t in types:
                MODE_BY_TYPE[t] = report_mode
        self.mode_by_type = MODE_BY_TYPE
        # nodes
        self.xy: dict[int, tuple[float, float]] = {}
        self.ll: dict[int, tuple[float, float]] = {}
        self.node_pid: dict[int, str] = {}
        for nid, npid, x, y, lat, lon in con.execute(
                "SELECT n.node_id, n.node_pid, n.x, n.y, t.lat, t.lon FROM network_nodes n "
                "JOIN tiles t ON t.kind='node' AND t.ref_id=n.node_id").fetchall():
            self.xy[nid] = (x, y)
            self.ll[nid] = (lat, lon)
            self.node_pid[nid] = pid("node", npid)
        if len(self.xy) != 84094:
            raise BuildError(f"expected 84,094 nodes with tiles, got {len(self.xy)}")
        # edges
        self.endpoints: dict[int, tuple[int, int]] = {}
        self.edge_mode: dict[int, str] = {}
        self.edge_len: dict[int, float] = {}
        self.edge_by_pid: dict[str, int] = {}
        self.edge_pid: dict[int, str] = {}
        self.edge_corridor: dict[int, str] = {}
        for eid, epid, a, b, typ, length, cid in con.execute(
                "SELECT edge_id, edge_pid, from_node, to_node, type, length_m, corridor_id "
                "FROM network_edges").fetchall():
            self.endpoints[eid] = (a, b)
            self.edge_mode[eid] = MODE_BY_TYPE.get(typ, "unknown")
            self.edge_len[eid] = length or 0.0
            p = pid("edge", epid)
            self.edge_by_pid[p] = eid
            self.edge_pid[eid] = p
            if cid:
                self.edge_corridor[eid] = cid
        if len(self.endpoints) != 93049:
            raise BuildError(f"expected 93,049 edges, got {len(self.endpoints)}")
        # hub public id -> internal
        self.hub_by_pid: dict[str, dict] = {}
        for hub_id, hpid, name, node_id, community, region in con.execute(
                "SELECT hub_id, hub_pid, hub_name, node_id, community, region FROM hub_community").fetchall():
            self.hub_by_pid[pid("hub", hpid)] = {"hub_id": hub_id, "node_id": node_id,
                                                 "name": name, "community": community,
                                                 "region": region}
        self.breaks: list[str] = []

    def resolve_edges(self, edge_pids: list[str], where: str) -> list[int]:
        out = []
        for p in edge_pids:
            if p not in self.edge_by_pid:
                raise BuildError(f"{where}: unknown edge id {p}")
            out.append(self.edge_by_pid[p])
        return out

    def polyline(self, edge_ids: list[int], tol_m: float, where: str) -> list[list[list[float]]]:
        """One or more [lon,lat] sequences (more than one only after a break)."""
        parts = chain(edge_ids, self.endpoints)
        if len(parts) > 1:
            self.breaks.append(f"{where}: {len(parts) - 1} break(s) in {len(edge_ids)} edges")
        return [nodes_to_coords(p, self.xy, self.ll, tol_m) for p in parts]

    def edge_coords(self, eid: int) -> list[list[float]]:
        a, b = self.endpoints[eid]
        return nodes_to_coords([a, b], self.xy, self.ll, 0.0)

    def modes_of(self, edge_ids: list[int]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for e in edge_ids:
            m = self.edge_mode[e]
            counts[m] = counts.get(m, 0) + 1
        return counts


def extract_hubs(net: Network, out_dir: Path, voided_hubs: set[str]) -> dict:
    con = net.con
    scenario = read_json(net.harness / "agentic_harness_workflow" / "scenarios" / f"{SCENARIO}.json")
    dest = {d["hub"]: d for d in scenario["task"]["destination_hubs"]}
    rows = con.execute("""
        SELECT h.hub_id, h.hub_pid, h.hub_name, h.community, h.region, h.hub_type, h.deliv_meth,
               h.node_id, t.lat, t.lon, h.mapped_facilities, h.mapped_remote,
               h.km_to_community_facilities, n.hub_cap
        FROM hub_community h
        JOIN tiles t ON t.kind='node' AND t.ref_id=h.node_id
        JOIN network_nodes n ON n.node_id=h.node_id
        ORDER BY h.hub_pid""").fetchall()
    access = {}
    for hpid, mode, months in con.execute(
            "SELECT hub_pid, mode, months_passable FROM hub_access").fetchall():
        access.setdefault(pid("hub", hpid), {})[MODE_BY_TYPE.get(mode, mode.lower())] = \
            mask_to_list(months_to_mask(months))
    hubs = []
    for (hub_id, hpid, name, community, region, hub_type, deliv, node_id, lat, lon,
         mapped, mapped_remote, km, cap) in rows:
        p = pid("hub", hpid)
        lon = lon - 360 if lon > 0 else lon
        role = "origin" if p == ORIGIN_HUB else ("destination" if p in dest else None)
        hub = {
            "pid": p, "hub_id": hub_id, "name": name, "community": community,
            "region": region, "hub_type": hub_type, "deliv_meth": deliv,
            "node_id": node_id, "lon": round(lon, 5), "lat": round(lat, 5),
            "capacity_gal": cap, "mapped_facilities": mapped, "mapped_remote": mapped_remote,
            "km_to_community_facilities": round(km, 1) if km is not None else None,
            "access": access.get(p, {}),
            "role": role, "voided": p in voided_hubs,
        }
        if p in dest:
            d = dest[p]
            hub["scenario"] = {"label": d["label"], "designation": d["designation"],
                               "delivery_methods": d["delivery_methods"],
                               "facilities": d["facilities"],
                               "remote_last_mile": d["remote_last_mile"]}
        hubs.append(hub)
    if len(hubs) != 329:
        raise BuildError(f"expected 329 hubs, got {len(hubs)}")
    payload = {"n": len(hubs), "origin": ORIGIN_HUB, "nome": NOME_HUB,
               "destinations": list(dest), "hubs": hubs}
    write_json(out_dir / "hubs.json", payload)
    return payload


def extract_facilities(net: Network, out_dir: Path, voided_fac: set[str]) -> dict:
    rows = net.con.execute("""
        SELECT f.facility_id, f.facility_pid, f.latitude, f.longitude, f.community_name,
               f.delivery_method_1, f.delivery_method_2, f.qc_status,
               m.hub_id, n.hub_pid, m.last_mile, m.distance_m
        FROM facilities f
        LEFT JOIN hub_facility_map m USING (facility_id)
        LEFT JOIN network_nodes n ON n.hub_id = m.hub_id AND n.is_hub
        ORDER BY f.facility_pid""").fetchall()
    facs = []
    for fid, fpid, lat, lon, community, m1, m2, qc, hub_id, hpid, last_mile, dist in rows:
        p = pid("facility", fpid)
        lon = lon - 360 if lon and lon > 0 else lon
        facs.append({"pid": p, "lon": round(lon, 5), "lat": round(lat, 5),
                     "community": community, "method_1": m1, "method_2": m2,
                     "qc_status": qc, "hub_pid": pid("hub", hpid) if hpid else None,
                     "last_mile": last_mile,
                     "hub_km": round(dist / 1000, 1) if dist is not None else None,
                     "voided": p in voided_fac})
    if len(facs) != 1740:
        raise BuildError(f"expected 1,740 facilities, got {len(facs)}")
    payload = {"n": len(facs), "facilities": facs}
    write_json(out_dir / "facilities.json", payload)
    return payload


def extract_corridors(net: Network, out_dir: Path, voided_cor: set[str]) -> dict:
    rows = net.con.execute("""
        SELECT c.corridor_id, c.corridor_pid, c.mode, c.kind, c.hub_a, c.hub_b,
               c.n_edges, c.length_m, c.months_passable,
               list(ce.edge_id ORDER BY ce.seq) AS edge_ids
        FROM corridors c JOIN corridor_edges ce USING (corridor_id)
        GROUP BY ALL ORDER BY c.corridor_pid""").fetchall()
    hub_pid_by_id = {v["hub_id"]: k for k, v in net.hub_by_pid.items()}
    feats = []
    stats = {"modes": {}, "by_month": [0] * 12}
    for cid, cpid, mode, kind, hub_a, hub_b, n_edges, length, months, edge_ids in rows:
        p = pid("corridor", cpid)
        mask = months_to_mask(months)
        parts = net.polyline(list(edge_ids), 400.0, p)
        geom = ({"type": "LineString", "coordinates": parts[0]} if len(parts) == 1
                else {"type": "MultiLineString", "coordinates": parts})
        rmode = MODE_BY_TYPE.get(mode, str(mode).lower())
        props = {"pid": p, "mode": rmode, "months": mask,
                 "hub_a": hub_pid_by_id.get(hub_a), "hub_b": hub_pid_by_id.get(hub_b),
                 "km": round(length / 1000, 1), "n_edges": n_edges,
                 "voided": p in voided_cor}
        for m in range(1, 13):
            props[f"m{m}"] = bool(mask >> (m - 1) & 1)
            if props[f"m{m}"]:
                stats["by_month"][m - 1] += 1
        stats["modes"][rmode] = stats["modes"].get(rmode, 0) + 1
        feats.append({"type": "Feature", "geometry": geom, "properties": props})
    fc = {"type": "FeatureCollection", "features": feats}
    write_json(out_dir / "corridors.geojson", fc)
    return {"n": len(feats), **stats}


def passable_counts(net: Network) -> dict:
    """Edges open per month per mode: the seasonality the data encodes."""
    rows = net.con.execute("""
        SELECT w.month, w.mode, count(*) FROM edge_month_weights w
        WHERE w.passable GROUP BY 1, 2 ORDER BY 1, 2""").fetchall()
    out: dict[str, list[int]] = {}
    for month, mode, n in rows:
        out.setdefault(MODE_BY_TYPE.get(mode, mode.lower()), [0] * 12)[month - 1] = n
    return out


if __name__ == "__main__":  # quick manual check
    import sys
    net = Network(Path(sys.argv[1]))
    print(len(net.xy), len(net.endpoints), len(net.hub_by_pid))
    print(json.dumps(passable_counts(net)))
