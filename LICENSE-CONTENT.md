# Content licence

The explanatory text of the site, the notebooks, `README.md`, and the derived data files in
`site/data/` (hub, facility and corridor extracts; route geometries; the disruption bundle; the
archived report extracts; the text bundle) are licensed under the
**Creative Commons Attribution 4.0 International** licence (CC BY 4.0):
https://creativecommons.org/licenses/by/4.0/

Attribution: *Julia Cheesman, Erin Trochim, Diego Arias Arana — Geospatial Agentic Harness for
Alaska's fuel network, University of Alaska Fairbanks; Department of Energy.*

## What is covered and where it comes from

| Material | Source | Status |
|---|---|---|
| Harness text shown verbatim (skills, adapters, tool docstrings, deliveries, concept-map pages, data guide, report format, glossary) | `jccheesman/agentic_harness_for_alaska_fuel_network` at commit `8eef6ac1…` | Owner-authored; republished here under CC BY 4.0 |
| Network extracts and route geometries | `fuel_network.duckdb` in the harness, built from `jccheesman/alaska-fuel-spatial-network` | Derived data; check the data repository's own licence before redistributing further |
| Archived agent reports and their figures | `run_archives/2026-10-22_…` in the harness | AI-generated research records (DeepSeek V3.2), reproduced verbatim; see `NOTICE.md` |
| Coastline (`site/data/land.geojson`) | Natural Earth, via `nvkelso/natural-earth-vector` | Public domain |
| MapLibre GL JS (`site/vendor/maplibre-gl/`) | maplibre.org | BSD-3-Clause (licence file included) |
| IBM Plex fonts (loaded from Google Fonts, optional) | IBM | SIL Open Font License 1.1 |

Third-party documents the harness exposes to agents at layer L3 (market, fiscal, sector and
strategic reports under the harness's `inputs/`) are **not** included in this repository in any
form; the site lists their titles only.
