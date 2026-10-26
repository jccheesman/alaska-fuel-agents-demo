"""Reference routes (the deterministic answer key) and the agents' routes
(from archived reports), both as deduplicated simplified polylines."""
from __future__ import annotations

import json
from pathlib import Path

from common import ARM, BuildError, CHECKPOINTS, RUNS, SCENARIO, read_json, write_json
from extract_network import Network
from geom import flat, geom_id

ROUTE_TOL_M = 200.0


class GeomStore:
    def __init__(self, net: Network):
        self.net = net
        self.geoms: dict[str, dict] = {}

    def add(self, edge_pids: list[str], where: str, lenient: bool = False) -> str | None:
        """Store the polyline split into runs of one mode, so the map can
        color a road-then-barge route the way the harness's own figures do.
        With lenient=True an unknown edge id (possible in a fresh run from the
        notebook) skips the geometry instead of failing the build."""
        gid = geom_id(edge_pids)
        if gid not in self.geoms:
            try:
                eids = self.net.resolve_edges(edge_pids, where)
            except BuildError as e:
                if not lenient:
                    raise
                print(f"  warning: {e}; leg drawn without geometry")
                return None
            runs: list[tuple[str, list[int]]] = []
            for e in eids:
                m = self.net.edge_mode[e]
                if runs and runs[-1][0] == m:
                    runs[-1][1].append(e)
                else:
                    runs.append((m, [e]))
            parts = []
            for m, run in runs:
                for pl in self.net.polyline(run, ROUTE_TOL_M, f"{where}/{m}"):
                    parts.append([m, flat(pl)])
            self.geoms[gid] = {"n_edges": len(eids),
                               "modes": self.net.modes_of(eids),
                               "parts": parts}
        return gid

    def write(self, out_dir: Path) -> int:
        return write_json(out_dir / "route_geoms.json", self.geoms)


def extract_reference(net: Network, store: GeomStore, out_dir: Path, hubs: dict) -> dict:
    ref = read_json(net.harness / "agentic_harness_workflow" / "tests" / "reference_answers" / "routes.json")
    if ref["db"]["sha256"][:16] != "a8b38b71dc7d16b9":
        raise BuildError("routes.json was made from a different database")
    label = {h["pid"]: (h.get("scenario", {}).get("label") or h["community"] or h["name"])
             for h in hubs["hubs"]}

    def one(entry: dict, where: str) -> dict:
        out = {}
        for phase in ("baseline", "post_closure"):
            e = entry[phase]
            pids = e["edges"].split()
            out[phase] = {"geom": store.add(pids, f"{where}/{phase}"),
                          "cost_per_gallon": e["cost_per_gallon"],
                          "length_km": e["length_km"], "n_edges": e["n_edges"],
                          "uses_closed_edges": e.get("uses_closed_edges", []),
                          "last_edge": pids[-1]}
        out["outcome"] = entry["outcome"]
        if entry["baseline"]["cost_per_gallon"]:
            out["delta_cost"] = round(entry["post_closure"]["cost_per_gallon"]
                                      - entry["baseline"]["cost_per_gallon"], 4)
            out["delta_km"] = round(entry["post_closure"]["length_km"]
                                    - entry["baseline"]["length_km"], 1)
        return out

    def scenario(sid: str) -> dict:
        s = ref["scenarios"][sid]
        reqs = []
        for rid, r in s["requests"].items():
            reqs.append({"id": rid, "origin": r["origin_hub"], "dest": r["destination_hub"],
                         "dest_label": label.get(r["destination_hub"], r["destination_hub"]),
                         "month": r["month"],
                         "objectives": {k: one(v, f"{sid}/{rid}/{k}")
                                        for k, v in r["objectives"].items()}})
        reqs.sort(key=lambda q: q["dest_label"])
        n_aff = sum(1 for q in reqs if q["objectives"]["cost"]["outcome"] != "unaffected")
        return {"scenario": sid, "disruption": s["disruption_id"], "month": 9,
                "n_requests": len(reqs), "n_affected_cost": n_aff, "requests": reqs}

    payload = {"db_sha256": ref["db"]["sha256"], **scenario(SCENARIO),
               "anchorage_nome_v1": scenario("anchorage_nome_v1")}
    write_json(out_dir / "reference_routes.json", payload)
    return payload


def read_report(run_dir: Path, ckpt: str):
    rep = read_json(run_dir / f"report_{ckpt}.json")
    seg_path = run_dir / f"report_{ckpt}.segments.json"
    seg = read_json(seg_path) if seg_path.exists() else {}
    return rep, seg


def leg_edges(route: dict, leg_i: int, leg: dict, seg: dict) -> list[str]:
    if leg.get("segments"):
        return list(leg["segments"])
    by_route = seg.get(route["route_id"], {})
    if isinstance(by_route, dict):
        return list(by_route.get(str(leg_i), []))
    return []


def extract_agent_routes(net: Network, store: GeomStore, run_dir: Path, topo: str,
                         voided_edges: set[str], lenient: bool = False) -> dict:
    """Routes, coverage, claims and log for the three checkpoints of one run."""
    out = {}
    for ckpt in CHECKPOINTS:
        if not (run_dir / f"report_{ckpt}.json").exists():
            continue
        rep, seg = read_report(run_dir, ckpt)
        routes = []
        voided_total = 0
        months_used: set[int] = set()
        for route in rep["plan"]["routes"]:
            legs = []
            for i, leg in enumerate(route["legs"]):
                pids = leg_edges(route, i, leg, seg)
                hits = sorted(set(pids) & voided_edges)
                voided_total += bool(hits)
                ms = leg["months"]
                mlist = ([ms["start"]] if ms["start"] == ms["end"] else
                         [((ms["start"] - 1 + k) % 12) + 1
                          for k in range(((ms["end"] - ms["start"]) % 12) + 1)])
                months_used.update(mlist)
                legs.append({"i": i, "mode": leg["mode"], "months": ms, "month_list": mlist,
                             "n_edges": leg.get("n_edges", len(pids)),
                             "cost_per_gallon": leg.get("cost_per_gallon"),
                             "length_km": leg.get("length_km"),
                             "first_edge": leg.get("first_edge") or (pids[0] if pids else None),
                             "last_edge": leg.get("last_edge") or (pids[-1] if pids else None),
                             "from_receipt": leg.get("from_receipt"),
                             "geom": store.add(pids, f"{topo}/{ckpt}/{route['route_id']}/{i}", lenient) if pids else None,
                             "voided_hits": hits})
            routes.append({"route_id": route["route_id"], "legs": legs,
                           "facilities_served": route.get("facilities_served", []),
                           "cost_per_gallon": round(sum((l["cost_per_gallon"] or 0) for l in legs), 4),
                           "length_km": round(sum((l["length_km"] or 0) for l in legs), 1)})
        cov = rep.get("coverage", {})
        out[ckpt] = {
            "summary": rep.get("summary", ""),
            "routes": routes,
            "n_routes": len(routes),
            "n_legs": sum(len(r["legs"]) for r in routes),
            "routes_through_voided": voided_total,
            "months_with_service": sorted(months_used),
            "coverage": {"served": cov.get("facilities_served", []),
                         "unserved": cov.get("facilities_unserved", []),
                         "remote": cov.get("facilities_remote_declared", []),
                         "expanded_from_hubs": cov.get("expanded_from_hubs", [])},
            "claims": rep.get("claims", []),
            "revision_log": (rep.get("revision") or {}).get("log", []),
        }
    return out
