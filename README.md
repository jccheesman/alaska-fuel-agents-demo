# Alaska Fuel Agents Demo

A teaching demo of the agentic harness built around Alaska's fuel-delivery network, for
researchers who are new to agents, agent skills, harnesses, MCP servers and the four
team paradigms the study compares (`lin`, `crew`, `mass`, `self`).

**Live site:** https://jccheesman.github.io/alaska-fuel-agents-demo/

The page explains the vocabulary, shows the five skills and the 29 tools as the agents read
them, walks the life of a run, and centers on an interactive map in four states:

1. **Before the storm** — the network the agents query (corridors by month and mode) and the
   reference routes from Anchorage to the 20 Bering Straits hubs.
2. **The storm hits** — disruption D2 closes the Port of Nome: the 19 voided elements, and which
   baseline routes break.
3. **Reference reroute** — the deterministic answer key after the closure.
4. **What the agents did** — one archived run per paradigm (plan, revision, reassessment),
   shown verbatim with the study's own caveats.

Three Colab notebooks go with it (`notebooks/`): DuckDB on the real database (with duckrouting,
Onager, H3, spatial, DuckPGQ and full-text search), the agents' tools without a model, and a
full `lin` run with an open-weight model served by Ollama on a GPU runtime.

## How it is built

Nothing here is edited by hand from the harness. `build/build_all.py` reads a clone of the
harness repository at a **pinned commit** and writes small JSON files into `site/data/`:

```
python -m venv .venv && . .venv/bin/activate
pip install -r build/requirements-build.txt
python build/build_all.py --harness ../agentic_harness_for_alaska_fuel_network
python build/make_notebooks.py          # regenerates notebooks/*.ipynb
```

The build asserts the harness commit (`8eef6ac1…`, branch `refine-tools-MCP`) and the SHA-256 of
`fuel_network.duckdb`, resolves every route edge id, validates each output against
`build/schemas/`, and refuses to finish above a size budget. `site/data/provenance.json` records
what was built from what.

To add a fresh run (for example the one notebook 02 produces):

```
python build/build_all.py --harness <clone> --fresh-run <unzipped run folder> --fresh-model "qwen2.5:14b via Ollama"
```

The site is plain static files: `site/index.html`, `site/css/`, `site/js/` (ES modules, no
bundler), `site/vendor/maplibre-gl/` (MapLibre GL JS 4.7.1, BSD) and `site/data/`. The basemap is
a bundled Natural Earth coastline, so the page makes no request to any tile server and works
offline. Serve it locally with `python -m http.server -d site 8765`.

`verify/screenshot_states.mjs` walks the map states in headless Chromium with external hosts
blocked and fails on any console or request error:

```
node verify/screenshot_states.mjs --phone
```

## Repository layout

```
build/        extraction scripts, schemas, caveats.yaml, notebook generator
site/         the static site (index.html, css, js, vendor, data, img)
notebooks/    the three Colab notebooks
verify/       headless-browser walkthrough
.github/      GitHub Pages deployment and the verification workflow
```

## Provenance and honesty

* Data: the harness's `fuel_network.duckdb`, built from the public data repository
  [alaska-fuel-spatial-network](https://github.com/jccheesman/alaska-fuel-spatial-network).
  Edge costs are modeled values (miles × friction × a per-mode rate), not observed prices.
* Reference routes: `agentic_harness_workflow/tests/reference_answers/routes.json` (September,
  disruption D2).
* Agent reports: the arm `run_archives/2026-10-22_bering_straits_annual_v1_deepseek-v3.2_fuse_seed20261022`,
  one finished run per topology, DeepSeek V3.2 on both tiers. They are AI-generated research
  records shown as saved, including their mistakes; `build/caveats.yaml` paraphrases the arm's own
  `FINDINGS.md` beside each report. Nothing in them is advice.
* Third-party documents the agents read at layer L3 are **not** reproduced; the site shows
  document titles only.
* The harness repository is private while the study is under way. The notebooks therefore read a
  read-only GitHub token from Colab Secrets (`GH_TOKEN`); the site itself needs no credentials
  because its data is committed here.

## License

Code: MIT (`LICENSE`). Text and derived data in `site/data/`, `notebooks/` and this README:
CC BY 4.0 (`LICENSE-CONTENT.md`). Attribution: Julia Cheesman, Erin Trochim, Diego Arias Arana,
University of Alaska Fairbanks; Department of Energy. See `NOTICE.md` for the status of the
AI-generated reports and third-party components.
