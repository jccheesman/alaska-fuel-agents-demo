"""Build every data file the site reads.

    python build/build_all.py --harness ../agentic_harness_for_alaska_fuel_network \
        [--out site/data] [--fresh-run <run folder>] [--skip-land]

Reads a clone of the harness at the pinned commit (asserted), writes JSON
into site/data, validates each file against build/schemas, and refuses to
finish if the total grows past the size budget.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import BuildError, PALETTE, MODE_LABEL, check_pin, write_json  # noqa: E402
from extract_network import Network, extract_corridors, extract_facilities, extract_hubs, passable_counts  # noqa: E402
from extract_disruption import extract_disruption, load_d2  # noqa: E402
from extract_routes import GeomStore, extract_reference  # noqa: E402
from extract_monthly import compute_monthly  # noqa: E402
from extract_runs import extract_runs  # noqa: E402
from extract_text import extract_text  # noqa: E402

SIZE_BUDGET_MB = 12.0


def validate(out_dir: Path) -> list[str]:
    import jsonschema
    problems = []
    schema_dir = Path(__file__).with_name("schemas")
    for schema_path in sorted(schema_dir.glob("*.schema.json")):
        target = out_dir / schema_path.name.replace(".schema.json", "")
        if not target.exists():
            problems.append(f"{target.name}: missing")
            continue
        schema = json.loads(schema_path.read_text())
        data = json.loads(target.read_text(encoding="utf-8"))
        try:
            jsonschema.validate(data, schema)
        except jsonschema.ValidationError as e:
            problems.append(f"{target.name}: {e.message[:200]} at {list(e.absolute_path)[:6]}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--harness", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=Path("site/data"))
    ap.add_argument("--img", type=Path, default=Path("site/img"))
    ap.add_argument("--fresh-run", type=Path, default=None)
    ap.add_argument("--fresh-label", default="Your run (open model, Colab)")
    ap.add_argument("--fresh-model", default=None, help='model name to display, e.g. "qwen2.5:14b via Ollama"')
    ap.add_argument("--skip-land", action="store_true")
    ap.add_argument("--land-cache", type=Path, default=Path(".cache/natural_earth"))
    ap.add_argument("--allow-dirty", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    harness = args.harness.resolve()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    pin = check_pin(harness, allow_dirty=args.allow_dirty)
    print(f"harness {pin['harness_commit'][:12]}  db {pin['db_sha256'][:16]}  ok")

    net = Network(harness)
    d2 = load_d2(harness)
    voided_edges = set(d2["voided"]["edges"])
    print("network loaded")

    hubs = extract_hubs(net, out, set(d2["voided"]["hubs"]))
    facs = extract_facilities(net, out, set(d2["voided"]["facilities"]))
    cors = extract_corridors(net, out, set(d2["voided"]["corridors"]))
    print(f"hubs {hubs['n']}  facilities {facs['n']}  corridors {cors['n']}")

    store = GeomStore(net)
    reference = extract_reference(net, store, out, hubs)
    print(f"reference routes: {reference['n_requests']} requests, {reference['n_affected_cost']} affected (cost)")
    reference["monthly"] = compute_monthly(net, store, harness, reference)
    write_json(out / "reference_routes.json", reference)
    print("monthly cheapest paths computed with the harness router; September matches the frozen reference")
    disruption = extract_disruption(net, harness, out, d2, reference)
    runs = extract_runs(net, store, harness, out, args.img, voided_edges,
                        fresh_run=args.fresh_run, fresh_label=args.fresh_label,
                        fresh_model=args.fresh_model)
    n_geoms = len(store.geoms)
    store.write(out)
    print(f"agent runs: {list(runs['runs'])}; {n_geoms} distinct route geometries")
    text = extract_text(harness, out)
    print(f"text bundle: {text}")

    if not args.skip_land:
        from fetch_land import build_land
        land = build_land(out / "land.geojson", args.land_cache)
        print(f"land: {land}")

    meta = {
        **pin,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "arm": runs["arm"], "model": runs["model"],
        "palette": PALETTE, "mode_label": MODE_LABEL,
        "passable_edges_by_month": passable_counts(net),
        "corridors_by_month": cors["by_month"], "corridors_by_mode": cors["modes"],
        "counts": {"hubs": hubs["n"], "facilities": facs["n"], "corridors": cors["n"],
                   "nodes": len(net.xy), "edges": len(net.endpoints),
                   "route_geoms": n_geoms},
        "polyline_breaks": net.breaks,
        "fresh_run": str(args.fresh_run) if args.fresh_run else None,
    }
    sizes = {p.name: p.stat().st_size for p in sorted(out.iterdir()) if p.is_file()}
    meta["file_bytes"] = sizes
    write_json(out / "provenance.json", meta, pretty=True)

    total_mb = sum(sizes.values()) / 1e6
    for name, b in sizes.items():
        print(f"  {name:28s} {b / 1e6:7.2f} MB")
    print(f"  total {total_mb:.2f} MB  ({time.time() - t0:.0f}s)")
    if net.breaks:
        print(f"polyline breaks ({len(net.breaks)}):")
        for b in net.breaks[:20]:
            print("  ", b)
    problems = validate(out)
    if problems:
        print("SCHEMA PROBLEMS:")
        for p in problems:
            print("  ", p)
        return 2
    if total_mb > SIZE_BUDGET_MB:
        print(f"size budget exceeded: {total_mb:.1f} MB > {SIZE_BUDGET_MB} MB")
        return 3
    print("build ok")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BuildError as e:
        print(f"BUILD ERROR: {e}")
        sys.exit(1)
