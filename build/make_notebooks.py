"""Generate the three Colab notebooks under notebooks/.

    python build/make_notebooks.py

Kept as a script so the notebooks can be regenerated when the pinned commit
moves. Cells are written to be re-runnable and to continue past a missing
DuckDB extension with a clear message.
"""
from __future__ import annotations

import sys
from pathlib import Path

import nbformat as nbf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DB_SHA256, HARNESS_COMMIT  # noqa: E402

REPO = "jccheesman/agentic_harness_for_alaska_fuel_network"
DEMO = "jccheesman/alaska-fuel-agents-demo"
OUT = Path(__file__).resolve().parent.parent / "notebooks"

COLAB_BADGE = "[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/{demo}/blob/main/notebooks/{nb})"


def md(src: str):
    return nbf.v4.new_markdown_cell(src.strip("\n"))


def code(src: str):
    return nbf.v4.new_code_cell(src.strip("\n"))


def notebook(cells, title):
    nb = nbf.v4.new_notebook()
    nb.cells = cells
    nb.metadata = {
        "colab": {"name": title, "provenance": []},
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"},
    }
    return nb


# --------------------------------------------------------------------------
# shared cells
# --------------------------------------------------------------------------
TOKEN_CELL = code(f'''
# The harness repository is private while the study runs, so this notebook
# reads a GitHub token from Colab's Secrets panel (the key icon on the left):
#   name: GH_TOKEN   value: a fine-grained personal access token with
#   read-only "Contents" permission on {REPO}
# Nothing is written back to GitHub. Outside Colab, export GH_TOKEN instead.
import os
try:
    from google.colab import userdata  # type: ignore
    GH_TOKEN = userdata.get("GH_TOKEN")
except Exception:
    GH_TOKEN = os.environ.get("GH_TOKEN", "")
assert GH_TOKEN, "Add GH_TOKEN to Colab Secrets (or export it) and re-run this cell."

HARNESS_COMMIT = "{HARNESS_COMMIT}"   # the commit this demo is pinned to
DB_SHA256 = "{DB_SHA256}"
REPO = "{REPO}"
print("token present; pinned commit", HARNESS_COMMIT[:12])
''')

DB_DOWNLOAD_CELL = code(f'''
# Download just the database (29.9 MB) through the GitHub contents API at the
# pinned commit, then verify its hash against the one the demo was built from.
import hashlib, pathlib, requests

db = pathlib.Path("fuel_network.duckdb")
if not db.exists():
    url = f"https://api.github.com/repos/{{REPO}}/contents/fuel_network.duckdb?ref={{HARNESS_COMMIT}}"
    r = requests.get(url, headers={{"Authorization": f"Bearer {{GH_TOKEN}}",
                                   "Accept": "application/vnd.github.raw+json"}}, stream=True, timeout=120)
    r.raise_for_status()
    with open(db, "wb") as f:
        for chunk in r.iter_content(1 << 20):
            f.write(chunk)
sha = hashlib.sha256(db.read_bytes()).hexdigest()
print(db, f"{{db.stat().st_size/1e6:.1f}} MB", "sha256", sha[:16])
assert sha == DB_SHA256, "database hash differs from the pinned one"
''')

CLONE_CELL = code(f'''
# Clone the harness at the pinned commit (shallow: one commit, ~270 MB of
# tracked files including the database and the archived runs).
import os, subprocess, pathlib
root = pathlib.Path("/content/harness") if pathlib.Path("/content").exists() else pathlib.Path("harness").resolve()
if not (root / ".git").exists():
    root.mkdir(parents=True, exist_ok=True)
    remote = f"https://x-access-token:{{GH_TOKEN}}@github.com/{REPO}.git"
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "remote", "add", "origin", remote], cwd=root, check=True)
    subprocess.run(["git", "fetch", "-q", "--depth", "1", "origin", HARNESS_COMMIT], cwd=root, check=True)
    subprocess.run(["git", "checkout", "-q", "FETCH_HEAD"], cwd=root, check=True)
    subprocess.run(["git", "remote", "set-url", "origin", f"https://github.com/{REPO}.git"], cwd=root, check=True)  # drop the token from .git/config
os.chdir(root)
head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
assert head == HARNESS_COMMIT, head
import hashlib
assert hashlib.sha256(open("fuel_network.duckdb", "rb").read()).hexdigest() == DB_SHA256
print("harness at", head[:12], "in", root)
''')


# --------------------------------------------------------------------------
# 00 · DuckDB on the real network
# --------------------------------------------------------------------------
def nb_duckdb():
    cells = [
        md(f"""
# DuckDB on the real Alaska fuel network

{COLAB_BADGE.format(demo=DEMO, nb='00_duckdb_fuel_network.ipynb')}

The agents in the harness never see a map. They see **one DuckDB file**, `fuel_network.duckdb`
(29.9 MB), through a handful of tools. This notebook opens that same file directly and shows what
DuckDB brings to the problem: plain SQL over a million weight rows, table macros and views that
encode the season, and community extensions that put **routing (duckrouting)**, **graph analytics
(Onager)**, **H3 tiles**, **spatial types** and **full-text search** inside the database.

Boxes marked **Callout** say where the harness itself relies on the feature.

Runs on a CPU runtime in a few minutes. Needs a read-only GitHub token in Colab Secrets (see the first cell);
the harness repository is private while the study is under way.
"""),
        md("## 1 · Get the database"),
        TOKEN_CELL,
        code("""
# DuckDB 1.5.6 is the version the database was written with (schema_meta.duckdb_min)
# and the one the extensions were validated on by the harness's VM tests.
%pip -q install duckdb==1.5.6 pandas matplotlib requests
import duckdb, pandas as pd
print("duckdb", duckdb.__version__)
"""),
        DB_DOWNLOAD_CELL,
        md("""
## 2 · DuckDB in one minute

> **Callout — why DuckDB here.** One file, no server, columnar storage, SQL that runs in-process
> next to Python. The whole network (84,094 nodes, 93,049 edges, 1.1 million edge-month weights and
> as many costs) opens read-only in milliseconds, so the harness can hand every agent process its own
> connection and never worry about state leaking between runs.
"""),
        code("""
con = duckdb.connect("fuel_network.duckdb", read_only=True)
con.sql("SHOW TABLES")
"""),
        code("""
# Every table with its row count, in one query over the catalog
con.sql('''
SELECT table_name, estimated_size AS rows, column_count
FROM duckdb_tables() ORDER BY rows DESC
''')
"""),
        code("""
con.sql("SELECT * FROM schema_meta")   # what the harness stamped into the file
"""),
        code("""
con.sql("DESCRIBE network_edges")
"""),
        code("""
# SUMMARIZE profiles a whole table (min/max/approx distinct/nulls) in one call
con.sql("SUMMARIZE SELECT latitude, longitude, delivery_method_1, qc_status FROM facilities")
"""),
        md("""
## 3 · The graph as tables

Nodes and edges are ordinary tables. **Edges have no geometry of their own**: a line is drawn from
one node's coordinates to the other's. Every edge gets one row per month in `edge_month_weights`
(friction and passability) and one in `edge_costs` (modelled cost per gallon).

> **Callout — season is data, not code.** "Ice roads are open January to March" is not an `if`
> statement anywhere in the harness. It is the `passable` flag on 1,282 ice-road edges in three of
> their twelve monthly rows. That is why a disruption can be expressed the same way: as a filter.
"""),
        code("""
# Passable edges per mode per month. PIVOT turns months into columns.
con.sql('''
PIVOT (SELECT mode, month, count(*) AS n FROM edge_month_weights WHERE passable GROUP BY 1, 2)
ON month USING sum(n) GROUP BY mode ORDER BY mode
''')
"""),
        code("""
# The modes table: edge types -> report mode, and the cost rates the costs were built with
con.sql("SELECT mode, report_mode, edge_types, rate_per_gallon_mile, transfer_fee_per_gallon FROM modes")
"""),
        code("""
# A hub is a node with is_hub = true. Here is Nome, resolved by community name.
nome = con.sql("SELECT hub_id, hub_pid, node_id, community, region, hub_type, deliv_meth FROM hub_community WHERE community = 'Nome'").df()
anch = con.sql("SELECT hub_id, hub_pid, node_id, community, region, hub_type FROM hub_community WHERE hub_pid = 'h000698'").df()
display(nome, anch)
NOME_NODE, ANCH_NODE = int(nome.node_id[0]), int(anch.node_id[0])
"""),
        md("""
## 4 · Macros and views the harness built

`schema_stage0.py` added a table macro and three views on top of the four base tables. The macro
`passable_edges(month, modes)` is the one every router uses.

> **Callout — "a disruption is a WHERE clause, never a mutation."** The harness module that
> created this macro says exactly that. To close the Port of Nome you do not delete anything: you
> run the same query with `AND edge_id NOT IN (...)`. The data stays frozen and auditable.
"""),
        code("""
# the macro, as DuckDB stores it
print(con.sql("SELECT macro_definition FROM duckdb_functions() WHERE function_name = 'passable_edges'").fetchone()[0])
"""),
        code("""
ALL_MODES = ['Road', 'Barge', 'Plane', 'IceRoad', 'Transfer']
con.sql("SELECT mode, count(*) AS edges, round(avg(cost_per_gallon), 4) AS avg_cost FROM passable_edges(9, ?) GROUP BY 1 ORDER BY 1", params=[ALL_MODES])
"""),
        code("""
# hub_access: which modes reach each hub's own node, and in which months
con.sql("SELECT hub_pid, community, mode, n_edges, months_passable FROM hub_access WHERE community IN ('Nome', 'Unalakleet', 'Shishmaref') ORDER BY 2, 3")
"""),
        code("""
# corridor_graph: the coarse graph (hub to hub, one mode per corridor) that the analytics tools use
con.sql("SELECT month, count(*) AS corridors, sum(passable::int) AS passable FROM corridor_graph GROUP BY 1 ORDER BY 1")
"""),
        md("""
## 5 · Routing inside the database with **duckrouting**

`duckrouting` is a community extension that exposes pgRouting-style functions over any SQL query
that returns `id, source, target, cost, reverse_cost`. The harness's `graph.py` has a
`DuckroutingEngine` that builds exactly the query below.

> **Callout — the accepted route engine.** On the study VM, `DOE_MAS_GRAPH_ENGINE=duckrouting`
> read the reference routes identical to the pure-Python oracle, edge for edge, in two runs in a
> row, and passed the 27 router tests (INTERNAL_NOTES, 2026-10-14). It was accepted. The Python
> oracle stays the default because the two are byte-equal and the oracle needs no extension.
"""),
        code("""
def load_ext(name, community=True):
    try:
        con.execute(f"LOAD {name}")
        return True
    except Exception:
        try:
            con.execute(f"INSTALL {name}{' FROM community' if community else ''}")
            con.execute(f"LOAD {name}")
            return True
        except Exception as e:
            print(f"[{name}] could not be installed here: {str(e)[:160]}")
            return False

HAVE_ROUTING = load_ext("duckrouting")
print("duckrouting loaded:", HAVE_ROUTING)
"""),
        code("""
# the edge SQL duckrouting wants, built the way graph.DuckroutingEngine._edges_sql builds it
def edges_sql(month=9, weight="cost_per_gallon", avoid=()):
    modes = ", ".join(f"'{m}'" for m in ALL_MODES)
    sql = (f"SELECT edge_id AS id, from_node AS source, to_node AS target, "
           f"{weight} AS cost, {weight} AS reverse_cost "
           f"FROM passable_edges({month}, [{modes}]) WHERE {weight} IS NOT NULL")
    if avoid:
        sql += " AND edge_id NOT IN (" + ", ".join(str(int(e)) for e in avoid) + ")"
    return sql

def dijkstra(src, dst, month=9, avoid=()):
    rows = con.execute("SELECT node, edge, agg_cost FROM duckrouting_dijkstra(?, ?, ?)",
                       [edges_sql(month, avoid=avoid), int(src), int(dst)]).fetchall()
    edges = [int(r[1]) for r in rows if int(r[1]) != -1]
    return edges, (rows[-1][2] if rows else None)

if HAVE_ROUTING:
    base_edges, base_cost = dijkstra(ANCH_NODE, NOME_NODE)
    print(f"Anchorage -> Nome, September, cheapest: {len(base_edges)} edges, ${base_cost:.3f}/gal")
"""),
        code("""
# Reference answer in the harness: 4,899 edges and $1.848/gal (tests/reference_answers/routes.json).
# The route's modes, in travel order, and its length:
if HAVE_ROUTING:
    con.register("route_edges", pd.DataFrame({"seq": range(len(base_edges)), "edge_id": base_edges}))
    display(con.sql('''
        SELECT m.report_mode AS mode, count(*) AS edges, round(sum(e.length_m)/1000, 1) AS km
        FROM route_edges r JOIN network_edges e USING (edge_id)
        JOIN modes m ON list_contains(m.edge_types, e.type)
        GROUP BY 1 ORDER BY min(r.seq)
    '''))
"""),
        md("""
### The storm closes the port

Disruption **D2** voids three transfer edges at Nome (`edge:e091382`, `edge:e094423`,
`edge:e097314`), the Nome hub, nine facilities and three corridors. Removing the three edges from
the month's graph is the whole reroute.
"""),
        code("""
D2_EDGE_PIDS = ['e091382', 'e094423', 'e097314']
d2_ids = [r[0] for r in con.execute("SELECT edge_id FROM network_edges WHERE edge_pid IN (SELECT unnest(?::VARCHAR[]))", [D2_EDGE_PIDS]).fetchall()]
print("internal edge ids voided by D2:", d2_ids)
if HAVE_ROUTING:
    post_edges, post_cost = dijkstra(ANCH_NODE, NOME_NODE, avoid=d2_ids)
    print(f"after the closure: {len(post_edges)} edges, ${post_cost:.3f}/gal  (reference: 4,922 edges, $2.066/gal)")
    print("baseline used a voided edge:", bool(set(base_edges) & set(d2_ids)), "| reroute uses one:", bool(set(post_edges) & set(d2_ids)))
"""),
        code("""
# k shortest paths (Yen) and a cost-budget reach, both straight from SQL.
# duckrouting follows pgRouting's KSP column layout: seq, path_id, path_seq, node, edge, cost, agg_cost.
if HAVE_ROUTING:
    ksp = con.execute("SELECT * FROM duckrouting_ksp(?, ?, ?, ?)", [edges_sql(9), ANCH_NODE, NOME_NODE, 3]).df()
    display(ksp.groupby(ksp.columns[1]).agg(edges=(ksp.columns[4], 'count'), cost=(ksp.columns[-1], 'max')))
    reach = con.execute("SELECT count(*) AS nodes_within_budget FROM duckrouting_driving_distance(?, ?, ?)", [edges_sql(9), NOME_NODE, 0.5]).df()
    display(reach)   # nodes reachable from Nome for at most $0.50/gal in September
"""),
        code("""
# Connected components per month: how fragmented is the passable network in April vs September?
if HAVE_ROUTING:
    for month in (4, 9):
        comps = con.execute("SELECT * FROM duckrouting_connected_components(?)", [edges_sql(month)]).df()
        col = [c for c in comps.columns if 'comp' in c.lower()][0]
        sizes = comps.groupby(col).size().sort_values(ascending=False)
        print(f"month {month}: {len(sizes)} components, largest {sizes.iloc[0]} nodes")
"""),
        md("""
> **Callout — how an extension earns trust.** The VM tests record where duckrouting disagrees
> with the oracle and why: its `duckrouting_bridges` (Boost biconnected components) misreads
> parallel corridors and self-loops, so bridges are compared on a simplified graph; its betweenness
> returned NaN on this graph, so the oracle's `betweenness` stays the engine. Extensions are
> adopted function by function, against a reference, never wholesale.
"""),
        md("""
## 6 · Graph analytics inside SQL with **Onager**

The `region` and `global_topology` tools work on the ~2,300-corridor September graph, not on the
93,000 edges. Onager's table functions take a subquery of `(source, target)` rows.

> **Callout — Onager in the harness.** `onager_cmm_louvain` and `onager_sub_k_hop` are checked
> against the pure-Python `graph_analytics.py` on the VM. Onager's Louvain takes no weight column,
> so the harness compares it with the oracle's *unweighted* Louvain (modularity 0.862 vs 0.861) and
> keeps the inverse-cost community the `region` tool reports on the Python side. The owner also
> ruled that a graph-theory "bridge" is called a **failure corridor** everywhere agents can see it,
> because in this network a bridge is a road structure over water.
"""),
        code("""
HAVE_ONAGER = load_ext("onager")
MONTH = 9
ONAGER_EDGES = f"(SELECT node_a AS source, node_b AS target FROM corridor_graph WHERE month = {MONTH} AND passable AND cost_per_gallon IS NOT NULL)"
if HAVE_ONAGER:
    comps = con.sql(f"SELECT * FROM onager_cmm_components({ONAGER_EDGES})").df()
    print("components:", comps.iloc[:, -1].nunique(), "| nodes:", len(comps))
    louv = con.sql(f"SELECT * FROM onager_cmm_louvain({ONAGER_EDGES}, seed := 1)").df()
    print("Louvain communities:", louv.iloc[:, -1].nunique())
    khop = con.sql(f"SELECT * FROM onager_sub_k_hop({ONAGER_EDGES}, start := {NOME_NODE}, k := 2)").df()
    print("nodes within 2 corridors of Nome:", len(khop))
    display(khop.head())
"""),
        code("""
# Which Louvain community does Nome fall in, and which hubs share it?
if HAVE_ONAGER:
    node_col, comm_col = louv.columns[0], louv.columns[-1]
    con.register("louv", louv)
    nome_comm = con.execute(f"SELECT {comm_col} FROM louv WHERE {node_col} = ?", [NOME_NODE]).fetchone()
    if nome_comm:
        display(con.sql(f'''
            SELECT h.community, h.hub_pid, h.region FROM louv l JOIN hub_community h ON h.node_id = l.{node_col}
            WHERE l.{comm_col} = {nome_comm[0]} ORDER BY 1
        '''))
"""),
        md("""
## 7 · **H3** tiles: the honest spatial key

Every node, hub and facility carries an H3 cell at resolution 5 (about 17 km across) and
resolution 4. Agents cite cells in receipts and the L3 context index is grounded to them.

> **Callout — an index, never a filter.** `schema_tiles.py` writes the `tiles` table with the H3
> DuckDB extension where it loads and the `h3` Python package where it cannot, and records which in
> `schema_meta.tiles_source`. Tiles index pages and lookups; the router never filters on them.
"""),
        code("""
HAVE_H3 = load_ext("h3")
if HAVE_H3:
    mism = con.sql('''
        SELECT count(*) FROM tiles
        WHERE h3_latlng_to_cell(lat, lon, 5) <> h3_r5 OR h3_cell_to_parent(h3_r5, 4) <> h3_r4
    ''').fetchone()[0]
    print("stored tiles that disagree with the extension:", mism, "(the VM test expects 0)")
    nome_cell = con.sql("SELECT h3_r5_str FROM tiles WHERE kind='node' AND ref_id = ?", params=[NOME_NODE]).fetchone()[0]
    print("Nome's r5 cell:", nome_cell)
    display(con.sql(f'''
        WITH ring AS (SELECT unnest(h3_grid_disk(h3_string_to_h3('{nome_cell}'), 1)) AS cell)
        SELECT t.kind, count(*) AS n FROM tiles t JOIN ring r ON t.h3_r5 = r.cell GROUP BY 1
    '''))   # what sits within one ring of Nome's cell
"""),
        code("""
# facilities per r5 cell: the densest cells in the state
con.sql('''
SELECT h3_r5_str AS cell, count(*) AS facilities, any_value(f.community_name) AS a_community
FROM tiles t JOIN facilities f ON t.kind = 'facility' AND t.ref_id = f.facility_id
GROUP BY 1 ORDER BY 2 DESC LIMIT 8
''')
"""),
        md("""
## 8 · The **spatial** extension: coordinates, reprojection, GeoJSON out

Node coordinates are stored in EPSG:3338 (NAD83 / Alaska Albers, metres). The spatial extension
reprojects in SQL and exports GeoJSON that any GIS or web map can read.
"""),
        code("""
HAVE_SPATIAL = load_ext("spatial", community=False)
if HAVE_SPATIAL:
    display(con.sql('''
        SELECT n.node_id,
               ST_X(ST_Transform(ST_Point(n.x, n.y), 'EPSG:3338', 'EPSG:4326', always_xy := true)) AS lon_sql,
               t.lon AS lon_stored,
               ST_Y(ST_Transform(ST_Point(n.x, n.y), 'EPSG:3338', 'EPSG:4326', always_xy := true)) AS lat_sql,
               t.lat AS lat_stored
        FROM network_nodes n JOIN tiles t ON t.kind='node' AND t.ref_id=n.node_id
        WHERE n.is_hub LIMIT 5
    '''))
"""),
        code("""
# export the hubs as GeoJSON (GDAL driver) for QGIS or a web map
if HAVE_SPATIAL:
    con.sql('''
        COPY (SELECT hub_pid, community, region, hub_type,
                     ST_Transform(ST_Point(x, y), 'EPSG:3338', 'EPSG:4326', always_xy := true) AS geom
              FROM hub_community)
        TO 'hubs.geojson' WITH (FORMAT GDAL, DRIVER 'GeoJSON')
    ''')
    import os; print("hubs.geojson", os.path.getsize("hubs.geojson"), "bytes")
"""),
        code("""
# a quick map: baseline vs post-closure route, voided edges in red (palette from report_figures.py)
import matplotlib.pyplot as plt
PAL = {"road": "#2a78d6", "barge": "#eb6834", "plane": "#1baf7a", "ice_road": "#4a3aa7", "transfer": "#7a6a58"}
node_ll = dict(con.sql("SELECT ref_id, [lon, lat] FROM tiles WHERE kind='node'").fetchall())
ends = dict(con.sql("SELECT edge_id, [from_node, to_node] FROM network_edges").fetchall())

def draw(ax, edges, **kw):
    for e in edges:
        a, b = ends[e]
        (x1, y1), (x2, y2) = node_ll[a], node_ll[b]
        ax.plot([x1, x2], [y1, y2], **kw)

if HAVE_ROUTING:
    fig, ax = plt.subplots(figsize=(9, 6))
    hubs = con.sql("SELECT x, y, community FROM hub_community").df()
    ax.scatter(*zip(*[node_ll[n] for n in con.sql("SELECT node_id FROM hub_community").df().node_id]), s=4, c="#9aa", zorder=1)
    draw(ax, base_edges, color="#9aa", lw=2.5, alpha=0.6, label="before")
    draw(ax, post_edges, color=PAL["barge"], lw=1.4, label="after D2")
    draw(ax, d2_ids, color="#d03b3b", lw=5, label="voided edges")
    for n, name in ((ANCH_NODE, "Anchorage"), (NOME_NODE, "Nome")):
        ax.annotate(name, node_ll[n], fontsize=9, fontweight="bold")
    ax.set_xlim(-171, -147); ax.set_ylim(59.5, 66.5); ax.set_title("Anchorage → Nome, September: before and after the Port of Nome closure")
    ax.set_xlabel("lon"); ax.set_ylabel("lat")
    h, l = ax.get_legend_handles_labels(); ax.legend(dict(zip(l, h)).values(), dict(zip(l, h)).keys(), loc="lower left")
    plt.show()
"""),
        md("""
## 9 · DuckPGQ: the graph as a property graph (optional)

DuckPGQ adds SQL/PGQ `MATCH` patterns over ordinary tables. The harness only checks that it loads
(`tools/vm_first_tests`, test 6); it is shown here because it is the most readable way to ask a
graph question in SQL. Skip-safe.
"""),
        code("""
HAVE_PGQ = load_ext("duckpgq")
if HAVE_PGQ:
    try:
        pg = duckdb.connect()   # a scratch in-memory db we may write to
        pg.execute("LOAD duckpgq")
        pg.execute("ATTACH 'fuel_network.duckdb' AS fn (READ_ONLY)")
        pg.execute("CREATE TABLE hubs AS SELECT node_id, hub_pid, community FROM fn.hub_community")
        pg.execute(f'''CREATE TABLE cors AS SELECT node_a, node_b, corridor_pid, mode, cost_per_gallon
                       FROM fn.corridor_graph WHERE month = {MONTH} AND passable AND node_a IN (SELECT node_id FROM hubs) AND node_b IN (SELECT node_id FROM hubs)''')
        pg.execute('''CREATE PROPERTY GRAPH fuel
                      VERTEX TABLES (hubs PROPERTIES (node_id, hub_pid, community) LABEL hub)
                      EDGE TABLES (cors SOURCE KEY (node_a) REFERENCES hubs (node_id)
                                        DESTINATION KEY (node_b) REFERENCES hubs (node_id)
                                        PROPERTIES (corridor_pid, mode, cost_per_gallon) LABEL corridor)''')
        display(pg.sql('''FROM GRAPH_TABLE (fuel
                          MATCH (a:hub WHERE a.community = 'Nome')-[c:corridor]-(b:hub)
                          COLUMNS (b.community, b.hub_pid, c.mode, c.cost_per_gallon)) ORDER BY 4 LIMIT 10'''))
    except Exception as e:
        print("DuckPGQ loaded but the pattern query failed here:", str(e)[:200])
"""),
        md("""
## 10 · Full-text search over the concept map pages

> **Callout — the L3 `search_context` tool.** Context documents are cut into chunks and ranked with
> BM25, in Python by default or with DuckDB's `fts` extension when it loads; every result records
> which engine answered. Here the same mechanism runs over a few dozen hub pages of the concept map.
""")
        ,
        code("""
# fetch ~40 hub pages of the OKF concept map through the same API (small markdown files)
import json
def gh_json(path):
    r = requests.get(f"https://api.github.com/repos/{REPO}/contents/{path}?ref={HARNESS_COMMIT}",
                     headers={"Authorization": f"Bearer {GH_TOKEN}", "Accept": "application/vnd.github+json"}, timeout=60)
    r.raise_for_status(); return r.json()
def gh_raw(path):
    r = requests.get(f"https://api.github.com/repos/{REPO}/contents/{path}?ref={HARNESS_COMMIT}",
                     headers={"Authorization": f"Bearer {GH_TOKEN}", "Accept": "application/vnd.github.raw+json"}, timeout=60)
    r.raise_for_status(); return r.text
index = json.loads(gh_raw("okf/_index.json"))
hub_pages = [v["path"] for k, v in index.items() if v["kind"] == "hub"][:40]
pages = pd.DataFrame({"path": hub_pages, "body": [gh_raw("okf/" + p) for p in hub_pages]})
print(len(pages), "pages; e.g.", pages.path[0])
"""),
        code("""
HAVE_FTS = load_ext("fts", community=False)
if HAVE_FTS:
    mem = duckdb.connect()
    mem.execute("LOAD fts")
    mem.register("pages_src", pages)
    mem.execute("CREATE TABLE pages AS SELECT row_number() OVER () AS i, path, body FROM pages_src")
    mem.execute("PRAGMA create_fts_index('pages', 'i', 'body', stemmer='none', stopwords='none', ignore='(\\\\.|[^a-z0-9])+', lower=true)")
    display(mem.sql('''
        SELECT path, round(fts_main_pages.match_bm25(i, 'barge transfer receiver'), 3) AS score
        FROM pages WHERE score IS NOT NULL ORDER BY score DESC LIMIT 5
    '''))
"""),
        md("""
## 11 · Where the agents meet the database

The tools an agent calls are thin wrappers around queries like the ones above, plus one thing the
raw database does not give you: a **receipt**. Every call is logged with an `r-####` id, its
arguments and a hash of its result, and a report may only cite receipts the run actually received.
The second notebook calls those tools directly.

A last export, for anyone who wants the hub table in another tool:
"""),
        code("""
con.sql("COPY (SELECT * FROM hub_community) TO 'hub_community.parquet' (FORMAT PARQUET)")
import os; print("hub_community.parquet", os.path.getsize("hub_community.parquet"), "bytes")
con.close()
"""),
    ]
    return notebook(cells, "00 · DuckDB on the Alaska fuel network")


# --------------------------------------------------------------------------
# 01 · Explore the tools, no LLM
# --------------------------------------------------------------------------
def nb_tools():
    cells = [
        md(f"""
# Call the agents' tools yourself (no language model)

{COLAB_BADGE.format(demo=DEMO, nb='01_explore_the_tools.ipynb')}

Everything an agent can do with the network, it does through about thirty tools behind a
**receipt gate**: each call is checked against the layers the run has been granted, executed,
stored under an `r-####` id, and logged. This notebook plays the harness and the agent at once:
it opens a run folder, grants layer L1, calls the tools, delivers the D2 storm notice, and watches
the tool surface grow.

No model is involved and nothing costs money. Needs a read-only GitHub token in Colab Secrets.
"""),
        md("## 1 · Get the harness at the pinned commit"),
        TOKEN_CELL,
        CLONE_CELL,
        code("""
# the small runtime subset: DuckDB, H3 (route receipts carry tiles), YAML (the community list),
# jsonschema (report tools), pypdf (context reads), mcp (to list the server surface)
%pip -q install duckdb==1.5.6 h3 pyyaml jsonschema pypdf "mcp>=1.23,<2"
"""),
        md("""
## 2 · Open a run folder and grant layer L1

A run is a folder. `DOE_MAS_RUN_DIR` points the tools at it; `layer_grants.jsonl` inside it says
which layers are open. Nothing answers until a grant is written, and tools of a layer the run does
not have answer exactly like tools that do not exist.
"""),
        code("""
import os, json, pathlib
RUN = pathlib.Path("/content/demo_run") if pathlib.Path("/content").exists() else pathlib.Path("demo_run").resolve()
RUN.mkdir(exist_ok=True)
os.environ["DOE_MAS_RUN_DIR"] = str(RUN)
os.environ["DOE_MAS_ALLOW_PROVISIONAL_COMMUNITY_LIST"] = "1"   # the community list is still marked provisional
os.environ["DOE_MAS_GRAPH_ENGINE"] = "python"                  # the oracle router; no extension needed

from agentic_harness_workflow import checkpoints, layer_tools
checkpoints.write_grants(RUN, ["L1"], "provisioned")
print(open(RUN / "layer_grants.jsonl").read())
print("tools on the surface with L1:", layer_tools.tools_for_layers(["L1"]))
"""),
        md("""
## 3 · The same surface over MCP

The crew topology does not import the tools; it starts the harness's **MCP server** as a separate
process and talks to it over standard input and output. `--list` prints what a client would see,
read from the run folder's grants.
"""),
        code("""
!DOE_MAS_RUN_DIR=$DOE_MAS_RUN_DIR python -m agentic_harness_workflow.mcp_server --list | python -c "import json,sys; t=json.load(sys.stdin); print(len(t), 'tools'); [print(' -', x['name'], '|', x['description'][:70]) for x in t]"
"""),
        md("## 4 · Orient: describe, resolve, lookup"),
        code("""
def call(name, **kw):
    out = layer_tools.call_tool(name, **kw)
    view = json.loads(out)
    print(f"{name} -> receipt {view.get('r_id')} ({view.get('rows_returned')} rows{', truncated view' if view.get('truncated') else ''})")
    return view

d = call("describe")
print([r["relation"] for r in d["data"]["relations"]][:12], "...")
print("id kinds:", d["data"].get("id_kinds") or d["data"].get("ids"))
"""),
        code("""
r = call("resolve", name="Nome")
print(json.dumps(r["data"], indent=1)[:900])
NOME = [m for m in r["data"]["matches"]][0]["hubs"][0] if r["data"].get("matches") else "hub:h000493"
ANCHORAGE = "hub:h000698"
print("Nome resolves to", NOME)
"""),
        code("""
fac = call("lookup", kind="hub_facility_map", hub=NOME)
print(json.dumps(fac["data"], indent=1)[:700])
"""),
        md("""
## 5 · Route, and read the receipt

The view you get back is deliberately short. The **receipt** holds the complete path. A report
never copies 4,899 edge ids; it commits the leg *by reference* to the receipt.
"""),
        code("""
rt = call("route", hubs=[ANCHORAGE, NOME], month=9)
legs = rt["data"]["legs"]
for leg in legs:
    print(f"  leg {leg['leg']}: {leg['mode']:9s} {leg['n_edges']:5d} edges  ${leg['cost_per_gallon']:.3f}/gal  {leg['length_km']:.0f} km  {leg['first_edge']} .. {leg['last_edge']}")
print("total", rt["data"].get("totals") or {k: rt["data"][k] for k in rt["data"] if k.startswith("total")})
ROUTE_RECEIPT = rt["r_id"]
"""),
        code("""
# page through the receipt with the budget-free `read` tool
page = call("read", handle=ROUTE_RECEIPT, select="data/legs/0", limit=5)
print(json.dumps(page["data"], indent=1)[:600])
"""),
        md("""
## 6 · Deliver the storm notice and watch the surface grow

The harness, not the agent, decides when layer L2 opens. `deliver_disruption` renders the frozen
delivery template around the D2 notice, records the delivery, and grants L2. Two tools appear.
"""),
        code("""
before = set(layer_tools.tools_for_layers(["L1"]))
notice = checkpoints.deliver_disruption(RUN, "D2")
print(notice[:1400], "\\n...")
after = set(layer_tools.tools_for_layers(["L1", "L2"]))
print("\\nnew tools:", sorted(after - before))
print(open(RUN / "layer_grants.jsonl").read())
"""),
        code("""
# Which of MY ids does the disruption touch? The tool answers only about the ids you pass.
mine = [leg["first_edge"] for leg in legs] + [leg["last_edge"] for leg in legs] + [NOME, ANCHORAGE]
imp = call("check_disruption_impact", ids=mine)
for row in imp["data"]:
    print(f"  {row['id']:16s} {row['status']}")
"""),
        md("""
## 7 · Reroute with `perturb`

`perturb` runs the same delivery with a mask you state (edge, corridor or hub ids) and returns the
unmasked and the rerouted path side by side, with the cost delta. Its receipt commits the reroute.
"""),
        code("""
voided_edges = ["edge:e091382", "edge:e094423", "edge:e097314"]
p = call("perturb", hub_a=ANCHORAGE, hub_b=NOME, month=9, avoid=voided_edges)
d = p["data"]
print("outcome:", d.get("outcome"))
print("cost delta $/gal:", d.get("cost_delta") or d.get("delta_cost_per_gallon"), "| length delta km:", d.get("length_delta_km") or d.get("delta_length_km"))
print("masked edges the old path used:", d.get("masked_edges_used") or d.get("used_masked_edges"))
"""),
        md("## 8 · The concept map, one page per call"),
        code("""
node = call("read_node", id=NOME)
print(node["data"]["frontmatter"]["title"], "|", len(node["data"]["frontmatter"].get("links", [])), "links")
print(node["data"].get("body", node["data"].get("text", ""))[:800])
"""),
        md("""
## 9 · The ledger an agent leaves behind

Every call above is one line in `tool_log.jsonl`, with the full payload under `tool_results/`.
This is what the scorers read when they check a report's citations, and what the blind judge is
*not* shown.
"""),
        code("""
for line in open(RUN / "tool_log.jsonl"):
    rec = json.loads(line)
    print(f"{rec['r_ids']} {rec['tool']:24s} layer {rec['layer']}  {rec['bytes_returned']:6d} bytes  args={json.dumps(rec['args'])[:60]}")
print("\\nfiles in the run folder:", sorted(p.name for p in RUN.iterdir()))
"""),
        md("""
### Where to go next

* The first notebook opens the same database directly with DuckDB and its extensions.
* The third runs the whole `lin` team with an open model on a GPU runtime.
* `agentic_harness_workflow/README.md` in the harness maps every file to its place in a run.
"""),
    ]
    return notebook(cells, "01 · Call the agents' tools (no LLM)")


# --------------------------------------------------------------------------
# 02 · Run lin with Ollama
# --------------------------------------------------------------------------
def nb_lin():
    cells = [
        md(f"""
# Run the linear team with an open-weight model

{COLAB_BADGE.format(demo=DEMO, nb='02_run_lin_with_ollama.ipynb')}

This notebook runs one full progressive chain of the **`lin`** topology (plan → D2 storm notice →
revision → context release → reassessment) on the Bering Straits task, with an open-weight model
served locally by **Ollama** on Colab's GPU. At the end you download the run folder; the demo's
build script adds it to the map as "your run".

**Runtime:** choose *Runtime → Change runtime type → T4 GPU* (or better) before starting.
Expect 20–60 minutes for the model pulls and the run. Nothing leaves the machine except the
download to your browser.

**What this is not.** The study ran Claude Haiku 4.5 / Sonnet 4.6 (frozen tiers) and, for
shakedowns, DeepSeek V3.2. A 7–14 B open model on a T4 is a plumbing demonstration; it may plan
poorly or fail a checkpoint. That is part of what the harness makes visible: the save gate still
rejects invented ids, and the ledger still records every call.
"""),
        md("## 1 · Harness at the pinned commit, plus its runtime dependencies"),
        TOKEN_CELL,
        CLONE_CELL,
        code("""
import subprocess, sys
gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"], capture_output=True, text=True)
print("GPU:", gpu.stdout.strip() or "none found — switch the runtime to a GPU before continuing")
"""),
        code("""
# the harness's runtime subset (crewai is what pipeline.get_llm uses to talk to Ollama)
%pip -q install -r requirements-harness.txt
"""),
        md("""
## 2 · Start Ollama and pull an open model

The harness prompts are long (the task specification, data guide, skills and tool docs run to tens
of thousands of tokens), and `pipeline._get_llm_ollama` sets no context size, so the server is
started with `OLLAMA_CONTEXT_LENGTH=32768`. A 14 B model at 4-bit fits a T4 (16 GB); the 8 B
fallback is faster.
"""),
        code("""
import os, subprocess, time, requests
MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:14b")       # fallback: "llama3.1:8b"
subprocess.run("curl -fsSL https://ollama.com/install.sh | sh", shell=True, check=True)
env = dict(os.environ, OLLAMA_CONTEXT_LENGTH="32768", OLLAMA_KEEP_ALIVE="2h")
server = subprocess.Popen(["ollama", "serve"], env=env, stdout=open("ollama.log", "w"), stderr=subprocess.STDOUT)
for _ in range(60):
    try:
        requests.get("http://localhost:11434/api/tags", timeout=2); break
    except Exception:
        time.sleep(1)
subprocess.run(["ollama", "pull", MODEL], check=True)
print(requests.get("http://localhost:11434/api/tags").json())
"""),
        code("""
os.environ["LLM_PROVIDER"] = "ollama"
os.environ["OLLAMA_MODEL"] = MODEL
os.environ["OLLAMA_API_BASE"] = "http://localhost:11434"
import pipeline
pipeline.check_llm()      # a one-token round trip through the harness's own LLM factory
"""),
        md("""
## 3 · Preflight

The runner refuses a real run unless the frozen manifest verifies and the fairness audit passes on
this checkout. Both should pass on the pinned commit; if they do not, stop and read the message.
"""),
        code("""
!python -m agentic_harness_workflow.manifest verify
!python -m agentic_harness_workflow.audit
"""),
        md("""
## 4 · Run one `lin` chain

`--arm pilot --cell progressive` builds the seeded run plan for the Bering Straits scenario and
`--topology lin --limit 1` keeps the first linear run. Output goes under `DOE_MAS_OUTPUT_ROOT`.
Watch the log: each stage prints its data rounds, and each checkpoint ends with the save gate's
verdict.
"""),
        code("""
import pathlib
OUT = pathlib.Path("/content/runs") if pathlib.Path("/content").exists() else pathlib.Path("runs").resolve()
OUT.mkdir(exist_ok=True)
os.environ["DOE_MAS_OUTPUT_ROOT"] = str(OUT)
os.environ["DOE_MAS_ALLOW_PROVISIONAL_COMMUNITY_LIST"] = "1"
SEED = 20261101
!python -m agentic_harness_workflow.run_experiment run --arm pilot --scenario bering_straits_annual_v1 --cell progressive --topology lin --limit 1 --seed $SEED 2>&1 | tail -n 80
"""),
        md("## 5 · What came out"),
        code("""
import json
runs = sorted(list(OUT.glob("arm_*/run-*")) + list(OUT.glob("arm_*/runs/run-*")))
assert runs, "no run folder found; read the log above"
run = runs[-1]
print(run)
for name in sorted(p.name for p in run.iterdir()):
    print("  ", name)
m = json.loads((run / "run_summary_manifest.json").read_text())
print(json.dumps({k: m[k] for k in ("cell", "failure") if k in m}, indent=1))
print("reports:", {k: (v or {}).get("sha256", "")[:12] for k, v in (m.get("reports") or {}).items()})
"""),
        code("""
for ck in ("plan", "revision", "reassessment"):
    p = run / f"report_{ck}.json"
    if not p.exists():
        print(ck, ": not saved"); continue
    rep = json.loads(p.read_text())
    routes = rep["plan"]["routes"]
    print(f"{ck}: {len(routes)} routes, {len(rep['claims'])} claims, served {len(rep['coverage']['facilities_served'])}, unserved {len(rep['coverage']['facilities_unserved'])}")
    print("   summary:", (rep["summary"] or "")[:200].replace("\\n", " "))
"""),
        md("""
## 6 · Download the run folder

Zip it and download. In the demo repository, run

```
python build/build_all.py --harness <harness clone> --fresh-run <unzipped run folder> --fresh-model "<model> via Ollama"
```

and the run appears on the map's fourth state as **"Your run (open model, Colab)"**, flagged as a
notebook run rather than study data.
"""),
        code("""
import shutil
zip_path = shutil.make_archive(str(OUT / f"{run.name}_{MODEL.replace(':', '-')}"), "zip", run)
print(zip_path)
try:
    from google.colab import files  # type: ignore
    files.download(zip_path)
except Exception:
    print("not on Colab: the zip is at", zip_path)
"""),
    ]
    return notebook(cells, "02 · Run lin with an open model (Ollama)")


def main():
    OUT.mkdir(exist_ok=True)
    for name, nb in (("00_duckdb_fuel_network.ipynb", nb_duckdb()),
                     ("01_explore_the_tools.ipynb", nb_tools()),
                     ("02_run_lin_with_ollama.ipynb", nb_lin())):
        nbf.validate(nb)
        nbf.write(nb, OUT / name)
        print("wrote", OUT / name, len(nb.cells), "cells")


if __name__ == "__main__":
    main()
