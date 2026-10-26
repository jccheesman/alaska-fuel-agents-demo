# Notice

**AI-generated content.** The agent reports shown on the map's fourth state and in the results
table (`site/data/agent_runs.json`, `site/img/revision_overview_*.png`) were produced by language
models (DeepSeek V3.2 via OpenRouter) inside the research harness on 2026-10-22. They are
reproduced exactly as the agents saved them, including factual and planning errors that the
study's own read-out documents. They are research records, not recommendations, and nothing on
the site should be read as operational advice about fuel delivery in Alaska.

**Modeled costs.** Every cost per gallon on the site is a modeled value from the data
pipeline (distance × environmental friction × a per-mode rate), not an observed price.

**Scenario status.** The scenario and disruption files in the harness carry the status
`authored_2026-10-01_pending_owner_review`; the community list used by the `resolve` tool is marked
provisional. The demo reflects the harness at one pinned commit.

**Third-party components.** MapLibre GL JS (BSD-3-Clause), Natural Earth (public domain),
IBM Plex (OFL 1.1). DuckDB and its community extensions (duckrouting, Onager, H3, spatial,
DuckPGQ, fts) are used by the notebooks under their own licenses and are not vendored here.
