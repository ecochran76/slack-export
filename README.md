# Slack Exporter

A Python script to export Slack conversations, canvases, and files.

This repo also contains the newer `slack_mirror` package for multi-workspace ingest, local search, and always-on live sync. For current live-ops setup, use the runbooks in [docs/dev/LIVE_MODE.md](/home/ecochran76/workspace.local/slack-export/docs/dev/LIVE_MODE.md) and [docs/CLI.md](/home/ecochran76/workspace.local/slack-export/docs/CLI.md).
For the shipped local API and MCP response semantics, including outbound writes and listener deliveries, see [docs/API_MCP_CONTRACT.md](/home/ecochran76/workspace.local/slack-export/docs/API_MCP_CONTRACT.md).

## New Install Quickstart

For the canonical fresh-install-to-first-workspace path, start with [docs/dev/USER_INSTALL.md](/home/ecochran76/workspace.local/slack-export/docs/dev/USER_INSTALL.md).

The supported operator sequence is:

1. `uv run slack-mirror user-env install`
2. edit `~/.config/slack-mirror/config.yaml`
3. `slack-mirror-user workspaces sync-config`
4. `slack-mirror-user workspaces verify --require-explicit-outbound`
5. `scripts/install_live_mode_systemd_user.sh <workspace>`
6. `slack-mirror-user user-env check-live`
7. `slack-mirror-user user-env provision-frontend-user --username <identity> --password-env <ENV_VAR>`
8. browser smoke on `http://slack.localhost/login`

Use these companion docs for detail, not as separate competing entrypoints:

- install and onboarding: [docs/dev/USER_INSTALL.md](/home/ecochran76/workspace.local/slack-export/docs/dev/USER_INSTALL.md)
- config fields and token semantics: [docs/CONFIG.md](/home/ecochran76/workspace.local/slack-export/docs/CONFIG.md)
- live per-workspace services: [docs/dev/LIVE_MODE.md](/home/ecochran76/workspace.local/slack-export/docs/dev/LIVE_MODE.md)

For release smoke and unattended installs, treat `slack-mirror user-env check-live` as the managed-runtime gate. It now verifies:

- wrapper and unit-file presence for the managed CLI, API, MCP, and runtime-report surfaces
- active `slack-mirror-runtime-report.timer` scheduling
- a real MCP stdio health probe through `slack-mirror-mcp`
- a bounded concurrent MCP readiness probe across multiple simultaneous wrapper launches
- full live validation for config, DB, workspace sync, tokens, queue health, and live units

For release signoff from a repo checkout, use `slack-mirror release check --require-managed-runtime` to combine repo release discipline with the installed `slack-mirror-user user-env check-live --json` gate. Keep plain `slack-mirror release check` for repo-only development machines that do not have a managed install.

For agent clients, use the managed MCP launcher at `~/.local/bin/slack-mirror-mcp` after `check-live` passes. The supported release-baseline MCP tool groups, outbound-write cautions, listener workflow, tracing flags, and non-goals are documented in [docs/API_MCP_CONTRACT.md](/home/ecochran76/workspace.local/slack-export/docs/API_MCP_CONTRACT.md#mcp-release-baseline).

A fresh `user-env install` is intentionally narrower: it bootstraps the managed runtime, seeds the configured dotenv file if needed, and leaves workspace credentials plus live units for the later onboarding steps.

For adding another tenant/workspace to an existing managed install, prefer the guided scaffold path:

```bash
slack-mirror-user tenants onboard \
  --name polymer \
  --domain polymerconsul-clo9441 \
  --display-name "Polymer Consulting Group"
slack-mirror-user tenants credentials polymer --credential token=... --credential outbound_token=... --credential app_token=... --credential signing_secret=...
slack-mirror-user tenants status polymer
slack-mirror-user tenants activate polymer
```

The same config-backed onboarding and local credential-install flow is available in the authenticated browser at `http://slack.localhost/settings/tenants`. Tenant cards refresh in place after scaffold, credential install, activation, live-control, backfill, and retire actions, and the manifest is exposed through a `Copy Manifest JSON` button so it can be pasted directly into Slack's app-manifest UI.
Tenant tiles on that page also expose guarded activation, bounded backfill, live-sync start/restart/stop, and guarded tenant retirement controls.
Bounded initial sync now persists durable reconcile-state evidence, so a successful browser-triggered backfill clears the misleading `needs_initial_sync` state on the tenant tile.
For operator visibility, the authenticated browser also exposes a bounded logs surface at `http://slack.localhost/logs` for tenant live units plus the shared API and runtime-report services.

## Current Live Topology

For unattended live operation, the supported systemd user-service topology is:

- one `serve-socket-mode` unit per workspace
- one unified `daemon` unit per workspace

Do not run the older split `process-events` and `process-embedding-jobs` units alongside the unified daemon for the same workspace. That creates duplicate writers against the same SQLite DB and can lead to lock contention.

Useful commands:

```bash
scripts/install_live_mode_systemd_user.sh default
scripts/install_live_mode_systemd_user.sh soylei
scripts/live_mode_status_all.sh
slack-mirror user-env validate-live
slack-mirror user-env validate-live --json
slack-mirror --config ~/.config/slack-mirror/config.yaml mirror status --workspace default --healthy --enforce-stale
slack-mirror user-env check-live
slack-mirror user-env check-live --json
slack-mirror user-env status --json
slack-mirror user-env provision-frontend-user --username ecochran76@gmail.com --password-env SLACK_MIRROR_BOOTSTRAP_PASSWORD
slack-mirror user-env snapshot-report
slack-mirror user-env snapshot-report --name morning-ops --json
python scripts/render_runtime_report.py --base-url http://slack.localhost --format markdown --output /tmp/slack-mirror-runtime-report.md
python scripts/render_runtime_report.py --base-url http://slack.localhost --format html --output /tmp/slack-mirror-runtime-report.html
slack-mirror user-env recover-live
slack-mirror user-env recover-live --apply
slack-mirror user-env rollback
slack-mirror mirror process-derived-text-jobs --workspace default
slack-mirror mirror process-derived-text-jobs --workspace default --kind ocr_text
slack-mirror mirror reconcile-files --workspace default --auth-mode user --limit 100
slack-mirror mirror reconcile-files --workspace default --auth-mode user --limit 100 --json
python scripts/export_channel_day_docx.py --input-json exports/day.json --output-docx exports/day.docx
python scripts/export_channel_day_docx.py --input-json exports/day.json --output-docx exports/day.docx --font-family Aptos --font-size-pt 11 --margin-in 1.25 --compactness cozy --accent-color 8B5CF6
python scripts/export_multi_day_docx.py --inputs exports/*.json --output-docx exports/daypack.docx
python scripts/render_export_docx_fixtures.py --output-dir exports/docx-fixtures
python scripts/validate_export_docx.py --input-docx exports/day.docx --json --fail-on-issues
PYTHONPATH=. ./.venv/bin/python scripts/export_channel_day.py --config ~/.config/slack-mirror/config.yaml --db ~/.local/state/slack-mirror/slack_mirror.db --workspace default --channel general --day 2026-04-12 --managed-export --link-audience local
slack-mirror api serve
slack-mirror search derived-text --workspace default --query "incident review"
slack-mirror search derived-text --workspace default --query "invoice total" --kind ocr_text
slack-mirror search corpus --workspace default --query "incident review" --mode hybrid
slack-mirror search corpus --workspace default --query "incident review" --mode hybrid --rerank --rerank-top-n 50
slack-mirror search corpus --workspace default --query "incident review" --mode hybrid --fusion rrf --explain
slack-mirror search corpus --all-workspaces --query "incident review" --mode hybrid
slack-mirror search profiles
slack-mirror search semantic-readiness --workspace default --json
slack-mirror search corpus --workspace default --query "incident review" --retrieval-profile baseline
slack-mirror search context-pack --targets-json '[{"kind":"message","workspace":"default","channel_id":"C123","ts":"1712870400.000100"}]' --before 2 --after 2 --json
slack-mirror search context-pack --targets-json '[{"kind":"message","workspace":"default","channel_id":"C123","ts":"1712870400.000100"}]' --managed-export --title "Selected incident context" --json
slack-mirror search scale-review --workspace default --profiles baseline --query "incident review" --repeats 2 --limit 5 --json
slack-mirror search benchmark-validate --workspace default --dataset ./docs/dev/benchmarks/slack_live_relevance_noncontent.jsonl --profiles baseline,local-bge-http --json
slack-mirror search profile-benchmark --workspace default --dataset ./docs/dev/benchmarks/slack_smoke.jsonl --profiles baseline,local-bge-http --json
slack-mirror search profile-benchmark --workspace default --dataset ./docs/dev/benchmarks/slack_live_relevance_noncontent.jsonl --profiles baseline,local-bge-http --fusion rrf --json
slack-mirror search benchmark-diagnose --workspace default --dataset ./docs/dev/benchmarks/slack_live_relevance_noncontent.jsonl --profiles baseline,local-bge-http,local-bge-http-rerank --json
slack-mirror search benchmark-query-variants --workspace default --dataset ./docs/dev/benchmarks/slack_live_relevance_noncontent.jsonl --profiles baseline,local-bge-http --variants original,lowercase,dehyphen,alnum --json
slack-mirror mirror benchmark-embeddings-backfill --workspace default --dataset ./docs/dev/benchmarks/slack_live_relevance_noncontent.jsonl --retrieval-profile local-bge-http --json
slack-mirror mirror rollout-plan --workspace default --retrieval-profile local-bge --limit 500 --json
slack-mirror search health --workspace default
slack-mirror search health --workspace default --dataset ./docs/dev/benchmarks/slack_corpus_smoke.jsonl
slack-mirror search health --workspace default --target derived_text --dataset ./docs/dev/benchmarks/slack_derived_text_smoke.jsonl --mode semantic
slack-mirror search health --workspace default --dataset ./docs/dev/benchmarks/slack_corpus_depth.jsonl
slack-mirror release check
slack-mirror release check --require-managed-runtime
slack-mirror release check --require-clean --require-release-version
./.venv/bin/python -m unittest discover -s tests -v
```

## Search Direction

The current repo has:

- keyword, semantic, and hybrid message search
- first-class derived-text storage for files and canvases
- a queued attachment-text extraction path for canvases, UTF-8 text-like files, OOXML and OpenDocument office files (`.docx`, `.pptx`, `.xlsx`, `.odt`, `.odp`, `.ods`), with `.docx` extraction now including visible text from document, header, footer, footnote, and endnote story parts, `.pptx` extraction now using visible slide text, `.xlsx` extraction now resolving shared strings, inline strings, and numeric cell values, and machine-readable PDFs when `pdftotext` is available
- an OCR-derived text path for image-like files and scanned PDFs when `tesseract` and `pdftoppm` are available
- a shared extraction-provider boundary that keeps the current host-local toolchain as the default path and now supports optional command-backed and HTTP-backed providers selected from config, with local extraction retained as the fallback path by default
- a corpus-wide hybrid search path over messages plus derived text through `search corpus`
- an explicit cross-workspace corpus-search path through `search corpus --all-workspaces`
- chunk-aware derived-text retrieval so long attachments and OCR-heavy documents surface the matching segment instead of only the top-level document row
- a machine-readable search health path over readiness plus optional smoke benchmarks through `search health`
- a shared embedding-provider seam under `slack_mirror.search.embeddings`, with the current `local-hash-128` baseline now owned in one place across sync-time embedding jobs and query-time semantic retrieval
- provider-routed message embeddings, so message embedding jobs and message-backed corpus search can now resolve through either:
  - the built-in `local_hash` baseline
  - an optional `sentence_transformers` local provider for stronger models such as `BAAI/bge-m3`
- config-driven message-semantic provider selection through `search.semantic.provider`, while keeping `search.semantic.model` as the canonical model selector
- a repo-owned semantic provider probe at `slack-mirror search provider-probe`, so GPU/runtime readiness can be checked before attempting a heavier local semantic model rehearsal
- bounded message-embedding rollout controls through `slack-mirror mirror embeddings-backfill --channels ... --oldest ... --latest ... --order ...`
- persisted derived-text chunk embeddings keyed by chunk id and model id, so semantic attachment/OCR search can reuse stored vectors instead of embedding every chunk at query time
- semantic derived-text search now routes through the same configured embedding provider/model seam as messages, while preferring stored chunk vectors when they exist
- bounded derived-text chunk rollout controls through `slack-mirror mirror derived-text-embeddings-backfill --kind ... --source-kind ... --order ...`
- model-aware readiness and health reporting, so partial rollout of the configured semantic model is visible instead of silently looking complete
- an explicit derived-text benchmark target through `search health --target derived_text`, with chunk-aware benchmark query reports for attachment/OCR evaluation
- an explicit reranker-provider seam, with the current heuristic reranker available for opt-in message and corpus searches before learned local reranking is introduced
- an optional learned local reranker provider through `sentence_transformers` CrossEncoder models, with a readiness/smoke probe before use
- a loopback-only local inference service boundary through `search inference-serve`, so heavier embedding and reranker models can stay warm for CLI/API/MCP clients instead of paying cold-load cost per process
- HTTP-backed embedding and reranker providers that can target the same local inference service with the existing `embed_texts` and `rerank_score` request shapes
- corpus hybrid search now has explicit fusion policy controls:
  - `weighted` preserves the current release-safe weighted score behavior
  - `rrf` enables opt-in reciprocal-rank fusion for deterministic lexical/semantic candidate blending
- corpus results now include machine-readable `_explain` metadata with source, fusion method, lane ranks, score breakdown, weights, and rerank provider when applicable
- corpus results now include stable `action_target` metadata for message and derived-text hits so agents and future browser workflows can select candidates for export/report/action handoff without re-parsing display fields
- selected corpus `action_target` values can now be expanded into bounded context packs through CLI/API/MCP, including before/hit/after message context, derived-text chunk context, and linked Slack messages for file-backed derived text
- selected corpus `action_target` values can now be persisted as managed `selected-results` export bundles, with a neutral `selected-results.json` artifact, a polished human-readable HTML report at `/exports/{export_id}`, and a manifest for later report rendering or agent handoff
- the authenticated `/search` page can now select individual or visible-page result candidates with `action_target` metadata and create managed `selected-results` reports directly from the browser
- named retrieval profiles for operator rollout control:
  - `baseline` for the shipped local-hash release-safe path
  - `local-bge` for bounded `BAAI/bge-m3` semantic rollout
  - `local-bge-rerank` for experimental learned local reranking on top of BGE retrieval
  - `local-bge-http` and `local-bge-http-rerank` for the same BGE paths through the loopback inference service
- API and MCP corpus search accept the same named retrieval-profile selector, so agent clients can use `baseline` or an explicitly rolled-out profile instead of guessing provider/model settings
- tenant semantic-readiness diagnostics across CLI, API, MCP, and the authenticated tenant settings page
- a read-only semantic rollout planner at `slack-mirror mirror rollout-plan`, which reports tenant coverage for the profile model and emits bounded probe/backfill/health commands
- a benchmark-target embedding backfill at `slack-mirror mirror benchmark-embeddings-backfill`, which covers only labels referenced by a benchmark dataset
- a read-only scale review at `slack-mirror search scale-review`, which reports corpus size, embedding coverage, timed retrieval-profile latency, and the current SQLite/index plus inference-boundary recommendation
- a read-only benchmark validator at `slack-mirror search benchmark-validate`, which checks dataset label resolvability and per-profile model coverage before interpreting relevance evidence
- an aggregate-safe profile benchmark at `slack-mirror search profile-benchmark`, which compares named profiles and opt-in corpus fusion methods against a JSONL benchmark dataset without emitting per-query detail unless `--include-details` is set
- a non-content benchmark diagnostic at `slack-mirror search benchmark-diagnose`, which reports expected target ranks, profile-to-profile movement, top result labels, and compact lane contribution metadata without emitting Slack bodies by default
- a read-only query-variant benchmark at `slack-mirror search benchmark-query-variants`, which compares deterministic query rewrites and authored `query_variants` fixture values without changing production query behavior
- bounded exact-scan discipline for the shipped SQLite path:
  - message semantic retrieval honors the computed candidate cap
  - chunk-backed derived-text semantic retrieval projects matched chunk text and stored embeddings without duplicating full document bodies per candidate
- a bounded DOCX-grade export follow-up lane, with channel/day JSON as the canonical artifact for future DOCX rendering

For local semantic model work such as `BAAI/bge-m3`, install the optional extra into the repo env first:

```bash
uv sync --extra local-semantic
uv run slack-mirror search provider-probe --json
```

For the managed user-scoped runtime, keep the default install lightweight and opt into the local semantic stack explicitly:

```bash
slack-mirror-user user-env update --extra local-semantic
slack-mirror-user search provider-probe --retrieval-profile local-bge --smoke --json
slack-mirror-user search inference-probe --smoke --model local-hash-128 --json
slack-mirror-user search provider-probe --retrieval-profile local-bge-http --smoke --json
```

Before changing a tenant, inspect the retrieval profile and rollout plan:

```bash
uv run slack-mirror search profiles
uv run slack-mirror search semantic-readiness --workspace default --json
uv run slack-mirror search scale-review --workspace default --profiles baseline --query "incident review" --repeats 2 --limit 5 --json
uv run slack-mirror search benchmark-validate --workspace default --dataset docs/dev/benchmarks/slack_live_relevance_noncontent.jsonl --profiles baseline,local-bge-http,local-bge-http-rerank --json
uv run slack-mirror mirror benchmark-embeddings-backfill --workspace default --dataset docs/dev/benchmarks/slack_live_relevance_noncontent.jsonl --retrieval-profile local-bge-http --json
uv run slack-mirror search profile-benchmark --workspace default --dataset docs/dev/benchmarks/slack_smoke.jsonl --profiles baseline,local-bge-http,local-bge-http-rerank --json
uv run slack-mirror search profile-benchmark --workspace default --dataset docs/dev/benchmarks/slack_live_relevance_noncontent.jsonl --profiles baseline,local-bge-http,local-bge-http-rerank --fusion rrf --json
uv run slack-mirror search benchmark-diagnose --workspace default --dataset docs/dev/benchmarks/slack_live_relevance_noncontent.jsonl --profiles baseline,local-bge-http,local-bge-http-rerank --json
uv run slack-mirror search benchmark-query-variants --workspace default --dataset docs/dev/benchmarks/slack_live_relevance_noncontent.jsonl --profiles baseline,local-bge-http --variants original,lowercase,dehyphen,alnum --json
uv run slack-mirror search provider-probe --retrieval-profile local-bge --json
uv run slack-mirror mirror rollout-plan --workspace default --retrieval-profile local-bge --limit 500 --json
```

`search semantic-readiness` is read-only and shows which profiles are ready, partial, unavailable, or still need rollout. `search scale-review` is also read-only; its default `baseline` profile path is safe for release checks and should be run before changing index or inference architecture. `search benchmark-validate` verifies benchmark labels and profile-model coverage before interpreting relevance results. `mirror benchmark-embeddings-backfill` is the narrow write path for covering only benchmark-labeled targets under a retrieval profile. `search profile-benchmark` reuses the `search health` benchmark evaluator across multiple profiles and defaults to aggregate-only output; use `--fusion rrf` to compare reciprocal-rank fusion against the release-default `weighted` path without changing tenant defaults. `search benchmark-diagnose` is the next read-only step when aggregate relevance is weak; it shows rank movement and lexical/semantic/rerank contribution metadata without content unless `--include-text` is explicitly provided. `search benchmark-query-variants` compares deterministic query formulations such as `original`, `lowercase`, `dehyphen`, `alnum`, and authored fixture `query_variants` values without changing default query parsing. The rollout plan is read-only; it reports message and derived-text chunk coverage for the selected profile model and prints the exact bounded commands to run next.

For query-pipeline diagnostics, use `--explain` and optionally compare fusion strategies without changing tenant defaults:

```bash
uv run slack-mirror search corpus --workspace default --query "incident review" --mode hybrid --fusion weighted --explain
uv run slack-mirror search corpus --workspace default --query "incident review" --mode hybrid --fusion rrf --explain
uv run slack-mirror search corpus --workspace default --query "nylon since:2022-01-01 until:2023-01-01" --mode hybrid --explain
uv run slack-mirror search corpus --workspace default --query "deploy on:2026-04-21 participant:@alice" --mode lexical --explain
uv run slack-mirror search corpus --workspace default --query "incident has:attachment filename:report extension:pdf" --mode hybrid --explain
```

`weighted` remains the default. `rrf` is an opt-in reciprocal-rank fusion strategy for comparing lexical and semantic candidate blending. Temporal operators accept numeric Slack timestamps and UTC ISO dates/datetimes; `on:YYYY-MM-DD` expands to that UTC day, while `since:` and `until:` are portable aliases for lower and upper bounds. `participant:` and `user:` are sender aliases for Slack message search. Attachment operators include `has:attachment`, `filename:`, `mime:`, `extension:`/`ext:`, and `attachment-type:`; message search applies them through persisted message-file links, while derived-text search applies them to extracted file/canvas text rows. In corpus search, message-lane operators constrain the message lane and suppress unfiltered derived-text hits unless linked file metadata can satisfy the attachment constraints.

Release policy for the first stable MCP-capable user-scoped install:

- `baseline` remains the default installed retrieval profile.
- `local-bge` is supported as an explicit operator-controlled rollout profile after provider probe, rollout plan, bounded backfill, semantic readiness, and search health checks.
- `local-bge-rerank` remains experimental until benchmark and live-query evidence justify promotion.
- SQLite remains the canonical store. After the semantic candidate/projection fix, the measured release `baseline` path is interactive on `default`; evaluate a SQLite-native vector extension only if new exact-scan measurements regress above target.
- The local inference service is installed as a user-scoped loopback unit for opt-in semantic acceleration, but the release `baseline` profile does not depend on it being active.
- DuckDB is sidelined for this release path. It may be revisited later as an analytics, reporting, or search-sidecar experiment, not as canonical storage.

The probe reports:

- configured provider type
- model id and expected dimensions
- `sentence_transformers` / `torch` availability
- CUDA and GPU visibility when torch is installed
- optional `nvidia-smi` memory details
- an embed smoke result when `--smoke` is requested

For bounded live `BAAI/bge-m3` rollout on messages, use this loop:

```bash
uv sync --extra local-semantic
uv run slack-mirror search provider-probe --smoke --json
uv run slack-mirror mirror embeddings-backfill --workspace default --model BAAI/bge-m3 --channels C123,C456 --limit 500 --json
uv run slack-mirror search health --workspace default --model BAAI/bge-m3
```

`search readiness` and `search health` now report configured-model coverage separately from total message embeddings, so a partial `bge-m3` rollout shows up as incomplete coverage rather than looking fully migrated.

For bounded derived-text chunk rollout under the configured semantic model, use this loop:

```bash
uv sync --extra local-semantic
uv run slack-mirror mirror process-derived-text-jobs --workspace default --kind attachment_text
uv run slack-mirror mirror derived-text-embeddings-backfill --workspace default --model BAAI/bge-m3 --kind attachment_text --limit 500 --json
uv run slack-mirror search derived-text --workspace default --query "invoice total" --kind attachment_text --mode semantic --model BAAI/bge-m3
uv run slack-mirror search health --workspace default --model BAAI/bge-m3
```

`search readiness` and `search health` now also report configured-model chunk coverage for `attachment_text` and `ocr_text`, so a partial derived-text rollout is visible separately from message coverage.

For derived-text benchmark smoke after chunk rollout, use the shipped dataset:

```bash
uv run slack-mirror search health \
  --workspace default \
  --target derived_text \
  --dataset ./docs/dev/benchmarks/slack_derived_text_smoke.jsonl \
  --mode semantic \
  --model BAAI/bge-m3
```

The derived-text benchmark target emits chunk-aware query reports, including `chunk_index`, `matched_text`, and source metadata for the top derived-text results, so degraded attachment/OCR queries are diagnosable without ad hoc local probing.

For bounded reranking on top of the current retrieval candidates, use:

```bash
uv run slack-mirror search corpus \
  --workspace default \
  --query "incident review" \
  --mode hybrid \
  --rerank \
  --rerank-top-n 50 \
  --explain
```

The default shipped reranker provider is still heuristic. To try learned local reranking, configure the optional CrossEncoder provider and probe it before use:

```yaml
search:
  rerank:
    provider:
      type: sentence_transformers
      model: BAAI/bge-reranker-v2-m3
      device: cuda
      batch_size: 16
```

```bash
uv sync --extra local-semantic
uv run slack-mirror search reranker-probe --smoke --json
uv run slack-mirror search corpus --workspace default --query "incident review" --mode hybrid --rerank --rerank-top-n 50 --explain
```

This remains opt-in. The CLI/API/MCP `rerank` controls select whether reranking runs; config selects whether that reranker is the heuristic baseline or the learned local CrossEncoder.
- the shipped DOCX baseline now includes:
  - explicit paragraph styles over the same channel/day JSON artifact
  - compact 1in-margin, sans-serif 10pt defaults
  - subtle paragraph shading for top-level and reply message blocks
  - reply indentation without internal thread-ID noise
  - tighter sender metadata alignment
  - attachment link/source blocks with compact type badges and human-readable type labels
  - safer link preference for public URLs/permalinks over brittle local filesystem links
  - config-backed managed export bundles with deterministic export IDs and reverse-proxied `/exports/<export-id>/<filepath>` download URLs
  - shared portable attachment links across HTML, PDF, and DOCX through emitted `public_url` / `download_url` fields, plus audience-keyed `download_urls` / `preview_urls`
  - API-served export manifests through `/v1/exports` and `/v1/exports/<export-id>` so the live service owns the configured bundle URL contract
  - bundle HTML reports published directly at `/exports/<export-id>`
  - channel/day HTML reports now render message bubbles and sender avatars when profile imagery is available, group consecutive same-sender messages, use participant-aware DM titles instead of raw workspace/channel ids, show tenant/channel/thread identifiers in code-style metadata, keep attachment metadata compact instead of printing full raw URLs, materialize Slack-native email previews into managed bundles when no local binary exists, opportunistically download hosted Slack attachments into the managed bundle when a file row exists but the mirror has not yet persisted a local binary, and preserve repaired local email HTML artifacts with companion inline-asset directories when those artifacts are published, while rejecting Slack HTML/login interstitials instead of publishing them as fake local files
  - `mirror reconcile-files` now reports separate counts for repaired ordinary binaries versus repaired Slack-for-Gmail email containers, so operators can tell what kind of recovery actually occurred
  - `mirror reconcile-files` also reports partial email-container localization warnings when the HTML body is repaired but some inline assets remain missing
  - `mirror reconcile-files` now emits per-reason remediation hints in both plain output and `--json`
  - `mirror reconcile-files` now persists the last run outcome in local state and compares the current batch to the previous run in both plain output and `--json`, so operators can spot regressions instead of reading each batch in isolation
  - `user-env validate-live` and `user-env check-live` now surface the latest persisted reconcile-files evidence per workspace, and warn when the most recent repair batch recorded warnings or failures
  - `user-env check-live` now also verifies that the managed `slack-mirror-mcp` wrapper answers a real MCP health request, not just that the wrapper file exists
  - `user-env status` and `user-env check-live` now also verify bounded multi-client MCP readiness through concurrent wrapper probes, so adding several Codex/OpenClaw clients can be gated explicitly instead of assumed
  - lightweight managed-runtime status is now queryable over CLI, API (`/v1/runtime/status`), and MCP (`runtime.status`), including the latest persisted reconcile summary per workspace
  - `scripts/render_runtime_report.py` now consumes `/v1/runtime/status` and `/v1/runtime/live-validation` to generate shareable Markdown or HTML runtime snapshots for ops review
  - `user-env snapshot-report` now writes Markdown and HTML runtime snapshots into the managed state directory under `runtime-reports/`, alongside stable `*.latest.*` copies for review or handoff, while pruning older timestamped snapshots with a bounded retention policy
  - the local API now publishes the latest managed runtime snapshots through `/v1/runtime/reports`, `/v1/runtime/reports/<name>`, `/v1/runtime/reports/latest`, a browser index at `/runtime/reports`, and direct HTML at `/runtime/reports/<name>` or `/runtime/reports/latest`, with the freshest snapshot highlighted on the index and header links for the latest HTML and manifest
- the local API now supports bounded runtime report lifecycle operations through `POST /v1/runtime/reports`, `POST /v1/runtime/reports/<name>/rename`, and `DELETE /v1/runtime/reports/<name>`
- the local API now supports bounded managed-export lifecycle operations through `POST /v1/exports`, `POST /v1/exports/<export-id>/rename`, and `DELETE /v1/exports/<export-id>`, with create intentionally limited to channel-day exports
- the browser now exposes those same bounded lifecycle operations through `/runtime/reports` and `/exports`, so reports and channel-day exports can be created and managed without hand-calling the JSON routes
- the browser now also exposes authenticated corpus search through `/search`, with workspace/all-workspace scope, mode and derived-text filters, bounded previous/next pagination with total-result counts, inline workspace readiness context, and stable JSON detail destinations for message and derived-text hits over the shipped search APIs
- the main authenticated browser entry surfaces (`/`, `/settings`, and `/search`) now share a common topbar with identity context and direct navigation across home, search, runtime reports, exports, and settings
- the `/exports` browser flow now uses valid mirrored workspace/channel choices from the current DB instead of raw free-text entry, and defaults the date field from the selected channel's latest mirrored day when available
- the `/exports` browser flow now also supports channel filtering for larger workspaces, with client-side match counts and empty-filter feedback over the same valid mirrored choices
- the `/exports` browser manager now uses inline export rename controls instead of prompt-driven rename dialogs
- successful export rename and delete now update the `/exports` page inline instead of forcing a full page reload
- successful export creation now inserts the new row inline instead of forcing a full page reload
- deleting the final row on `/runtime/reports` or `/exports` now restores an explicit empty-state row instead of leaving an empty table body
- authenticated browser creation of runtime reports now uses shared runtime-service payloads instead of unauthenticated loopback calls back into `/v1/runtime/*`
- managed export creation in installed `user-env` environments now ships the package-owned `scripts/export_channel_day.py` path expected by the shared service layer
- inline rename/delete controls on `/runtime/reports` and `/exports` now disable themselves while a row mutation is in flight, so double-clicks do not race duplicate requests
- create controls on `/runtime/reports` and `/exports` now disable themselves while creation is in flight, so create requests cannot be double-submitted
- the `/runtime/reports` browser flow now uses configured publish-origin choices, guided report-name presets, and inline rename controls instead of raw base-URL entry and prompt-driven rename
- successful runtime-report rename and delete now update the `/runtime/reports` page inline instead of forcing a full page reload
- successful runtime-report creation now inserts the new row inline, promotes it to the latest row, and resets the suggested report name without forcing a full page reload
  - MCP now exposes the freshest managed runtime snapshot manifest through `runtime.report.latest`
- the local API now supports a bounded local-password browser-auth baseline for `/runtime/reports*` and `/exports*`, with login/register HTML pages and cookie-backed sessions modeled on the lighter parts of the `../litscout` hosted auth seam
- frontend auth cookie policy is now request-aware, so browser-origin HTTPS ingress can use `Secure` cookies without breaking the local `http://slack.localhost` path
- the browser root `/` is now an authenticated landing page over existing runtime-status, runtime-report, and export-manifest data, instead of a dead 404
- browser auth POST routes now enforce same-origin `Origin`/`Referer` checks, so login, registration, and logout are intentionally browser-local rather than general cross-origin API endpoints
- frontend auth now exposes current-user session listing and per-session revocation through `/auth/sessions` and `/auth/sessions/<id>/revoke`
- `/auth/status` now distinguishes open vs allowlisted registration, instead of reporting any self-registration-capable install as fully open
- browser-auth sessions now expire on inactivity through a config-backed idle timeout, not only absolute session age
- `/auth/login` now has a bounded failed-login throttle with config-backed window and threshold controls
- `/settings` now provides a browser-facing account page over the same frontend-auth session and registration-policy data
- `/settings` now also surfaces the active auth-governance policy, including session lifetime, idle timeout, and login-throttle settings
- `/login` and `/settings` now explicitly tell operators that browser sessions persist across restarts until the configured session lifetime or idle timeout expires
- `/login` and `/settings` now also surface the supported CLI password-reset hint: `slack-mirror-user user-env provision-frontend-user --username <identity> --password-env <ENV_VAR> --reset-password`
- the shipped config template now defaults browser self-registration to off; enabling it for an externally exposed install is an explicit policy choice
- `user-env provision-frontend-user` is the supported first-user bootstrap path when browser self-registration stays closed
- `/settings` now updates session revocation state inline instead of depending on a full page reload
- frontend auth registration can now be restricted to an explicit allowlist of normalized usernames, including email-style usernames such as `ecochran76@gmail.com`
- `/register` now surfaces that live allowlist policy directly in the browser instead of leaving the identity constraint implicit
- `/login` now matches that language with an `Email or username` field label
- browser manager controls on `/runtime/reports` and `/exports` now show inline `creating…`, `saving…`, and `deleting…` labels while mutations are in flight
- browser manager rows on `/runtime/reports` and `/exports` now render row-local rename/delete errors in place, instead of relying only on the page-level feedback banner
- browser create panels on `/runtime/reports` and `/exports` now render local create errors in place, instead of relying only on the page-level feedback banner
- browser create forms on `/runtime/reports` and `/exports` now block obviously invalid submissions before the request is sent
- browser create forms now also highlight the specific invalid input before submission, focus the first invalid field, and expose the local error region through `aria-describedby`
- browser create forms now also show field-local helper and error text, so validation guidance lands next to the relevant input instead of only in the shared form banner
- browser manager rows now expose compact per-row outcome chips for recent inline mutation results, so rename/save failures are easier to scan without relying only on the page banner
  - the managed user-env install now also provisions `slack-mirror-runtime-report.timer`, which runs `user-env snapshot-report` hourly into the same managed state directory
  - bounded browser preview support for images, PDFs, and text-like files through `/exports/<export-id>/<filepath>/preview`
  - lightweight `.docx` browser preview through `mammoth`, without requiring a full office server
  - lightweight `.pptx` and `.xlsx` browser previews through the repo's OOXML extraction layer, without requiring a full office server
  - lightweight OpenDocument browser previews for `.odt`, `.odp`, and `.ods` through the repo's extraction layer, without requiring a full office server
  - render-engine-compatible OOXML output that can be visually QA'd through the `docx-skill` render path
  - bounded appearance controls for font family, body size, margins, compactness, and accent color
  - a one-command fixture-artifact generator for canonical DOCX/PDF/PNG visual review outputs

The active search modernization lane is [0006-2026-04-11-search-evaluation-modernization.md](/home/ecochran76/workspace.local/slack-export/docs/dev/plans/0006-2026-04-11-search-evaluation-modernization.md). The derived-text ownership contract for this first slice is in [DERIVED_TEXT_CONTRACT.md](/home/ecochran76/workspace.local/slack-export/docs/dev/DERIVED_TEXT_CONTRACT.md).

## Description

The `slack_export.py` script uses a Slack user token to export:

- Public Channels
- Private Channels
- Direct Messages (1:1 DMs)
- Multi-Person Messages (Group DMs)
- Canvases
- Files

This script retrieves all conversations your user participates in, downloads their complete message history, and saves each as separate JSON files. It also exports canvases and files you have access to into dedicated directories. Unlike Slack's official exporter, which only covers public channels, this tool provides a user-centric export, including private content you can see.

**Note**: Export capabilities may be limited by your Slack workspace’s plan (e.g., free plans restrict some historical data) or your user’s permissions.

Slack endorses this API usage for personal exports (see [Slack's API documentation](https://get.slack.help/hc/en-us/articles/204897248)):  
*"If you want to export the contents of your own private groups and direct messages, please see our API documentation."*

### Getting a Slack Token

To use this script, you need a Slack **user token** (starts with `xoxp-`). Legacy tokens are deprecated, so follow these steps to create a Slack app and obtain a user token:

1. **Create a Slack App**:
   - Go to [api.slack.com/apps](https://api.slack.com/apps) and click "Create New App".
   - Name it (e.g., "Slack Exporter") and select your workspace.

2. **Configure Permissions**:
   - Navigate to "OAuth & Permissions".
   - Under "User Token Scopes", add:
     - `channels:history` (public channel messages)
     - `groups:history` (private channel messages)
     - `im:history` (1:1 DMs)
     - `mpim:history` (group DMs)
     - `files:read` (files and canvases)
     - `users:read` (user info for names/IDs)
   - These scopes enable the script to access your conversations, files, and canvases.

3. **Install the App**:
   - Go to "Install App" and click "Install to Workspace".
   - Authorize as yourself (e.g., `ecochran76`).
   - Copy the **User OAuth Token** (`xoxp-...`) from "OAuth & Permissions".

4. **Use the Token**:
   - Pass it to the script with the `--token` argument.

#### Bot vs. User Tokens
- **User Tokens (`xoxp-`)**:
  - Act as you (e.g., `ecochran76`), exporting data you can see in Slack.
  - Include private channels, DMs, and files/canvases you have access to, based on your permissions.
  - **Required** for this script to export your full personal data.

- **Bot Tokens (`xoxb-`)**:
  - Represent a bot user tied to the app, not your account.
  - Limited to public channels and bot interactions unless invited to private conversations.
  - **Not suitable** here—using a bot token will omit private channels, DMs, and most user-specific files/canvases.

Ensure you use a user token (`xoxp-`) for complete exports.

---

## Credits

This project is a fork of [zach-snell/slack-export](https://github.com/zach-snell/slack-export). Many thanks to Zach Snell for the original implementation, which inspired and formed the basis for this enhanced version.

---

## Dependencies

Install the required Python packages:

```bash
pip install slack_sdk  # https://github.com/slackapi/python-slack-sdk
pip install pick       # https://github.com/wong2/pick
pip install requests   # For downloading files and canvases
```

---

## Usage

The script exports all conversations (public channels, private channels, group DMs, 1:1 DMs), canvases, and files your user can access by default, saving them to a directory named `<timestamp>-slack_export` (e.g., `20250303-172345-slack_export`). Use the flags below to customize the export process, filter conversations, or modify output behavior.

### Command-Line Flags

- **`--token TOKEN`**  
  - **Required**: The Slack user token (`xoxp-...`) obtained from your Slack app.
  - Example: `--token xoxp-123...`

- **`--zip ZIP_NAME`**  
  - Optional: Creates a zip archive of the export directory (e.g., `slack_export.zip`) and deletes the original folder after zipping.
  - Useful for compatibility with tools like `slack-export-viewer`.
  - Default: No zip file is created.
  - Example: `--zip my_export`

- **`-o, --output PATH`**  
  - Optional: Specifies the base directory where the export folder (`<timestamp>-slack_export`) is created.
  - Supports `~` for your home directory (e.g., `~/slack_backups` on Windows becomes `C:\Users\YourUsername\slack_backups`).
  - Default: Current working directory.
  - Example: `-o ~/slack_backups`

- **`--dryRun`**  
  - Optional: Lists all available conversations (public channels, private channels, group DMs, 1:1 DMs) your user can export without fetching or saving anything.
  - Useful for previewing what will be exported.
  - Default: Disabled (full export runs).
  - Example: `--dryRun`

- **`--publicChannels [CHANNEL_NAME ...]`**  
  - Optional: Exports public channels. Without names, exports all public channels you’re in; with names, filters to the specified channels.
  - Names are case-sensitive and must match exactly (e.g., `General`, not `general`).
  - Default: Exports all public channels unless filtered.
  - Example: `--publicChannels General Random`

- **`--groups [GROUP_NAME ...]`**  
  - Optional: Exports private channels and group DMs. Without names, exports all you’re in; with names, filters to the specified ones.
  - Names must match exactly (e.g., `my_private_channel` or `mpdm-user1--user2-1`).
  - Default: Exports all private channels and group DMs unless filtered.
  - Example: `--groups my_private_channel`

- **`--directMessages [USER_NAME ...]`**  
  - Optional: Exports 1:1 DMs. Without names, exports all your DMs; with names, filters to the specified users.
  - Uses Slack usernames (e.g., `jane_smith`), not display names.
  - Default: Exports all 1:1 DMs unless filtered.
  - Example: `--directMessages jane_smith john_doe`

- **`--prompt`**  
  - Optional: Opens an interactive menu to select conversations (public channels, private channels/group DMs, 1:1 DMs) to export.
  - If combined with `--publicChannels`, `--groups`, or `--directMessages` with names, those named items are exported automatically, and the prompt applies to the unspecified types.
  - Default: Disabled (exports all conversations unless filtered).
  - Example: `--prompt`

### Usage Examples

```bash
# Export everything (channels, DMs, canvases, files) to the current directory
python slack_export.py --token xoxp-123...

# Export everything and save to a custom directory
python slack_export.py --token xoxp-123... -o ~/slack_backups

# Export everything into a zip file
python slack_export.py --token xoxp-123... --zip slack_export

# Preview all exportable conversations without saving
python slack_export.py --token xoxp-123... --dryRun

# Export only specific public channels
python slack_export.py --token xoxp-123... --publicChannels General Random

# Export all private channels and group DMs to a custom directory
python slack_export.py --token xoxp-123... --groups -o ~/backups

# Export 1:1 DMs with specific users
python slack_export.py --token xoxp-123... --directMessages jane_smith john_doe

# Export all public channels and specific group DMs
python slack_export.py --token xoxp-123... --publicChannels --groups mpdm-user1--user2-1

# Export DMs with jane_smith and prompt for public channels
python slack_export.py --token xoxp-123... --directMessages jane_smith --publicChannels --prompt

# Prompt for all conversation types interactively
python slack_export.py --token xoxp-123... --prompt

# Export public/private channels (no DMs) into a zip file
python slack_export.py --token xoxp-123... --publicChannels --groups --zip channels_only
```

### Notes on Behavior
- **Default Behavior**: Without filtering flags (`--publicChannels`, `--groups`, `--directMessages`), all conversations, canvases, and files are exported unless `--prompt` is used to select manually.
- **Combining Flags**: Use multiple flags to export specific subsets (e.g., `--publicChannels --directMessages` skips private channels/group DMs).
- **Canvases and Files**: Always exported unless `--dryRun` is used, regardless of conversation filters.
- **Rate Limits**: The script includes `sleep(1)` between API calls to respect Slack’s rate limits, which may slow large exports.

---

## Credits

This project is a fork of [zach-snell/slack-export](https://github.com/zach-snell/slack-export). Many thanks to Zach Snell for the original implementation, which inspired and formed the basis for this enhanced version.

---

## Dependencies

Install the required Python packages:

```bash
pip install slack_sdk  # https://github.com/slackapi/python-slack-sdk
pip install pick       # https://github.com/wong2/pick
pip install requests   # For downloading files and canvases
```

---

## Output Structure

- `users.json`: List of workspace users.
- `channels.json`: Metadata for exported conversations.
- `<channel_name>/<date>.json`: Message history for each channel/DM, split by date.
- `canvases/canvases.json`: Metadata for exported canvases.
- `canvases/<canvas_title>_<id>.html`: Exported canvas files.
- `files/files.json`: Metadata for exported files.
- `files/<file_name>`: Exported files (e.g., PDFs, images).

---

## Recommended Tools

Pairs with `slack-export-viewer` for viewing exports:

```bash
pip install slack-export-viewer
slack-export-viewer -z slack_export.zip
```

---

## Limitations

- Requires a user token (`xoxp-`) with scopes like `channels:history`, `files:read`, etc.
- Exports are limited to what your user can access in Slack.
- Free Slack plans may restrict message history or file access.

---

## License

This script is provided as-is, with no guarantees of updates or support. See the original repository for licensing details: [zach-snell/slack-export](https://github.com/zach-snell/slack-export).
