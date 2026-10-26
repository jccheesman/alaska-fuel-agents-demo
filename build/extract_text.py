"""The harness texts the site shows: skills, adapters, tools, deliveries, OKF
pages, the data guide, the report format, glossaries, and the run lifecycle.

Everything is prerendered to HTML at build time so the site needs no markdown
library. Only owner-authored harness text is bundled: third-party documents
under inputs/ are never read, and L3 release notes contribute document titles
only (see extract_runs.l3_titles).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from common import md_to_html, read_json, read_text, split_frontmatter, write_json

AHW = "agentic_harness_workflow"

OKF_PAGES = {
    "start": "okf/START.md",
    "ontology": "okf/ONTOLOGY.md",
    "region:bering-straits": "okf/regions/bering-straits.md",
    "hub:h000493": "okf/hubs/h000493.md",
    "corridor:c003688": "okf/corridors/c003688.md",
    "corridor:c004896": "okf/corridors/c004896.md",
    "month:09": "okf/months/09.md",
    "disruption:D2": "okf/disruptions/D2.md",
}


def parse_md_table(text: str, heading: str) -> list[dict]:
    """Rows of the first markdown table under `heading` as {col: cell}."""
    m = re.search(rf"^##+\s+{re.escape(heading)}\s*$", text, re.M)
    if not m:
        return []
    lines = text[m.end():].splitlines()
    rows, header = [], None
    for line in lines:
        s = line.strip()
        if not s.startswith("|"):
            if header:
                break
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if header is None:
            header = cells
            continue
        if set("".join(cells)) <= set("-: "):
            continue
        rows.append(dict(zip(header, cells)))
    return rows


def strip_md(s: str) -> str:
    return re.sub(r"[*`]", "", s)


def skill_bundle(harness: Path) -> list[dict]:
    out = []
    for d in sorted((harness / AHW / "skills").iterdir()):
        f = d / "SKILL.md"
        if not f.exists():
            continue
        meta, body = split_frontmatter(read_text(f))
        out.append({"name": meta.get("name", d.name), "description": meta.get("description", ""),
                    "stages": meta.get("stages", ""), "layer": meta.get("layer", ""),
                    "tools": [t.strip() for t in meta.get("tools", "").split(",") if t.strip()],
                    "html": md_to_html(body), "path": f"{AHW}/skills/{d.name}/SKILL.md"})
    return out


def adapter_bundle(harness: Path) -> dict:
    spine = read_text(harness / AHW / "adapters" / "_SPINE.md")
    out = {"spine_md": spine, "spine_html": md_to_html(spine), "rows": {}}
    for row in ("lin", "crew", "mass", "self"):
        text = read_text(harness / AHW / "adapters" / f"{row}.md")
        pos = text.split("## Position", 1)[1].strip() if "## Position" in text else ""
        out["rows"][row] = {"position_md": pos, "position_html": md_to_html(pos),
                            "path": f"{AHW}/adapters/{row}.md"}
    template = harness / AHW / "adapters" / "TEMPLATE.md"
    if template.exists():
        out["template_html"] = md_to_html(read_text(template))
    return out


def tool_bundle(harness: Path) -> dict:
    reg = read_json(harness / AHW / "tool_registry.json")
    tools = []
    for e in reg["entries"]:
        tools.append({"name": e["name"], "layer": e["layer"], "gate": e.get("gate"),
                      "terminal": e.get("terminal", False), "module": e.get("module"),
                      "purpose": e["purpose"]})
    groups = {
        "L1 · the network": [t for t in tools if t["layer"] == "L1" and not t["gate"]],
        "L1 · report builder (DOE_MAS_REPORT_TOOLS)": [t for t in tools if t.get("gate") == "DOE_MAS_REPORT_TOOLS"],
        "L1 · optional": [t for t in tools if t["layer"] == "L1" and t["gate"] and t["gate"] != "DOE_MAS_REPORT_TOOLS"],
        "L2 · the disruption": [t for t in tools if t["layer"] == "L2"],
        "L3 · the context documents": [t for t in tools if t["layer"] == "L3"],
    }
    return {"version": reg.get("version"), "n_tools": reg.get("n_tools", len(tools)),
            "comment": reg.get("_comment", ""), "tools": tools,
            "groups": {k: [t["name"] for t in v] for k, v in groups.items() if v}}


def okf_bundle(harness: Path) -> dict:
    index = read_json(harness / "okf" / "_index.json")
    kinds: dict[str, int] = {}
    for v in index.values():
        kinds[v["kind"]] = kinds.get(v["kind"], 0) + 1
    pages = {}
    for key, rel in OKF_PAGES.items():
        meta, body = split_frontmatter(read_text(harness / rel))
        links = []
        try:
            links = json.loads(meta.get("links", "[]"))
        except json.JSONDecodeError:
            pass
        rel_counts: dict[str, int] = {}
        for l in links:
            rel_counts[l.get("rel", "?")] = rel_counts.get(l.get("rel", "?"), 0) + 1
        pages[key] = {"id": meta.get("id", key), "kind": meta.get("kind"), "layer": meta.get("layer"),
                      "title": meta.get("title"), "built_from": meta.get("built_from"),
                      "n_links": len(links), "link_rels": rel_counts,
                      "links": links[:12], "html": md_to_html(body),
                      "md": body.strip(), "path": rel}
    return {"n_pages_indexed": len(index), "kinds": kinds, "pages": pages,
            "schema": "okf/0.1"}


def delivery_bundle(harness: Path) -> dict:
    out = {}
    for f in sorted((harness / AHW / "deliveries").glob("*.md")):
        text = read_text(f)
        out[f.stem] = {"md": text, "html": md_to_html(text.replace("{payload}", "**{payload}**")),
                       "path": f"{AHW}/deliveries/{f.name}"}
    return out


def mcp_snippet(harness: Path) -> dict:
    src = read_text(harness / AHW / "mcp_server.py")
    doc = src.split('"""', 2)[1].strip() if src.count('"""') >= 2 else ""
    main = ""
    m = re.search(r"\ndef main\(.*", src, re.S)
    if m:
        main = m.group(0).strip()[:3000]
    name = re.search(r'SERVER_NAME\s*=\s*"([^"]+)"', src)
    return {"docstring": doc, "main": main, "server_name": name.group(1) if name else None,
            "path": f"{AHW}/mcp_server.py"}


def lifecycle() -> list[dict]:
    return [
        {"id": "freeze", "title": "Before any run: build, freeze, audit",
         "plain": "The data layers are built once (public ids, the hub-to-facility map, the disruption bindings, the concept map). Then every file an agent will ever see is hashed into a frozen manifest, and an audit checks that the four topologies get a fair, identical treatment surface.",
         "layers": [], "tools": [], "skill": None,
         "artifacts": ["frozen_artifacts_manifest.json", "audit.py passes"],
         "files": ["agentic_harness_workflow/manifest.py", "agentic_harness_workflow/audit.py"]},
        {"id": "provision", "title": "1 · The harness opens the run",
         "plain": "A run folder is created, the task specification is delivered word for word, and layer L1 (the network) is granted. From now on every tool call is logged with a receipt id.",
         "layers": ["L1"], "tools": ["describe", "resolve", "lookup", "route", "validate_routes", "perturb", "region", "global_topology", "read", "read_node", "begin_report", "…"],
         "skill": "orient_in_the_data",
         "artifacts": ["scenario_task_delivered.md", "layer_grants.jsonl"],
         "files": ["agentic_harness_workflow/deliveries/scenario_task_delivery.md", "agentic_harness_workflow/checkpoints.py"]},
        {"id": "plan", "title": "2 · Plan checkpoint",
         "plain": "The team queries the network, routes month by month, and assembles its report with the report tools. finalize_report submits it; the save gate rejects any report with invented ids or citations the run never received.",
         "layers": ["L1"], "tools": ["route", "lookup", "add_route", "set_coverage", "add_claim", "check_report", "finalize_report"],
         "skill": "plan_routes_and_coverage",
         "artifacts": ["report_plan.json", "report_plan.segments.json", "tool_log.jsonl"],
         "files": ["agentic_harness_workflow/report_builder.py", "agentic_harness_workflow/save_report.py"]},
        {"id": "disruption", "title": "3 · The disruption arrives (L2)",
         "plain": "The harness delivers the operator notice for D2 and grants layer L2. Two new tools appear: one re-serves the notice, the other says which of the team's own ids the disruption affects.",
         "layers": ["L1", "L2"], "tools": ["query_disruption_notice", "check_disruption_impact"],
         "skill": "revise_under_disruption",
         "artifacts": ["disruption_delivered.json"],
         "files": ["agentic_harness_workflow/deliveries/disruption_delivery.md", "agentic_harness_workflow/disruptions/D2_notice.md"]},
        {"id": "revision", "title": "4 · Revision checkpoint",
         "plain": "The team carries its plan forward and changes only what the notice changes: reroute with perturb, move facilities an affected hub served to another route or to unserved, log every claim whose status changed.",
         "layers": ["L1", "L2"], "tools": ["carry_forward", "perturb", "drop_route", "add_route", "log_revision", "finalize_report"],
         "skill": "revise_under_disruption",
         "artifacts": ["report_revision.json"],
         "files": ["agentic_harness_workflow/impact.py"]},
        {"id": "l3", "title": "5 · Context documents are released (L3)",
         "plain": "Socio-economic documents are unlocked, as context tends to arrive late in real planning. The harness also pushes a few passages found along the saved routes, each with a receipt to cite.",
         "layers": ["L1", "L2", "L3"], "tools": ["list_context_folders", "read_context_document", "search_context"],
         "skill": "reassess_with_lagging_context",
         "artifacts": ["l3_unlock_delivered.md"],
         "files": ["agentic_harness_workflow/deliveries/socioeconomic_unlock_delivery.md", "agentic_harness_workflow/context_index.py"]},
        {"id": "reassessment", "title": "6 · Reassessment checkpoint",
         "plain": "The team confirms, changes or defers each decision in the light of the documents. Leaving the plan unchanged is a valid outcome; an empty revision log records that choice.",
         "layers": ["L1", "L2", "L3"], "tools": ["search_context", "add_claim", "retire_claim", "finalize_report"],
         "skill": "reassess_with_lagging_context",
         "artifacts": ["report_reassessment.json"],
         "files": []},
        {"id": "finalize", "title": "7 · The run is sealed",
         "plain": "The runner hashes the reports into the run summary manifest, classifies any failure, and renders a PDF with maps so a person can read the run by eye.",
         "layers": [], "tools": [], "skill": None,
         "artifacts": ["run_summary_manifest.json", "report.pdf", "revision_overview.png"],
         "files": ["agentic_harness_workflow/run_experiment.py", "agentic_harness_workflow/render_report.py"]},
        {"id": "score", "title": "8 · Scoring and the blind judge",
         "plain": "Deterministic scorers check completion, grounding (every citation against the tool log), the revision against the disruption's hidden answer key, continuity and seasonal validity. A separate model judges each report blind, without knowing the topology.",
         "layers": [], "tools": [], "skill": "judge_report_quality (grader-only)",
         "artifacts": ["results.csv", "judge/means.json"],
         "files": ["agentic_harness_workflow/scorers/", "agentic_harness_workflow/skills_scoring/"]},
        {"id": "archive", "title": "9 · Archive",
         "plain": "Each arm is archived with a README, a card per run, the reports, the scores and the read-out, so the study can be re-read later.",
         "layers": [], "tools": [], "skill": None,
         "artifacts": ["run_archives/<arm>/"],
         "files": ["agentic_harness_workflow/archive_arm.py", "run_archives/README.md"]},
    ]


def extract_text(harness: Path, out_dir: Path) -> dict:
    glossary = [{"term": strip_md(r.get("Term", "")), "meaning": r.get("Meaning", "")}
                for r in parse_md_table(read_text(harness / "run_archives" / "README.md"), "Glossary")]
    key_terms = [{"term": strip_md(r.get("Term", "")), "meaning": r.get("Meaning", "")}
                 for r in parse_md_table(read_text(harness / AHW / "README.md"), "Key terms")]
    data_guide = read_text(harness / AHW / "data_guide.md")
    report_format = read_text(harness / AHW / "report_format.md")
    payload = {
        "skills": skill_bundle(harness),
        "adapters": adapter_bundle(harness),
        "tools": tool_bundle(harness),
        "okf": okf_bundle(harness),
        "deliveries": delivery_bundle(harness),
        "mcp": mcp_snippet(harness),
        "data_guide_html": md_to_html(data_guide.split("## Recipes", 1)[0]),
        "report_format_html": md_to_html(report_format),
        "glossary": glossary,
        "key_terms": key_terms,
    }
    write_json(out_dir / "text_bundle.json", payload)
    write_json(out_dir / "lifecycle.json", {"steps": lifecycle()})
    return {"skills": len(payload["skills"]), "tools": payload["tools"]["n_tools"],
            "okf_pages": len(payload["okf"]["pages"]), "glossary": len(glossary),
            "key_terms": len(key_terms)}
