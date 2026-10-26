"""Shared helpers for the demo build.

Everything here reads a clone of the harness repository at the pinned commit
and never writes into it. The pin is asserted by `check_pin()` so the demo's
data can always be traced to one commit and one database hash.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

HARNESS_COMMIT = "8eef6ac13d36ac1f23d742466ec0789ca3fe9c8c"
HARNESS_BRANCH = "refine-tools-MCP"
DB_SHA256 = "a8b38b71dc7d16b9c3eecf0d83714552edbb9aaa1f81c4055e0fb5fd8a13d3d4"
DB_SHA_SHORT = DB_SHA256[:16]

ARM = "2026-10-22_bering_straits_annual_v1_deepseek-v3.2_fuse_seed20261022"
RUNS = {"lin": "run-0004_lin", "crew": "run-0006_crew",
        "mass": "run-0007_mass", "self": "run-0001_self"}
ARM_MODEL = "DeepSeek V3.2 (via OpenRouter)"
CHECKPOINTS = ("plan", "revision", "reassessment")

ORIGIN_HUB = "hub:h000698"
NOME_HUB = "hub:h000493"
SCENARIO = "bering_straits_annual_v1"

# Palette: the harness's own report figures (agentic_harness_workflow/report_figures.py).
PALETTE = {
    "road": "#2a78d6", "barge": "#eb6834", "plane": "#1baf7a",
    "ice_road": "#4a3aa7", "transfer": "#7a6a58",
    "voided": "#d03b3b", "warning": "#fab219",
    "context_open": "#8a8983", "context_closed": "#e6e4dd", "surface": "#fcfcfb",
}
MODE_LABEL = {"road": "Road", "barge": "Barge", "plane": "Plane",
              "ice_road": "Ice road", "transfer": "Transfer"}


class BuildError(RuntimeError):
    pass


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_pin(harness: Path, allow_dirty: bool = False) -> dict:
    """Assert the clone is at the pinned commit and carries the pinned database."""
    head = subprocess.run(["git", "-C", str(harness), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    if head != HARNESS_COMMIT:
        raise BuildError(f"harness clone is at {head}, expected {HARNESS_COMMIT}")
    db = harness / "fuel_network.duckdb"
    sha = sha256_of(db)
    if sha != DB_SHA256:
        raise BuildError(f"fuel_network.duckdb sha256 {sha} != pinned {DB_SHA256}")
    dirty = subprocess.run(["git", "-C", str(harness), "status", "--porcelain"],
                           capture_output=True, text=True, check=True).stdout.strip()
    if dirty and not allow_dirty:
        raise BuildError("harness clone has uncommitted changes; refuse to build from it")
    return {"harness_commit": head, "harness_branch": HARNESS_BRANCH,
            "db_sha256": sha, "db_bytes": db.stat().st_size}


def read_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj, pretty: bool = False) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (json.dumps(obj, indent=1, ensure_ascii=False) if pretty
            else json.dumps(obj, separators=(",", ":"), ensure_ascii=False))
    path.write_text(text, encoding="utf-8")
    return len(text.encode("utf-8"))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


_FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)


def split_frontmatter(text: str) -> tuple[dict, str]:
    """Split a `---` YAML header from a markdown body. Header values that are
    plain `key: value` lines are parsed; multi-line values are joined."""
    m = _FRONT.match(text)
    if not m:
        return {}, text
    header, body = m.group(1), text[m.end():]
    meta: dict = {}
    key = None
    for line in header.splitlines():
        if line[:1].isspace() and key:
            meta[key] = (meta[key] + " " + line.strip()).strip()
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            meta[key] = val.strip()
    return meta, body


def md_to_html(text: str) -> str:
    import markdown
    return markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])


def pid(kind: str, raw: str) -> str:
    """Public id with its kind prefix, whatever form the table stored."""
    raw = str(raw)
    return raw if raw.startswith(kind + ":") else f"{kind}:{raw}"


def months_to_mask(spec) -> int:
    """Accepts "1,2,3", "[1, 2, 3]" or a list of ints."""
    mask = 0
    if isinstance(spec, (list, tuple)):
        parts = [str(int(m)) for m in spec]
    else:
        parts = str(spec or "").strip("[] ").split(",")
    for part in parts:
        part = part.strip()
        if part:
            mask |= 1 << (int(part) - 1)
    return mask


def mask_to_list(mask: int) -> list[int]:
    return [m for m in range(1, 13) if mask >> (m - 1) & 1]
