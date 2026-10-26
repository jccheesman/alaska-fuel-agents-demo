"""The D2 disruption as one bundle: what the harness voided, where it is, and
the operator notice the agents were handed."""
from __future__ import annotations

from pathlib import Path

from common import md_to_html, read_json, read_text, write_json
from extract_network import Network


def load_d2(harness: Path) -> dict:
    d = harness / "agentic_harness_workflow" / "disruptions"
    spec = read_json(d / "D2.json")
    binding = read_json(d / "D2_binding_report.json")
    notice = read_text(d / "D2_notice.md")
    voided = {"hubs": [], "facilities": [], "corridors": [], "edges": [], "symbolic": []}
    for ref in spec["voided_refs"]:
        kind = ref.split(":", 1)[0]
        key = {"hub": "hubs", "facility": "facilities", "corridor": "corridors",
               "edge": "edges"}.get(kind, "symbolic")
        voided[key].append(ref)
    return {"spec": spec, "binding": binding, "notice": notice, "voided": voided}


def extract_disruption(net: Network, harness: Path, out_dir: Path, d2: dict,
                       reference: dict) -> dict:
    voided = d2["voided"]
    edge_geoms = {}
    edge_info = {}
    for p in voided["edges"]:
        eid = net.edge_by_pid[p]
        edge_geoms[p] = net.edge_coords(eid)
        edge_info[p] = {"mode": net.edge_mode[eid], "length_m": round(net.edge_len[eid], 1),
                        "corridor": net.edge_corridor.get(eid)}
    nome = net.hub_by_pid["hub:h000493"]
    lat, lon = net.ll[nome["node_id"]]
    # which baseline reference routes cross a voided edge (cost objective, the planning objective)
    crossings = {}
    for req in reference["requests"]:
        used = req["objectives"]["cost"]["baseline"].get("uses_closed_edges") or []
        if used:
            crossings[req["id"]] = used
    payload = {
        "id": d2["spec"]["disruption_id"],
        "title": d2["spec"]["title"],
        "notes": d2["spec"]["notes"],
        "notice_md": d2["notice"],
        "notice_html": md_to_html(d2["notice"]),
        "voided": voided,
        "counts": d2["binding"]["counts"],
        "anchor": {"hub": "hub:h000493", "name": "Nome", "lon": round(lon, 5), "lat": round(lat, 5)},
        "client_hubs": d2["binding"]["client_hubs"],
        "declared_approximations": d2["binding"]["declared_approximations"],
        "bound_on": d2["binding"]["bound_on"],
        "edge_geoms": edge_geoms,
        "edge_info": edge_info,
        "baseline_crossings": crossings,
        "preserved_outs": [
            "Coastal communities served directly by ocean barge without transfer at Nome are not affected.",
            "Nome's runways and airport fuel storage are intact: air substitution from Nome stays feasible.",
            "Only the Barge method is affected; facilities without it are preserved outs.",
        ],
    }
    write_json(out_dir / "disruption_d2.json", payload)
    return payload
