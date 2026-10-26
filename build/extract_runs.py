"""The archived agent runs (one per topology) and the arm's results table.

The reports are shown as the agents produced them. Honest flags come from
`caveats.yaml`, which paraphrases the arm's own FINDINGS.md and judge notes.
"""
from __future__ import annotations

import csv
import json
import shutil
from datetime import datetime
from pathlib import Path

import yaml

from common import ARM, ARM_MODEL, BuildError, CHECKPOINTS, RUNS, read_json, read_text, write_json
from extract_network import Network
from extract_routes import GeomStore, extract_agent_routes

METRIC_COLS = ["routes", "legs", "claims", "sourced_share", "citation_faith",
               "voided_edges_used", "plan_cost_per_gal", "coverage_accounted_share",
               "n_months_with_service", "unserved_honest", "remote_declared",
               "invented_edge_ids", "seasonal_validity", "continuity_rate"]


def _num(v):
    if v in ("", None):
        return None
    try:
        f = float(v)
        return int(f) if f.is_integer() and "." not in str(v) else f
    except ValueError:
        return v


def wall_seconds(manifest: dict) -> float | None:
    t = manifest.get("timing") or {}
    try:
        a = datetime.fromisoformat(t["started_at"])
        b = datetime.fromisoformat(t["ended_at"])
        return (b - a).total_seconds()
    except (KeyError, ValueError, TypeError):
        return None


def fmt_wall(s: float | None) -> str:
    if s is None:
        return "?"
    s = int(s)
    if s < 3600:
        return f"{s // 60} min"
    return f"{s // 3600} h {(s % 3600) // 60:02d} min"


def l3_titles(path: Path) -> list[dict]:
    """Document titles and pages from an L3 release note, never the quoted passages."""
    out = []
    if not path.exists():
        return out
    for line in read_text(path).splitlines():
        line = line.strip()
        if not line.startswith("- ") or "(cite" not in line:
            continue
        head = line[2:].split("(cite", 1)[0].strip()
        out.append(head)
    return out


def load_run(net: Network, store: GeomStore, run_dir: Path, topo: str, voided_edges: set[str],
             results_row: dict | None, judge: dict | None, caveats: dict, img_dir: Path,
             label: str, model: str, source: str, lenient: bool = False) -> dict:
    manifest = read_json(run_dir / "run_summary_manifest.json")
    checkpoints = extract_agent_routes(net, store, run_dir, topo, voided_edges, lenient)
    metrics = {}
    if results_row:
        for ck in CHECKPOINTS:
            metrics[ck] = {c: _num(results_row.get(f"{ck}_{c}")) for c in METRIC_COLS}
        for ck in CHECKPOINTS:
            if ck in checkpoints:
                rec = metrics[ck]["voided_edges_used"]
                mine = checkpoints[ck]["routes_through_voided"]
                if rec not in (None, "") and ck != "plan" and int(rec) != mine:
                    print(f"  note: {topo}/{ck}: results.csv voided_edges_used={rec}, "
                          f"recomputed legs-through-voided={mine} (counted per leg here)")
    for ck, cav in (caveats.get(topo) or {}).items():
        if ck in checkpoints:
            checkpoints[ck]["caveats"] = cav
    png = run_dir / "revision_overview.png"
    img = None
    if png.exists():
        img = f"img/revision_overview_{topo}.png"
        img_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(png, img_dir / f"revision_overview_{topo}.png")
    task_md = run_dir / "scenario_task_delivered.md"
    return {
        "topology": topo, "label": label, "run_id": manifest["run_id"], "model": model,
        "source": source, "cell": manifest.get("cell"),
        "framework": manifest.get("framework"),
        "usd": _num(results_row.get("usd")) if results_row else None,
        "llm_calls": _num(results_row.get("llm_calls")) if results_row else
                     (manifest.get("budget", {}).get("consumed", {}) or {}).get("llm_calls"),
        "prompt_tokens": (manifest.get("budget", {}).get("consumed", {}) or {}).get("prompt_tokens"),
        "wall_s": wall_seconds(manifest), "wall": fmt_wall(wall_seconds(manifest)),
        "judge": judge, "metrics": metrics, "checkpoints": checkpoints,
        "l3_documents": l3_titles(run_dir / "l3_unlock_delivered.md"),
        "task_delivered_md": read_text(task_md) if task_md.exists() else None,
        "overview_png": img,
    }


def extract_runs(net: Network, store: GeomStore, harness: Path, out_dir: Path, img_dir: Path,
                 voided_edges: set[str], fresh_run: Path | None = None,
                 fresh_label: str = "Your run (open model, Colab)",
                 fresh_model: str | None = None) -> dict:
    arm_dir = harness / "run_archives" / ARM
    results = {r["topology"]: r for r in csv.DictReader(open(arm_dir / "results" / "results.csv"))}
    judge = {j["topology"]: j for j in read_json(arm_dir / "judge" / "means.json")}
    caveats = yaml.safe_load(read_text(Path(__file__).with_name("caveats.yaml")))
    runs = {}
    for topo, folder in RUNS.items():
        run_dir = arm_dir / "runs" / folder
        if not run_dir.exists():
            raise BuildError(f"missing archived run {run_dir}")
        runs[topo] = load_run(net, store, run_dir, topo, voided_edges, results.get(topo),
                              judge.get(topo), caveats, img_dir,
                              label=caveats.get("labels", {}).get(topo, topo),
                              model=ARM_MODEL, source=f"run_archives/{ARM}/runs/{folder}")
    if fresh_run:
        manifest = read_json(fresh_run / "run_summary_manifest.json")
        topo = manifest["cell"]["topology"]
        mc = manifest.get("model_config") or {}
        model = fresh_model or (f"{mc.get('provider')}: {(mc.get('tier_map') or {}).get('writer', '?')}"
                                if mc.get("provider") != "ollama" else "open model via Ollama")
        runs["fresh"] = load_run(net, store, fresh_run, topo, voided_edges, None, None,
                                 {}, img_dir, label=fresh_label, model=str(model),
                                 source=str(fresh_run.name), lenient=True)
        runs["fresh"]["checkpoints"] = {
            ck: {**v, "caveats": ["A fresh run from the companion notebook with an open model; "
                                  "not part of the archived study."]}
            for ck, v in runs["fresh"]["checkpoints"].items()}
    arm_notes = caveats.get("arm_notes", [])
    payload = {"arm": ARM, "model": ARM_MODEL, "caps_mode": "fuse",
               "scenario": "bering_straits_annual_v1", "disruption": "D2",
               "scope_facilities": 136, "arm_notes": arm_notes,
               "order": [t for t in ("lin", "crew", "mass", "self", "fresh") if t in runs],
               "runs": runs}
    write_json(out_dir / "agent_runs.json", payload)

    # the compact results table
    rows = []
    for topo in payload["order"]:
        r = runs[topo]
        ck = r["checkpoints"]
        def tri(key):
            return " → ".join(str(ck[c][key]) if c in ck else "–" for c in CHECKPOINTS)
        last = ck.get("reassessment") or ck.get("revision") or ck.get("plan") or {}
        cov = last.get("coverage", {})
        rows.append({
            "topology": topo, "label": r["label"], "run": r["run_id"],
            "routes": tri("n_routes"), "claims": " → ".join(str(len(ck[c]["claims"])) if c in ck else "–" for c in CHECKPOINTS),
            "months": ", ".join(str(m) for m in last.get("months_with_service", [])) or "–",
            "served_unserved_remote": f"{len(cov.get('served', []))} / {len(cov.get('unserved', []))} / {len(cov.get('remote', []))}",
            "legs_through_voided_after_notice": (ck.get("revision") or {}).get("routes_through_voided"),
            "sourced_share": (r["metrics"].get("reassessment") or {}).get("sourced_share"),
            "citation_faith": (r["metrics"].get("reassessment") or {}).get("citation_faith"),
            "usd": r["usd"], "wall": r["wall"], "llm_calls": r["llm_calls"],
            "judge_mean": (r["judge"] or {}).get("run_mean"),
            "judge": {k: (r["judge"] or {}).get(k) for k in CHECKPOINTS},
        })
    table = {"arm": ARM, "rows": rows, "arm_notes": arm_notes,
             "judge_scale": "blind model judge, 0–4, five dimensions; mean per report",
             "source": "results/results.csv, judge/means.json, FINDINGS.md of the arm"}
    write_json(out_dir / "study_results.json", table)
    return payload
