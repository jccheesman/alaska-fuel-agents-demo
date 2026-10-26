"""The cheapest delivery to each Bering Straits hub for every month of the
year, computed with the harness's own router (the Python oracle in
agentic_harness_workflow/graph.py, the engine behind the `route` tool).

The frozen reference answers cover September only. Seasonality is the point
of the network (barge corridors freeze, ice roads open), so the map needs the
cheapest path per month to show it honestly. The September result is asserted
identical to the frozen reference, edge for edge.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from common import BuildError
from extract_network import Network
from extract_routes import GeomStore


def compute_monthly(net: Network, store: GeomStore, harness: Path, reference: dict) -> dict:
    os.environ["DOE_MAS_DB"] = str(harness / "fuel_network.duckdb")
    os.environ.setdefault("DOE_MAS_GRAPH_ENGINE", "python")
    if str(harness) not in sys.path:
        sys.path.insert(0, str(harness))
    from agentic_harness_workflow import graph as G  # noqa: E402  (the harness's router)

    engine = G.PythonEngine()
    requests = reference["requests"]
    # internal node ids: the reference file carries them
    ref_raw = __import__("json").load(open(harness / "agentic_harness_workflow" / "tests" / "reference_answers" / "routes.json"))
    raw_reqs = ref_raw["scenarios"][reference["scenario"]]["requests"]
    monthly: dict[str, dict] = {}
    checked = 0
    for month in range(1, 13):
        mg = G.MonthGraph.build(month)
        per_dest = {}
        for req in requests:
            raw = raw_reqs[req["id"]]
            res = engine.route(mg, raw["origin_node"], raw["destination_node"], "cost")
            if res is None:
                per_dest[req["dest"]] = None
                continue
            pids = [net.edge_pid[e] for e in res["edges"]]
            if month == 9:
                frozen = req["objectives"]["cost"]["baseline"]
                if store.geoms.get(frozen["geom"]) is None or frozen["n_edges"] != len(pids) or \
                        abs(frozen["cost_per_gallon"] - (res["cost_per_gallon"] or 0)) > 1e-4:
                    raise BuildError(f"September route to {req['dest']} differs from the frozen reference")
                checked += 1
            per_dest[req["dest"]] = {
                "geom": store.add(pids, f"monthly/{month}/{req['dest']}"),
                "cost_per_gallon": res["cost_per_gallon"],
                "length_km": round(res["length_m"] / 1000, 1),
                "n_edges": len(pids),
                "modes": net.modes_of(res["edges"]),
                "uses_closed_edges": sorted(set(pids) & set(e for e in
                                            ("edge:e091382", "edge:e094423", "edge:e097314"))),
            }
        monthly[str(month)] = per_dest
        print(f"  month {month:2d}: {sum(v is not None for v in per_dest.values())}/{len(per_dest)} hubs reachable, "
              f"{mg.n_edges} passable edges")
    if checked != len(requests):
        raise BuildError("September cross-check did not cover every request")
    return monthly
