# Runbook (Handoff + Operations)

This file is the continuity guide for future agents and contributors.

## Current Mission

Evolve this repo from one-time exporter to multi-workspace, continuously updated mirror platform.

## Working Conventions

- Planning/dev docs live in `docs/dev/`
- User-facing docs live in `docs/`
- Keep this runbook updated at each meaningful milestone
- Prefer small, coherent commits with explicit milestone labels

## Session Startup Checklist

1. Read:
   - `README.md`
   - `docs/ARCHITECTURE.md`
   - `docs/ROADMAP.md`
   - `docs/dev/PLAN.md`
   - `docs/dev/RUNBOOK.md`
2. Check repo status:
   - `git status --short --branch`
3. Confirm branch and open tasks before coding

## Milestone Log

### 2026-02-25 — Phase F PR-F6 (optional reranker + query profiles)

- Added optional reranking controls:
  - `--rerank`
  - `--rerank-top-n`
- Added saved query profile support:
  - `--profile <name>`
  - config-backed profiles under `search.query_profiles`
- Query profile capabilities include:
  - query prefix injection (scoping/filter presets)
  - mode/model defaults
  - semantic and keyword weight presets
- Added heuristic reranker pass in search engine for top-N refinement
- Updated `config.example.yaml` with a sample `nylon-research` profile

### 2026-02-25 — Phase F PR-F5 (portable eval harness + benchmark packs)

- Upgraded `scripts/eval_search.py` with portable corpus modes:
  - `--corpus slack-db`
  - `--corpus dir`
- Added baseline benchmark packs:
  - `docs/dev/benchmarks/slack_smoke.jsonl`
  - `docs/dev/benchmarks/dir_docs_smoke.jsonl`
- Updated eval documentation:
  - `docs/dev/SEARCH_EVAL.md` now includes cross-corpus usage and id conventions
- Verified both corpus modes execute and report nDCG/MRR/hit/latency metrics

### 2026-02-25 — Phase F PR-F4 (directory corpus adapter + CLI entrypoint)

- Added directory corpus search adapter: `slack_mirror/search/dir_adapter.py`
- Added CLI command:
  - `search query-dir --path <root> --query <text> [--mode lexical|semantic|hybrid] [--glob ...]`
- Directory search returns scored file hits with snippets for quick triage
- Updated completion/parser coverage for `query-dir`
- Confirmed command works against local docs corpus

### 2026-02-25 — Phase F PR-F3 (adapter-style search interfaces)

- Added reusable search platform interfaces in `slack_mirror/search/platform.py`
  - `CorpusAdapter` protocol
  - shared `SearchDocument` model
- Added SQLite adapter implementation in `slack_mirror/search/sqlite_adapter.py`
- Refactored keyword search engine to use adapter retrieval methods for:
  - lexical candidate collection
  - semantic candidate collection
- Preserved existing ranking behavior while decoupling retrieval backend from engine logic

### 2026-02-25 — Phase F PR-F2 (thread grouping, dedupe, snippets, explain)

- Added result shaping flags to `search keyword` / `search semantic`:
  - `--group-by-thread`
  - `--dedupe`
  - `--snippet-chars <n>`
  - `--explain`
- Implemented thread-level best-hit grouping and near-duplicate text collapse
- Added concise snippet generation for terminal output and JSON enrichment
- Added explain output for source + score components per row
- Updated completion/help wiring and semantic CLI parser coverage

### 2026-02-25 — Phase F PR-F1 (source include/exclude + strict source filters)

- Added query syntax support in search parser:
  - `in:<source1,source2>`
  - `source:<pattern>` / `channel:<pattern>` with `*` wildcard
  - negated source filters (e.g. `-source:oc-*`)
- Applied these filters at query-planner layer so they affect lexical + semantic paths consistently
- Updated CLI help text to document `in:` and `source:` filter support
- Added parser behavior tests in `tests/test_search.py`

### 2026-02-25 — Phase F planning kickoff (reusable search platform)

- Added roadmap doc: `docs/dev/PHASE_F_SEARCH_PLATFORM.md`
- Defined adapter-based search architecture for reuse across:
  - DB corpora
  - directory/file corpora
  - mixed attachment corpora
- Prioritized quick wins + PR sequence for a portable search stack

### 2026-02-24 — Semi-permanent local test DB baseline

- Added setup guide: `docs/dev/TEST_DB_SETUP.md`
- Standardized local test DB pathing (gitignored):
  - `config.local.yaml`
  - `.local/state/slack_mirror_test.db`
  - `.local/cache`
- Updated `.gitignore` to keep local DB/config runtime artifacts out of repo

### 2026-02-24 — Ranking weight knobs via CLI/config (queue item #3)

- Added keyword ranking weight knobs in `search keyword`:
  - `--rank-term-weight`
  - `--rank-link-weight`
  - `--rank-thread-weight`
  - `--rank-recency-weight`
- Added config support for keyword ranking defaults:
  - `search.keyword.weights.{term,link,thread,recency}`
- Wired ranking weights through search engine scoring path
- Updated shell completion for the new search flags
- Added CLI parse coverage for ranking-weight flags

### 2026-02-24 — Backfill message-only mode (queue item #2)

- Added dedicated backfill mode to skip users/channels bootstrap:
  - `mirror backfill --include-messages --messages-only`
- Added optional channel override for user-token pulls:
  - `--channels C123,C456`
- Extended message backfill worker to accept explicit channel id overrides
- Added CLI parse coverage for new flags in `tests/test_cli.py`
- Updated shell completion (bash/zsh) for new backfill flags

### 2026-02-24 — CLI auth-mode guardrails (queue item #1)

- Added CLI guardrail mode for backfill auth:
  - `mirror backfill --auth-mode bot|user` (default: `bot`)
- Added token-type detection and enforcement:
  - user token with default `bot` mode now fails with explicit override guidance
  - mismatched `--auth-mode user` + bot token also fails
- Updated completion support (bash/zsh) for `--auth-mode`
- Added tests for guardrail helpers:
  - `tests/test_auth_mode.py`

### 2026-02-24 — Phase E PR5 (eval harness + instrumentation)

- Added evaluation harness script: `scripts/eval_search.py`
  - computes nDCG/MRR/hit@k and latency percentiles for lexical/semantic/hybrid
- Added eval docs and sample dataset:
  - `docs/dev/SEARCH_EVAL.md`
  - `docs/dev/search_eval_dataset.jsonl`
- Added lightweight search instrumentation in CLI summary:
  - latency in ms
  - result source breakdown (`lexical` / `semantic` / `hybrid`)

### 2026-02-24 — Phase E PR4 (semantic alias + config knobs)

- Added `search semantic` command alias (maps to semantic mode)
- Added config-backed semantic defaults:
  - `search.semantic.mode_default`
  - `search.semantic.model`
  - `search.semantic.weights.{lexical,semantic,semantic_scale}`
- Added CLI knobs for hybrid tuning:
  - `--lexical-weight`
  - `--semantic-weight`
  - `--semantic-scale`
- Updated shell completion entries for new search command/flags
- Updated `config.example.yaml` with semantic settings block

### 2026-02-24 — Phase E PR3 (hybrid retrieval mode)

- Extended `search keyword` with retrieval mode support:
  - `--mode lexical|semantic|hybrid`
  - `--model <embedding-model-id>` for semantic/hybrid paths
- Implemented semantic retrieval path in `slack_mirror/search/keyword.py`:
  - vector scoring over `message_embeddings`
  - cosine similarity scoring
- Implemented hybrid score fusion (lexical + semantic merge)
- Added test coverage updates:
  - `tests/test_search.py` semantic/hybrid assertions
  - `tests/test_cli.py` parsing coverage for `--mode semantic`

### 2026-02-24 — Phase E PR2 kickoff (embedding queue + backfill commands)

- Added migration: `0005_embedding_jobs.sql`
- Added embedding-job queue hooks in message upsert path
- Added local embedding sync module: `slack_mirror/sync/embeddings.py`
  - `backfill_message_embeddings(...)`
  - `process_embedding_jobs(...)`
- Added CLI commands:
  - `mirror embeddings-backfill`
  - `mirror process-embedding-jobs`
- Added test coverage:
  - `tests/test_embeddings.py`
  - extended `tests/test_db.py` for embedding job enqueue behavior

### 2026-02-24 — Phase E semantic plan approved

- Added implementation plan doc: `docs/dev/PHASE_E_SEMANTIC_SEARCH.md`
- Locked incremental PR plan (PR1..PR5) for semantic/hybrid search rollout
- Chosen approach for current architecture:
  - SQLite-first semantic implementation now
  - maintain backend boundary compatible with future Postgres/pgvector profile


### 2026-02-23 — Planning docs baseline

- Captured architecture, roadmap, engineering plan, and runbook
- Established docs split (`docs/` vs `docs/dev/`)

### 2026-02-23 — Phase A scaffolding (initial)

- Added `config.example.yaml` with env-var interpolation patterns
- Added `slack_mirror` package skeleton (`core`, `cli`, `search`, `service`, `integrations`)
- Added SQLite migration scaffold: `slack_mirror/core/migrations/0001_init.sql`
- Added config loader with `${ENV}` / `${ENV:-default}` support
- Added DB connector + migration applier
- Added CLI skeleton (`slack-mirror`) with stubs for:
  - `mirror init`
  - `workspaces list`
  - `channels sync-from-tool`
  - `docs generate`
  - `completion print bash|zsh`
- Added adapter for existing `~/.openclaw/workspace/scripts/slack_channels`

### 2026-02-23 — Phase A scaffolding (packaging + tests + workspace bootstrap)

- Added `pyproject.toml` with `slack-mirror` CLI entrypoint
- Added tests:
  - `tests/test_config.py`
  - `tests/test_db.py`
- Added workspace DB bootstrap commands:
  - `workspaces sync-config`
  - `workspaces list` now reads from DB
- Added DB helpers: `upsert_workspace`, `list_workspaces`

### 2026-02-23 — Phase B kickoff (API pagination + first backfill)

- Added Slack API client module: `slack_mirror/core/slack_api.py`
  - `auth_test`
  - cursor-paginated `users_list`
  - cursor-paginated `conversations_list`
- Added first backfill worker: `slack_mirror/sync/backfill.py`
  - backfills users + channels into DB
- Added DB upsert helpers:
  - `upsert_user`
  - `upsert_channel`
  - `get_workspace_by_name`
- Extended CLI:
  - `workspaces verify [--workspace <name>]`
  - `mirror backfill --workspace <name>`
  - `scripts/catchup_mirror.sh [config] [--workspace <name> ...] [--max-passes N]`

### 2026-03-09 — Resumable catch-up with Slack rate-limit backoff

- Added automatic 429 handling in `slack_mirror/core/slack_api.py`
  - honors `Retry-After`
  - retries with a small safety buffer
- Added resumable catch-up runner:
  - `scripts/catchup_until_complete.py`
  - works channel-by-channel using existing checkpoints
  - persists pass/channel attempt state in `.local/state/catchup_state.json`
- Updated wrapper script:
  - `scripts/catchup_mirror.sh`
  - now forwards to the resumable runner

### 2026-02-23 — Phase B (message history backfill + checkpoints)

- Added `conversations.history` pagination in `SlackApiClient`
- Added message backfill flow with per-channel checkpoints in `sync_state`
- Added DB helpers:
  - `upsert_message`
  - `list_channel_ids`
  - `set_sync_state` / `get_sync_state`
- Extended CLI `mirror backfill` with:
  - `--include-messages`
  - `--channel-limit`

### 2026-02-23 — Phase B (files/canvases metadata backfill)

- Checked the prior failed edit warning in `slack_mirror/core/slack_api.py` (it was a no-op edit attempt; file state is good)
- Added `files.list` pagination helper in Slack API client
- Added DB upserts:
  - `upsert_file`
  - `upsert_canvas`
- Added backfill flow for files/canvases metadata + deterministic local cache paths
- Extended CLI `mirror backfill` with:
  - `--include-files`
  - `--cache-root`

### 2026-02-23 — Phase B (file/canvas content downloads)

- Added downloader module with retries + SHA256 checksum:
  - `slack_mirror/sync/downloads.py`
- Added file DB update helper:
  - `update_file_download`
- Extended file/canvas backfill to optionally download content:
  - `--download-content`
- Verified with bot token:
  - `files_downloaded=15`, `canvases_downloaded=19`

### 2026-02-23 — Phase C kickoff (webhook service skeleton)

- Added HTTP webhook server skeleton:
  - `slack_mirror/service/server.py`
  - endpoint: `/slack/events`
  - health endpoint: `/healthz`
  - Slack signature verification + replay-window check
  - URL verification challenge support
- Added event-log DB helper:
  - `insert_event`
- Added CLI command:
  - `mirror serve-webhooks --workspace <name> [--bind] [--port]`
  - persists incoming events into `events` table with `pending` status

### 2026-02-23 — Phase C (event processor worker)

- Added event processor module:
  - `slack_mirror/service/processor.py`
  - consumes `events.status='pending'`
  - applies basic upserts for:
    - messages
    - channel_created/channel_rename
    - file_created/file_shared/file_change
  - marks events as `processed` or `error`
- Added CLI command:
  - `mirror process-events --workspace <name> [--limit N]`
- Added tests:
  - `tests/test_processor.py`

### 2026-02-23 — Phase C (expanded event coverage + loop mode)

- Expanded processor message handling:
  - supports `message_changed`
  - supports `message_deleted`
- Added processor loop mode:
  - `mirror process-events --loop --interval <seconds> [--max-cycles N]`

### 2026-02-24 — Phase C (channel membership events)

- Added DB migration:
  - `0002_channel_members.sql`
- Added DB helpers:
  - `upsert_channel_member`
  - `remove_channel_member`
- Expanded event processor coverage:
  - `member_joined_channel`
  - `member_left_channel`
- Added tests for channel membership writes and event handling

### 2026-02-24 — Phase B/C utility (message backfill time windows)

- Extended CLI `mirror backfill` with message window flags:
  - `--oldest`
  - `--latest`
- Extended backfill message path to pass bounds into `conversations.history`
- Preserved checkpoint behavior for default incremental mode only:
  - when no explicit `--oldest/--latest` is provided, checkpoint updates continue
  - when explicit bounds are provided, run is windowed and does not mutate channel checkpoint
- Updated CLI parsing tests and config docs examples

### 2026-02-24 — Phase B utility (smarter file type coverage)

- Extended files/canvases backfill with configurable file types:
  - new `mirror backfill --file-types <csv|all>` flag
  - default remains `images,snippets,gdocs,zips,pdfs`
  - `all` (or `*`) pulls all non-canvas file types
- Added canvas/file dedupe by file id when broad file fetch is used
- Updated CLI parsing tests and config docs examples

### 2026-02-24 — CLI UX (dynamic completion plumbing)

- Implemented `completion print bash|zsh` script emitters in CLI
- Added DB-backed/dynamic workspace completion:
  - completion scripts query `workspaces list --json` at completion time
- Added completion coverage for key backfill/event flags (including `--file-types`)
- Updated config docs with completion usage examples

### 2026-02-24 — Docs generation command implemented

- Implemented `docs generate` with output targets:
  - `--format markdown` (default) -> `docs/CLI.md` (default path)
  - `--format man` -> `docs/slack-mirror.1` (default path)
- Added parser support:
  - `docs generate --format <markdown|man> --output <path>`
- Added CLI parse test coverage for docs generation flags
- Updated config docs with docs-generation command examples

### 2026-02-24 — Docs generation fidelity pass

- Improved generated docs to include richer option details:
  - option help text
  - default values when applicable
- Added positional argument section generation
- Added top-level and subcommand help text to parser definitions
- Regenerated `docs/CLI.md` and `docs/slack-mirror.1`

### 2026-02-24 — Docs generation wired into CI/release checks

- Added CI workflow: `.github/workflows/ci.yml`
  - installs package
  - runs unit tests
  - verifies generated docs are current
- Added docs consistency checker:
  - `scripts/check_generated_docs.py`
  - regenerates docs and fails if `docs/CLI.md` or `docs/slack-mirror.1` are dirty
- Updated config docs with local docs-check command

### 2026-02-24 — Docs generation examples pass

- Added template-driven command examples in generated docs for key commands:
  - top-level bootstrap/list usage
  - `mirror backfill`
  - `mirror serve-webhooks`
  - `mirror process-events`
  - `docs generate`
- Regenerated `docs/CLI.md` and `docs/slack-mirror.1`

### 2026-02-24 — Phase D kickoff (keyword search command)

- Added search module:
  - `slack_mirror/search/keyword.py`
  - keyword search over mirrored messages table
- Added CLI command:
  - `search keyword --workspace <name> --query <text> [--limit N] [--json]`
- Added shell-completion support for `search keyword` in bash/zsh generators
- Added tests:
  - CLI parse coverage for search command
  - `tests/test_search.py` for keyword search behavior
- Updated docs command examples to include search usage

### 2026-02-24 — Search syntax expansion (complex filters)

- Extended keyword query parser to support inline filters/operators:
  - `from:<user_id>`
  - `channel:<channel_id_or_name>`
  - `before:<ts>` / `after:<ts>`
  - `is:thread` / `is:reply` / `is:edited`
  - `has:link`
  - quoted phrases and `-term` negation
- Updated CLI help text for `search keyword --query`
- Expanded tests to cover combined filter behavior and negation

### 2026-02-26 — First-class sync/daemon/status contract

- Promoted completeness operations into first-class mirror commands in CLI:
  - `mirror sync`
  - `mirror status`
  - `mirror daemon`
- Added doc:
  - `docs/dev/SYNC_DAEMON.md`
- Goal: no “magic incantation” workflows for routine completeness/reconcile.

### 2026-02-26 — Mirror completeness hardening

- Added thread-reply ingestion during message backfill:
  - `slack_mirror/sync/backfill.py` now fetches `conversations.replies` for roots with `reply_count > 0`
- Added completeness audit script:
  - `scripts/audit_mirror_completeness.py`
  - reports per-workspace/channel-class freshness and zero-message coverage
- Added catch-up sweep script:
  - `scripts/catchup_mirror.sh`
  - runs user-auth message catch-up + embedding job processing + audit output

### 2026-02-26 — Repo-bundled Slack Mirror agent skill pack

- Added installable skill pack to repo:
  - `agent-skills/slack-mirror-orchestrator`
  - `agent-skills/slack-mirror-live-ops`
  - `agent-skills/slack-mirror-ingest`
  - `agent-skills/slack-mirror-search`
  - `agent-skills/slack-mirror-export`
- Added cross-runtime installer script:
  - `scripts/install_agent_skills.sh`
  - default targets:
    - `~/.openclaw/skills`
    - `~/.codex/skills`
    - `~/.gemini/skills`
- Added documentation:
  - `docs/dev/AGENT_SKILLS.md`

### 2026-02-26 — Export workflows (HTML/JSON/PDF + semantic daypack)

- Added export workflow docs:
  - `docs/dev/EXPORTS.md`
- Documents current scripts:
  - `scripts/export_channel_day.py`
  - `scripts/export_channel_day_pdf.py`
  - `scripts/export_multi_day_pdf.py`
  - `scripts/export_semantic_daypack.py`
- Includes current PDF options and behavior:
  - inline image embedding (`--embed-attachments`)
  - embedded PDF file attachments (`--attach-files`)
  - prominent clickable attachment links
  - speaker color-coded bold datestamp lines

### 2026-02-26 — User-scope isolated install/update/uninstall system

- Added installer lifecycle script:
  - `scripts/user_env.sh`
  - subcommands:
    - `install` (snapshot repo -> user app dir, create venv, install package, init/sync DB)
    - `update` (refresh app/venv, preserve config + DB, run migrations)
    - `uninstall [--purge-data]` (remove runtime; optional data/config purge)
    - `status`
- Added docs:
  - `docs/dev/USER_INSTALL.md`
- Designed for independent user runtime at:
  - app: `~/.local/share/slack-mirror/app`
  - venv: `~/.local/share/slack-mirror/venv`
  - config: `~/.config/slack-mirror/config.yaml`
  - data: `~/.local/share/slack-mirror/var`

### 2026-02-26 — Live mode operationalization (always-on workers)

- Added tmux launcher script:
  - `scripts/live_mode_tmux.sh`
  - starts 3-pane live stack:
    - `mirror serve-webhooks`
    - `mirror process-events --loop`
    - `mirror process-embedding-jobs` in a short loop
- Added focused operations doc:
  - `docs/dev/LIVE_MODE.md`
  - quick start, manual commands, and health checks
- Added systemd user-service installer:
  - `scripts/install_live_mode_systemd_user.sh`
  - installs/enables/starts:
    - `slack-mirror-webhooks.service`
    - `slack-mirror-events.service`
    - `slack-mirror-embeddings.service`
  - includes journald/status commands for ops visibility
- Added clean uninstall helper:
  - `scripts/uninstall_live_mode_systemd_user.sh`
  - disables/stops services, removes user unit files, reloads systemd user daemon

### 2026-02-24 — Search speed enhancement (FTS prefilter path)

- Added migration `0003_messages_fts_v2.sql`:
  - `messages_fts` now stores unindexed join keys (`workspace_id`, `channel_id`, `user_id`, `ts`) + indexed `text`
- Added keyword-index maintenance command:
  - `search reindex-keyword --workspace <name>`
- Added FTS-aware query execution:
  - `search keyword` now uses FTS prefilter when positive terms exist
  - automatic SQL fallback when FTS index is missing/stale
  - `--no-fts` flag to force SQL-only path
- Updated bash/zsh completion for new search command/flag
- Expanded tests for search parse + behavior with FTS reindex path

### 2026-02-24 — Incremental FTS sync hooks

- Added incremental `messages_fts` maintenance in `upsert_message(...)`:
  - delete prior FTS row for `(workspace_id, channel_id, ts)`
  - insert fresh FTS row for non-deleted messages
  - keep deleted messages out of FTS
- Added DB tests validating incremental FTS updates and delete behavior
- Removes dependency on frequent full `reindex-keyword` for ongoing event/backfill updates

### 2026-02-24 — Keyword ranking/weighting pass

- Added ranking layer on keyword search results (applied after SQL/FTS candidate fetch):
  - term frequency boost
  - link presence boost
  - thread participation boost
  - recency weighting
- Expanded candidate window before ranking (`limit*5`, min 100) to improve relevance quality
- Keeps deterministic top-N output while preserving `--limit`

## Next Actions Queue

1. Expand semantic eval dataset from sample to real gold set (30-100 queries)
2. Add CI runtime dependency note/check so local CLI test runs fail fast when `pyyaml` missing
3. Add functional test coverage for message-only backfill execution path
4. Plan Phase F reusable search platform roadmap (DB + directory corpus support)

## Decision Log Pointer

Use `docs/dev/DECISIONS.md` for ADR-style architectural decisions.

## Useful Commands

```bash
# quick sanity
python3 -m py_compile slack_export.py

# repo state
git status --short --branch
git log --oneline -n 10
```

## Handoff Template

When pausing, append:

- What changed
- What is pending
- Risks/blockers
- Recommended next command
